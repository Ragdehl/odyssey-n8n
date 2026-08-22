"""Fail-closed interpretation of user requests into safe Odyssey RequestPlans."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from odyssey_core.context import ContextFilter, validate_context_filters
from odyssey_core.notes.validation import NoteValidationError, validate_field_value
from odyssey_core.planner_capabilities import (
    LIMITATIONS,
    build_planner_capabilities,
    build_write_capabilities,
)

PLANNER_MODEL = "gpt-5.6-sol"
PLANNER_REASONING_EFFORT = "low"
WRITE_INTENTS = ("record", "amend", "remove", "delete")
_PROPERTY_OPS = ("set", "remove")
_CURRENT_CONTEXT_KEYS = frozenset({"date", "time", "timezone"})
_RETRIEVAL_CAPABILITY_PLACEHOLDER = "{{RETRIEVAL_CAPABILITIES}}"
_WRITE_CAPABILITY_PLACEHOLDER = "{{WRITE_CAPABILITIES}}"
_PROMPT_TEMPLATE = """You convert one user request into one strict JSON RequestPlan. Use the supplied current date, time, and timezone.

Hard filters can permanently remove valid notes: apply a deterministic restriction only when the request maps explicitly and safely to this capability contract. Otherwise preserve the meaning in `query`. Words such as before, earlier, previously, beforehand, antes, anteriormente, previamente, and ya había pensado describe knowledge semantics, not note lifecycle, unless the user explicitly refers to when a note, entry, or item was created, written, added, updated, modified, or recorded. Only that explicit lifecycle timing authorizes created_at or updated_at filters. Multiple RetrieveActions are only for genuinely independent candidate-set branches; ordinary semantic OR stays one query.

RetrieveAction.plan and every KnowledgeUnit.target use the same selection shape: non-empty query, optional canonical type, and filters. A RetrieveAction exists only when the user asks to retrieve or inspect knowledge. A write target is identity evidence for later existing-entity resolution and must not create an extra RetrieveAction. For writes, put a property mentioned only to identify the target in target.filters when it maps safely to the filter contract; put it in properties only when the user is asking to record/change/remove that property. The same field may appear in target.filters as the old identifying value and properties as a corrected new value. Meaning that cannot safely become a filter stays in target.query.

Decompose write knowledge semantically: group changes for the same logical target only when their mutation intent is compatible; different intents for the same target produce separate KnowledgeUnits. Split independent targets and preserve references between units. Use only record, amend, remove, and delete. `properties` contains only canonical type-specific property changes supplied by the write capability contract. Use op=set for record/amend and op=remove with value=null for remove. Do not invent fields. If a fact is fully represented by a canonical property, do not duplicate it in facts; keep only remaining free-text knowledge in facts. Amend/remove require at least one mutation across properties or facts. Delete uses properties: [] and facts: []. Record normally contains properties and/or facts; both may be empty only for a semantic reference-target unit that supports another KnowledgeUnit in the same WriteAction. Do not attempt canonical type reassignment in Phase 15.1.

Do not infer repository existence, resolve identity, choose CREATE versus UPDATE, generate IDs, paths, Markdown, SQL, or persistence instructions, or execute retrieval, persistence, or entity resolution. Use limitation codes only with their defined meanings. Return strict structured JSON.

Planner retrieval/selection capabilities (derived dynamically from the canonical schema):

{{RETRIEVAL_CAPABILITIES}}

Planner writable type/property capabilities (derived dynamically from the same canonical schema):

{{WRITE_CAPABILITIES}}"""


class RequestPlanningError(ValueError):
    """Indicate malformed, unsupported, or unsafe RequestPlan model output."""


class ResponsesClient(Protocol):
    """Describe the injected subset of the OpenAI Responses client used by the planner."""

    responses: Any


@dataclass(frozen=True, slots=True)
class SelectionCriteria:
    """Represent shared query/type/filter criteria without prescribing execution semantics."""

    query: str
    type: str | None
    filters: tuple[ContextFilter, ...]


# Keep the established public name while sharing the same selection value with write targets.
RetrievalPlan = SelectionCriteria


@dataclass(frozen=True, slots=True)
class RetrieveAction:
    """Represent one ordered, non-executing retrieval action."""

    plan: SelectionCriteria
    kind: str = "retrieve"


@dataclass(frozen=True, slots=True)
class KnowledgeReference:
    """Represent one semantic in-plan reference to another knowledge unit."""

    target_index: int
    role: str


@dataclass(frozen=True, slots=True)
class PropertyChange:
    """Represent one validated canonical property mutation requested by the user."""

    field: str
    op: str
    value: Any


@dataclass(frozen=True, slots=True)
class KnowledgeUnit:
    """Represent one semantic write target and the requested knowledge mutation."""

    target: SelectionCriteria
    intent: str
    properties: tuple[PropertyChange, ...]
    facts: tuple[str, ...]
    references: tuple[KnowledgeReference, ...]


@dataclass(frozen=True, slots=True)
class WriteAction:
    """Represent semantic write preparation without physical persistence decisions."""

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
    """Render the production planner prompt from current schema and caller context."""
    _validate_current_context(current_context)
    if _PROMPT_TEMPLATE.count(_RETRIEVAL_CAPABILITY_PLACEHOLDER) != 1:
        raise RuntimeError("Request planner retrieval capability placeholder is invalid")
    if _PROMPT_TEMPLATE.count(_WRITE_CAPABILITY_PLACEHOLDER) != 1:
        raise RuntimeError("Request planner write capability placeholder is invalid")
    retrieval = build_planner_capabilities(schema, current_context=current_context)
    writable = build_write_capabilities(schema)
    rendered = _PROMPT_TEMPLATE.replace(
        _RETRIEVAL_CAPABILITY_PLACEHOLDER,
        json.dumps(retrieval, ensure_ascii=False, separators=(",", ":")),
    )
    return rendered.replace(
        _WRITE_CAPABILITY_PLACEHOLDER,
        json.dumps(writable, ensure_ascii=False, separators=(",", ":")),
    )


def request_plan_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Build the strict Structured Outputs schema for the active canonical schema."""
    retrieval_capabilities = build_planner_capabilities(schema)
    write_capabilities = build_write_capabilities(schema)
    selection_schema = _selection_json_schema(retrieval_capabilities)
    property_changes_schema = _property_changes_json_schema(write_capabilities)
    return {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["retrieve"]},
                                "plan": selection_schema,
                            },
                            "required": ["kind", "plan"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["write"]},
                                "units": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "target": selection_schema,
                                            "intent": {
                                                "type": "string",
                                                "enum": list(WRITE_INTENTS),
                                            },
                                            "properties": property_changes_schema,
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
                                            "target",
                                            "intent",
                                            "properties",
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
    """Validate untrusted model output and return an immutable non-executing plan."""
    retrieval_capabilities = build_planner_capabilities(schema)
    write_capabilities = build_write_capabilities(schema)
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
    actions = tuple(
        _validate_action(action, schema, retrieval_capabilities, write_capabilities)
        for action in raw_actions
    )
    return RequestPlan(actions=actions, limitations=tuple(limitations))


class OpenAIRequestPlanner:
    """Plan requests with Sol/low while leaving all execution outside this boundary."""

    def __init__(
        self, client: ResponsesClient, schema: Mapping[str, Any], current_context: Mapping[str, str]
    ) -> None:
        """Initialize a planner with an injected client and runtime schema/context."""
        _validate_current_context(current_context)
        self._client = client
        self._schema = schema
        self._current_context = dict(current_context)

    @classmethod
    def from_environment(
        cls, schema: Mapping[str, Any], current_context: Mapping[str, str]
    ) -> OpenAIRequestPlanner:
        """Create a production planner using the environment-provided OpenAI API key."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise RequestPlanningError("OPENAI_API_KEY is required for request planning")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RequestPlanningError("Install the OpenAI SDK for request planning") from error
        return cls(OpenAI(), schema, current_context)

    def plan(self, request: str) -> RequestPlan:
        """Interpret one non-empty user request and fail closed on invalid model output."""
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


def _selection_json_schema(capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Build the one shared query/type/filter Structured Outputs shape."""
    alternatives = _filter_json_schema_alternatives(capabilities)
    if not alternatives:
        raise RequestPlanningError("Canonical schema exposes no planner filters")
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "type": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "enum": list(capabilities["types"])},
                ]
            },
            "filters": {"type": "array", "items": {"anyOf": alternatives}},
        },
        "required": ["query", "type", "filters"],
        "additionalProperties": False,
    }


def _filter_json_schema_alternatives(capabilities: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build strict dynamic filter alternatives shared by retrieve and write target selection."""
    alternatives: list[dict[str, Any]] = []
    for field, definition in capabilities["filters"].items():
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
                        "value": {"type": "array", "items": scalar}
                        if operator == "in"
                        else scalar,
                    },
                    "required": ["field", "op", "value"],
                    "additionalProperties": False,
                }
            )
    return alternatives


def _property_changes_json_schema(write_capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Build dynamic strict property-change alternatives from type-specific schema properties."""
    alternatives: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for type_definition in write_capabilities["types"].values():
        for field, definition in type_definition["properties"].items():
            existing = seen.get(field)
            if existing is not None and existing != definition:
                raise RequestPlanningError(
                    f"Writable property {field!r} has incompatible definitions across types"
                )
            if existing is not None:
                continue
            seen[field] = definition
            scalar = _property_value_json_schema(definition)
            alternatives.extend(
                [
                    {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string", "enum": [field]},
                            "op": {"type": "string", "enum": ["set"]},
                            "value": scalar,
                        },
                        "required": ["field", "op", "value"],
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string", "enum": [field]},
                            "op": {"type": "string", "enum": ["remove"]},
                            "value": {"type": "null"},
                        },
                        "required": ["field", "op", "value"],
                        "additionalProperties": False,
                    },
                ]
            )
    if alternatives:
        return {"type": "array", "items": {"anyOf": alternatives}}
    return {
        "type": "array",
        "items": {"type": "object", "properties": {}, "additionalProperties": False},
        "maxItems": 0,
    }


def _property_value_json_schema(definition: Mapping[str, Any]) -> dict[str, Any]:
    """Map one Core-supported property value definition to strict Structured Outputs JSON Schema."""
    value_type = definition["value_type"]
    constraints = definition.get("constraints", {})
    if value_type == "integer":
        result: dict[str, Any] = {"type": "integer"}
        if "minimum" in constraints:
            result["minimum"] = constraints["minimum"]
        return result
    if value_type == "array[string]":
        result = {"type": "array", "items": {"type": "string"}}
        if constraints.get("unique_items") is True:
            result["uniqueItems"] = True
        return result
    if value_type in {"string", "date"}:
        result = {"type": "string"}
        if constraints.get("non_empty") is True:
            result["minLength"] = 1
        return result
    raise RequestPlanningError(f"Unsupported writable property value type: {value_type!r}")


def _validate_current_context(current_context: Mapping[str, str]) -> None:
    """Reject incomplete dynamic date/time context before it reaches a planner prompt."""
    if set(current_context) != _CURRENT_CONTEXT_KEYS or not all(
        isinstance(value, str) and value.strip() for value in current_context.values()
    ):
        raise RequestPlanningError(
            "Current context must contain non-empty date, time, and timezone"
        )


def _validate_action(
    action: Any,
    schema: Mapping[str, Any],
    retrieval_capabilities: Mapping[str, Any],
    write_capabilities: Mapping[str, Any],
) -> RequestAction:
    """Validate one discriminated action without executing retrieval or persistence."""
    if not isinstance(action, dict):
        raise RequestPlanningError("RequestPlan action must be an object")
    if action.get("kind") == "write":
        return _validate_write_action(
            action, schema, retrieval_capabilities, write_capabilities
        )
    if action.get("kind") != "retrieve" or set(action) != {"kind", "plan"}:
        raise RequestPlanningError("RequestPlan action kind is invalid")
    plan = _validate_selection(
        action["plan"], schema, retrieval_capabilities, label="RetrievalPlan"
    )
    return RetrieveAction(plan=plan)


def _validate_selection(
    raw: Any,
    schema: Mapping[str, Any],
    capabilities: Mapping[str, Any],
    *,
    label: str,
) -> SelectionCriteria:
    """Validate the shared query/type/filters selection contract."""
    if not isinstance(raw, dict) or set(raw) != {"query", "type", "filters"}:
        raise RequestPlanningError(f"{label} must contain exactly query, type, and filters")
    query, note_type, raw_filters = raw["query"], raw["type"], raw["filters"]
    if not isinstance(query, str) or not query.strip():
        raise RequestPlanningError(f"{label} query must be non-empty")
    if note_type is not None and note_type not in capabilities["types"]:
        raise RequestPlanningError(f"{label} type is invalid")
    if not isinstance(raw_filters, list):
        raise RequestPlanningError(f"{label} filters must be a list")
    _validate_planner_filters(raw_filters, note_type, capabilities)
    try:
        validate_context_filters(dict(schema), raw_filters, note_type=note_type)
    except ValueError as error:
        raise RequestPlanningError(f"{label} filters are invalid") from error
    return SelectionCriteria(
        query=query.strip(),
        type=note_type,
        filters=tuple(
            ContextFilter(item["field"], item["op"], item["value"]) for item in raw_filters
        ),
    )


def _validate_write_action(
    action: Mapping[str, Any],
    schema: Mapping[str, Any],
    retrieval_capabilities: Mapping[str, Any],
    write_capabilities: Mapping[str, Any],
) -> WriteAction:
    """Validate semantic knowledge units without resolving identity or choosing persistence."""
    raw_units = action.get("units")
    if set(action) != {"kind", "units"} or not isinstance(raw_units, list) or not raw_units:
        raise RequestPlanningError("WriteAction must contain non-empty units")
    units = tuple(
        _validate_knowledge_unit(
            raw, schema, retrieval_capabilities, write_capabilities
        )
        for raw in raw_units
    )
    for index, unit in enumerate(units):
        for reference in unit.references:
            if reference.target_index >= len(units) or reference.target_index == index:
                raise RequestPlanningError("KnowledgeUnit reference target is invalid")
    referenced_targets = {reference.target_index for unit in units for reference in unit.references}
    for index, unit in enumerate(units):
        has_payload = bool(unit.properties or unit.facts)
        if unit.intent in {"amend", "remove"} and not has_payload:
            raise RequestPlanningError(
                "KnowledgeUnit amend and remove intents require properties or facts"
            )
        if unit.intent == "record" and not has_payload and index not in referenced_targets:
            raise RequestPlanningError(
                "KnowledgeUnit record intent requires properties or facts unless referenced"
            )
    return WriteAction(units=units)


def _validate_knowledge_unit(
    unit: Any,
    schema: Mapping[str, Any],
    retrieval_capabilities: Mapping[str, Any],
    write_capabilities: Mapping[str, Any],
) -> KnowledgeUnit:
    """Validate one write target, its property/fact payload, and local reference syntax."""
    required = {"target", "intent", "properties", "facts", "references"}
    if not isinstance(unit, dict) or set(unit) != required:
        raise RequestPlanningError("KnowledgeUnit fields are invalid")
    target = _validate_selection(
        unit["target"], schema, retrieval_capabilities, label="KnowledgeUnit target"
    )
    intent = unit["intent"]
    if intent not in WRITE_INTENTS:
        raise RequestPlanningError("KnowledgeUnit intent is invalid")

    raw_properties = unit["properties"]
    if not isinstance(raw_properties, list):
        raise RequestPlanningError("KnowledgeUnit properties must be a list")
    properties = _validate_property_changes(
        raw_properties, target.type, intent, write_capabilities
    )

    raw_facts = unit["facts"]
    if (
        not isinstance(raw_facts, list)
        or len(raw_facts) != len(set(raw_facts))
        or not all(isinstance(fact, str) and fact.strip() for fact in raw_facts)
    ):
        raise RequestPlanningError("KnowledgeUnit facts must be unique non-empty strings")
    if intent == "delete" and (raw_properties or raw_facts):
        raise RequestPlanningError("KnowledgeUnit delete intent requires empty properties and facts")

    raw_references = unit["references"]
    if not isinstance(raw_references, list):
        raise RequestPlanningError("KnowledgeUnit references must be a list")
    references: list[KnowledgeReference] = []
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
        target=target,
        intent=intent,
        properties=properties,
        facts=tuple(fact.strip() for fact in raw_facts),
        references=tuple(references),
    )


def _validate_property_changes(
    raw_properties: Sequence[Any],
    note_type: str | None,
    intent: str,
    write_capabilities: Mapping[str, Any],
) -> tuple[PropertyChange, ...]:
    """Validate generic property changes against the selected canonical type and shared value rules."""
    if raw_properties and note_type is None:
        raise RequestPlanningError("KnowledgeUnit properties require a canonical target type")
    if intent == "delete" and raw_properties:
        raise RequestPlanningError("KnowledgeUnit delete intent cannot mutate properties")
    allowed_ops = {
        "record": {"set"},
        "amend": {"set"},
        "remove": {"remove"},
        "delete": set(),
    }[intent]
    type_properties = (
        write_capabilities["types"][note_type]["properties"] if note_type is not None else {}
    )
    changes: list[PropertyChange] = []
    seen: set[str] = set()
    for raw in raw_properties:
        if not isinstance(raw, dict) or set(raw) != {"field", "op", "value"}:
            raise RequestPlanningError("Each property change must contain field, op, and value")
        field, op, value = raw["field"], raw["op"], raw["value"]
        if not isinstance(field, str) or field not in type_properties:
            raise RequestPlanningError("KnowledgeUnit property field is invalid for its target type")
        if field in seen:
            raise RequestPlanningError("KnowledgeUnit property fields must be unique")
        seen.add(field)
        if op not in _PROPERTY_OPS or op not in allowed_ops:
            raise RequestPlanningError("KnowledgeUnit property operation is incompatible with intent")
        if op == "remove":
            if value is not None:
                raise RequestPlanningError("Property remove operation requires null value")
        else:
            if value is None:
                raise RequestPlanningError("Property set operation requires a non-null value")
            try:
                validate_field_value(field, value, type_properties[field])
            except NoteValidationError as error:
                raise RequestPlanningError("KnowledgeUnit property value is invalid") from error
        changes.append(PropertyChange(field=field, op=op, value=value))
    return tuple(changes)


def _validate_planner_filters(
    filters: Sequence[Any], note_type: str | None, capabilities: Mapping[str, Any]
) -> None:
    """Restrict selection filters to dynamic planner capabilities and compatible type scopes."""
    known = capabilities["filters"]
    candidates = set(capabilities["types"])
    if note_type is not None:
        candidates &= {note_type}
    for item in filters:
        if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
            raise RequestPlanningError("Each selection filter must contain field, op, and value")
        definition = known.get(item["field"])
        if definition is None or item["op"] not in definition["operators"]:
            raise RequestPlanningError("Selection filter field or operator is invalid")
        if item["op"] == "in":
            if not isinstance(item["value"], list) or not item["value"]:
                raise RequestPlanningError("The in operator requires a non-empty value list")
        elif isinstance(item["value"], list):
            raise RequestPlanningError("Only the in operator accepts a value list")
        if item["field"] == "type":
            values = item["value"] if isinstance(item["value"], list) else [item["value"]]
            candidates &= set(values)
    if not candidates:
        raise RequestPlanningError("Selection type restrictions are contradictory")
    for item in filters:
        if item["field"] != "type" and not candidates <= set(known[item["field"]]["applies_to"]):
            raise RequestPlanningError("Selection filter is incompatible with its candidate types")
