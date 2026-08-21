"""Fail-closed interpretation of user requests into safe Odyssey RequestPlans."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from odyssey_core.context import ContextFilter, validate_context_filters
from odyssey_core.planner_capabilities import LIMITATIONS, build_planner_capabilities

PLANNER_MODEL = "gpt-5.6-sol"
PLANNER_REASONING_EFFORT = "low"
WRITE_INTENTS = ("record", "amend", "remove", "delete")
_CURRENT_CONTEXT_KEYS = frozenset({"date", "time", "timezone"})
_CAPABILITY_PLACEHOLDER = "{{RETRIEVAL_CAPABILITIES}}"
_PROMPT_TEMPLATE = """You convert one user request into one strict JSON RequestPlan. Use the supplied current date, time, and timezone.

Hard filters can permanently remove valid notes: apply a deterministic restriction only when the request maps explicitly and safely to this capability contract. Otherwise preserve the meaning in `query`. Multiple RetrieveActions are only for genuinely independent candidate-set branches; ordinary semantic OR stays one query.

Use a canonical type restriction only when the request explicitly and safely identifies that canonical class; never infer a canonical type from semantic facets. Decompose write knowledge semantically: group facts for the same logical subject only when their semantic mutation intent is compatible; different intents for the same subject produce separate KnowledgeUnits. Split independent subjects and preserve references between units. Use only record, amend, remove, and delete. Amend requires concrete facts describing the corrected state. Remove requires concrete facts identifying the knowledge to remove. Delete uses facts: [] and must not invent filler or deletion prose. Record normally contains facts; facts: [] is allowed only for a semantic reference-target unit that supports another KnowledgeUnit in the same WriteAction. Do not infer repository existence, resolve identity, choose CREATE versus UPDATE, generate IDs, paths, Markdown, SQL, or persistence instructions, or execute retrieval, persistence, or entity resolution. Use limitation codes only with their defined meanings. Return strict structured JSON.

Planner retrieval capabilities (derived dynamically from the canonical schema):

{{RETRIEVAL_CAPABILITIES}}"""


class RequestPlanningError(ValueError):
    """Indicate malformed, unsupported, or unsafe RequestPlan model output."""


class ResponsesClient(Protocol):
    """Describe the injected subset of the OpenAI Responses client used by the planner."""

    responses: Any


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    """Represent one validated Phase 13-compatible retrieval request."""

    query: str
    type: str | None
    filters: tuple[ContextFilter, ...]


@dataclass(frozen=True, slots=True)
class RetrieveAction:
    """Represent one ordered, non-executing retrieval action."""

    plan: RetrievalPlan
    kind: str = "retrieve"


@dataclass(frozen=True, slots=True)
class KnowledgeReference:
    """Represent one semantic in-plan reference to another knowledge unit.

    Args:
        target_index: Zero-based index of another unit in the same write action.
        role: Human-readable semantic role of the referenced unit.
    """

    target_index: int
    role: str


@dataclass(frozen=True, slots=True)
class KnowledgeUnit:
    """Represent grouped facts about one subject without resolving or persisting it.

    Args:
        subject: Non-empty user-level subject reference.
        type: Optional canonical type directly expressed by the request.
        intent: Controlled semantic mutation intent for later resolution.
        facts: Concrete facts grouped for this subject, possibly empty for a delete or a
            reference-only record target.
        references: Semantic pointers to other units in the same write action.
    """

    subject: str
    type: str | None
    intent: str
    facts: tuple[str, ...]
    references: tuple[KnowledgeReference, ...]


@dataclass(frozen=True, slots=True)
class WriteAction:
    """Represent semantic write preparation without physical persistence decisions.

    Args:
        units: Non-empty related knowledge units in request order.
    """

    units: tuple[KnowledgeUnit, ...]
    kind: str = "write"


RequestAction = RetrieveAction | WriteAction


@dataclass(frozen=True, slots=True)
class RequestPlan:
    """Contain an ordered, validated interpretation of one user request."""

    actions: tuple[RequestAction, ...]
    limitations: tuple[str, ...]


def render_request_planner_prompt(
    schema: Mapping[str, Any], current_context: Mapping[str, str]
) -> str:
    """Render the production planner prompt from current schema and caller context.

    Args:
        schema: Parsed canonical Odyssey schema.
        current_context: Current date, time, and timezone supplied at request time.

    Returns:
        A compact prompt containing dynamic planner capabilities.

    Raises:
        RequestPlanningError: If the runtime context is incomplete or malformed.
    """
    _validate_current_context(current_context)
    if _PROMPT_TEMPLATE.count(_CAPABILITY_PLACEHOLDER) != 1:
        raise RuntimeError("Request planner prompt template is invalid")
    capabilities = build_planner_capabilities(schema, current_context=current_context)
    return _PROMPT_TEMPLATE.replace(
        _CAPABILITY_PLACEHOLDER,
        json.dumps(capabilities, ensure_ascii=False, separators=(",", ":")),
    )


def request_plan_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Build the strict Structured Outputs schema for the current canonical schema.

    Args:
        schema: Parsed canonical Odyssey schema.

    Returns:
        Closed JSON Schema accepted by the Responses API for a RequestPlan.

    Raises:
        RequestPlanningError: If canonical capabilities cannot form a usable contract.
    """
    capabilities = build_planner_capabilities(schema)
    filters = capabilities["filters"]
    alternatives = []
    for field, definition in filters.items():
        scalar: dict[str, Any] = {
            "type": "integer" if definition["value_type"] == "integer" else "string"
        }
        if definition["controlled_values"]:
            scalar["enum"] = definition["controlled_values"]
        for operator in definition["operators"]:
            alternatives.append(
                {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": [field]},
                        "op": {"type": "string", "enum": [operator]},
                        "value": {"type": "array", "items": scalar} if operator == "in" else scalar,
                    },
                    "required": ["field", "op", "value"],
                    "additionalProperties": False,
                }
            )
    if not alternatives:
        raise RequestPlanningError("Canonical schema exposes no planner filters")
    retrieve = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "type": {
                "anyOf": [{"type": "null"}, {"type": "string", "enum": list(capabilities["types"])}]
            },
            "filters": {"type": "array", "items": {"anyOf": alternatives}},
        },
        "required": ["query", "type", "filters"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {"kind": {"const": "retrieve"}, "plan": retrieve},
                            "required": ["kind", "plan"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"const": "write"},
                                "units": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "subject": {"type": "string"},
                                            "type": {
                                                "anyOf": [
                                                    {"type": "null"},
                                                    {
                                                        "type": "string",
                                                        "enum": list(capabilities["types"]),
                                                    },
                                                ]
                                            },
                                            "intent": {
                                                "type": "string",
                                                "enum": list(WRITE_INTENTS),
                                            },
                                            "facts": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                                "minItems": 0,
                                            },
                                            "references": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "target_index": {
                                                            "type": "integer",
                                                            "minimum": 0,
                                                        },
                                                        "role": {"type": "string"},
                                                    },
                                                    "required": ["target_index", "role"],
                                                    "additionalProperties": False,
                                                },
                                            },
                                        },
                                        "required": [
                                            "subject",
                                            "type",
                                            "intent",
                                            "facts",
                                            "references",
                                        ],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["kind", "units"],
                            "additionalProperties": False,
                        },
                    ]
                },
            },
            "limitations": {
                "type": "array",
                "items": {"type": "string", "enum": list(LIMITATIONS)},
            },
        },
        "required": ["actions", "limitations"],
        "additionalProperties": False,
    }


def validate_request_plan(payload: Any, schema: Mapping[str, Any]) -> RequestPlan:
    """Validate untrusted model output and return an immutable executable-safe plan.

    Args:
        payload: JSON-decoded model output.
        schema: Parsed canonical Odyssey schema.

    Returns:
        A locally validated RequestPlan, without performing any action.

    Raises:
        RequestPlanningError: If output is malformed, empty, or violates deterministic retrieval rules.
    """
    capabilities = build_planner_capabilities(schema)
    if not isinstance(payload, dict) or set(payload) != {"actions", "limitations"}:
        raise RequestPlanningError("RequestPlan must contain exactly actions and limitations")
    raw_actions, limitations = payload["actions"], payload["limitations"]
    if not isinstance(raw_actions, list) or not raw_actions:
        raise RequestPlanningError("RequestPlan actions must be a non-empty list")
    if (
        not isinstance(limitations, list)
        or len(limitations) != len(set(limitations))
        or not all(isinstance(item, str) and item in LIMITATIONS for item in limitations)
    ):
        raise RequestPlanningError("RequestPlan limitations are invalid")
    actions = tuple(_validate_action(action, schema, capabilities) for action in raw_actions)
    return RequestPlan(actions=actions, limitations=tuple(limitations))


class OpenAIRequestPlanner:
    """Plan requests with Sol/low while leaving all execution outside this boundary."""

    def __init__(
        self, client: ResponsesClient, schema: Mapping[str, Any], current_context: Mapping[str, str]
    ) -> None:
        """Initialize a planner with an injected client and runtime schema/context.

        Args:
            client: OpenAI-compatible Responses client supplied by composition code.
            schema: Current canonical Odyssey schema.
            current_context: Current date, time, and timezone for lifecycle interpretation.

        Raises:
            RequestPlanningError: If current context is malformed.
        """
        _validate_current_context(current_context)
        self._client = client
        self._schema = schema
        self._current_context = dict(current_context)

    @classmethod
    def from_environment(
        cls, schema: Mapping[str, Any], current_context: Mapping[str, str]
    ) -> OpenAIRequestPlanner:
        """Create a production planner using the environment-provided OpenAI API key.

        Args:
            schema: Current canonical Odyssey schema.
            current_context: Current date, time, and timezone for lifecycle interpretation.

        Returns:
            A planner backed by the OpenAI Responses API.

        Raises:
            RequestPlanningError: If the API key or OpenAI SDK is unavailable.
        """
        if not os.environ.get("OPENAI_API_KEY"):
            raise RequestPlanningError("OPENAI_API_KEY is required for request planning")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RequestPlanningError("Install the OpenAI SDK for request planning") from error
        return cls(OpenAI(), schema, current_context)

    def plan(self, request: str) -> RequestPlan:
        """Interpret one non-empty user request and fail closed on invalid model output.

        Args:
            request: User request to interpret.

        Returns:
            A validated RequestPlan that has not been executed.

        Raises:
            RequestPlanningError: If the request, provider response, JSON, or plan is invalid.
        """
        if not isinstance(request, str) or not request.strip():
            raise RequestPlanningError("Request text must be non-empty")
        try:
            response = self._client.responses.create(
                model=PLANNER_MODEL,
                reasoning={"effort": PLANNER_REASONING_EFFORT},
                store=False,
                input=[
                    {
                        "role": "system",
                        "content": render_request_planner_prompt(
                            self._schema, self._current_context
                        ),
                    },
                    {"role": "user", "content": request},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_request_plan",
                        "strict": True,
                        "schema": request_plan_json_schema(self._schema),
                    }
                },
            )
        except Exception as error:
            raise RequestPlanningError("Request planner provider call failed") from error
        try:
            payload = json.loads(response.output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise RequestPlanningError("Request planner returned malformed JSON") from error
        return validate_request_plan(payload, self._schema)


def _validate_current_context(current_context: Mapping[str, str]) -> None:
    """Reject incomplete dynamic date/time context before it reaches a planner prompt."""
    if set(current_context) != _CURRENT_CONTEXT_KEYS or not all(
        isinstance(value, str) and value.strip() for value in current_context.values()
    ):
        raise RequestPlanningError(
            "Current context must contain non-empty date, time, and timezone"
        )


def _validate_action(
    action: Any, schema: Mapping[str, Any], capabilities: Mapping[str, Any]
) -> RequestAction:
    """Validate one discriminated action without executing retrieval or persistence."""
    if not isinstance(action, dict):
        raise RequestPlanningError("RequestPlan action must be an object")
    if action.get("kind") == "write":
        return _validate_write_action(action, capabilities)
    if action.get("kind") != "retrieve" or set(action) != {"kind", "plan"}:
        raise RequestPlanningError("RequestPlan action kind is invalid")
    raw_plan = action["plan"]
    if not isinstance(raw_plan, dict) or set(raw_plan) != {"query", "type", "filters"}:
        raise RequestPlanningError("RetrieveAction must contain exactly one retrieval plan")
    query, note_type, raw_filters = raw_plan["query"], raw_plan["type"], raw_plan["filters"]
    if not isinstance(query, str) or not query.strip():
        raise RequestPlanningError("RetrievalPlan query must be non-empty")
    if note_type is not None and note_type not in capabilities["types"]:
        raise RequestPlanningError("RetrievalPlan type is invalid")
    if not isinstance(raw_filters, list):
        raise RequestPlanningError("RetrievalPlan filters must be a list")
    _validate_planner_filters(raw_filters, note_type, capabilities)
    try:
        validate_context_filters(dict(schema), raw_filters, note_type=note_type)
    except ValueError as error:
        raise RequestPlanningError("RetrievalPlan filters are invalid") from error
    return RetrieveAction(
        RetrievalPlan(
            query=query.strip(),
            type=note_type,
            filters=tuple(
                ContextFilter(item["field"], item["op"], item["value"]) for item in raw_filters
            ),
        )
    )


def _validate_write_action(
    action: Mapping[str, Any], capabilities: Mapping[str, Any]
) -> WriteAction:
    """Validate semantic knowledge units without resolving identity or choosing persistence.

    Args:
        action: Untrusted write-action object returned by the planner.
        capabilities: Canonical type capabilities derived from the active schema.

    Returns:
        Immutable semantic write preparation with valid references and intent-specific fact rules.

    Raises:
        RequestPlanningError: If a unit is malformed, violates its intent-specific fact rule, or
            references an unknown or self target.
    """
    raw_units = action.get("units")
    if set(action) != {"kind", "units"} or not isinstance(raw_units, list) or not raw_units:
        raise RequestPlanningError("WriteAction must contain non-empty units")
    units = tuple(_validate_knowledge_unit(raw, capabilities) for raw in raw_units)
    for index, unit in enumerate(units):
        for reference in unit.references:
            if reference.target_index >= len(units) or reference.target_index == index:
                raise RequestPlanningError("KnowledgeUnit reference target is invalid")
    referenced_targets = {reference.target_index for unit in units for reference in unit.references}
    for index, unit in enumerate(units):
        if unit.intent in {"amend", "remove"} and not unit.facts:
            raise RequestPlanningError("KnowledgeUnit amend and remove intents require facts")
        if unit.intent == "record" and not unit.facts and index not in referenced_targets:
            raise RequestPlanningError(
                "KnowledgeUnit record intent requires facts unless referenced"
            )
    return WriteAction(units=units)


def _validate_knowledge_unit(unit: Any, capabilities: Mapping[str, Any]) -> KnowledgeUnit:
    """Validate one grouped knowledge unit and its local reference syntax.

    Args:
        unit: Untrusted model object for one semantic subject.
        capabilities: Canonical type capabilities derived from the active schema.

    Returns:
        One immutable semantic unit with no physical persistence fields.

    Raises:
        RequestPlanningError: If fields are incomplete, unknown, or contain malformed fact text.
    """
    required = {"subject", "type", "intent", "facts", "references"}
    if not isinstance(unit, dict) or set(unit) != required:
        raise RequestPlanningError("KnowledgeUnit fields are invalid")
    subject, note_type, intent = unit["subject"], unit["type"], unit["intent"]
    raw_facts, raw_references = unit["facts"], unit["references"]
    if not isinstance(subject, str) or not subject.strip():
        raise RequestPlanningError("KnowledgeUnit subject must be non-empty")
    if note_type is not None and note_type not in capabilities["types"]:
        raise RequestPlanningError("KnowledgeUnit type is invalid")
    if intent not in WRITE_INTENTS:
        raise RequestPlanningError("KnowledgeUnit intent is invalid")
    if intent == "delete" and raw_facts:
        raise RequestPlanningError("KnowledgeUnit delete intent requires facts to be empty")
    if (
        not isinstance(raw_facts, list)
        or len(raw_facts) != len(set(raw_facts))
        or not all(isinstance(fact, str) and fact.strip() for fact in raw_facts)
    ):
        raise RequestPlanningError("KnowledgeUnit facts must be unique non-empty strings")
    if not isinstance(raw_references, list):
        raise RequestPlanningError("KnowledgeUnit references must be a list")
    references = []
    for reference in raw_references:
        if (
            not isinstance(reference, dict)
            or set(reference) != {"target_index", "role"}
            or not isinstance(reference["target_index"], int)
            or isinstance(reference["target_index"], bool)
            or reference["target_index"] < 0
            or not isinstance(reference["role"], str)
            or not reference["role"].strip()
        ):
            raise RequestPlanningError("KnowledgeUnit reference is invalid")
        references.append(
            KnowledgeReference(
                target_index=reference["target_index"], role=reference["role"].strip()
            )
        )
    return KnowledgeUnit(
        subject=subject.strip(),
        type=note_type,
        intent=intent,
        facts=tuple(fact.strip() for fact in raw_facts),
        references=tuple(references),
    )


def _validate_planner_filters(
    filters: Sequence[Any], note_type: str | None, capabilities: Mapping[str, Any]
) -> None:
    """Restrict model filters to dynamic planner capabilities and compatible type scopes."""
    known = capabilities["filters"]
    candidates = set(capabilities["types"])
    if note_type is not None:
        candidates &= {note_type}
    for item in filters:
        if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
            raise RequestPlanningError("Each retrieval filter must contain field, op, and value")
        definition = known.get(item["field"])
        if definition is None or item["op"] not in definition["operators"]:
            raise RequestPlanningError("Retrieval filter field or operator is invalid")
        if item["op"] == "in":
            if not isinstance(item["value"], list) or not item["value"]:
                raise RequestPlanningError("The in operator requires a non-empty value list")
        elif isinstance(item["value"], list):
            raise RequestPlanningError("Only the in operator accepts a value list")
        if item["field"] == "type":
            values = item["value"] if isinstance(item["value"], list) else [item["value"]]
            candidates &= set(values)
    if not candidates:
        raise RequestPlanningError("RetrievalPlan type restrictions are contradictory")
    for item in filters:
        if item["field"] != "type" and not candidates <= set(known[item["field"]]["applies_to"]):
            raise RequestPlanningError("Retrieval filter is incompatible with its candidate types")
