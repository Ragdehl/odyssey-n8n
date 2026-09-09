"""Non-production Luna-first request-planning experiment.

This module prepares a provider boundary and validates its results.  It deliberately has no
retrieval, mutation, delegation, fallback, or action-execution capability.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from odyssey_core.observability import normalize_provider_usage
from odyssey_core.planner_capabilities import (
    build_planner_capabilities,
    build_write_capabilities,
)
from odyssey_core.request_planning import (
    PlannerClarification,
    RequestPlan,
    RequestPlanningError,
    planner_result_json_schema,
    request_plan_json_schema,
    validate_planner_result,
)

LUNA_EXPERIMENT_MODEL = "gpt-5.6-luna"
LUNA_EXPERIMENT_REASONING_EFFORT = "low"
LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS = 2048
LUNA_EXPERIMENT_AUTOMATIC_RETRIES = 0

_CURRENT_CONTEXT_KEYS = frozenset({"date", "time", "timezone"})
_TEACHING_EXAMPLES_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "luna_first_planner"
    / "teaching_examples.json"
)


class ResponsesClient(Protocol):
    """Describe the injected Responses API subset used by the experiment."""

    responses: Any


@dataclass(frozen=True, slots=True)
class PlannerEscalation:
    """Represent a safe request for the established planner, with no executable content."""

    outcome: str = "ESCALATE"


ExperimentalPlannerResult = RequestPlan | PlannerClarification | PlannerEscalation


def luna_experimental_result_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Build the strict nested PLAN/CLARIFY/ESCALATE provider schema.

    PLAN embeds the existing RequestPlan provider schema.  The root remains a closed object and
    the union remains beneath ``result`` for the supported Structured Outputs subset.
    """
    production_schema = planner_result_json_schema(schema)
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
    return {
        "type": "object",
        "properties": {"result": {"anyOf": [*existing_branches, escalate_branch]}},
        "required": ["result"],
        "additionalProperties": False,
    }


def validate_luna_experimental_result(
    payload: Any, schema: Mapping[str, Any]
) -> ExperimentalPlannerResult:
    """Validate an experimental result without weakening production validation.

    PLAN and CLARIFY pass directly through ``validate_planner_result``.  ESCALATE accepts only the
    same closed field set with three null payload fields, so it carries no action or invented user
    knowledge.
    """
    if not isinstance(payload, dict) or set(payload) != {
        "outcome",
        "actions",
        "limitations",
        "clarification_code",
    }:
        raise RequestPlanningError("Experimental planner result fields are invalid")
    if payload["outcome"] != "ESCALATE":
        return validate_planner_result(payload, schema)
    if any(
        payload[field] is not None for field in ("actions", "limitations", "clarification_code")
    ):
        raise RequestPlanningError("ESCALATE must carry no actions or other semantic payload")
    return PlannerEscalation()


def render_luna_experimental_prompt(
    schema: Mapping[str, Any],
    current_context: Mapping[str, str],
    *,
    teaching_examples: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Render the Luna-specific first-pass prompt against current Core capabilities.

    Args:
        schema: Parsed canonical Odyssey note schema.
        current_context: Explicit date, time, and timezone for relative date interpretation.
        teaching_examples: Frozen examples, injectable only for deterministic tests.

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
    retrieval = build_planner_capabilities(schema, current_context=current_context)
    writable = build_write_capabilities(schema)
    rendered_examples = "\n\n".join(
        f"User: {item['request']}\nSafe result: "
        f"{json.dumps(item['result'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"Lesson: {item['lesson']}"
        for item in examples
    )
    return f"""You are Odyssey's inexpensive first-pass request planner. Return exactly one strict JSON result. You never execute actions.

Choose the outcome before drafting fields:
1. PLAN only when you can preserve every material user intent in the supplied current RequestPlan contract without unsafe approximation.
2. CLARIFY only for input with no safely interpretable or actionable Odyssey intent. Use only clarification_code UNRECOGNIZED_REQUEST.
3. ESCALATE whenever the request is understandable but you are uncertain about its safe representation, candidate-set scope, identity, mutation meaning, branch structure, or supported semantics. ESCALATE is correct safety behavior. Never force a PLAN to appear helpful.
4. CLARIFY and ESCALATE carry null actions, null limitations, and null clarification_code except that CLARIFY uses UNRECOGNIZED_REQUEST. They carry no prose or user knowledge.

When choosing PLAN, obey these rules in order:
1. Reuse the RequestPlan contract exactly. Identify each Odyssey candidate set first (entity, query, type, filters, link_scope), then choose retrieve, write, or delegate. Never invent IDs, existence, fields, tags, links, actions, facts, or authority.
2. Hard filters remove candidates. Use one only for an explicit, exact mapping in the capabilities. If meaning is semantic or mapping is uncertain, preserve it in query and ESCALATE when the remaining plan would be materially ambiguous.
3. Never approximate a fact, event, decision, purchase, travel, employment, or other domain date with note lifecycle created_at/updated_at. Those fields are allowed only when the user explicitly asks when Odyssey notes/items were created, written, recorded, modified, or updated. Preserve unsupported domain time in query and use unsupported_domain_date when required.
4. Filters within one selection are global AND. For genuinely independent OR candidate sets, emit separate actions so each branch has only its own restrictions. Do not combine both sides' filters in one action. Ordinary semantic alternatives that need no distinct hard restrictions may remain in one query.
5. For writes, keep a non-empty identity query, preserve independently meaningful facts, separate incompatible intents, and use references only for real semantic relationships. Never turn write-target resolution into an extra retrieval.
6. Delegate only a requested specialized operation such as count, sum, comparison, translation, or external-artifact analysis. Preserve any safe Odyssey selection separately. Delegation does not choose an application or execute work.
7. Preserve mixed action order and all material constraints. If a safe exact PLAN depends on guessing, return ESCALATE.

Current context: {json.dumps(dict(current_context), ensure_ascii=False, separators=(",", ":"))}
Retrieval/selection capabilities: {json.dumps(retrieval, ensure_ascii=False, separators=(",", ":"))}
Writable capabilities: {json.dumps(writable, ensure_ascii=False, separators=(",", ":"))}

Teaching examples (not evaluation cases):

{rendered_examples}
"""


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
    ) -> None:
        self._client = client
        self._schema = schema
        self._current_context = current_context
        self.model = LUNA_EXPERIMENT_MODEL
        self.reasoning_effort = LUNA_EXPERIMENT_REASONING_EFFORT
        self.max_output_tokens = LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS
        self.max_retries = LUNA_EXPERIMENT_AUTOMATIC_RETRIES
        self.last_usage: dict[str, int] | None = None
        self.last_response_id: str | None = None
        self.last_provider_status: str | None = None

    @classmethod
    def from_environment(
        cls, schema: Mapping[str, Any], current_context: Mapping[str, str]
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
        return cls(OpenAI(max_retries=LUNA_EXPERIMENT_AUTOMATIC_RETRIES), schema, current_context)

    def plan(self, request: str) -> ExperimentalPlannerResult:
        """Make exactly one bounded Luna attempt and validate without executing its result."""
        if not isinstance(request, str) or not request.strip():
            raise RequestPlanningError("Request text must be non-empty")
        self.last_usage = None
        self.last_response_id = None
        self.last_provider_status = None
        response = self._client.responses.create(
            model=LUNA_EXPERIMENT_MODEL,
            reasoning={"effort": LUNA_EXPERIMENT_REASONING_EFFORT},
            store=False,
            max_output_tokens=LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
            input=[
                {
                    "role": "system",
                    "content": render_luna_experimental_prompt(self._schema, self._current_context),
                },
                {"role": "user", "content": request},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "odyssey_luna_first_planner_result",
                    "strict": True,
                    "schema": luna_experimental_result_json_schema(self._schema),
                }
            },
        )
        self.last_usage = normalize_provider_usage(response)
        self.last_response_id = _bounded_metadata(getattr(response, "id", None))
        self.last_provider_status = _bounded_metadata(getattr(response, "status", None))
        if self.last_provider_status != "completed":
            raise RequestPlanningError("Luna experiment provider response was not completed")
        try:
            payload = json.loads(response.output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise RequestPlanningError("Luna experiment returned malformed JSON") from error
        if not isinstance(payload, dict) or set(payload) != {"result"}:
            raise RequestPlanningError("Luna experiment result wrapper is invalid")
        return validate_luna_experimental_result(payload["result"], self._schema)


def _bounded_metadata(value: Any, *, maximum: int = 160) -> str | None:
    """Retain a small provider identifier/status without arbitrary response content."""
    if not isinstance(value, str) or not value:
        return None
    return value[:maximum]


def production_result_contract_unchanged(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the imported production schema only for deterministic comparison tests."""
    return planner_result_json_schema(schema)


def embedded_request_plan_contract(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the exact reused RequestPlan provider contract for deterministic tests."""
    return request_plan_json_schema(schema)
