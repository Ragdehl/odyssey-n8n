"""Fail-closed interpretation of user requests into safe Odyssey RequestPlans."""

from __future__ import annotations

import json
import os
import re
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
_TAG_CHANGE_OPS = ("add", "remove")
_LINK_DIRECTIONS = ("incoming", "outgoing", "both")
_CURRENT_CONTEXT_KEYS = frozenset({"date", "time", "timezone"})
_RETRIEVAL_CAPABILITY_PLACEHOLDER = "{{RETRIEVAL_CAPABILITIES}}"
_WRITE_CAPABILITY_PLACEHOLDER = "{{WRITE_CAPABILITIES}}"
_REFERENCE_MARKER_PATTERN = re.compile(r"\{\{ref:(\d+)\}\}")
_PROMPT_TEMPLATE = """You convert one user request into one strict JSON RequestPlan. Use the supplied current date, time, and timezone.

Interpret each requested action in this order. FIRST identify the Odyssey knowledge candidate set and preserve every safely representable SelectionCriteria field: entity, query, type, filters, and link_scope. THEN choose what operation the user wants on that set: ordinary retrieval uses RetrieveAction, ordinary knowledge mutation uses WriteAction, and work requiring a specialized capability uses DelegateAction. The action kind changes what happens to the candidate set; it never weakens or erases that set.
For every KnowledgeUnit, set `cardinality` to `one` for one logical identity, including when
resolution may later be ambiguous, or to `all_matching` only when the user means the complete set
represented by the selection. Do not infer `all_matching` from plural wording alone, from several
semantic candidates, or from an explicit list of independent names. Preserve an all-matching intent
even when current execution cannot authorize its selector. Cardinality belongs only to KnowledgeUnit;
do not add it to SelectionCriteria. An all-matching unit has no singular entity identity.

Hard filters can permanently remove valid notes: apply a deterministic restriction only when the request maps explicitly and safely to this capability contract. Otherwise preserve the meaning in `query`. Words such as before, earlier, previously, beforehand, antes, anteriormente, previamente, and ya había pensado describe knowledge semantics, not note lifecycle, unless the user explicitly refers to when a note, entry, or item was created, written, added, updated, modified, or recorded. Only that explicit lifecycle timing authorizes created_at or updated_at filters. Multiple RetrieveActions are only for genuinely independent candidate-set branches; ordinary semantic OR stays one query.

RetrieveAction.plan and every KnowledgeUnit.target use the same selection shape. A non-null DelegateAction.selection obeys those same SelectionCriteria rules. Entity is only a safely explicit primary-name/alias candidate from the user's wording; it is never an Odyssey ID and does not assert repository existence. Do not turn every noun phrase or mentioned name into entity: contextual descriptions such as "la tienda de la esquina" and "la amiga de Marta" keep entity=null. A null link_scope means the direct note only, never a graph neighborhood. Ordinary knowledge about one entity uses that direct selection. When the user explicitly selects notes through linked, related, backlink/reference, direction, or bounded-hop graph meaning that the existing LinkScope can represent, link_scope is required; retaining that graph meaning only in query is insufficient. Its non-recursive anchor independently selects the one safe note identity. Do not execute traversal.

Tags are explicit-only. Semantic words such as idea, reflection, decision, review, or question never create a tags filter or tag mutation. Emit tags contains a controlled canonical ID only when the user explicitly says tag/etiqueta, and emit add/remove TagChange only when explicitly requested. Never replace the complete tags array and never invent an unknown tag ID.

Use DelegateAction only when the requested operation needs a specialized capability that RetrieveAction or WriteAction cannot express, such as aggregate computation (count, sum, average, grouping or comparison), analysis of an external artifact, or translation. DelegateAction.request preserves that specialized operation and its material constraints. DelegateAction.selection preserves the already interpreted Odyssey candidate set, including any representable link_scope, filters, type, or entity; it may be null only when the request has no safely representable Odyssey knowledge candidate set, as may occur for an external artifact. Do not keyword-route: recording an intention to compare is WriteAction, while asking for the comparison now is DelegateAction. DelegateAction never chooses an application, app_id, router, SQL, execution instruction, or result. Preserve independent action order. Do not create cross-action result bindings or placeholders.

A RetrieveAction exists only when the user asks to retrieve or inspect knowledge. A write target is identity evidence for later existing-entity resolution and must not create an extra RetrieveAction. For writes, put a property mentioned only to identify the target in target.filters when it maps safely to the filter contract; put it in properties only when the user is asking to record/change/remove that property. The same field may appear in target.filters as the old identifying value and properties as a corrected new value. Meaning that cannot safely become a filter stays in target.query.

Every write target query must remain a non-empty human-readable identity query, including when filters also identify an existing target. Do not copy a newly recorded canonical property into target.filters unless its old value is explicitly being used to identify an existing target. Preserve contextual wording that remains part of a fact; do not drop it merely because it also helps identify the target.

Decompose write knowledge semantically: group changes for the same logical target only when their mutation intent is compatible; different intents for the same target produce separate KnowledgeUnits. Split independently meaningful knowledge into one atomic `facts` entry each, preserving their order and references. Use only record, amend, remove, and delete. For an explicit correction, use a remove unit describing the false prior fact plus a separate amend unit with corrected fact(s) and any authorized property change. `properties` contains only canonical type-specific property changes supplied by the write capability contract. Use op=set for record/amend and op=remove with value=null for remove. Do not invent fields. For conversational knowledge that safely maps to a property, emit both the property and its human knowledge fact; properties do not replace retained knowledge. Amend/remove require at least one mutation across properties or facts. Delete uses properties: [] and facts: []. Record normally contains properties and/or facts; both may be empty only for a semantic reference-target unit that supports another KnowledgeUnit in the same WriteAction. Set `destination_type` to null for ordinary writes. Set it only for an explicit request to reclassify the same existing note; it is the resulting canonical type, while target.type constrains the current source note. A migration uses intent=amend and cardinality=one. Do not infer it from prose, represent it as a property change, or use it to resolve identity.

When a fact semantically refers to another KnowledgeUnit, replace that occurrence in the fact with `{{ref:N}}`, where N is the zero-based index in that KnowledgeUnit's own `references` array. Preserve the original human-readable wording in that reference's `mention` field. The marker may occur repeatedly for repeated mentions. Do not emit Markdown `[[wikilinks]]`. Do not create a reference merely because another entity name appears: use a marker only for a semantic relationship that needs a KnowledgeReference. A name used only to identify the write target is not automatically a fact reference. References never authorize an inverse or mirrored write into the referenced unit.

Example: for "La amiga de Marta ahora trabaja en Airbus", use target query "la amiga de Marta", fact "Ahora trabaja en {{ref:0}}.", and reference 0 with mention "Airbus". Do not create a reference to Marta because Marta only identifies the target. A reference-only target unit may have empty facts when another unit points to it.

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

    entity: str | None
    query: str
    type: str | None
    filters: tuple[ContextFilter, ...]
    link_scope: LinkScope | None


@dataclass(frozen=True, slots=True)
class NoteSelector:
    """Represent a non-recursive graph-anchor note selector."""

    entity: str | None
    query: str
    type: str | None
    filters: tuple[ContextFilter, ...]


@dataclass(frozen=True, slots=True)
class LinkScope:
    """Represent requested wikilink traversal intent without executing it."""

    anchor: NoteSelector
    direction: str
    max_depth: int


# Keep the established public name while sharing the same selection value with write targets.
RetrievalPlan = SelectionCriteria


@dataclass(frozen=True, slots=True)
class RetrieveAction:
    """Represent one ordered, non-executing retrieval action."""

    plan: SelectionCriteria
    kind: str = "retrieve"


@dataclass(frozen=True, slots=True)
class KnowledgeReference:
    """Represent one semantic in-plan reference and its preserved fact wording."""

    target_index: int
    role: str
    mention: str


@dataclass(frozen=True, slots=True)
class PropertyChange:
    """Represent one validated canonical property mutation requested by the user."""

    field: str
    op: str
    value: Any


@dataclass(frozen=True, slots=True)
class TagChange:
    """Represent one explicit controlled-tag item mutation requested by the user."""

    op: str
    value: str


@dataclass(frozen=True, slots=True)
class KnowledgeUnit:
    """Represent one semantic write target and the requested knowledge mutation."""

    target: SelectionCriteria
    intent: str
    properties: tuple[PropertyChange, ...]
    tag_changes: tuple[TagChange, ...]
    facts: tuple[str, ...]
    references: tuple[KnowledgeReference, ...]
    cardinality: str = "one"
    destination_type: str | None = None


@dataclass(frozen=True, slots=True)
class WriteAction:
    """Represent semantic write preparation without physical persistence decisions."""

    units: tuple[KnowledgeUnit, ...]
    kind: str = "write"


@dataclass(frozen=True, slots=True)
class DelegateAction:
    """Represent non-executing work that requires a later specialized capability."""

    request: str
    selection: SelectionCriteria | None
    kind: str = "delegate"


RequestAction = RetrieveAction | WriteAction | DelegateAction


@dataclass(frozen=True, slots=True)
class RequestPlan:
    """Contain an ordered, validated interpretation of one user request."""

    actions: tuple[RequestAction, ...]
    limitations: tuple[str, ...]


def plan_fact_ordinals(plan: RequestPlan) -> tuple[tuple[int, ...], ...]:
    """Return write-unit fact ordinals flattened in validated request-plan order.

    Retrieval and delegated actions contribute no ordinals. The result is ordered by write action
    and then unit, and remains unchanged by later execution success or failure.
    """
    if not isinstance(plan, RequestPlan):
        raise TypeError("plan must be a RequestPlan")
    next_ordinal = 0
    result: list[tuple[int, ...]] = []
    for action in plan.actions:
        if not isinstance(action, WriteAction):
            continue
        for unit in action.units:
            result.append(tuple(range(next_ordinal, next_ordinal + len(unit.facts))))
            next_ordinal += len(unit.facts)
    return tuple(result)


def render_request_planner_prompt(
    schema: Mapping[str, Any], current_context: Mapping[str, str]
) -> str:
    """Render the production planner prompt from active schema and runtime context.

    Args:
        schema: Parsed canonical Odyssey schema used to derive selection and write capabilities.
        current_context: Current date, time, and timezone supplied by the caller.

    Returns:
        Planner instructions containing dynamic retrieval/selection and writable-property contracts.

    Raises:
        RequestPlanningError: If the runtime context is incomplete or malformed.
        ValueError: If the canonical schema cannot be projected safely into planner capabilities.
        RuntimeError: If an internal capability placeholder is missing or duplicated.
    """
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
    """Build the strict Structured Outputs schema for the active canonical schema.

    Args:
        schema: Parsed canonical Odyssey schema that defines types, filters, and writable properties.

    Returns:
        Closed JSON Schema accepted by the Responses API for one Phase 15.1 RequestPlan.

    Raises:
        RequestPlanningError: If the active capabilities cannot form a usable structured contract.
        ValueError: If the canonical schema declares malformed or unsupported planner semantics.
    """
    retrieval_capabilities = build_planner_capabilities(schema)
    write_capabilities = build_write_capabilities(schema)
    selection_schema = _selection_json_schema(retrieval_capabilities)
    property_changes_schema = _property_changes_json_schema(write_capabilities)
    return {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "minItems": 1,
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
                                            "cardinality": {
                                                "type": "string",
                                                "enum": ["one", "all_matching"],
                                            },
                                            "destination_type": {
                                                "anyOf": [
                                                    {"type": "null"},
                                                    {
                                                        "type": "string",
                                                        "enum": sorted(write_capabilities["types"]),
                                                    },
                                                ]
                                            },
                                            "intent": {
                                                "type": "string",
                                                "enum": list(WRITE_INTENTS),
                                            },
                                            "properties": property_changes_schema,
                                            "tag_changes": _tag_changes_json_schema(
                                                retrieval_capabilities
                                            ),
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
                                                        "mention": {"type": "string"},
                                                    },
                                                    "required": ["target_index", "role", "mention"],
                                                    "additionalProperties": False,
                                                },
                                            },
                                        },
                                        "required": [
                                            "target",
                                            "cardinality",
                                            "destination_type",
                                            "intent",
                                            "properties",
                                            "tag_changes",
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
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["delegate"]},
                                "request": {"type": "string"},
                                "selection": {"anyOf": [{"type": "null"}, selection_schema]},
                            },
                            "required": ["kind", "request", "selection"],
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
    """Validate untrusted model output and return an immutable non-executing plan.

    Args:
        payload: JSON-decoded planner output to validate locally.
        schema: Parsed canonical Odyssey schema used for dynamic type, filter, and property checks.

    Returns:
        A validated RequestPlan that has not performed retrieval, resolution, or persistence.

    Raises:
        RequestPlanningError: If output is malformed, empty, unsafe, or violates the active contract.
        ValueError: If the canonical schema cannot be projected into safe planner capabilities.
    """
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
        """Initialize a planner with an injected client and runtime schema/context.

        Args:
            client: OpenAI-compatible Responses client supplied by composition code.
            schema: Current canonical Odyssey schema.
            current_context: Current date, time, and timezone used during interpretation.

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
            current_context: Current date, time, and timezone used during interpretation.

        Returns:
            A planner backed by the OpenAI Responses API.

        Raises:
            RequestPlanningError: If the API key, OpenAI SDK, or runtime context is unavailable.
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
            request: User request to interpret as one ordered RequestPlan.

        Returns:
            A locally validated RequestPlan that has not been executed.

        Raises:
            RequestPlanningError: If the request, provider call, JSON response, or plan is invalid.
            ValueError: If the active schema cannot be projected into safe planner capabilities.
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


def _selection_json_schema(capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Build the shared query/type/filter selection contract."""
    alternatives = _filter_json_schema_alternatives(capabilities)
    if not alternatives:
        raise RequestPlanningError("Canonical schema exposes no planner filters")
    selector_schema = _note_selector_json_schema(capabilities)
    return {
        "type": "object",
        "properties": {
            "entity": {"type": ["string", "null"]},
            "query": {"type": "string"},
            "type": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "enum": list(capabilities["types"])},
                ]
            },
            "filters": {"type": "array", "items": {"anyOf": alternatives}},
            "link_scope": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "properties": {
                            "anchor": selector_schema,
                            "direction": {"type": "string", "enum": list(_LINK_DIRECTIONS)},
                            "max_depth": {"type": "integer", "minimum": 1},
                        },
                        "required": ["anchor", "direction", "max_depth"],
                        "additionalProperties": False,
                    },
                ]
            },
        },
        "required": ["entity", "query", "type", "filters", "link_scope"],
        "additionalProperties": False,
    }


def _note_selector_json_schema(capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Build the non-recursive graph-anchor selector Structured Outputs shape."""
    alternatives = _filter_json_schema_alternatives(capabilities)
    return {
        "type": "object",
        "properties": {
            "entity": {"type": ["string", "null"]},
            "query": {"type": "string"},
            "type": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "enum": list(capabilities["types"])},
                ]
            },
            "filters": {"type": "array", "items": {"anyOf": alternatives}},
        },
        "required": ["entity", "query", "type", "filters"],
        "additionalProperties": False,
    }


def _tag_changes_json_schema(capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Build the controlled item-level tag mutation Structured Outputs shape."""
    tag_values = capabilities["filters"].get("tags", {}).get("controlled_values", [])
    if not tag_values:
        raise RequestPlanningError("Canonical schema exposes no controlled tags")
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": list(_TAG_CHANGE_OPS)},
                "value": {"type": "string", "enum": tag_values},
            },
            "required": ["op", "value"],
            "additionalProperties": False,
        },
    }


def _filter_json_schema_alternatives(capabilities: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build strict dynamic filter alternatives shared by retrieval and write selection."""
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
                        "value": {"type": "array", "items": scalar} if operator == "in" else scalar,
                    },
                    "required": ["field", "op", "value"],
                    "additionalProperties": False,
                }
            )
    return alternatives


def _property_changes_json_schema(write_capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Build dynamic strict property-change alternatives from type-specific properties."""
    alternatives: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for type_definition in write_capabilities["types"].values():
        for field, definition in type_definition["properties"].items():
            definition_key = json.dumps(definition, sort_keys=True, separators=(",", ":"))
            key = (field, definition_key)
            if key in seen:
                continue
            seen.add(key)
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
    """Map one supported property definition to its basic strict JSON value shape."""
    value_type = definition["value_type"]
    if value_type == "integer":
        return {"type": "integer"}
    if value_type == "array[string]":
        return {"type": "array", "items": {"type": "string"}}
    if value_type in {"string", "date"}:
        return {"type": "string"}
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
        return _validate_write_action(action, schema, retrieval_capabilities, write_capabilities)
    if action.get("kind") == "delegate":
        return _validate_delegate_action(action, schema, retrieval_capabilities)
    if action.get("kind") != "retrieve" or set(action) != {"kind", "plan"}:
        raise RequestPlanningError("RequestPlan action kind is invalid")
    plan = _validate_selection(
        action["plan"], schema, retrieval_capabilities, label="RetrievalPlan"
    )
    return RetrieveAction(plan=plan)


def _validate_delegate_action(
    action: Mapping[str, Any], schema: Mapping[str, Any], capabilities: Mapping[str, Any]
) -> DelegateAction:
    """Validate generic delegated work without selecting or executing an application."""
    if set(action) != {"kind", "request", "selection"}:
        raise RequestPlanningError("DelegateAction fields are invalid")
    request, raw_selection = action["request"], action["selection"]
    if not isinstance(request, str) or not request.strip():
        raise RequestPlanningError("DelegateAction request must be non-empty")
    selection = (
        None
        if raw_selection is None
        else _validate_selection(raw_selection, schema, capabilities, label="DelegateAction selection")
    )
    return DelegateAction(request=request.strip(), selection=selection)


def _validate_selection(
    raw: Any,
    schema: Mapping[str, Any],
    capabilities: Mapping[str, Any],
    *,
    label: str,
) -> SelectionCriteria:
    """Validate the shared query/type/filters selection contract."""
    required = {"entity", "query", "type", "filters", "link_scope"}
    legacy_required = {"query", "type", "filters"}
    if not isinstance(raw, dict) or (set(raw) != required and set(raw) != legacy_required):
        raise RequestPlanningError(f"{label} fields are invalid")
    entity, query, note_type, raw_filters = (
        raw.get("entity"),
        raw["query"],
        raw["type"],
        raw["filters"],
    )
    if entity is not None and (not isinstance(entity, str) or not entity.strip()):
        raise RequestPlanningError(f"{label} entity must be null or non-empty")
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
    link_scope = _validate_link_scope(raw.get("link_scope"), schema, capabilities, label=label)
    return SelectionCriteria(
        entity=entity.strip() if isinstance(entity, str) else None,
        query=query.strip(),
        type=note_type,
        filters=tuple(
            ContextFilter(item["field"], item["op"], item["value"]) for item in raw_filters
        ),
        link_scope=link_scope,
    )


def _validate_note_selector(
    raw: Any, schema: Mapping[str, Any], capabilities: Mapping[str, Any], *, label: str
) -> NoteSelector:
    """Validate a graph anchor without permitting recursive link scopes."""
    required = {"entity", "query", "type", "filters"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise RequestPlanningError(f"{label} fields are invalid")
    entity, query, note_type, raw_filters = (
        raw["entity"],
        raw["query"],
        raw["type"],
        raw["filters"],
    )
    if entity is not None and (not isinstance(entity, str) or not entity.strip()):
        raise RequestPlanningError(f"{label} entity must be null or non-empty")
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
    return NoteSelector(
        entity=entity.strip() if isinstance(entity, str) else None,
        query=query.strip(),
        type=note_type,
        filters=tuple(
            ContextFilter(item["field"], item["op"], item["value"]) for item in raw_filters
        ),
    )


def _validate_link_scope(
    raw: Any, schema: Mapping[str, Any], capabilities: Mapping[str, Any], *, label: str
) -> LinkScope | None:
    """Validate optional non-executing wikilink traversal intent."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"anchor", "direction", "max_depth"}:
        raise RequestPlanningError(f"{label} link_scope is invalid")
    direction, max_depth = raw["direction"], raw["max_depth"]
    if direction not in _LINK_DIRECTIONS:
        raise RequestPlanningError(f"{label} link_scope direction is invalid")
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth < 1:
        raise RequestPlanningError(f"{label} link_scope max_depth is invalid")
    return LinkScope(
        anchor=_validate_note_selector(
            raw["anchor"], schema, capabilities, label=f"{label} anchor"
        ),
        direction=direction,
        max_depth=max_depth,
    )


def _validate_write_action(
    action: Mapping[str, Any],
    schema: Mapping[str, Any],
    retrieval_capabilities: Mapping[str, Any],
    write_capabilities: Mapping[str, Any],
) -> WriteAction:
    """Validate one semantic write action without resolving identity or persisting data."""
    raw_units = action.get("units")
    if set(action) != {"kind", "units"} or not isinstance(raw_units, list) or not raw_units:
        raise RequestPlanningError("WriteAction must contain non-empty units")
    units = tuple(
        _validate_knowledge_unit(raw, schema, retrieval_capabilities, write_capabilities)
        for raw in raw_units
    )
    for index, unit in enumerate(units):
        for reference in unit.references:
            if reference.target_index >= len(units) or reference.target_index == index:
                raise RequestPlanningError("KnowledgeUnit reference target is invalid")
    bulk_indexes = {index for index, unit in enumerate(units) if unit.cardinality == "all_matching"}
    for _index, unit in enumerate(units):
        if unit.cardinality == "all_matching" and unit.references:
            raise RequestPlanningError("all_matching KnowledgeUnit cannot contain references")
        if any(reference.target_index in bulk_indexes for reference in unit.references):
            raise RequestPlanningError("KnowledgeReference cannot target an all_matching unit")
    referenced_targets = {reference.target_index for unit in units for reference in unit.references}
    for index, unit in enumerate(units):
        has_payload = bool(unit.properties or unit.tag_changes or unit.facts or unit.destination_type)
        if unit.intent in {"amend", "remove"} and not has_payload:
            raise RequestPlanningError(
                "KnowledgeUnit amend and remove intents require mutation payload"
            )
        if unit.intent == "record" and not has_payload and index not in referenced_targets:
            raise RequestPlanningError(
                "KnowledgeUnit record intent requires mutation payload unless referenced"
            )
    return WriteAction(units=units)


def _validate_knowledge_unit(
    unit: Any,
    schema: Mapping[str, Any],
    retrieval_capabilities: Mapping[str, Any],
    write_capabilities: Mapping[str, Any],
) -> KnowledgeUnit:
    """Validate one write target, mutation payload, and local reference set."""
    required = {
        "target",
        "cardinality",
        "intent",
        "properties",
        "tag_changes",
        "facts",
        "references",
        "destination_type",
    }
    legacy_with_cardinality = required - {"destination_type"}
    legacy_required = required - {"cardinality", "destination_type"}
    legacy_without_tags = legacy_required - {"tag_changes"}
    if not isinstance(unit, dict) or (
        set(unit) != required
        and set(unit) != legacy_with_cardinality
        and set(unit) != legacy_required
        and set(unit) != legacy_without_tags
    ):
        raise RequestPlanningError("KnowledgeUnit fields are invalid")
    target = _validate_selection(
        unit["target"], schema, retrieval_capabilities, label="KnowledgeUnit target"
    )
    cardinality = unit.get("cardinality", "one")
    if cardinality not in {"one", "all_matching"}:
        raise RequestPlanningError("KnowledgeUnit cardinality is invalid")
    if cardinality == "all_matching" and target.entity is not None:
        raise RequestPlanningError("all_matching KnowledgeUnit target.entity must be null")
    intent = unit["intent"]
    if intent not in WRITE_INTENTS:
        raise RequestPlanningError("KnowledgeUnit intent is invalid")

    destination_type = unit.get("destination_type")
    if destination_type is not None and destination_type not in write_capabilities["types"]:
        raise RequestPlanningError("KnowledgeUnit destination_type is invalid")
    if destination_type is not None and (cardinality != "one" or intent != "amend"):
        raise RequestPlanningError("Type migration requires intent=amend and cardinality=one")

    raw_properties = unit["properties"]
    if not isinstance(raw_properties, list):
        raise RequestPlanningError("KnowledgeUnit properties must be a list")
    properties = _validate_property_changes(
        raw_properties, destination_type or target.type, intent, write_capabilities
    )

    raw_tag_changes = unit.get("tag_changes", [])
    tag_changes = _validate_tag_changes(raw_tag_changes, intent, retrieval_capabilities)

    raw_facts = unit["facts"]
    if (
        not isinstance(raw_facts, list)
        or len(raw_facts) != len(set(raw_facts))
        or not all(isinstance(fact, str) and fact.strip() for fact in raw_facts)
    ):
        raise RequestPlanningError("KnowledgeUnit facts must be unique non-empty strings")
    if any(
        "\n" in fact or "\r" in fact or "<!-- odyssey:fact" in fact for fact in raw_facts
    ):
        raise RequestPlanningError(
            "KnowledgeUnit facts must be single-line and must not contain Odyssey fact markers"
        )
    if intent == "delete" and (raw_properties or raw_tag_changes or raw_facts):
        raise RequestPlanningError(
            "KnowledgeUnit delete intent requires empty properties, tag_changes, and facts"
        )

    raw_references = unit["references"]
    if not isinstance(raw_references, list):
        raise RequestPlanningError("KnowledgeUnit references must be a list")
    references: list[KnowledgeReference] = []
    for reference in raw_references:
        if (
            not isinstance(reference, dict)
            or set(reference) != {"target_index", "role", "mention"}
            or not isinstance(reference["target_index"], int)
            or isinstance(reference["target_index"], bool)
            or reference["target_index"] < 0
            or not isinstance(reference["role"], str)
            or not reference["role"].strip()
            or not isinstance(reference["mention"], str)
            or not reference["mention"].strip()
            or "[[" in reference["mention"]
            or "]]" in reference["mention"]
        ):
            raise RequestPlanningError("KnowledgeUnit reference is invalid")
        references.append(
            KnowledgeReference(
                target_index=reference["target_index"],
                role=reference["role"].strip(),
                mention=reference["mention"].strip(),
            )
        )
    marker_indexes = _validate_fact_reference_markers(raw_facts, len(references))
    for reference_index in range(len(references)):
        if reference_index not in marker_indexes:
            raise RequestPlanningError("KnowledgeReference has no fact occurrence marker")
    return KnowledgeUnit(
        target=target,
        intent=intent,
        properties=properties,
        tag_changes=tag_changes,
        facts=tuple(fact.strip() for fact in raw_facts),
        references=tuple(references),
        cardinality=cardinality,
        destination_type=destination_type,
    )


def _validate_fact_reference_markers(facts: Sequence[Any], reference_count: int) -> set[int]:
    """Validate internal reference markers and return their local reference indexes."""
    indexes: set[int] = set()
    for fact in facts:
        if "[[" in fact or "]]" in fact:
            raise RequestPlanningError("Planner facts must not contain Markdown wikilinks")
        cursor = 0
        while True:
            start = fact.find("{{ref", cursor)
            if start < 0:
                break
            match = _REFERENCE_MARKER_PATTERN.match(fact, start)
            if match is None:
                raise RequestPlanningError("KnowledgeUnit fact reference marker is malformed")
            reference_index = int(match.group(1))
            if reference_index >= reference_count:
                raise RequestPlanningError("KnowledgeUnit fact reference marker is out of range")
            indexes.add(reference_index)
            cursor = match.end()
    return indexes


def _validate_property_changes(
    raw_properties: Sequence[Any],
    note_type: str | None,
    intent: str,
    write_capabilities: Mapping[str, Any],
) -> tuple[PropertyChange, ...]:
    """Validate property changes against the selected type and shared Core value rules."""
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
            raise RequestPlanningError(
                "KnowledgeUnit property field is invalid for its target type"
            )
        if field in seen:
            raise RequestPlanningError("KnowledgeUnit property fields must be unique")
        seen.add(field)
        if op not in _PROPERTY_OPS or op not in allowed_ops:
            raise RequestPlanningError(
                "KnowledgeUnit property operation is incompatible with intent"
            )
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


def _validate_tag_changes(
    raw_tag_changes: Any, intent: str, capabilities: Mapping[str, Any]
) -> tuple[TagChange, ...]:
    """Validate explicit controlled-tag item mutations for one knowledge unit."""
    if not isinstance(raw_tag_changes, list):
        raise RequestPlanningError("KnowledgeUnit tag_changes must be a list")
    allowed_ops = {
        "record": {"add", "remove"},
        "amend": {"add", "remove"},
        "remove": {"remove"},
        "delete": set(),
    }[intent]
    controlled_values = set(capabilities["filters"].get("tags", {}).get("controlled_values", []))
    if not controlled_values:
        raise RequestPlanningError("Canonical schema exposes no controlled tags")
    changes: list[TagChange] = []
    seen: set[str] = set()
    for raw in raw_tag_changes:
        if not isinstance(raw, dict) or set(raw) != {"op", "value"}:
            raise RequestPlanningError("Each tag change must contain op and value")
        op, value = raw["op"], raw["value"]
        if op not in _TAG_CHANGE_OPS or op not in allowed_ops:
            raise RequestPlanningError("KnowledgeUnit tag operation is incompatible with intent")
        if not isinstance(value, str) or value not in controlled_values:
            raise RequestPlanningError("KnowledgeUnit tag value is not a controlled tag")
        if value in seen:
            raise RequestPlanningError("KnowledgeUnit tag changes must not duplicate or conflict")
        seen.add(value)
        changes.append(TagChange(op=op, value=value))
    return tuple(changes)


def _validate_planner_filters(
    filters: Sequence[Any], note_type: str | None, capabilities: Mapping[str, Any]
) -> None:
    """Restrict selection filters to dynamic capabilities and compatible type scopes."""
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
