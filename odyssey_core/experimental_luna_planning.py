"""Non-production Luna-first request-planning experiment.

This module prepares a provider boundary and validates its results.  It deliberately has no
retrieval, mutation, delegation, fallback, or action-execution capability.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from odyssey_core.candidate_context import CoreCandidateContext
from odyssey_core.domain_interpretation import DomainInterpretation
from odyssey_core.observability import (
    OperationalOutcome,
    OperationalSpan,
    SpanRecorder,
    normalize_provider_usage,
)
from odyssey_core.openai_cache import explicit_cache_transport, explicit_system_content
from odyssey_core.request_planning import (
    LUNA_DYNAMIC_CONTEXT_MARKER,
    PlannerClarification,
    PlannerValidationCode,
    PlannerValidationStage,
    RequestPlan,
    RequestPlanningError,
    bind_plan_temporal_anchors,
    compact_planner_result_json_schema,
    finalize_request_plan,
    planner_authorized_calendar_dates,
    planner_result_json_schema,
    render_semantic_write_planner_prompt,
    request_plan_json_schema,
    validate_plan_against_domain_interpretation,
    validate_planner_result,
    validate_request_action,
)
from odyssey_core.schema_types import planning_schema_for_capability
from odyssey_core.semantic_write import (
    SemanticWriteCompileError,
    SemanticWriteIntent,
    TemporalReferencePart,
    compile_semantic_write,
    decode_semantic_write_action,
    semantic_write_action_json_schema,
    semantic_write_schema_definitions,
)

LUNA_EXPERIMENT_MODEL = "gpt-5.6-luna"
LUNA_EXPERIMENT_REASONING_EFFORT = "low"
LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS = 2048
LUNA_EXPERIMENT_AUTOMATIC_RETRIES = 0

_CURRENT_CONTEXT_KEYS = frozenset({"date", "time", "timezone"})
_MAX_ERROR_CHAIN_DEPTH = 5
_MAX_ERROR_TYPE_NAME_LENGTH = 120
_TEACHING_EXAMPLES_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "luna_first_planner"
    / "teaching_examples_v3.json"
)


class ResponsesClient(Protocol):
    """Describe the injected subset of the OpenAI Responses client used by the planner."""

    responses: Any


@dataclass(frozen=True, slots=True)
class PlannerEscalation:
    """Represent a safe request for the established planner, with no executable content."""

    outcome: str = "ESCALATE"


ExperimentalPlannerResult = RequestPlan | PlannerClarification | PlannerEscalation


def luna_experimental_result_json_schema(
    schema: Mapping[str, Any],
    domain_interpretation: DomainInterpretation | None = None,
    *,
    authorized_calendar_dates: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the strict nested PLAN/CLARIFY/ESCALATE provider schema.

    The production planner result contract is inherited unchanged and the Luna-only ESCALATE branch
    is appended. The root remains a closed object and the union stays beneath ``result`` for the
    supported Structured Outputs subset.
    """
    production_schema = compact_planner_result_json_schema(
        schema, authorized_calendar_dates=authorized_calendar_dates
    )
    existing_branches = production_schema["properties"]["result"]["anyOf"]
    escalate_branch = {
        "type": "object",
        "properties": {
            "outcome": {"type": "string", "enum": ["ESCALATE"]},
            "actions": {"type": "null"},
            "limitations": {"type": "null"},
            "clarification_code": {"type": "null"},
        },
        "required": ["outcome", "actions", "limitations", "clarification_code"],
        "additionalProperties": False,
    }
    definitions = deepcopy(production_schema["$defs"])
    semantic_definitions = semantic_write_schema_definitions(
        schema,
        include_temporal_reference=bool(
            domain_interpretation and domain_interpretation.temporal_references()
        ),
        authorized_calendar_dates=authorized_calendar_dates,
    )
    existing_filter_array = definitions["filter_array"]
    if semantic_definitions["filter_array"] != existing_filter_array:
        raise RequestPlanningError("Semantic WRITE filter schema diverged from shared selection")
    definitions.update(semantic_definitions)
    definitions["write_action"] = semantic_write_action_json_schema()
    definitions["escalate_result"] = escalate_branch
    return {
        "type": "object",
        "properties": {
            "result": {"anyOf": [*existing_branches, {"$ref": "#/$defs/escalate_result"}]}
        },
        "required": ["result"],
        "additionalProperties": False,
        "$defs": definitions,
    }


def validate_luna_experimental_result(
    payload: Any,
    schema: Mapping[str, Any],
    domain_interpretation: DomainInterpretation | None = None,
    *,
    authorized_calendar_dates: Sequence[str] = (),
    candidate_context: CoreCandidateContext | None = None,
) -> ExperimentalPlannerResult:
    """Validate a Luna result without weakening production planner validation.

    PLAN and CLARIFY pass directly through ``validate_planner_result``. ESCALATE accepts only the
    same closed field set with three null payload fields, so it carries no action or invented user
    knowledge.
    """
    if not isinstance(payload, dict):
        raise RequestPlanningError(
            "Experimental planner result fields are invalid",
            stage=PlannerValidationStage.PLANNER_RESULT_ENVELOPE,
            code=PlannerValidationCode.INVALID_FIELDS,
        )
    if payload.get("outcome") == "CLARIFY":
        return validate_planner_result(
            payload,
            schema,
            domain_interpretation,
            authorized_calendar_dates=authorized_calendar_dates,
        )
    if payload.get("outcome") == "PLAN":
        return _validate_luna_plan(
            payload,
            schema,
            domain_interpretation,
            authorized_calendar_dates=authorized_calendar_dates,
            candidate_context=candidate_context,
        )
    if payload.get("outcome") != "ESCALATE":
        return validate_planner_result(payload, schema)
    if set(payload) != {"outcome", "actions", "limitations", "clarification_code"}:
        raise RequestPlanningError(
            "Experimental planner result fields are invalid",
            stage=PlannerValidationStage.PLANNER_RESULT_ENVELOPE,
            code=PlannerValidationCode.INVALID_FIELDS,
        )
    if any(
        payload[field] is not None for field in ("actions", "limitations", "clarification_code")
    ):
        raise RequestPlanningError(
            "ESCALATE must carry no actions or other semantic payload",
            stage=PlannerValidationStage.PLANNER_RESULT_ENVELOPE,
            code=PlannerValidationCode.INVALID_FIELDS,
        )
    return PlannerEscalation()


def _validate_luna_plan(
    payload: Mapping[str, Any],
    schema: Mapping[str, Any],
    domain_interpretation: DomainInterpretation | None = None,
    *,
    authorized_calendar_dates: Sequence[str] = (),
    candidate_context: CoreCandidateContext | None = None,
) -> RequestPlan:
    """Compile semantic writes in provider order and reuse established action/final invariants."""
    required = {"outcome", "actions", "limitations", "clarification_code"}
    if (
        not required <= set(payload)
        or set(payload) - (required | {"presentation_intent"})
        or payload["clarification_code"] is not None
        or not isinstance(payload["actions"], list)
        or not isinstance(payload["limitations"], list)
    ):
        raise RequestPlanningError(
            "Luna PLAN fields are invalid",
            stage=PlannerValidationStage.PLANNER_RESULT_ENVELOPE,
            code=PlannerValidationCode.INVALID_FIELDS,
        )
    actions = []
    semantic_write_intents: list[SemanticWriteIntent] = []
    for raw_action in payload["actions"]:
        try:
            if isinstance(raw_action, dict) and raw_action.get("kind") == "write":
                intent = decode_semantic_write_action(
                    raw_action,
                    allow_temporal_reference=bool(
                        domain_interpretation and domain_interpretation.temporal_references()
                    ),
                )
                semantic_write_intents.append(intent)
                actions.append(
                    compile_semantic_write(
                        intent, schema, authorized_calendar_dates=authorized_calendar_dates
                    )
                )
            else:
                actions.append(
                    validate_request_action(
                        raw_action, schema, authorized_calendar_dates=authorized_calendar_dates
                    )
                )
        except SemanticWriteCompileError as error:
            raise RequestPlanningError(
                "Luna semantic WRITE failed local compilation",
                stage=PlannerValidationStage.WRITE_ACTION,
                code=PlannerValidationCode.INVALID_MUTATION,
            ) from error
    excluded_pending_temporals = _validate_semantic_temporal_evidence(
        semantic_write_intents, domain_interpretation, candidate_context
    )
    # Keep Temporal's original evidence immutable. For this opt-in planning
    # preflight ONLY, drop exactly those mentions which Core has source-located
    # inside an independently pending ambiguous source candidate. The ordinary
    # Core temporal validator must still reject every other missing date.
    scoped_temporal = domain_interpretation
    if excluded_pending_temporals and domain_interpretation is not None:
        remainder = excluded_pending_temporals.copy()
        kept = []
        for evidence in domain_interpretation.evidence:
            key = (evidence.source_text, evidence.value)
            if evidence.kind == "temporal_reference" and remainder[key] > 0:
                remainder[key] -= 1
                continue
            kept.append(evidence)
        if any(remainder.values()):
            raise RequestPlanningError("Ambiguous candidate temporal proof is incomplete")
        scoped_temporal = replace(domain_interpretation, evidence=tuple(kept))
    plan = finalize_request_plan(
        actions,
        payload["limitations"],
        payload.get("presentation_intent", "answer"),
    )
    validate_plan_against_domain_interpretation(plan, scoped_temporal)
    return bind_plan_temporal_anchors(plan, scoped_temporal)


def _validate_semantic_temporal_evidence(
    intents: Sequence[SemanticWriteIntent],
    interpretation: DomainInterpretation | None,
    candidate_context: CoreCandidateContext | None = None,
) -> Counter[tuple[str, str]]:
    """Require all non-pending Temporal evidence, returning precisely omitted pending pairs."""
    if interpretation is None:
        return Counter()
    allowed = Counter(
        (item.source_text, item.value) for item in interpretation.temporal_references()
    )
    found: Counter[tuple[str, str]] = Counter()
    consumed_values: set[str] = set()
    for intent in intents:
        for operation in intent.operations:
            if operation.target.note_type == "calendar_day":
                target_date = operation.target.description
                consumed_values.update(
                    item.value
                    for item in interpretation.temporal_references()
                    if item.temporal_anchor().date == target_date
                    and item.temporal_anchor().time is None
                )
            for fact in operation.facts:
                for part in fact.parts:
                    if isinstance(part, TemporalReferencePart):
                        found[(part.text, part.value)] += 1
    required = Counter(
        {pair: count for pair, count in allowed.items() if pair[1] not in consumed_values}
    )
    if found - required:
        raise RequestPlanningError(
            "Luna semantic WRITE contains temporal wording/temporal evidence not supplied by Temporal",
            stage=PlannerValidationStage.WRITE_ACTION,
            code=PlannerValidationCode.INVALID_MUTATION,
        )
    missing = required - found
    excluded: Counter[tuple[str, str]] = Counter()
    if missing and candidate_context is not None:
        # Source candidates are unverified hints; here they may *prevent an
        # unjustified global temporal-coverage veto*, not grant write authority.
        # A separate, mandatory Core-owned coverage manifest must still prove
        # that an omitted ambiguous candidate is explicitly pending.
        candidate_context.validate(interpretation.source_text)
        for pair, count in missing.items():
            mention, _value = pair
            source = candidate_context.source
            # Temporal exposes source text, not occurrence offsets. An
            # ambiguous repeated literal must not be matched to a guessed one.
            if count != 1 or source.count(mention) != 1:
                continue
            start = source.find(mention)
            end = start + len(mention)
            scoped = [
                candidate
                for candidate in candidate_context.candidates
                if any(anchor.start <= start and end <= anchor.end for anchor in candidate.anchors)
            ]
            if len(scoped) != 1 or scoped[0].state != "ambiguous_identity":
                continue
            if not any(
                role.role in {"date", "date_scope", "time", "time_approx"}
                and role.span.start <= start
                and end <= role.span.end
                for role in scoped[0].roles
            ):
                continue
            excluded[pair] = 1
        missing -= excluded
    if intents and missing:
        raise RequestPlanningError(
            "Luna semantic WRITE omitted required temporal wording/temporal evidence",
            stage=PlannerValidationStage.WRITE_ACTION,
            code=PlannerValidationCode.INVALID_MUTATION,
        )
    return excluded


def render_luna_experimental_prompt(
    schema: Mapping[str, Any],
    current_context: Mapping[str, str],
    *,
    teaching_examples: Sequence[Mapping[str, Any]] | None = None,
    conversation_context: Sequence[Mapping[str, str]] = (),
    size_components: dict[str, int] | None = None,
    domain_interpretation: DomainInterpretation | None = None,
    candidate_context: CoreCandidateContext | None = None,
) -> str:
    """Render the Luna-specific first-pass prompt against current Core capabilities.

    Args:
        schema: Parsed canonical Odyssey note schema.
        current_context: Explicit date, time, and timezone for relative date interpretation.
        teaching_examples: Frozen examples, injectable only for deterministic tests.
        conversation_context: Bounded recent conversation continuity evidence for this pass.

    Returns:
        Ordered safety instructions, current capability projections, and compact examples.

    Raises:
        RequestPlanningError: If current context or teaching examples are malformed.
    """
    if set(current_context) != _CURRENT_CONTEXT_KEYS or not all(
        isinstance(value, str) and value.strip() for value in current_context.values()
    ):
        raise RequestPlanningError(
            "Current context must contain non-empty date, time, and timezone"
        )
    examples = (
        list(teaching_examples) if teaching_examples is not None else load_teaching_examples()
    )
    _validate_teaching_examples(examples)
    for item in examples:
        validate_luna_experimental_result(item["result"], schema)
    rendered_examples = "\n\n".join(
        f"User: {item['request']}\nSafe result: "
        f"{json.dumps(_complete_example_selections(item['result']), ensure_ascii=False, separators=(',', ':'))}\n"
        f"Lesson: {item['lesson']}"
        for item in examples
    )
    semantic_prompt = render_semantic_write_planner_prompt(
        schema,
        current_context,
        conversation_context,
        size_components=size_components,
        domain_interpretation=domain_interpretation,
    )
    if semantic_prompt.count(LUNA_DYNAMIC_CONTEXT_MARKER) != 1:
        raise RuntimeError("Luna semantic prompt dynamic boundary is invalid")
    semantic_static, semantic_dynamic = semantic_prompt.split(LUNA_DYNAMIC_CONTEXT_MARKER, 1)
    # Keep request-specific candidate evidence out of Luna's shared cache prefix.
    if candidate_context is not None:
        if not isinstance(candidate_context, CoreCandidateContext):
            raise RequestPlanningError("Core candidate context must be Core-owned")
        candidate_section = candidate_context.prompt_suffix()
        semantic_dynamic += candidate_section
        if size_components is not None:
            size_components["candidate_context_bytes"] = len(candidate_section.encode("utf-8"))
    luna_static = f"""{semantic_static}

Choose the outcome before drafting fields:
1. PLAN only when every material intent is preserved by the inherited RequestPlan semantics without unsafe approximation.
2. CLARIFY only for unintelligible input; use only UNRECOGNIZED_REQUEST.
3. ESCALATE whenever the request is understandable but its safe representation, mutation meaning, branch structure, or supported semantics is uncertain. Never force a PLAN.
4. CLARIFY and ESCALATE carry null actions, null limitations, and null clarification_code except CLARIFY's UNRECOGNIZED_REQUEST.
Never approximate a fact, event, decision, purchase, or other domain date with note lifecycle fields; preserve uncertain meaning and ESCALATE rather than guessing.

Retrieval-shape tie-breakers:
- Choose result_shape=collection by the cardinality of the requested answer, not by the number of named source subjects. Several semantic members or values of one named subject are still a collection; keep that subject only in the lossless query and leave collection direct selectors null or empty.
- Use result_shape=single only when the requested answer is one fact or a synthesis rather than an enumerated member or value set.
Presentation tie-breaker:
- Selection semantics take precedence over presentation. If link_scope or relational_reference is required, presentation_intent MUST be answer even when the user asks to show notes; never weaken the required selection to produce note_set or answer_and_note_set.

Teaching examples (not evaluation cases):

{rendered_examples}
"""
    prompt = luna_static + LUNA_DYNAMIC_CONTEXT_MARKER + semantic_dynamic
    if size_components is not None:
        size_components["luna_rules_examples_bytes"] = len(luna_static.encode("utf-8")) - len(
            semantic_static.encode("utf-8")
        )
    return prompt


def _complete_example_selections(result: Mapping[str, Any]) -> dict[str, Any]:
    """Render inherited examples under the current retrieval-shape provider contract."""
    completed = deepcopy(dict(result))
    for action in completed.get("actions") or []:
        if action["kind"] == "retrieve":
            selections = [action["plan"]]
            action.setdefault(
                "result_shape",
                "collection" if action["plan"].get("semantic_set") is not None else "single",
            )
        elif action["kind"] == "write":
            selections = []
        else:
            selections = [action.get("selection")]
        for selection in selections:
            if isinstance(selection, dict):
                selection.setdefault("relational_reference", None)
                if action.get("result_shape") == "collection":
                    legacy_intent = selection.get("semantic_set")
                    selection.setdefault(
                        "collection_subject",
                        "self"
                        if isinstance(legacy_intent, dict)
                        and legacy_intent.get("subject_kind") == "self"
                        else "query",
                    )
                else:
                    selection.setdefault("collection_subject", None)
                selection.pop("semantic_set", None)
    return completed


def load_teaching_examples() -> list[dict[str, Any]]:
    """Load the frozen prompt-teaching registry from the repository."""
    try:
        payload = json.loads(_TEACHING_EXAMPLES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RequestPlanningError("Luna teaching examples are unavailable or malformed") from error
    if not isinstance(payload, dict) or set(payload) != {"version", "examples"}:
        raise RequestPlanningError("Luna teaching example registry is invalid")
    examples = payload["examples"]
    if not isinstance(examples, list):
        raise RequestPlanningError("Luna teaching examples must be a list")
    _validate_teaching_examples(examples)
    return examples


def _validate_teaching_examples(examples: Sequence[Mapping[str, Any]]) -> None:
    """Fail closed when prompt teaching material does not have the frozen closed shape."""
    if not examples:
        raise RequestPlanningError("Luna teaching examples must not be empty")
    seen: set[str] = set()
    for item in examples:
        if not isinstance(item, Mapping) or set(item) != {"id", "request", "result", "lesson"}:
            raise RequestPlanningError("Luna teaching example fields are invalid")
        if not all(
            isinstance(item[field], str) and item[field].strip()
            for field in ("id", "request", "lesson")
        ):
            raise RequestPlanningError("Luna teaching example text is invalid")
        if item["id"] in seen or not isinstance(item["result"], Mapping):
            raise RequestPlanningError(
                "Luna teaching examples contain a duplicate or invalid result"
            )
        seen.add(item["id"])


class OpenAILunaExperimentalPlanner:
    """Call Luna once and return only a locally validated, non-executing experiment result."""

    def __init__(
        self,
        client: ResponsesClient,
        schema: Mapping[str, Any],
        current_context: Mapping[str, str],
        monotonic: Any = perf_counter,
        *,
        teaching_examples: Sequence[Mapping[str, Any]] | None = None,
        domain_interpretation: DomainInterpretation | None = None,
        candidate_context: CoreCandidateContext | None = None,
        model: str = LUNA_EXPERIMENT_MODEL,
        reasoning_effort: str = LUNA_EXPERIMENT_REASONING_EFFORT,
        max_output_tokens: int = LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    ) -> None:
        self._client = client
        self._schema = schema
        self._current_context = current_context
        self._teaching_examples = (
            tuple(teaching_examples) if teaching_examples is not None else None
        )
        self._domain_interpretation = domain_interpretation
        self._candidate_context = candidate_context
        self._planning_schema = planning_schema_for_capability(
            schema,
            domain_interpretation.capability_id if domain_interpretation is not None else None,
        )
        self._monotonic = monotonic
        if not isinstance(model, str) or not model.strip():
            raise RequestPlanningError("Semantic planner model must be non-empty")
        if not isinstance(reasoning_effort, str) or not reasoning_effort.strip():
            raise RequestPlanningError("Semantic planner reasoning effort must be non-empty")
        if (
            not isinstance(max_output_tokens, int)
            or isinstance(max_output_tokens, bool)
            or max_output_tokens <= 0
        ):
            raise RequestPlanningError("Semantic planner max output tokens must be positive")
        self.model = model.strip()
        self.reasoning_effort = reasoning_effort.strip()
        self.max_output_tokens = max_output_tokens
        self.max_retries = LUNA_EXPERIMENT_AUTOMATIC_RETRIES
        self.last_usage: dict[str, int] | None = None
        self.last_response_id: str | None = None
        self.last_provider_status: str | None = None
        self.last_spans: tuple[OperationalSpan, ...] = ()
        self.last_input_sizes: dict[str, int] | None = None
        self.last_cache_diagnostics: dict[str, str | int | None] | None = None
        self.last_error_category: str | None = None
        self.last_error_chain: tuple[str, ...] | None = None
        self.last_parse_status: str | None = None
        self.last_validation_stage: str | None = None
        self.last_validation_code: str | None = None
        self.last_result_kind: str | None = None

    @classmethod
    def from_environment(
        cls,
        schema: Mapping[str, Any],
        current_context: Mapping[str, str],
        *,
        teaching_examples: Sequence[Mapping[str, Any]] | None = None,
        domain_interpretation: DomainInterpretation | None = None,
        candidate_context: CoreCandidateContext | None = None,
        model: str = LUNA_EXPERIMENT_MODEL,
        reasoning_effort: str = LUNA_EXPERIMENT_REASONING_EFFORT,
        max_output_tokens: int = LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    ) -> OpenAILunaExperimentalPlanner:
        """Construct the experimental client with automatic SDK retries disabled."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise RequestPlanningError("OPENAI_API_KEY is required for Luna experiment planning")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RequestPlanningError(
                "Install the OpenAI SDK for Luna experiment planning"
            ) from error
        return cls(
            OpenAI(max_retries=LUNA_EXPERIMENT_AUTOMATIC_RETRIES),
            schema,
            current_context,
            teaching_examples=teaching_examples,
            domain_interpretation=domain_interpretation,
            candidate_context=candidate_context,
            model=model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
        )

    def plan(
        self, request: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> ExperimentalPlannerResult:
        """Make exactly one bounded Luna attempt and validate without executing its result."""
        if not isinstance(request, str) or not request.strip():
            raise RequestPlanningError("Request text must be non-empty")
        if self._candidate_context is not None:
            if not isinstance(self._candidate_context, CoreCandidateContext):
                raise RequestPlanningError("Core candidate context must be Core-owned")
            try:
                self._candidate_context.validate(request)
            except ValueError as error:
                raise RequestPlanningError(
                    "Core candidate context is not grounded in request"
                ) from error
        self.last_usage = None
        self.last_response_id = None
        self.last_provider_status = None
        self.last_spans = ()
        self.last_input_sizes = None
        self.last_error_category = None
        self.last_error_chain = None
        self.last_parse_status = None
        self.last_validation_stage = None
        self.last_validation_code = None
        self.last_result_kind = None
        recorder = SpanRecorder(self._monotonic(), self._monotonic)
        input_started = self._monotonic()
        sizes: dict[str, int] = {}
        try:
            prompt = render_luna_experimental_prompt(
                self._planning_schema,
                self._current_context,
                teaching_examples=self._teaching_examples,
                conversation_context=conversation_context,
                size_components=sizes,
                domain_interpretation=self._domain_interpretation,
                candidate_context=self._candidate_context,
            )
            authorized_calendar_dates = planner_authorized_calendar_dates(
                self._current_context, self._domain_interpretation
            )
            output_schema = luna_experimental_result_json_schema(
                self._planning_schema,
                self._domain_interpretation,
                authorized_calendar_dates=authorized_calendar_dates,
            )
            sizes["user_request_bytes"] = len(request.encode("utf-8"))
            sizes["structured_output_schema_bytes"] = len(
                json.dumps(output_schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            )
        except Exception as error:
            recorder.add("input_build", input_started, OperationalOutcome.FAILED, error)
            self.last_spans = recorder.spans
            raise
        recorder.add("input_build", input_started)
        self.last_input_sizes = sizes
        self.last_cache_diagnostics = None
        if prompt.count(LUNA_DYNAMIC_CONTEXT_MARKER) != 1:
            raise RuntimeError("Luna prompt cache boundary is invalid")
        stable_prompt, dynamic_prompt = prompt.split(LUNA_DYNAMIC_CONTEXT_MARKER, 1)
        cache_transport, cache_diagnostics = explicit_cache_transport(
            model=self.model,
            capability="luna-first",
            stable_prefix=stable_prompt,
            proven_reusable=True,
        )
        # Cache eligibility must never become a new failure mode for Core planning.
        # If a future prompt/model is no longer eligible, keep the exact original
        # system text and let OpenAI use its ordinary implicit cache behavior.
        system_content = (
            explicit_system_content(stable_prompt, LUNA_DYNAMIC_CONTEXT_MARKER + dynamic_prompt)
            if cache_transport is not None
            else prompt
        )
        self.last_cache_diagnostics = cache_diagnostics.as_safe_mapping()
        provider_started = self._monotonic()
        try:
            response = self._client.responses.create(
                model=self.model,
                reasoning={"effort": self.reasoning_effort},
                store=False,
                max_output_tokens=self.max_output_tokens,
                **(cache_transport or {}),
                input=[
                    {
                        "role": "system",
                        "content": system_content,
                    },
                    {"role": "user", "content": request},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_luna_first_planner_result",
                        "strict": True,
                        "schema": output_schema,
                    }
                },
            )
        except Exception as error:
            recorder.add("provider", provider_started, OperationalOutcome.FAILED, error)
            self.last_spans = recorder.spans
            self.last_error_category = type(error).__name__[:120]
            self.last_error_chain = bounded_exception_type_chain(error)
            raise
        recorder.add("provider", provider_started)
        self.last_spans = recorder.spans
        self.last_usage = normalize_provider_usage(response)
        self.last_response_id = _bounded_metadata(getattr(response, "id", None))
        self.last_provider_status = _bounded_metadata(getattr(response, "status", None))
        if self.last_provider_status != "completed":
            self.last_error_category = "IncompleteProviderResponse"
            raise RequestPlanningError("Luna experiment provider response was not completed")
        parse_started = self._monotonic()
        try:
            payload = json.loads(response.output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            recorder.add("parse", parse_started, OperationalOutcome.FAILED, error)
            self.last_spans = recorder.spans
            self.last_parse_status = "failed"
            raw_output = getattr(response, "output_text", None)
            self.last_error_category = (
                "EmptyPlannerOutput"
                if not isinstance(raw_output, str) or not raw_output.strip()
                else "MalformedPlannerJSON"
            )
            raise RequestPlanningError("Luna experiment returned malformed JSON") from error
        recorder.add("parse", parse_started)
        self.last_parse_status = "succeeded"
        validation_started = self._monotonic()
        if not isinstance(payload, dict) or set(payload) != {"result"}:
            recorder.add("validate", validation_started, OperationalOutcome.FAILED)
            self.last_spans = recorder.spans
            self.last_error_category = "LocalPlannerValidationError"
            self.last_validation_stage = "PLANNER_RESULT_ENVELOPE"
            self.last_validation_code = "INVALID_FIELDS"
            raise RequestPlanningError("Luna experiment result wrapper is invalid")
        try:
            result = validate_luna_experimental_result(
                payload["result"],
                self._planning_schema,
                self._domain_interpretation,
                authorized_calendar_dates=planner_authorized_calendar_dates(
                    self._current_context, self._domain_interpretation
                ),
                candidate_context=self._candidate_context,
            )
        except RequestPlanningError as error:
            recorder.add("validate", validation_started, OperationalOutcome.FAILED, error)
            self.last_spans = recorder.spans
            self.last_error_category = "LocalPlannerValidationError"
            self.last_validation_stage = (
                error.validation_stage.value if error.validation_stage is not None else None
            )
            self.last_validation_code = (
                error.validation_code.value if error.validation_code is not None else None
            )
            raise
        recorder.add("validate", validation_started)
        self.last_spans = recorder.spans
        self.last_result_kind = (
            "escalate"
            if isinstance(result, PlannerEscalation)
            else "clarify"
            if isinstance(result, PlannerClarification)
            else "plan"
        )
        return result


def _bounded_metadata(value: Any, *, maximum: int = 160) -> str | None:
    """Retain a small provider identifier/status without arbitrary response content."""
    if not isinstance(value, str) or not value:
        return None
    return value[:maximum]


def bounded_exception_type_chain(error: BaseException) -> tuple[str, ...]:
    """Return a bounded, cycle-safe exception type chain without exception content.

    Prefer explicit causes, falling back to implicit contexts only when there is no cause.
    This diagnostic deliberately retains class names only: provider messages, requests, headers,
    payloads, and arbitrary exception representations never enter benchmark evidence.
    """
    chain: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and len(chain) < _MAX_ERROR_CHAIN_DEPTH:
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        chain.append(type(current).__name__[:_MAX_ERROR_TYPE_NAME_LENGTH])
        cause = current.__cause__
        current = cause if cause is not None else current.__context__
    return tuple(chain)


def production_result_contract_unchanged(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the imported production schema only for deterministic comparison tests."""
    return planner_result_json_schema(schema)


def embedded_request_plan_contract(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the exact reused RequestPlan provider contract for deterministic tests."""
    return request_plan_json_schema(schema)
