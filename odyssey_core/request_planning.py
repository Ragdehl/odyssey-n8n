"""Fail-closed interpretation of user requests into safe Odyssey RequestPlans."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from functools import wraps
from time import perf_counter
from typing import Any, Protocol

from odyssey_core.context import ContextFilter, validate_context_filters
from odyssey_core.notes.validation import NoteValidationError, validate_field_value
from odyssey_core.observability import (
    OperationalOutcome,
    OperationalSpan,
    SpanRecorder,
    normalize_provider_usage,
)
from odyssey_core.planner_capabilities import (
    LIMITATIONS,
    build_planner_capabilities,
    build_write_capabilities,
)

PLANNER_MODEL = "gpt-5.6-sol"
PLANNER_REASONING_EFFORT = "low"
PLANNER_MAX_OUTPUT_TOKENS = 4096
PLANNER_AUTOMATIC_RETRIES = 0
PLANNER_CLARIFICATION_CODES = ("UNRECOGNIZED_REQUEST",)
WRITE_INTENTS = ("record", "amend", "remove", "delete")
_PROPERTY_OPS = ("set", "remove")
_TAG_CHANGE_OPS = ("add", "remove")
_LINK_DIRECTIONS = ("incoming", "outgoing", "both")
PRESENTATION_INTENTS = ("answer", "note_set", "answer_and_note_set")
SELF_TARGET = "self"
_CURRENT_CONTEXT_KEYS = frozenset({"date", "time", "timezone"})
_RETRIEVAL_CAPABILITY_PLACEHOLDER = "{{RETRIEVAL_CAPABILITIES}}"
_WRITE_CAPABILITY_PLACEHOLDER = "{{WRITE_CAPABILITIES}}"
_REFERENCE_MARKER_PATTERN = re.compile(r"\{\{ref:(\d+)\}\}")
_STABLE_ID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
_PROMPT_TEMPLATE = """You convert one user request into one strict JSON PlannerResult. Use the supplied current date, time, and timezone.

Bounded recent conversation evidence may resolve a referent or conversational continuity, but it records only what was said and is never current personal truth. Use it only to identify the subject or interaction the user means. Do not turn a prior user statement or assistant response into a current-fact filter, retrieval constraint, or asserted fact. Canonical notes remain the authority for current facts. A follow-up write may reuse an explicit fact from earlier user text only when the ordinary write contract can represent it; assistant text never supplies a fact or mutation target. If the recent evidence still leaves the referent or requested mutation ambiguous, return CLARIFY rather than guessing.

Return outcome PLAN with a RequestPlan when the request contains safely interpretable Odyssey retrieval, knowledge mutation, or specialized-capability intent. Return outcome CLARIFY with clarification_code UNRECOGNIZED_REQUEST when the input has no safely interpretable or actionable Odyssey intent, including meaningless fragments such as "Bdbd", "asdfgh", or "???". CLARIFY must contain no RequestPlan and never becomes a DelegateAction. Do not invent an action merely to satisfy the schema.

Every PLAN has presentation_intent. Use `answer` by default. Use `note_set` only for one direct RetrieveAction when the user explicitly asks to see a collection/list/set of matching notes; it never adds retrieval authority or turns a write/delegation into retrieval. Use `answer_and_note_set` only for one direct RetrieveAction when the user explicitly asks both for an answer/synthesis and the matching notes. For writes, delegation, multiple independent actions, clarification, any link_scope, relational_reference, or semantic_set, use `answer`; do not discard or weaken meaning merely to produce a note set.

Interpret each requested action in this order. FIRST identify the Odyssey knowledge candidate set and preserve every safely representable SelectionCriteria field: entity, query, type, filters, link_scope, self_target, and relational_reference. For a direct first-person target, set self_target to "self"; this means only the authenticated human's canonical person note, not a name, alias, provider identity, or person mentioned in a relationship. THEN choose what operation the user wants on that set: ordinary retrieval uses RetrieveAction, ordinary knowledge mutation uses WriteAction, and work requiring a specialized capability uses DelegateAction. The action kind changes what happens to the candidate set; it never weakens or erases that set.
Set relational_reference only when the selected identity is defined by a relationship or complete finite participant set in an existing canonical source, such as "mi hija", "sus hijos", or "todos los que estaban ayer". Preserve the user's reference wording, source_kind=self with source_query=null only when the source is the authenticated human, otherwise source_kind=existing with bounded source_query wording identifying an existing source, and members=one or complete_set. This is language-independent wording, not a relation type or a stable identity. The source may be identified by recent conversation, but current canonical Markdown alone establishes membership. Set entity=null, self_target=null, and link_scope=null for the relational selection; direct self remains self_target. Never enumerate members, invent a source, or assert IDs, filenames, paths, or relationship types. When relational evidence is missing or ambiguous, Core clarifies; relational wording never authorizes CREATE. For a complete_set shared-fact write, emit one record KnowledgeUnit with cardinality=one, the asserted fact, and no fabricated member units or references; relational_reference.members carries the complete-set meaning, while cardinality=one denotes the one natural source write. Core expands only a complete current set into the existing safe source-write path.
For a finite semantic group drawn from several current facts on one source, set semantic_set only on RetrieveAction. Use anchor_kind=self with anchor_query=null for the authenticated person, or anchor_kind=existing with a bounded existing-source query. Preserve only the group wording, explicit qualifiers, and asks_exhaustive. Set entity=null, self_target=null, link_scope=null, filters=[], and relational_reference=null. Never include stable IDs, paths, fact locators, candidate lists, members, links, mutation authority, or inferred relationship types. Core alone finds, bounds, and validates canonical evidence. Do not use semantic_set for writes or delegate actions.
Use self_target only when the direct selected entity is the current human, as in "¿Dónde trabajo?" or "Apunta que vivo en Toulouse". Do not set it merely because a possessive occurs: "Mi hermano vive en Madrid" targets the brother, and "Mi coche es un Scénic" retains its ordinary target semantics. Never emit a user ID, person note ID, email, provider subject, filename, or other identity value in planner output.
For every KnowledgeUnit, set `cardinality` to `one` for one logical identity, including when
resolution may later be ambiguous, or to `all_matching` only when the user means the complete set
represented by the selection. Do not infer `all_matching` from plural wording alone, from several
semantic candidates, or from an explicit list of independent names. Preserve an all-matching intent
even when current execution cannot authorize its selector. Cardinality belongs only to KnowledgeUnit;
do not add it to SelectionCriteria. An all-matching unit has no singular entity identity.

Hard filters can permanently remove valid notes: apply a deterministic restriction only when the request maps explicitly and safely to this capability contract. Otherwise preserve the meaning in `query`. Words such as before, earlier, previously, beforehand, antes, anteriormente, previamente, and ya había pensado describe knowledge semantics, not note lifecycle, unless the user explicitly refers to when a note, entry, or item was created, written, added, updated, modified, or recorded. Only that explicit lifecycle timing authorizes created_at or updated_at filters. Multiple RetrieveActions are only for genuinely independent candidate-set branches; ordinary semantic OR stays one query.

RetrieveAction.plan and every KnowledgeUnit.target use the same selection shape. A non-null DelegateAction.selection obeys those same SelectionCriteria rules. Entity is only a safely explicit primary-name/alias candidate from the user's wording; it is never an Odyssey ID and does not assert repository existence. Do not turn every noun phrase or mentioned name into entity: contextual descriptions such as "la tienda de la esquina" and "la amiga de Marta" keep entity=null. A null link_scope means the direct note only, never a graph neighborhood. Ordinary knowledge about one entity uses that direct selection. When the user explicitly selects notes through linked, related, backlink/reference, direction, or bounded-hop graph meaning that the existing LinkScope can represent, link_scope is required; retaining that graph meaning only in query is insufficient. Its non-recursive anchor independently selects the one safe note identity. Do not execute traversal.


Use DelegateAction only when the requested operation needs a specialized capability that RetrieveAction or WriteAction cannot express, such as aggregate computation (count, sum, average, grouping or comparison), analysis of an external artifact, or translation. DelegateAction.request preserves that specialized operation and its material constraints. DelegateAction.selection preserves the already interpreted Odyssey candidate set, including any representable link_scope, filters, type, or entity; it may be null only when the request has no safely representable Odyssey knowledge candidate set, as may occur for an external artifact. Do not keyword-route: recording an intention to compare is WriteAction, while asking for the comparison now is DelegateAction. DelegateAction never chooses an application, app_id, router, SQL, execution instruction, or result. Preserve independent action order. Do not create cross-action result bindings or placeholders.

A RetrieveAction exists only when the user asks to retrieve or inspect knowledge. A write target is identity evidence for later existing-entity resolution and must not create an extra RetrieveAction. For writes, put a property mentioned only to identify the target in target.filters when it maps safely to the filter contract; put it in properties only when the user is asking to record/change/remove that property. The same field may appear in target.filters as the old identifying value and properties as a corrected new value. Meaning that cannot safely become a filter stays in target.query.

Every write target query must remain a non-empty human-readable identity query, including when filters also identify an existing target. Do not copy a newly recorded canonical property into target.filters unless its old value is explicitly being used to identify an existing target. Preserve contextual wording that remains part of a fact; do not drop it merely because it also helps identify the target.

Tags are generic free-form metadata. Emit a tag filter only when the user explicitly asks to search by a tag, using `tags` with `contains`; emit `tag_changes` only when the user explicitly asks to add or remove a tag. Never infer tags from semantic words such as idea, decision, reflection, or review, and never require a registry or controlled vocabulary.

Decompose write knowledge semantically: group changes for the same logical target only when their mutation intent is compatible; different intents for the same target produce separate KnowledgeUnits. Split independently meaningful knowledge into one atomic `facts` entry each, preserving their order and references. Atomicity is semantic, not punctuation-based: keep sentences or clauses together when they form one coherent explanation, reflection, or decision with dependent reasons whose meaning would be lost by splitting; split when each result remains independently meaningful durable knowledge, even if independent facts share one sentence. For example, separate "Marta vive en Lyon y trabaja en Thales" into two facts, but keep "Quiero mudarme a Lyon porque tendríamos más espacio y estaríamos cerca de nuestros amigos" as one coherent decision/reason fact. Use only record, amend, remove, and delete. For an explicit correction, use a remove unit describing the false prior fact plus a separate amend unit with corrected fact(s) and any authorized property change. `properties` contains only canonical type-specific property changes supplied by the write capability contract. Use op=set for record/amend and op=remove with value=null for remove. Do not invent fields. For conversational knowledge that safely maps to a property, emit both the property and its human knowledge fact; properties do not replace retained knowledge. Amend/remove require at least one mutation across properties or facts. Delete uses properties: [] and facts: []. Record normally contains properties and/or facts; both may be empty only for a semantic reference-target unit that supports another KnowledgeUnit in the same WriteAction. Set `destination_type` to null for ordinary writes. Set it only for an explicit request to reclassify the same existing note; it is the resulting canonical type, while target.type constrains the current source note. A migration uses intent=amend and cardinality=one. Do not infer it from prose, represent it as a property change, or use it to resolve identity.

When a fact semantically refers to another KnowledgeUnit, replace that occurrence in the fact with `{{ref:N}}`, where N is the zero-based index in that KnowledgeUnit's own `references` array. Preserve the original human-readable wording in that reference's `mention` field. The marker may occur repeatedly for repeated mentions. Do not emit Markdown `[[wikilinks]]`. Do not create a reference merely because another entity name appears: use a marker only for a semantic relationship that needs a KnowledgeReference. A name used only to identify the write target is not automatically a fact reference. References never authorize an inverse or mirrored write into the referenced unit.

Example: for "La amiga de Marta ahora trabaja en Airbus", use target query "la amiga de Marta" with relational_reference preserving that wording, source_kind=existing, source_query="Marta", and members=one. Use fact "Ahora trabaja en {{ref:0}}." and reference 0 with mention "Airbus". Do not create a reference to Marta because Marta only identifies the relational source. The ordinary named-target example "Marta trabaja en Airbus" uses no relational_reference and retains its explicit Airbus KnowledgeReference. A reference-only target unit may have empty facts when another unit points to it.

Do not infer repository existence, resolve identity, choose CREATE versus UPDATE, generate IDs, paths, Markdown, SQL, or persistence instructions, or execute retrieval, persistence, or entity resolution. Use limitation codes only with their defined meanings. Return strict structured JSON.

Planner retrieval/selection capabilities (derived dynamically from the canonical schema):

{{RETRIEVAL_CAPABILITIES}}

Planner writable type/property capabilities (derived dynamically from the same canonical schema):

{{WRITE_CAPABILITIES}}"""


class PlannerValidationStage(StrEnum):
    """Allowlisted local boundary that rejected decoded planner output."""

    PLANNER_RESULT_ENVELOPE = "PLANNER_RESULT_ENVELOPE"
    REQUEST_PLAN = "REQUEST_PLAN"
    RETRIEVE_ACTION = "RETRIEVE_ACTION"
    WRITE_ACTION = "WRITE_ACTION"
    KNOWLEDGE_UNIT = "KNOWLEDGE_UNIT"
    DELEGATE_ACTION = "DELEGATE_ACTION"
    SELECTION = "SELECTION"
    LINK_SCOPE = "LINK_SCOPE"
    NOTE_SELECTOR = "NOTE_SELECTOR"
    FILTER = "FILTER"
    PROPERTY_CHANGE = "PROPERTY_CHANGE"
    TAG_CHANGE = "TAG_CHANGE"
    REFERENCE = "REFERENCE"


class PlannerValidationCode(StrEnum):
    """Small stable vocabulary for bounded local validation diagnostics."""

    INVALID_FIELDS = "INVALID_FIELDS"
    EMPTY_QUERY = "EMPTY_QUERY"
    INVALID_TYPE = "INVALID_TYPE"
    INVALID_FILTER = "INVALID_FILTER"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    INVALID_CARDINALITY = "INVALID_CARDINALITY"
    INVALID_MUTATION = "INVALID_MUTATION"
    INVALID_LIMITATIONS = "INVALID_LIMITATIONS"
    EMPTY_REQUEST = "EMPTY_REQUEST"


class RequestPlanningError(ValueError):
    """Indicate malformed, unsupported, or unsafe RequestPlan model output.

    ``validation_stage`` and ``validation_code`` are bounded, optional metadata.  The
    exception message remains compatible with existing callers and is never used as telemetry.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: PlannerValidationStage | None = None,
        code: PlannerValidationCode | None = None,
    ) -> None:
        super().__init__(message)
        self.validation_stage = stage
        self.validation_code = code


def _validation_boundary(
    stage: PlannerValidationStage,
    code: PlannerValidationCode = PlannerValidationCode.INVALID_FIELDS,
):
    """Attach stable boundary metadata without inspecting exception text or payloads."""

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except RequestPlanningError as error:
                if error.validation_stage is not None:
                    raise
                raise RequestPlanningError(str(error), stage=stage, code=code) from error

        return wrapped

    return decorate


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
    self_target: str | None = None
    relational_reference: RelationalReference | None = None
    semantic_set: SemanticSetIntent | None = None


@dataclass(frozen=True, slots=True)
class RelationalReference:
    """Preserve one source-relative identity request without asserting canonical members."""

    reference: str
    source_kind: str
    source_query: str | None
    members: str


@dataclass(frozen=True, slots=True)
class SemanticSetIntent:
    """Preserve a bounded group request without asserting members or canonical identity."""

    anchor_kind: str
    anchor_query: str | None
    group_query: str
    explicit_qualifiers: str
    asks_exhaustive: bool


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
    """Explicit generic free-form tag mutation requested by the user."""

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
    presentation_intent: str = "answer"


@dataclass(frozen=True, slots=True)
class PlannerClarification:
    """Represent a closed non-executing request for user clarification."""

    code: str


PlannerResult = RequestPlan | PlannerClarification


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
    schema: Mapping[str, Any],
    current_context: Mapping[str, str],
    conversation_context: Sequence[Mapping[str, str]] = (),
    *,
    size_components: dict[str, int] | None = None,
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
    retrieval_json = json.dumps(retrieval, ensure_ascii=False, separators=(",", ":"))
    writable_json = json.dumps(writable, ensure_ascii=False, separators=(",", ":"))
    rendered = _PROMPT_TEMPLATE.replace(
        _RETRIEVAL_CAPABILITY_PLACEHOLDER,
        retrieval_json,
    )
    prompt = rendered.replace(
        _WRITE_CAPABILITY_PLACEHOLDER,
        writable_json,
    )
    context_bytes = 0
    if conversation_context:
        bounded = [
            {"role": item.get("role"), "text": item.get("text")} for item in conversation_context
        ]
        context_section = (
            "\n\nBounded active-conversation evidence (what was said, not current truth):\n"
            + json.dumps(bounded, ensure_ascii=False, separators=(",", ":"))
        )
        prompt += context_section
        context_bytes = len(context_section.encode("utf-8"))
    if size_components is not None:
        retrieval_bytes = len(retrieval_json.encode("utf-8"))
        writable_bytes = len(writable_json.encode("utf-8"))
        size_components.update(
            fixed_instructions_bytes=(
                len(prompt.encode("utf-8")) - retrieval_bytes - writable_bytes - context_bytes
            ),
            retrieval_capabilities_bytes=retrieval_bytes,
            write_capabilities_bytes=writable_bytes,
            recent_context_bytes=context_bytes,
        )
    return prompt


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
                                            "tag_changes": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "op": {
                                                            "type": "string",
                                                            "enum": ["add", "remove"],
                                                        },
                                                        "value": {"type": "string"},
                                                    },
                                                    "required": ["op", "value"],
                                                    "additionalProperties": False,
                                                },
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
            "presentation_intent": {"type": "string", "enum": list(PRESENTATION_INTENTS)},
        },
        "required": ["actions", "limitations", "presentation_intent"],
        "additionalProperties": False,
    }


def planner_result_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Build the closed production result envelope around a plan or clarification.

    Args:
        schema: Parsed canonical Odyssey schema used by the nested RequestPlan contract.

    Returns:
        A strict object schema whose PLAN/CLARIFY alternatives mirror local envelope invariants.
    """
    plan_schema = request_plan_json_schema(schema)
    required = ["outcome", "actions", "limitations", "clarification_code", "presentation_intent"]
    plan_branch = {
        "type": "object",
        "properties": {
            "outcome": {"type": "string", "enum": ["PLAN"]},
            "actions": plan_schema["properties"]["actions"],
            "limitations": plan_schema["properties"]["limitations"],
            "clarification_code": {"type": "null"},
            "presentation_intent": plan_schema["properties"]["presentation_intent"],
        },
        "required": required,
        "additionalProperties": False,
    }
    clarify_branch = {
        "type": "object",
        "properties": {
            "outcome": {"type": "string", "enum": ["CLARIFY"]},
            "actions": {"type": "null"},
            "limitations": {"type": "null"},
            "clarification_code": {
                "type": "string",
                "enum": list(PLANNER_CLARIFICATION_CODES),
            },
            "presentation_intent": {"type": "null"},
        },
        "required": required,
        "additionalProperties": False,
    }
    # Structured Outputs rejects a root-level anyOf; keep the root closed and
    # place the discriminated union beneath the required result property.
    return {
        "type": "object",
        "properties": {"result": {"anyOf": [plan_branch, clarify_branch]}},
        "required": ["result"],
        "additionalProperties": False,
    }


def compact_planner_result_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Build the exact PlannerResult language with shared Structured Outputs definitions.

    The established inline schema remains the production Sol contract. This representation is for
    callers that need the same accepted payload language without repeatedly serializing the
    selection/filter subtree. Local validation remains the semantic authority for either form.

    Args:
        schema: Parsed canonical Odyssey schema used by the existing planner schema generator.

    Returns:
        A closed PlannerResult envelope whose local ``$defs`` share the otherwise identical PLAN
        and CLARIFY substructures.
    """
    inline = planner_result_json_schema(schema)
    plan_branch, clarify_branch = deepcopy(inline["properties"]["result"]["anyOf"])
    actions = plan_branch["properties"]["actions"]
    retrieve_action, write_action, delegate_action = actions["items"]["anyOf"]
    selection = retrieve_action["properties"]["plan"]
    filter_array = selection["properties"]["filters"]
    link_scope = selection["properties"]["link_scope"]["anyOf"][1]
    note_selector = link_scope["properties"]["anchor"]

    note_selector["properties"]["filters"] = {"$ref": "#/$defs/filter_array"}
    link_scope["properties"]["anchor"] = {"$ref": "#/$defs/note_selector"}
    selection["properties"]["filters"] = {"$ref": "#/$defs/filter_array"}
    selection["properties"]["link_scope"] = {
        "anyOf": [{"type": "null"}, {"$ref": "#/$defs/link_scope"}]
    }
    write_action["properties"]["units"]["items"]["properties"]["target"] = {
        "$ref": "#/$defs/selection"
    }
    delegate_action["properties"]["selection"] = {
        "anyOf": [{"type": "null"}, {"$ref": "#/$defs/selection"}]
    }
    retrieve_action["properties"]["plan"] = {"$ref": "#/$defs/selection"}
    actions["items"]["anyOf"] = [
        {"$ref": "#/$defs/retrieve_action"},
        {"$ref": "#/$defs/write_action"},
        {"$ref": "#/$defs/delegate_action"},
    ]
    plan_branch["properties"]["actions"] = {"$ref": "#/$defs/actions"}
    plan_branch["properties"]["limitations"] = {"$ref": "#/$defs/limitations"}

    definitions = {
        "filter_array": filter_array,
        "note_selector": note_selector,
        "link_scope": link_scope,
        "selection": selection,
        "retrieve_action": retrieve_action,
        "write_action": write_action,
        "delegate_action": delegate_action,
        "actions": actions,
        "limitations": inline["properties"]["result"]["anyOf"][0]["properties"]["limitations"],
        "plan_result": plan_branch,
        "clarify_result": clarify_branch,
    }
    return {
        "type": "object",
        "properties": {
            "result": {
                "anyOf": [
                    {"$ref": "#/$defs/plan_result"},
                    {"$ref": "#/$defs/clarify_result"},
                ]
            }
        },
        "required": ["result"],
        "additionalProperties": False,
        "$defs": definitions,
    }


@_validation_boundary(PlannerValidationStage.PLANNER_RESULT_ENVELOPE)
def validate_planner_result(payload: Any, schema: Mapping[str, Any]) -> PlannerResult:
    """Validate the production planner envelope without executing either outcome.

    Args:
        payload: Untrusted decoded provider output.
        schema: Active canonical schema used to validate a nested RequestPlan.

    Returns:
        A validated RequestPlan or a closed non-executing clarification.

    Raises:
        RequestPlanningError: If the discriminator, payload combination, or nested plan is invalid.
    """
    required_fields = {"outcome", "actions", "limitations", "clarification_code"}
    if (
        not isinstance(payload, dict)
        or not required_fields <= set(payload)
        or set(payload) - (required_fields | {"presentation_intent"})
    ):
        raise RequestPlanningError("PlannerResult must contain only its required fields")
    outcome = payload["outcome"]
    if outcome == "PLAN":
        if (
            set(payload) - (required_fields | {"presentation_intent"})
            or payload["clarification_code"] is not None
            or not isinstance(payload["actions"], list)
            or not isinstance(payload["limitations"], list)
        ):
            raise RequestPlanningError("PLAN must contain actions and limitations only")
        return validate_request_plan(
            {
                "actions": payload["actions"],
                "limitations": payload["limitations"],
                "presentation_intent": payload.get("presentation_intent", "answer"),
            },
            schema,
        )
    if outcome == "CLARIFY":
        code = payload["clarification_code"]
        if (
            set(payload) - (required_fields | {"presentation_intent"})
            or payload["actions"] is not None
            or payload["limitations"] is not None
            or code not in PLANNER_CLARIFICATION_CODES
            or payload.get("presentation_intent") is not None
        ):
            raise RequestPlanningError("CLARIFY must contain one supported code and no actions")
        return PlannerClarification(code)
    raise RequestPlanningError("PlannerResult outcome is unsupported")


@_validation_boundary(PlannerValidationStage.REQUEST_PLAN)
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
    if not isinstance(payload, dict) or set(payload) - {
        "actions",
        "limitations",
        "presentation_intent",
    }:
        raise RequestPlanningError("RequestPlan contains unsupported fields")
    raw_actions, limitations = payload.get("actions"), payload.get("limitations")
    presentation_intent = payload.get("presentation_intent", "answer")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise RequestPlanningError("RequestPlan actions must be a non-empty list")
    if (
        not isinstance(limitations, list)
        or len(limitations) != len(set(limitations))
        or not all(isinstance(item, str) and item in LIMITATIONS for item in limitations)
    ):
        raise RequestPlanningError(
            "RequestPlan limitations are invalid",
            stage=PlannerValidationStage.REQUEST_PLAN,
            code=PlannerValidationCode.INVALID_LIMITATIONS,
        )
    actions = tuple(
        _validate_action(action, schema, retrieval_capabilities, write_capabilities)
        for action in raw_actions
    )
    if presentation_intent not in PRESENTATION_INTENTS:
        raise RequestPlanningError("RequestPlan presentation intent is invalid")
    if presentation_intent != "answer" and (
        len(actions) != 1
        or not isinstance(actions[0], RetrieveAction)
        or actions[0].plan.link_scope is not None
        or actions[0].plan.relational_reference is not None
    ):
        raise RequestPlanningError("Note-set presentation requires one direct retrieval")
    return RequestPlan(
        actions=actions, limitations=tuple(limitations), presentation_intent=presentation_intent
    )


class OpenAIRequestPlanner:
    """Plan requests with Sol/low while leaving all execution outside this boundary."""

    def __init__(
        self,
        client: ResponsesClient,
        schema: Mapping[str, Any],
        current_context: Mapping[str, str],
        monotonic: Any = perf_counter,
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
        self._monotonic = monotonic
        self.model = PLANNER_MODEL
        self.reasoning_effort = PLANNER_REASONING_EFFORT
        self.last_usage: dict[str, int] | None = None
        self.last_call = False
        self.last_attempt_count = 0
        self.last_response_id: str | None = None
        self.last_provider_status: str | None = None
        self.last_incomplete_reason: str | None = None
        self.last_output_text_chars: int | None = None
        self.last_output_text_bytes: int | None = None
        self.last_parse_status: str | None = None
        self.last_result_kind: str | None = None
        self.last_result_counts: dict[str, int] | None = None
        self.last_error_category: str | None = None
        self.last_validation_stage: str | None = None
        self.last_validation_code: str | None = None
        self.last_spans: tuple[OperationalSpan, ...] = ()
        self.last_input_sizes: dict[str, int] | None = None

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
        return cls(OpenAI(max_retries=PLANNER_AUTOMATIC_RETRIES), schema, current_context)

    def plan(
        self, request: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> PlannerResult:
        """Interpret one non-empty user request and fail closed on invalid model output.

        Args:
            request: User request to interpret as one ordered RequestPlan.

        Returns:
            A locally validated RequestPlan or non-executing clarification outcome.

        Raises:
            RequestPlanningError: If the request, provider call, JSON response, or plan is invalid.
            ValueError: If the active schema cannot be projected into safe planner capabilities.
        """
        if not isinstance(request, str) or not request.strip():
            raise RequestPlanningError("Request text must be non-empty")
        self.last_call = False
        self.last_usage = None
        self.last_attempt_count = 0
        self.last_response_id = None
        self.last_provider_status = None
        self.last_incomplete_reason = None
        self.last_output_text_chars = None
        self.last_output_text_bytes = None
        self.last_parse_status = None
        self.last_result_kind = None
        self.last_result_counts = None
        self.last_error_category = None
        self.last_validation_stage = None
        self.last_validation_code = None
        self.last_spans = ()
        self.last_input_sizes = None
        self.last_call = True
        self.last_attempt_count = 1
        recorder = SpanRecorder(self._monotonic(), self._monotonic)
        input_started = self._monotonic()
        sizes: dict[str, int] = {}
        try:
            prompt = render_request_planner_prompt(
                self._schema,
                self._current_context,
                conversation_context,
                size_components=sizes,
            )
            output_schema = planner_result_json_schema(self._schema)
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
        provider_started = self._monotonic()
        try:
            response = self._client.responses.create(
                model=PLANNER_MODEL,
                reasoning={"effort": PLANNER_REASONING_EFFORT},
                store=False,
                max_output_tokens=PLANNER_MAX_OUTPUT_TOKENS,
                input=[
                    {
                        "role": "system",
                        "content": prompt,
                    },
                    {"role": "user", "content": request},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_planner_result",
                        "strict": True,
                        "schema": output_schema,
                    }
                },
            )
        except Exception as error:
            recorder.add("provider", provider_started, OperationalOutcome.FAILED, error)
            self.last_spans = recorder.spans
            self.last_error_category = _bounded_provider_metadata(type(error).__name__)
            raise RequestPlanningError("Request planner provider call failed") from error
        recorder.add("provider", provider_started)
        self.last_spans = recorder.spans
        self.last_usage = normalize_provider_usage(response)
        self.last_response_id = _bounded_provider_metadata(getattr(response, "id", None))
        self.last_provider_status = _bounded_provider_metadata(getattr(response, "status", None))
        incomplete_details = getattr(response, "incomplete_details", None)
        incomplete_reason = (
            incomplete_details.get("reason")
            if isinstance(incomplete_details, Mapping)
            else getattr(incomplete_details, "reason", None)
        )
        self.last_incomplete_reason = _bounded_provider_metadata(incomplete_reason)
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            self.last_output_text_chars = len(output_text)
            self.last_output_text_bytes = len(output_text.encode("utf-8"))
        if self.last_provider_status != "completed":
            self.last_error_category = "IncompleteProviderResponse"
            raise RequestPlanningError("Request planner provider response was not completed")
        parse_started = self._monotonic()
        try:
            payload = json.loads(output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            recorder.add("parse", parse_started, OperationalOutcome.FAILED, error)
            self.last_spans = recorder.spans
            self.last_parse_status = "failed"
            self.last_error_category = (
                "EmptyPlannerOutput"
                if not isinstance(output_text, str) or not output_text.strip()
                else "MalformedPlannerJSON"
            )
            raise RequestPlanningError("Request planner returned malformed JSON") from error
        recorder.add("parse", parse_started)
        self.last_parse_status = "succeeded"
        validation_started = self._monotonic()
        if (
            not isinstance(payload, dict)
            or set(payload) != {"result"}
            or not isinstance(payload["result"], dict)
        ):
            self.last_error_category = "LocalPlannerValidationError"
            self.last_validation_stage = PlannerValidationStage.PLANNER_RESULT_ENVELOPE.value
            self.last_validation_code = PlannerValidationCode.INVALID_FIELDS.value
            recorder.add("validate", validation_started, OperationalOutcome.FAILED)
            self.last_spans = recorder.spans
            raise RequestPlanningError(
                "Request planner result wrapper is invalid",
                stage=PlannerValidationStage.PLANNER_RESULT_ENVELOPE,
                code=PlannerValidationCode.INVALID_FIELDS,
            )
        try:
            result = validate_planner_result(payload["result"], self._schema)
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
        self.last_result_kind = "clarify" if isinstance(result, PlannerClarification) else "plan"
        self.last_result_counts = _planner_result_counts(result)
        return result


def _bounded_provider_metadata(value: Any) -> str | None:
    """Keep one short provider identifier/status value without response content."""
    if not isinstance(value, str) or not value or len(value) > 128:
        return None
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", value) is None:
        return None
    return value


def _planner_result_counts(result: PlannerResult) -> dict[str, int]:
    """Count only bounded structural categories from one validated planner result."""
    counts = {
        "actions": 0,
        "units": 0,
        "properties": 0,
        "tag_changes": 0,
        "facts": 0,
        "references": 0,
        "filters": 0,
        "limitations": 0,
    }
    if isinstance(result, PlannerClarification):
        return counts
    counts["actions"] = len(result.actions)
    counts["limitations"] = len(result.limitations)
    for action in result.actions:
        selection = None
        if isinstance(action, RetrieveAction):
            selection = action.plan
        elif isinstance(action, WriteAction):
            _count_write_action_structure(counts, action)
        elif isinstance(action, DelegateAction):
            selection = action.selection
        if selection is not None:
            counts["filters"] += _selection_filter_count(selection)
    return counts


def _count_write_action_structure(counts: dict[str, int], action: WriteAction) -> None:
    """Add bounded structural counts for one validated write action."""
    counts["units"] += len(action.units)
    for unit in action.units:
        counts["properties"] += len(unit.properties)
        counts["tag_changes"] += len(unit.tag_changes)
        counts["facts"] += len(unit.facts)
        counts["references"] += len(unit.references)
        counts["filters"] += _selection_filter_count(unit.target)


def _selection_filter_count(selection: SelectionCriteria) -> int:
    """Count direct and link-anchor filters without retaining their values."""
    anchor_count = (
        len(selection.link_scope.anchor.filters) if selection.link_scope is not None else 0
    )
    return len(selection.filters) + anchor_count


def _selection_json_schema(capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Build the shared query/type/filter Structured Outputs shape.

    Args:
        capabilities: Dynamic retrieval/selection capability projection from the canonical schema.

    Returns:
        Closed JSON Schema for either a RetrieveAction plan or KnowledgeUnit target.

    Raises:
        RequestPlanningError: If no deterministic planner filters are available.
    """
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
            "self_target": {"type": ["string", "null"], "enum": [SELF_TARGET, None]},
            "relational_reference": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "properties": {
                            "reference": {"type": "string"},
                            "source_kind": {"type": "string", "enum": ["self", "existing"]},
                            "source_query": {"type": ["string", "null"]},
                            "members": {"type": "string", "enum": ["one", "complete_set"]},
                        },
                        "required": ["reference", "source_kind", "source_query", "members"],
                        "additionalProperties": False,
                    },
                ]
            },
            "semantic_set": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "properties": {
                            "anchor_kind": {"type": "string", "enum": ["self", "existing"]},
                            "anchor_query": {"type": ["string", "null"]},
                            "group_query": {"type": "string"},
                            "explicit_qualifiers": {"type": "string"},
                            "asks_exhaustive": {"type": "boolean"},
                        },
                        "required": [
                            "anchor_kind",
                            "anchor_query",
                            "group_query",
                            "explicit_qualifiers",
                            "asks_exhaustive",
                        ],
                        "additionalProperties": False,
                    },
                ]
            },
        },
        "required": [
            "entity",
            "query",
            "type",
            "filters",
            "link_scope",
            "self_target",
            "relational_reference",
            "semantic_set",
        ],
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


def _filter_json_schema_alternatives(capabilities: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build strict dynamic filter alternatives shared by retrieval and write selection.

    Args:
        capabilities: Dynamic selection capabilities keyed by canonical filter field.

    Returns:
        JSON Schema alternatives for every supported field/operator combination.
    """
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
    """Build dynamic strict property-change alternatives from type-specific properties.

    Args:
        write_capabilities: Writable type/property projection from the canonical schema.

    Returns:
        Closed array schema supporting generic set/remove changes for known properties.

    Raises:
        RequestPlanningError: If a projected property uses an unsupported value type.
    """
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
    """Map one supported property definition to its basic strict JSON value shape.

    Args:
        definition: Schema-derived writable property capability.

    Returns:
        JSON Schema fragment for the property's value type.

    Raises:
        RequestPlanningError: If the property value type has no Structured Outputs mapping.
    """
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
    return _validate_retrieve_action(action, schema, retrieval_capabilities)


@_validation_boundary(PlannerValidationStage.RETRIEVE_ACTION)
def _validate_retrieve_action(
    action: Mapping[str, Any], schema: Mapping[str, Any], capabilities: Mapping[str, Any]
) -> RetrieveAction:
    """Validate one retrieval action and its shared selection criteria."""
    plan = _validate_selection(action["plan"], schema, capabilities, label="RetrievalPlan")
    return RetrieveAction(plan=plan)


@_validation_boundary(PlannerValidationStage.DELEGATE_ACTION)
def _validate_delegate_action(
    action: Mapping[str, Any], schema: Mapping[str, Any], capabilities: Mapping[str, Any]
) -> DelegateAction:
    """Validate generic delegated work without selecting or executing an application.

    Args:
        action: Untrusted delegated-action object returned by the planner.
        schema: Parsed canonical schema used by optional shared selection validation.
        capabilities: Dynamic shared selection capabilities derived from that schema.

    Returns:
        Immutable delegated work containing only a subrequest and optional generic selection.

    Raises:
        RequestPlanningError: If the action is not closed, has an empty request, or has invalid
            shared selection criteria.
    """
    if set(action) != {"kind", "request", "selection"}:
        raise RequestPlanningError("DelegateAction fields are invalid")
    request, raw_selection = action["request"], action["selection"]
    if not isinstance(request, str) or not request.strip():
        raise RequestPlanningError(
            "DelegateAction request must be non-empty",
            stage=PlannerValidationStage.DELEGATE_ACTION,
            code=PlannerValidationCode.EMPTY_REQUEST,
        )
    selection = (
        None
        if raw_selection is None
        else _validate_selection(
            raw_selection, schema, capabilities, label="DelegateAction selection"
        )
    )
    if selection is not None and selection.semantic_set is not None:
        raise RequestPlanningError("semantic set requires RetrieveAction")
    return DelegateAction(request=request.strip(), selection=selection)


@_validation_boundary(PlannerValidationStage.SELECTION)
def _validate_selection(
    raw: Any,
    schema: Mapping[str, Any],
    capabilities: Mapping[str, Any],
    *,
    label: str,
) -> SelectionCriteria:
    """Validate the shared query/type/filters selection contract.

    Args:
        raw: Untrusted selection object emitted by the planner.
        schema: Parsed canonical schema used by the shared deterministic filter validator.
        capabilities: Dynamic selection capabilities derived from that schema.
        label: Human-readable contract name used in validation errors.

    Returns:
        Immutable validated selection criteria reusable by retrieval or write targeting.

    Raises:
        RequestPlanningError: If query, type, filter shape, or filter semantics are invalid.
    """
    required = {
        "entity",
        "query",
        "type",
        "filters",
        "link_scope",
        "self_target",
        "relational_reference",
        "semantic_set",
    }
    previous_required = required - {"semantic_set"}
    pre_relational_required = required - {"semantic_set", "relational_reference"}
    legacy_required = {"entity", "query", "type", "filters", "link_scope"}
    legacy_minimum = {"query", "type", "filters"}
    if not isinstance(raw, dict) or (
        set(raw) != required
        and set(raw) != previous_required
        and set(raw) != pre_relational_required
        and set(raw) != legacy_required
        and set(raw) != legacy_minimum
    ):
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
        raise RequestPlanningError(
            f"{label} query must be non-empty",
            stage=PlannerValidationStage.SELECTION,
            code=PlannerValidationCode.EMPTY_QUERY,
        )
    if note_type is not None and note_type not in capabilities["types"]:
        raise RequestPlanningError(
            f"{label} type is invalid",
            stage=PlannerValidationStage.SELECTION,
            code=PlannerValidationCode.INVALID_TYPE,
        )
    if not isinstance(raw_filters, list):
        raise RequestPlanningError(f"{label} filters must be a list")
    _validate_planner_filters(raw_filters, note_type, capabilities)
    try:
        validate_context_filters(dict(schema), raw_filters, note_type=note_type)
    except ValueError as error:
        raise RequestPlanningError(
            f"{label} filters are invalid",
            stage=PlannerValidationStage.FILTER,
            code=PlannerValidationCode.INVALID_FILTER,
        ) from error
    link_scope = _validate_link_scope(raw.get("link_scope"), schema, capabilities, label=label)
    self_target = raw.get("self_target")
    if self_target not in (None, SELF_TARGET):
        raise RequestPlanningError(f"{label} self_target is invalid")
    if self_target == SELF_TARGET and (entity is not None or note_type not in (None, "person")):
        raise RequestPlanningError(f"{label} self_target must select the direct person target")
    relational = _validate_relational_reference(raw.get("relational_reference"), label=label)
    semantic_set = _validate_semantic_set_intent(raw.get("semantic_set"), label=label)
    if relational is not None and (
        entity is not None or self_target is not None or link_scope is not None or raw_filters
    ):
        raise RequestPlanningError(f"{label} relational reference conflicts with direct selection")
    if relational is not None and semantic_set is not None:
        raise RequestPlanningError(f"{label} semantic set conflicts with relational reference")
    if semantic_set is not None and (
        entity is not None or self_target is not None or link_scope is not None or raw_filters
    ):
        raise RequestPlanningError(f"{label} semantic set conflicts with direct selection")
    return SelectionCriteria(
        entity=entity.strip() if isinstance(entity, str) else None,
        query=query.strip(),
        type=note_type,
        filters=tuple(
            ContextFilter(item["field"], item["op"], item["value"]) for item in raw_filters
        ),
        link_scope=link_scope,
        self_target=self_target,
        relational_reference=relational,
        semantic_set=semantic_set,
    )


def _validate_semantic_set_intent(raw: Any, *, label: str) -> SemanticSetIntent | None:
    """Accept bounded set wording while rejecting planner-supplied canonical authority."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {
        "anchor_kind",
        "anchor_query",
        "group_query",
        "explicit_qualifiers",
        "asks_exhaustive",
    }:
        raise RequestPlanningError(f"{label} semantic set fields are invalid")
    anchor_kind = raw["anchor_kind"]
    anchor_query = raw["anchor_query"]
    group_query = raw["group_query"]
    qualifiers = raw["explicit_qualifiers"]
    exhaustive = raw["asks_exhaustive"]
    if (
        anchor_kind not in {"self", "existing"}
        or not isinstance(group_query, str)
        or not group_query.strip()
        or not isinstance(qualifiers, str)
        or not isinstance(exhaustive, bool)
        or (anchor_kind == "self" and anchor_query is not None)
        or (
            anchor_kind == "existing"
            and (not isinstance(anchor_query, str) or not anchor_query.strip())
        )
    ):
        raise RequestPlanningError(f"{label} semantic set is invalid")
    for value in (anchor_query, group_query, qualifiers):
        if value is None:
            continue
        if (
            len(value) > 256
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
            or _STABLE_ID_PATTERN.search(value)
            or "[[" in value
            or ".md" in value.casefold()
            or any(character in value for character in ("/", "\\"))
        ):
            raise RequestPlanningError(f"{label} semantic set wording is unsafe")
    return SemanticSetIntent(
        anchor_kind=anchor_kind,
        anchor_query=anchor_query.strip() if isinstance(anchor_query, str) else None,
        group_query=group_query.strip(),
        explicit_qualifiers=qualifiers.strip(),
        asks_exhaustive=exhaustive,
    )


def _validate_relational_reference(raw: Any, *, label: str) -> RelationalReference | None:
    """Accept only bounded source-relative wording, never a model-supplied identity."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {
        "reference",
        "source_kind",
        "source_query",
        "members",
    }:
        raise RequestPlanningError(f"{label} relational reference fields are invalid")
    if (
        not isinstance(raw["reference"], str)
        or not raw["reference"].strip()
        or raw["source_kind"] not in {"self", "existing"}
        or raw["members"] not in {"one", "complete_set"}
        or (raw["source_kind"] == "self" and raw["source_query"] is not None)
        or (
            raw["source_kind"] == "existing"
            and (not isinstance(raw["source_query"], str) or not raw["source_query"].strip())
        )
    ):
        raise RequestPlanningError(f"{label} relational reference is invalid")
    for value in (raw["reference"], raw["source_query"]):
        if value is None:
            continue
        if (
            len(value) > 256
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or _STABLE_ID_PATTERN.search(value)
            or "[[" in value
        ):
            raise RequestPlanningError(f"{label} relational wording is unsafe")
    if raw["source_query"] is not None and (
        ".md" in raw["source_query"].casefold()
        or any(character in raw["source_query"] for character in ("/", "\\"))
    ):
        raise RequestPlanningError(f"{label} relational source cannot be a path")
    return RelationalReference(
        raw["reference"].strip(),
        raw["source_kind"],
        raw["source_query"].strip() if raw["source_query"] is not None else None,
        raw["members"],
    )


@_validation_boundary(PlannerValidationStage.NOTE_SELECTOR)
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
        raise RequestPlanningError(
            f"{label} query must be non-empty",
            stage=PlannerValidationStage.NOTE_SELECTOR,
            code=PlannerValidationCode.EMPTY_QUERY,
        )
    if note_type is not None and note_type not in capabilities["types"]:
        raise RequestPlanningError(
            f"{label} type is invalid",
            stage=PlannerValidationStage.NOTE_SELECTOR,
            code=PlannerValidationCode.INVALID_TYPE,
        )
    if not isinstance(raw_filters, list):
        raise RequestPlanningError(f"{label} filters must be a list")
    _validate_planner_filters(raw_filters, note_type, capabilities)
    try:
        validate_context_filters(dict(schema), raw_filters, note_type=note_type)
    except ValueError as error:
        raise RequestPlanningError(
            f"{label} filters are invalid",
            stage=PlannerValidationStage.FILTER,
            code=PlannerValidationCode.INVALID_FILTER,
        ) from error
    return NoteSelector(
        entity=entity.strip() if isinstance(entity, str) else None,
        query=query.strip(),
        type=note_type,
        filters=tuple(
            ContextFilter(item["field"], item["op"], item["value"]) for item in raw_filters
        ),
    )


@_validation_boundary(PlannerValidationStage.LINK_SCOPE)
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


@_validation_boundary(PlannerValidationStage.WRITE_ACTION)
def _validate_write_action(
    action: Mapping[str, Any],
    schema: Mapping[str, Any],
    retrieval_capabilities: Mapping[str, Any],
    write_capabilities: Mapping[str, Any],
) -> WriteAction:
    """Validate one semantic write action without resolving identity or persisting data.

    Args:
        action: Untrusted write-action object returned by the planner.
        schema: Parsed canonical schema used by shared target-filter validation.
        retrieval_capabilities: Dynamic query/type/filter contract for write targets.
        write_capabilities: Dynamic canonical property contract for write mutations.

    Returns:
        Immutable semantic write preparation with safe targets, payloads, and references.

    Raises:
        RequestPlanningError: If units are malformed, violate intent payload rules, or reference an
            unknown or self target.
    """
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
        has_payload = bool(
            unit.properties or unit.tag_changes or unit.facts or unit.destination_type
        )
        if unit.intent in {"amend", "remove"} and not has_payload:
            raise RequestPlanningError(
                "KnowledgeUnit amend and remove intents require mutation payload"
            )
        if unit.intent == "record" and not has_payload and index not in referenced_targets:
            raise RequestPlanningError(
                "KnowledgeUnit record intent requires mutation payload unless referenced"
            )
    return WriteAction(units=units)


@_validation_boundary(PlannerValidationStage.KNOWLEDGE_UNIT)
def _validate_knowledge_unit(
    unit: Any,
    schema: Mapping[str, Any],
    retrieval_capabilities: Mapping[str, Any],
    write_capabilities: Mapping[str, Any],
) -> KnowledgeUnit:
    """Validate one write target, mutation payload, and local reference set.

    Args:
        unit: Untrusted model object for one semantic write target.
        schema: Parsed canonical schema used for deterministic target-filter validation.
        retrieval_capabilities: Shared query/type/filter capability projection.
        write_capabilities: Type-scoped writable property capability projection.

    Returns:
        One immutable KnowledgeUnit with no physical persistence authority.

    Raises:
        RequestPlanningError: If target, intent, properties, facts, or references violate the
            Phase 15.1 contract.
    """
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
    minimum = required - {"cardinality", "destination_type", "tag_changes"}
    if not isinstance(unit, dict) or not minimum.issubset(unit) or set(unit) - required:
        raise RequestPlanningError("KnowledgeUnit fields are invalid")
    target = _validate_selection(
        unit["target"], schema, retrieval_capabilities, label="KnowledgeUnit target"
    )
    if target.semantic_set is not None:
        raise RequestPlanningError("semantic set requires RetrieveAction")
    cardinality = unit.get("cardinality", "one")
    if cardinality not in {"one", "all_matching"}:
        raise RequestPlanningError(
            "KnowledgeUnit cardinality is invalid",
            stage=PlannerValidationStage.KNOWLEDGE_UNIT,
            code=PlannerValidationCode.INVALID_CARDINALITY,
        )
    if cardinality == "all_matching" and target.entity is not None:
        raise RequestPlanningError("all_matching KnowledgeUnit target.entity must be null")
    if cardinality == "all_matching" and target.self_target is not None:
        raise RequestPlanningError("self_target requires one direct target")
    if cardinality == "all_matching" and target.relational_reference is not None:
        raise RequestPlanningError("relational member sets use one source unit")
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
    tag_changes = _validate_tag_changes(unit.get("tag_changes", []), intent)

    raw_facts = unit["facts"]
    if (
        not isinstance(raw_facts, list)
        or len(raw_facts) != len(set(raw_facts))
        or not all(isinstance(fact, str) and fact.strip() for fact in raw_facts)
    ):
        raise RequestPlanningError("KnowledgeUnit facts must be unique non-empty strings")
    if any("\n" in fact or "\r" in fact or "<!-- odyssey:fact" in fact for fact in raw_facts):
        raise RequestPlanningError(
            "KnowledgeUnit facts must be single-line and must not contain Odyssey fact markers"
        )
    if intent == "delete" and (raw_properties or tag_changes or raw_facts):
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


@_validation_boundary(PlannerValidationStage.REFERENCE, PlannerValidationCode.INVALID_REFERENCE)
def _validate_fact_reference_markers(facts: Sequence[Any], reference_count: int) -> set[int]:
    """Validate internal reference markers and return their local reference indexes.

    Args:
        facts: Untrusted planner fact strings for one KnowledgeUnit.
        reference_count: Number of references in that same unit's references array.

    Returns:
        Set of local reference indexes represented by at least one marker.

    Raises:
        RequestPlanningError: If markers are malformed, out of range, or raw wikilinks appear.
    """
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


@_validation_boundary(PlannerValidationStage.PROPERTY_CHANGE)
def _validate_property_changes(
    raw_properties: Sequence[Any],
    note_type: str | None,
    intent: str,
    write_capabilities: Mapping[str, Any],
) -> tuple[PropertyChange, ...]:
    """Validate property changes against the selected type and shared Core value rules.

    Args:
        raw_properties: Untrusted ordered property-change objects from one KnowledgeUnit.
        note_type: Canonical target type used to scope allowed property IDs.
        intent: Semantic write intent controlling the allowed property operation.
        write_capabilities: Active schema-derived type/property capability projection.

    Returns:
        Immutable validated property changes in planner order.

    Raises:
        RequestPlanningError: If field scope, operation, uniqueness, nullability, or value semantics
            violate the active write contract.
    """
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


@_validation_boundary(PlannerValidationStage.TAG_CHANGE)
def _validate_tag_changes(raw_tag_changes: Any, intent: str) -> tuple[TagChange, ...]:
    """Validate explicit free-form tag mutations for one knowledge unit.

    Args:
        raw_tag_changes: Untrusted ordered tag operations from the planner.
        intent: Write intent that restricts allowed tag operations.
    Returns:
        Immutable item-level tag changes in planner order.

    Raises:
        RequestPlanningError: If operations are malformed, unknown, conflicting, or incompatible.
    """
    if not isinstance(raw_tag_changes, list):
        raise RequestPlanningError("KnowledgeUnit tag_changes must be a list")
    if intent == "delete" and raw_tag_changes:
        raise RequestPlanningError("Delete intent cannot mutate tags")
    if intent == "remove" and any(
        item.get("op") == "add" for item in raw_tag_changes if isinstance(item, dict)
    ):
        raise RequestPlanningError("Remove intent cannot add tags")
    result = []
    seen = set()
    for item in raw_tag_changes:
        if not isinstance(item, dict) or set(item) != {"op", "value"}:
            raise RequestPlanningError("Tag change is invalid")
        op, value = item["op"], item["value"]
        if (
            op not in _TAG_CHANGE_OPS
            or not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            or "\n" in value
            or "\r" in value
        ):
            raise RequestPlanningError("Tag change is invalid")
        key = value
        if key in seen:
            raise RequestPlanningError("Duplicate or conflicting tag change")
        seen.add(key)
        result.append(TagChange(op, value))
    return tuple(result)


@_validation_boundary(PlannerValidationStage.FILTER, PlannerValidationCode.INVALID_FILTER)
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
