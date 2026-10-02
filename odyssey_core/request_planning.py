"""Fail-closed interpretation of user requests into safe Odyssey RequestPlans."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import wraps
from time import perf_counter
from typing import Any, Protocol

from odyssey_core.context import ContextFilter, validate_context_filters
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainInterpretation,
)
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
from odyssey_core.temporal import TemporalValueError, calendar_day_wikilink, normalize_iso_date

PLANNER_MODEL = "gpt-5.6-sol"
PLANNER_REASONING_EFFORT = "low"
PLANNER_MAX_OUTPUT_TOKENS = 4096
PLANNER_AUTOMATIC_RETRIES = 0
PLANNER_CLARIFICATION_CODES = ("UNRECOGNIZED_REQUEST", "UNREPRESENTABLE_REQUEST")
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
_CALENDAR_DAY_LINK_PATTERN = re.compile(r"\[\[calendar/days/(\d{4}-\d{2}-\d{2})\|([^\]\r\n|]+)\]\]")
_STABLE_ID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
_PROMPT_TEMPLATE = """You convert one user request into one strict JSON PlannerResult. Use the supplied current date, time, and timezone.

Bounded recent conversation evidence may resolve a referent or conversational continuity, but it records only what was said and is never current personal truth. Use it only to identify the subject or interaction the user means. Do not turn a prior user statement or assistant response into a current-fact filter, retrieval constraint, or asserted fact. Canonical notes remain the authority for current facts. A follow-up write may reuse an explicit fact from earlier user text only when the ordinary write contract can represent it; assistant text never supplies a fact or mutation target. If the recent evidence still leaves the referent or requested mutation ambiguous, return CLARIFY rather than guessing.

Return outcome PLAN with a RequestPlan when the request contains safely interpretable Odyssey retrieval, knowledge mutation, or specialized-capability intent. Return outcome CLARIFY with clarification_code UNRECOGNIZED_REQUEST when the input has no safely interpretable or actionable Odyssey intent, including meaningless fragments such as "Bdbd", "asdfgh", or "???". CLARIFY must contain no RequestPlan and never becomes a DelegateAction. Do not invent an action merely to satisfy the schema.

Every PLAN has presentation_intent. Use `answer` by default. Use `note_set` only for one direct RetrieveAction with result_shape=single when the user explicitly asks to see matching notes as objects; it never adds retrieval authority or turns a write/delegation into retrieval. Use `answer_and_note_set` only for one direct RetrieveAction with result_shape=single when the user explicitly asks both for an answer/synthesis and the matching notes. For writes, delegation, multiple independent actions, clarification, any link_scope, relational_reference, or result_shape=collection, use `answer`; do not discard or weaken meaning merely to produce a note set.

Interpret each requested action in this order. FIRST identify the Odyssey knowledge candidate set and preserve every safely representable SelectionCriteria field: entity, query, type, filters, link_scope, self_target, and relational_reference. For a direct first-person target, set self_target to "self"; this means only the authenticated human's canonical person note, not a name, alias, provider identity, or person mentioned in a relationship. THEN choose what operation the user wants on that set: ordinary retrieval uses RetrieveAction, ordinary knowledge mutation uses WriteAction, and work requiring a specialized capability uses DelegateAction. The action kind changes what happens to the candidate set; it never weakens or erases that set.
Set relational_reference only when the selected identity is defined by a relationship or complete finite participant set in an existing canonical source, such as "mi hija", "sus hijos", or "todos los que estaban ayer". Preserve the user's reference wording, source_kind=self with source_query=null only when the source is the authenticated human, otherwise source_kind=existing with bounded source_query wording identifying an existing source, and members=one or complete_set. This is language-independent wording, not a relation type or a stable identity. The source may be identified by recent conversation, but current canonical Markdown alone establishes membership. Set entity=null, self_target=null, and link_scope=null for the relational selection; direct self remains self_target. Never enumerate members, invent a source, or assert IDs, filenames, paths, or relationship types. When relational evidence is missing or ambiguous, Core clarifies; relational wording never authorizes CREATE. When descriptive or event context does not have a safely bounded canonical source relationship, preserve the full description in ordinary `query` and leave relational_reference=null so Core can resolve it semantically across Odyssey. For singular WRITE with a bounded canonical relationship source, use relational_reference as a candidate anchor while target.query preserves the complete user description. Put only the relationship wording that defines the initial candidate universe in relational_reference.reference; preserve every additional qualifier in target.query so Core can disambiguate only within that relationship set using current note content and canonical incoming/outgoing evidence. For a qualified request that ultimately selects one member, relational_reference.members MUST be one even when the anchor relationship contains several current members; complete_set means the user targets the whole relationship set, not that the candidate universe initially contains multiple identities. When source_kind=existing, target.entity MUST remain null and the existing anchor source belongs only in relational_reference.source_query. Do not discard qualifiers merely because a relationship anchor exists, and do not invent members or stable identities. For complete_set shared-fact writes, the relational reference must still describe the complete requested set rather than a qualified subset; emit one record KnowledgeUnit with cardinality=one, the asserted fact, and no fabricated member units or references. relational_reference.members carries the complete-set meaning, while cardinality=one denotes the one natural source write. Core expands only a complete current set into the existing safe source-write path.
For retrieval, use result_shape=collection when the user is asking to enumerate or return multiple semantic members or values that together answer the request; use result_shape=single for ordinary fact retrieval or synthesis. Do not infer collection from grammatical plural alone. SelectionCriteria.query MUST preserve the complete useful request, including every material relation, scope, time, place, state, possession, purpose, context, and request for completeness. collection_subject belongs only to result_shape=collection; set it to null for every result_shape=single regardless of presentation intent. A collection has no direct entity, type, filters, link_scope, self_target, or relational_reference: set those to null or [] as appropriate. Set collection_subject=self only when the authenticated human is itself the semantic membership anchor: membership is directly defined by each member's relationship, action, state, or participation relative to that human. First-person possession, ownership, association, or contextual reference to another subject does not by itself make a collection self-scoped. When another object, concept, source, or set determines membership, set collection_subject=query and preserve the complete self-related context in query. This field contains no identity, name, path, generated subject phrase, relationship type, or inferred ontology. Core binds self and discovers bounded current canonical fact sources, selects only supplied evidence, and validates exact occurrences. Never provide collection members, IDs, paths, fact locators, candidate lists, links, mutation authority, or inferred relationship types. For an explicit list or set of matching Notes as objects, use result_shape=single with presentation_intent=note_set; multiple matching Notes are expected results, not ambiguity. Use ordinary single retrieval for one fact about a subject. Do not use collection shape for writes or delegate actions.
Use self_target only when the direct selected entity is the current human, as in "¿Dónde trabajo?" or "Apunta que vivo en Toulouse". Possessive or first-person context is identity evidence, not write ownership: "Mi hermano vive en Madrid" targets the brother, "Mi coche es un Scénic" retains its ordinary target semantics, and a description such as "mi compañero al que le gusta la bicicleta" targets that described entity rather than self. Never emit a user ID, person note ID, email, provider subject, filename, or other identity value in planner output.
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

For a write, determine semantic ownership before mutation payload. target.query describes only the subject being selected and must remain a non-empty human-readable identity description with all target-identifying qualifiers preserved; new predicates belong in `facts`, and referred entities belong in semantic references. If relational wording only identifies the subject of a different predicate, target that described subject and record only the new predicate. If the requested knowledge itself asserts one relationship from an explicit source, including self, the natural write target is that source and the related participants belong in the fact as semantic references. When several named or described participants share that one relationship to the same explicit source, emit exactly one source-targeted KnowledgeUnit and represent every participant as a semantic fact reference; NEVER split the relationship into participant-targeted units. By contrast, when the same independently true predicate applies to several distinct subjects and there is no natural shared source that owns the assertion, preserve those subjects as separate write targets. Minimize note mutations without changing semantic ownership: never invent an aggregate source merely to reduce writes, never infer pairwise relations from shared membership, and never move a fact to a less natural owner merely to use fewer notes.

Decompose only the new durable knowledge after ownership is fixed. Group compatible changes for the same logical target; different intents for the same target produce separate KnowledgeUnits. Atomicity is semantic, not punctuation-based: split independently meaningful knowledge into separate atomic `facts` entries, but keep sentences or clauses together when they form one coherent explanation, reflection, or decision with dependent reasons or other meaning that would be lost by splitting. Preserve order and references. A canonical property used only to identify an existing target may constrain `target.filters`; a newly recorded property belongs in `properties` and must not be copied into filters unless its old value is explicitly part of the identity evidence. For conversational knowledge that safely maps to a property, retain the human knowledge fact as well. Use only record, amend, remove, and delete. Explicit correction uses remove for the false prior fact and amend for the corrected knowledge. Amend/remove require at least one mutation across properties or facts. Record normally contains properties and/or facts; both may be empty only for a semantic reference-target unit that supports another KnowledgeUnit. Delete has no mutation payload. Set `destination_type` to null for ordinary writes. Set it only for an explicit reclassification of the same existing note, using intent=amend and cardinality=one.

Decide fact references last. Replace an occurrence with `{{ref:N}}`, where N is the zero-based index in that fact unit's own `references` array, only when that wording denotes another logical Odyssey note identity that can be selected safely under the active capabilities; the reference contains `mention`, `role`, and a compact semantic `selection` of `entity`, `query`, `type`, `filters`, and optional `relational_reference`. Preserve the user's complete identifying wording in `selection.query`. When the referred identity is defined by a bounded current relationship or event membership, use `relational_reference` under the same source rules as target selection, keep only the relationship anchor in `relational_reference.reference`, keep additional qualifiers in `selection.query`, and set `members=one`; Core then disambiguates only inside that grounded member set. A proper noun or ordinary fact argument is not enough by itself. Whenever a fact, event, or action describes a distinct participant that denotes a safely selectable logical Odyssey identity, represent that participant as a semantic reference even when identified only descriptively. Literal preservation is only for non-identity context or values; do not literalize a distinct identity participant. Type-null references are for wording that explicitly denotes an existing Odyssey identity whose exact type need not be asserted, not for speculative entity promotion. Do not create extra model-facing KnowledgeUnits merely to carry reference targets, resolve identities yourself, or emit stable IDs; do not emit Markdown `[[wikilinks]]`. Core owns identity resolution and binding. A fact reference must denote a different logical note from its own KnowledgeUnit target; never encode the unit target itself as `{{ref:N}}`. A mention used only to identify the write target or an incidental name is not automatically a reference, and references never authorize inverse or mirrored writes.

Tags are generic free-form metadata. Emit a tag filter only when the user explicitly asks to search by a tag, using `tags` with `contains`; emit `tag_changes` only when the user explicitly asks to add or remove a tag. Never infer tags from semantic words such as idea, decision, reflection, or review, and never require a registry or controlled vocabulary.

Do not infer repository existence, resolve identity, choose CREATE versus UPDATE, generate IDs, paths, Markdown, SQL, or persistence instructions, or execute retrieval, persistence, or entity resolution. Use limitation codes only with their defined meanings. Return strict structured JSON.

Planner retrieval/selection capabilities (derived dynamically from the canonical schema):

{{RETRIEVAL_CAPABILITIES}}

Planner writable type/property capabilities (derived dynamically from the same canonical schema):

{{WRITE_CAPABILITIES}}"""

_SEMANTIC_WRITE_PROMPT_REPLACEMENTS = {
    "Every PLAN has presentation_intent.": """Every PLAN has presentation_intent. Use `answer` by default. Use `note_set` only for one direct RetrieveAction with result_shape=single when the user explicitly asks to see matching notes as objects; it never adds retrieval authority or turns a write/delegation into retrieval. Use `answer_and_note_set` only for one direct RetrieveAction with result_shape=single when the user explicitly asks both for an answer/synthesis and the matching notes. For semantic writes, delegation, multiple independent actions, clarification, any retrieval link_scope or relational_reference, any write candidate_scope, or result_shape=collection, use `answer`; do not discard or weaken meaning merely to produce a note set.""",
    "Interpret each requested action in this order.": """Interpret each requested action in provider order and preserve that order exactly. For retrieval and delegation, FIRST identify the Odyssey knowledge candidate set and preserve every safely representable SelectionCriteria field: entity, query, type, filters, link_scope, self_target, and relational_reference. For a direct first-person retrieval/delegation target, self_target means only the authenticated human's canonical person note. THEN choose retrieve, semantic write, or delegate. The action kind changes what happens to the candidate set; it never weakens or erases that set.
Set relational_reference only when a retrieval or delegation identity is defined by a relationship or complete finite participant set in an existing canonical source. Preserve the user's reference wording, source_kind=self with source_query=null only when the source is the authenticated human, otherwise source_kind=existing with bounded source_query wording identifying an existing source, and members=one or complete_set. This is language-independent wording, not a relation type or a stable identity. The source may be identified by recent conversation, but current canonical Markdown alone establishes membership. Set entity=null, self_target=null, and link_scope=null for the relational selection; direct self remains self_target. Never enumerate members, invent a source, or assert IDs, filenames, paths, or relationship types. When relational evidence is missing or ambiguous, Core clarifies; relational wording never authorizes CREATE. When descriptive or event context does not have a safely bounded canonical source relationship, preserve the full description in ordinary query and leave relational_reference=null so Core can resolve it semantically across Odyssey.
For retrieval, use result_shape=collection when the user is asking to enumerate or return multiple semantic members or values that together answer the request; use result_shape=single for ordinary fact retrieval or synthesis. Do not infer collection from grammatical plural alone. SelectionCriteria.query MUST preserve the complete useful request, including every material relation, scope, time, place, state, possession, purpose, context, and request for completeness. collection_subject belongs only to result_shape=collection; set it to null for every result_shape=single regardless of presentation intent. A collection has no direct entity, type, filters, link_scope, self_target, or relational_reference: set those to null or [] as appropriate. Set collection_subject=self only when the authenticated human is itself the semantic membership anchor: membership is directly defined by each member's relationship, action, state, or participation relative to that human. First-person possession, ownership, association, or contextual reference to another subject does not by itself make a collection self-scoped. When another object, concept, source, or set determines membership, set collection_subject=query and preserve the complete self-related context in query. This field contains no identity, name, path, generated subject phrase, relationship type, or inferred ontology. Core binds self and discovers bounded current canonical fact sources, selects only supplied evidence, and validates exact occurrences. Never provide collection members, IDs, paths, fact locators, candidate lists, links, mutation authority, or inferred relationship types. For an explicit list or set of matching Notes as objects, use result_shape=single with presentation_intent=note_set; multiple matching Notes are expected results, not ambiguity. Use ordinary single retrieval for one fact about a subject. Do not use collection shape for writes or delegate actions.
Use self_target only when the direct retrieval/delegation entity is the current human. Possessive or first-person context is identity evidence, not ownership: a description such as "my colleague who likes cycling" selects that described entity rather than self. Semantic writes express the corresponding distinction with target.binding.
For a semantic write, describe meaning only. Each write action owns its ordered operations array and compiles independently to one existing Core WriteAction. Never merge separate write actions, never split one write action globally, and never create cross-action bindings. Each operation contains one semantic target, one genuine apply_to value, one mutation intent, and its ordered payload. Use apply_to=one for one logical identity and all_matching only when the user truly requests the complete deterministically selectable set; never infer all_matching from plural grammar, several candidates, or independent names.
An identity has a complete human-readable description, binding=self or described, optional direct_name, optional canonical note_type, explicit deterministic filters, and optional candidate_scope. binding=self is only for facts whose actual subject is the authenticated human; first-person possession or relationship wording does not make another subject self. A described identity may use candidate_scope when the request defines that identity through membership or relationship to SELF or to one described source. candidate_scope itself does not assert that the source or membership exists; Core must ground it from canonical evidence or clarify. candidate_scope.source is either SELF or one SOURCE_DESCRIPTION with free-text description. SOURCE_DESCRIPTION is the request-provided source description, not an existence claim, and never authorizes creation. member_query names the relationship-bounded candidates and extent is one_member or complete_set. Preserve all additional identity qualifiers in description. Candidate scope is non-recursive, never supplies members, IDs, paths, or a relationship taxonomy, and never itself authorizes CREATE. Candidate scope applies uniformly to every described semantic identity and every canonical note type: preserve it whenever SELF or one described source bounds the candidate set, whether that identity is the operation target or an identity part inside a fact. Never drop a required candidate_scope because the identity is non-person or because it appears inside a fact. Use complete_set only when the requested fact applies to that complete current finite set; otherwise use one_member. An unresolved choice among multiple grounded one_member candidates is still representable: keep extent=one_member and let Core clarify which member; do not ESCALATE merely because that member is not yet uniquely identified. Use direct_name only for safely explicit name/alias wording, and never combine direct_name or filters with candidate_scope.""",
    "RetrieveAction.plan and every KnowledgeUnit.target": """RetrieveAction.plan and a non-null DelegateAction.selection obey the same SelectionCriteria rules. Entity is only a safely explicit primary-name/alias candidate from the user's wording; it is never an Odyssey ID and does not assert repository existence. Do not turn every noun phrase or mentioned name into entity: contextual descriptions such as "the corner shop" and "Marta's friend" keep entity=null. A null link_scope means the direct note only, never a graph neighborhood. Ordinary knowledge about one entity uses that direct selection. When the user explicitly selects notes through linked, related, backlink/reference, direction, or bounded-hop graph meaning that the existing LinkScope can represent, link_scope is required; retaining that graph meaning only in query is insufficient. Its non-recursive anchor independently selects the one safe note identity. Do not execute traversal.""",
    "A RetrieveAction exists only": """A RetrieveAction exists only when the user asks to retrieve or inspect knowledge. A semantic write target is identity evidence for later existing-entity resolution and must not create an extra RetrieveAction. Put a property mentioned only to identify a write target in target.filters when it maps safely to the dynamic filter contract; put it in properties only when the user is asking to record, change, or remove that property. Meaning that cannot safely become a filter stays in target.description.

For every semantic write, determine ownership before mutation payload. target.description describes only the selected subject and preserves all target-identifying qualifiers; new predicates belong in facts, and distinct Odyssey identities mentioned by facts use identity parts. Relationship, possession, or membership wording used only to identify a described subject never transfers ownership of a different predicate to its source. When the new action, state, or property is about that described subject, keep that subject as the operation target even when its identity is bounded relative to SELF or another source; accompanying identities remain fact parts. If the requested knowledge asserts one relationship from an explicit source, including self, the natural target is that source and the related participants are identity parts in its fact. Several participants sharing that one source relationship stay in one source-targeted operation. By contrast, one independently true predicate applied to distinct subjects produces separate operations. Minimize note mutations without changing ownership: never invent an aggregate source, infer pairwise relations, or move a fact to a less natural owner.

After ownership is fixed, decompose only the new durable knowledge. Group compatible changes for the same logical target inside one operation; different intents remain distinct operations. Atomicity is semantic, not punctuation-based: use separate facts for independently meaningful knowledge, but keep clauses with dependent reasons, explanation, reflection, or decision wording together. Preserve operation, fact, and part order. Use only record, amend, remove, and delete. Explicit correction uses remove for false prior knowledge and amend for corrected knowledge. Amend/remove require a material payload; delete carries none. destination_type is null except for explicit metadata-only reclassification with intent=amend and apply_to=one.

Facts contain ordered parts. A literal part preserves non-identity wording exactly. An identity part contains the exact occurrence text plus an independently selectable semantic identity. Use identity parts for distinct participants that safely denote Odyssey note identities, including descriptive participants; do not promote ordinary places, dates, URLs, paths, external identifiers, or context into identities merely because they are nouns or proper names. An identity part must not select its own operation target. Reuse the same semantic identity wording within the same write action when occurrences refer to the same identity; Core derives all reference markers, indexes, lookup units, roles, and binding mechanics. Never emit those mechanical fields, stable IDs, Markdown wikilinks, or inferred inverse writes.

Properties, filters, note types, destination types, and property value types come only from the supplied dynamic capabilities. Tags are explicit free-form metadata; never infer tags from semantic words. Candidate complete_set and all_matching are distinct: complete_set is one relationship-bounded source operation, while all_matching is a bulk selection. If safe ownership, action boundaries, candidate scope, correction shape, or identity promotion remains uncertain, ESCALATE instead of approximating.""",
    "For a write, determine semantic ownership": "",
    "Decompose only the new durable knowledge": "",
    "Decide fact references last.": "",
}


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
    INVALID_SELECTION_FIELDS = "INVALID_SELECTION_FIELDS"
    INVALID_ENTITY = "INVALID_ENTITY"
    INVALID_SELF_TARGET = "INVALID_SELF_TARGET"
    SELECTION_MODE_CONFLICT = "SELECTION_MODE_CONFLICT"
    RELATIONAL_REFERENCE_CONFLICT = "RELATIONAL_REFERENCE_CONFLICT"
    INVALID_SEMANTIC_SET_FIELDS = "INVALID_SEMANTIC_SET_FIELDS"
    INVALID_SEMANTIC_SET_INVARIANT = "INVALID_SEMANTIC_SET_INVARIANT"
    UNSAFE_SEMANTIC_SET_WORDING = "UNSAFE_SEMANTIC_SET_WORDING"


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
                raise RequestPlanningError(
                    str(error), stage=stage, code=error.validation_code or code
                ) from error

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
    collection_subject: str | None = None


@dataclass(frozen=True, slots=True)
class RelationalReference:
    """Preserve one source-relative candidate relationship without asserting canonical members."""

    reference: str
    source_kind: str
    source_query: str | None
    members: str


@dataclass(frozen=True, slots=True)
class SemanticSetIntent:
    """Preserve a bounded semantic subject and requested members without storage assertions."""

    subject_kind: str
    subject_query: str | None
    member_query: str
    explicit_qualifiers: str
    asks_exhaustive: bool
    member_type: str | None = None


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
    result_shape: str = "single"


@dataclass(frozen=True, slots=True)
class KnowledgeReference:
    """Represent one semantic reference before or after Core lowers its lookup selection."""

    target_index: int | None
    role: str
    mention: str
    selection: SelectionCriteria | None = None


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
    reference_lookup_only: bool = False


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
    domain_interpretation: DomainInterpretation | None = None,
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
    return _render_request_planner_prompt_template(
        _PROMPT_TEMPLATE,
        schema,
        current_context,
        conversation_context,
        size_components=size_components,
        domain_interpretation=domain_interpretation,
        semantic_write_mode=False,
    )


def render_semantic_write_planner_prompt(
    schema: Mapping[str, Any],
    current_context: Mapping[str, str],
    conversation_context: Sequence[Mapping[str, str]] = (),
    *,
    size_components: dict[str, int] | None = None,
    domain_interpretation: DomainInterpretation | None = None,
) -> str:
    """Render the Luna semantic-WRITE variant while retaining common planner instructions.

    The production Sol renderer continues to consume ``_PROMPT_TEMPLATE`` unchanged. This variant
    replaces whole legacy WRITE-language paragraphs rather than appending corrective overrides, so
    Luna sees one coherent semantic contract and the common retrieval/delegation instructions.
    """
    paragraphs = _PROMPT_TEMPLATE.split("\n\n")
    replaced: set[str] = set()
    rendered: list[str] = []
    for paragraph in paragraphs:
        replacement = next(
            (
                value
                for prefix, value in _SEMANTIC_WRITE_PROMPT_REPLACEMENTS.items()
                if paragraph.startswith(prefix)
            ),
            None,
        )
        if replacement is None:
            rendered.append(paragraph)
            continue
        prefix = next(
            prefix for prefix in _SEMANTIC_WRITE_PROMPT_REPLACEMENTS if paragraph.startswith(prefix)
        )
        if prefix in replaced:
            raise RuntimeError("Semantic WRITE prompt replacement is ambiguous")
        replaced.add(prefix)
        if replacement:
            rendered.append(replacement)
    if replaced != set(_SEMANTIC_WRITE_PROMPT_REPLACEMENTS):
        raise RuntimeError("Semantic WRITE prompt replacement is incomplete")
    return _render_request_planner_prompt_template(
        "\n\n".join(rendered),
        schema,
        current_context,
        conversation_context,
        size_components=size_components,
        domain_interpretation=domain_interpretation,
        semantic_write_mode=True,
    )


def _render_request_planner_prompt_template(
    template: str,
    schema: Mapping[str, Any],
    current_context: Mapping[str, str],
    conversation_context: Sequence[Mapping[str, str]],
    *,
    size_components: dict[str, int] | None,
    domain_interpretation: DomainInterpretation | None,
    semantic_write_mode: bool,
) -> str:
    """Fill one reviewed planner template from current schema capabilities and context."""
    _validate_current_context(current_context)
    if template.count(_RETRIEVAL_CAPABILITY_PLACEHOLDER) != 1:
        raise RuntimeError("Request planner retrieval capability placeholder is invalid")
    if template.count(_WRITE_CAPABILITY_PLACEHOLDER) != 1:
        raise RuntimeError("Request planner write capability placeholder is invalid")
    retrieval = build_planner_capabilities(schema, current_context=current_context)
    writable = build_write_capabilities(schema)
    retrieval_json = json.dumps(retrieval, ensure_ascii=False, separators=(",", ":"))
    writable_json = json.dumps(writable, ensure_ascii=False, separators=(",", ":"))
    rendered = template.replace(
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
    if domain_interpretation is not None:
        domain_section = _render_domain_interpretation_section(
            domain_interpretation, semantic_write_mode=semantic_write_mode
        )
        prompt += domain_section
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


def _render_domain_interpretation_section(
    interpretation: DomainInterpretation, *, semantic_write_mode: bool
) -> str:
    """Render app-specialized evidence while keeping all Core semantic authority in Core."""
    if not isinstance(interpretation, DomainInterpretation):
        raise RequestPlanningError("Domain interpretation is invalid")
    payload = json.dumps(
        interpretation.to_prompt_payload(), ensure_ascii=False, separators=(",", ":")
    )
    if semantic_write_mode:
        temporal_instruction = (
            "For temporal_reference evidence that is material to a durable write, use exactly one "
            "semantic temporal_reference fact part with the supplied source_text and value; never "
            "invent or normalize another date yourself."
        )
    else:
        temporal_instruction = (
            "For temporal_reference evidence that is material to a durable write, preserve it as "
            "one Calendar Day link using exactly the supplied VALUE. SOURCE_TEXT grounds which temporal "
            "wording the evidence came from, but Core canonicalizes the durable link label; never "
            "invent or normalize another date yourself."
        )
    return (
        "\n\nSpecialized domain interpretation (trusted only as bounded domain evidence, never as "
        "mutation authority):\n"
        + payload
        + "\nCore still owns action choice, semantic ownership, targets, identities, references, "
        "cardinality, facts, validation, and mutation planning. Do not infer extra app semantics "
        "or copy application-specific structure into Core fields. " + temporal_instruction
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
    direct_selection_schema = _selection_json_schema(retrieval_capabilities)
    single_retrieval_selection_schema = _single_retrieval_selection_json_schema(
        direct_selection_schema
    )
    collection_selection_schema = _collection_selection_json_schema(direct_selection_schema)
    reference_selection_schema = _reference_selection_json_schema(retrieval_capabilities)
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
                                "result_shape": {"type": "string", "enum": ["single"]},
                                "plan": single_retrieval_selection_schema,
                            },
                            "required": ["kind", "result_shape", "plan"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["retrieve"]},
                                "result_shape": {"type": "string", "enum": ["collection"]},
                                "plan": collection_selection_schema,
                            },
                            "required": ["kind", "result_shape", "plan"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["write"]},
                                "units": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "target": direct_selection_schema,
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
                                                        "selection": reference_selection_schema,
                                                        "role": {"type": "string"},
                                                        "mention": {"type": "string"},
                                                    },
                                                    "required": ["selection", "role", "mention"],
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
                                "selection": {"anyOf": [{"type": "null"}, direct_selection_schema]},
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
    retrieve_action, collection_action, write_action, delegate_action = actions["items"]["anyOf"]
    collection_selection = collection_action["properties"]["plan"]
    single_retrieval_selection = retrieve_action["properties"]["plan"]
    selection = write_action["properties"]["units"]["items"]["properties"]["target"]
    filter_array = selection["properties"]["filters"]
    link_scope = selection["properties"]["link_scope"]["anyOf"][1]
    note_selector = link_scope["properties"]["anchor"]

    note_selector["properties"]["filters"] = {"$ref": "#/$defs/filter_array"}
    link_scope["properties"]["anchor"] = {"$ref": "#/$defs/note_selector"}
    selection["properties"]["filters"] = {"$ref": "#/$defs/filter_array"}
    selection["properties"]["link_scope"] = {
        "anyOf": [{"type": "null"}, {"$ref": "#/$defs/link_scope"}]
    }
    single_retrieval_selection["properties"]["filters"] = {"$ref": "#/$defs/filter_array"}
    single_retrieval_selection["properties"]["link_scope"] = {
        "anyOf": [{"type": "null"}, {"$ref": "#/$defs/link_scope"}]
    }
    write_action["properties"]["units"]["items"]["properties"]["target"] = {
        "$ref": "#/$defs/selection"
    }
    delegate_action["properties"]["selection"] = {
        "anyOf": [{"type": "null"}, {"$ref": "#/$defs/selection"}]
    }
    retrieve_action["properties"]["plan"] = {"$ref": "#/$defs/single_retrieval_selection"}
    collection_action["properties"]["plan"] = {"$ref": "#/$defs/collection_selection"}
    actions["items"]["anyOf"] = [
        {"$ref": "#/$defs/retrieve_action"},
        {"$ref": "#/$defs/collection_action"},
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
        "single_retrieval_selection": single_retrieval_selection,
        "collection_selection": collection_selection,
        "retrieve_action": retrieve_action,
        "collection_action": collection_action,
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
def validate_planner_result(
    payload: Any,
    schema: Mapping[str, Any],
    domain_interpretation: DomainInterpretation | None = None,
) -> PlannerResult:
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
        plan = validate_request_plan(
            {
                "actions": payload["actions"],
                "limitations": payload["limitations"],
                "presentation_intent": payload.get("presentation_intent", "answer"),
            },
            schema,
            allow_temporal_reference_links=bool(
                domain_interpretation and domain_interpretation.temporal_references()
            ),
        )
        validate_plan_against_domain_interpretation(plan, domain_interpretation)
        return plan
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


def validate_plan_against_domain_interpretation(
    plan: RequestPlan, interpretation: DomainInterpretation | None
) -> None:
    """Correlate specialized evidence to Core output without delegating Core semantics to an app."""
    if interpretation is None:
        return
    if not isinstance(interpretation, DomainInterpretation):
        raise RequestPlanningError("Domain interpretation is invalid")
    allowed = {
        item.value for item in interpretation.evidence if item.kind == TEMPORAL_REFERENCE_EVIDENCE
    }
    found: set[str] = set()
    for action in plan.actions:
        if not isinstance(action, WriteAction):
            continue
        for unit in action.units:
            for fact in unit.facts:
                for match in _CALENDAR_DAY_LINK_PATTERN.finditer(fact):
                    found.add(match.group(1))
    if found - allowed:
        raise RequestPlanningError(
            "Core plan contains temporal evidence not supplied by the specialized application",
            stage=PlannerValidationStage.WRITE_ACTION,
            code=PlannerValidationCode.INVALID_MUTATION,
        )
    if (
        allowed
        and any(isinstance(action, WriteAction) for action in plan.actions)
        and not allowed <= found
    ):
        raise RequestPlanningError(
            "Core write omitted required specialized temporal evidence",
            stage=PlannerValidationStage.WRITE_ACTION,
            code=PlannerValidationCode.INVALID_MUTATION,
        )


@_validation_boundary(PlannerValidationStage.REQUEST_PLAN)
def validate_request_plan(
    payload: Any, schema: Mapping[str, Any], *, allow_temporal_reference_links: bool = False
) -> RequestPlan:
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
    actions = tuple(
        _validate_action(
            action,
            schema,
            retrieval_capabilities,
            write_capabilities,
            allow_temporal_reference_links=allow_temporal_reference_links,
        )
        for action in raw_actions
    )
    return finalize_request_plan(actions, limitations, presentation_intent)


def validate_request_action(action: Any, schema: Mapping[str, Any]) -> RequestAction:
    """Validate one raw action for adapters that preserve a heterogeneous provider sequence."""
    return _validate_action(
        action,
        schema,
        build_planner_capabilities(schema),
        build_write_capabilities(schema),
    )


def finalize_request_plan(
    actions: Sequence[RequestAction], limitations: Any, presentation_intent: Any
) -> RequestPlan:
    """Apply shared plan-level limitations and presentation invariants to validated actions."""
    if not actions or not all(
        isinstance(action, (RetrieveAction, WriteAction, DelegateAction)) for action in actions
    ):
        raise RequestPlanningError("RequestPlan actions must be a non-empty validated sequence")
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
    if presentation_intent not in PRESENTATION_INTENTS:
        raise RequestPlanningError("RequestPlan presentation intent is invalid")
    if presentation_intent != "answer" and (
        len(actions) != 1
        or not isinstance(actions[0], RetrieveAction)
        or actions[0].result_shape != "single"
        or actions[0].plan.link_scope is not None
        or actions[0].plan.relational_reference is not None
    ):
        raise RequestPlanningError("Note-set presentation requires one direct retrieval")
    return RequestPlan(
        actions=tuple(actions),
        limitations=tuple(limitations),
        presentation_intent=presentation_intent,
    )


class OpenAIRequestPlanner:
    """Plan requests with Sol/low while leaving all execution outside this boundary."""

    def __init__(
        self,
        client: ResponsesClient,
        schema: Mapping[str, Any],
        current_context: Mapping[str, str],
        monotonic: Any = perf_counter,
        *,
        domain_interpretation: DomainInterpretation | None = None,
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
        self._domain_interpretation = domain_interpretation
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
        cls,
        schema: Mapping[str, Any],
        current_context: Mapping[str, str],
        *,
        domain_interpretation: DomainInterpretation | None = None,
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
        return cls(
            OpenAI(max_retries=PLANNER_AUTOMATIC_RETRIES),
            schema,
            current_context,
            domain_interpretation=domain_interpretation,
        )

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
                domain_interpretation=self._domain_interpretation,
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
            result = validate_planner_result(
                payload["result"], self._schema, self._domain_interpretation
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
            "relational_reference": _relational_reference_json_schema(),
            "collection_subject": {
                "type": ["string", "null"],
                "enum": ["self", "query", None],
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
            "collection_subject",
        ],
        "additionalProperties": False,
    }


def _relational_reference_json_schema() -> dict[str, Any]:
    """Build the shared bounded relationship-anchor shape for direct and reference selection."""
    return {
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
    }


def _reference_selection_json_schema(capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Build the compact fact-reference selector with only singular grounded anchors."""
    selector = deepcopy(_note_selector_json_schema(capabilities))
    shared_properties = {
        "reference": {"type": "string"},
        "members": {"type": "string", "enum": ["one"]},
    }
    self_reference = {
        "type": "object",
        "properties": {
            **shared_properties,
            "source_kind": {"type": "string", "enum": ["self"]},
            "source_query": {"type": "null"},
        },
        "required": ["reference", "source_kind", "source_query", "members"],
        "additionalProperties": False,
    }
    existing_reference = {
        "type": "object",
        "properties": {
            **shared_properties,
            "source_kind": {"type": "string", "enum": ["existing"]},
            "source_query": {"type": "string"},
        },
        "required": ["reference", "source_kind", "source_query", "members"],
        "additionalProperties": False,
    }
    selector["properties"]["relational_reference"] = {
        "anyOf": [{"type": "null"}, self_reference, existing_reference]
    }
    selector["required"] = [*selector["required"], "relational_reference"]
    return selector


def _collection_selection_json_schema(direct_selection_schema: Mapping[str, Any]) -> dict[str, Any]:
    """Restrict collection planning to a lossless query without direct selection authority."""
    collection_selection = deepcopy(direct_selection_schema)
    properties = collection_selection["properties"]
    properties["entity"] = {"type": "null"}
    empty_filters_schema = deepcopy(direct_selection_schema["properties"]["filters"])
    empty_filters_schema["maxItems"] = 0
    properties["filters"] = empty_filters_schema
    properties["link_scope"] = {"type": "null"}
    properties["self_target"] = {"type": "null"}
    properties["relational_reference"] = {"type": "null"}
    properties["type"] = {"type": "null"}
    properties["collection_subject"] = {"type": "string", "enum": ["self", "query"]}
    return collection_selection


def _single_retrieval_selection_json_schema(
    direct_selection_schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Restrict single retrievals so collection scope cannot compete with direct selection.

    Args:
        direct_selection_schema: Shared direct selection shape used by writes and delegation.

    Returns:
        Closed single-retrieval selection schema with no semantic-member collection scope.
    """
    single_retrieval_selection = deepcopy(direct_selection_schema)
    single_retrieval_selection["properties"]["collection_subject"] = {"type": "null"}
    return single_retrieval_selection


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


def planner_filter_array_json_schema(capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the shared dynamic closed filter array for alternate provider action branches."""
    return {
        "type": "array",
        "items": {"anyOf": _filter_json_schema_alternatives(capabilities)},
    }


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


def planner_property_changes_json_schema(
    write_capabilities: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose schema-derived property mutations without duplicating their value-type mapping."""
    return _property_changes_json_schema(write_capabilities)


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
    *,
    allow_temporal_reference_links: bool = False,
) -> RequestAction:
    """Validate one discriminated action without executing retrieval or persistence."""
    if not isinstance(action, dict):
        raise RequestPlanningError("RequestPlan action must be an object")
    if action.get("kind") == "write":
        return _validate_write_action(
            action,
            schema,
            retrieval_capabilities,
            write_capabilities,
            allow_temporal_reference_links=allow_temporal_reference_links,
        )
    if action.get("kind") == "delegate":
        return _validate_delegate_action(action, schema, retrieval_capabilities)
    if action.get("kind") != "retrieve" or set(action) not in (
        {"kind", "plan"},
        {"kind", "plan", "result_shape"},
    ):
        raise RequestPlanningError("RequestPlan action kind is invalid")
    return _validate_retrieve_action(action, schema, retrieval_capabilities)


@_validation_boundary(PlannerValidationStage.RETRIEVE_ACTION)
def _validate_retrieve_action(
    action: Mapping[str, Any], schema: Mapping[str, Any], capabilities: Mapping[str, Any]
) -> RetrieveAction:
    """Validate one retrieval action and its shared selection criteria."""
    plan = _validate_selection(action["plan"], schema, capabilities, label="RetrievalPlan")
    shape = action.get("result_shape", "single")
    if shape not in {"single", "collection"}:
        raise RequestPlanningError("RetrieveAction result shape is invalid")
    if plan.semantic_set is not None:
        # Historical validated plans remain readable, but new provider output has no such field.
        return RetrieveAction(plan=plan, result_shape="collection")
    if (
        shape == "collection"
        and plan.collection_subject is None
        and "collection_subject" not in action["plan"]
    ):
        # Historical plans did not encode collection scope.  Keep them readable under the
        # generic query scope; new Structured Output always emits the explicit required bit.
        plan = replace(plan, collection_subject="query")
    if shape == "collection" and (
        plan.entity is not None
        or plan.type is not None
        or plan.filters
        or plan.link_scope is not None
        or plan.self_target is not None
        or plan.relational_reference is not None
        or plan.semantic_set is not None
        or plan.collection_subject not in {"self", "query"}
    ):
        raise RequestPlanningError(
            "Collection retrieval conflicts with direct selection",
            code=PlannerValidationCode.SELECTION_MODE_CONFLICT,
        )
    if shape == "single" and plan.collection_subject is not None:
        raise RequestPlanningError(
            "Collection subject requires collection retrieval",
            code=PlannerValidationCode.SELECTION_MODE_CONFLICT,
        )
    return RetrieveAction(plan=plan, result_shape=shape)


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
        "collection_subject",
    }
    # Plans produced before the collection-subject correction remain readable.
    # Provider output for the current contract is still closed and includes it.
    previous_required = required - {"collection_subject"}
    current_provider_required = required - {"semantic_set"}
    older_required = required - {"semantic_set", "collection_subject"}
    pre_relational_required = required - {
        "semantic_set",
        "relational_reference",
        "collection_subject",
    }
    legacy_required = {"entity", "query", "type", "filters", "link_scope"}
    legacy_minimum = {"query", "type", "filters"}
    if not isinstance(raw, dict) or (
        set(raw) != required
        and set(raw) != previous_required
        and set(raw) != current_provider_required
        and set(raw) != older_required
        and set(raw) != pre_relational_required
        and set(raw) != legacy_required
        and set(raw) != legacy_minimum
    ):
        raise RequestPlanningError(
            f"{label} fields are invalid", code=PlannerValidationCode.INVALID_SELECTION_FIELDS
        )
    entity, query, note_type, raw_filters = (
        raw.get("entity"),
        raw["query"],
        raw["type"],
        raw["filters"],
    )
    if entity is not None and (not isinstance(entity, str) or not entity.strip()):
        raise RequestPlanningError(
            f"{label} entity must be null or non-empty", code=PlannerValidationCode.INVALID_ENTITY
        )
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
        raise RequestPlanningError(
            f"{label} filters must be a list", code=PlannerValidationCode.INVALID_SELECTION_FIELDS
        )
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
        raise RequestPlanningError(
            f"{label} self_target is invalid", code=PlannerValidationCode.INVALID_SELF_TARGET
        )
    if self_target == SELF_TARGET and (entity is not None or note_type not in (None, "person")):
        raise RequestPlanningError(
            f"{label} self_target must select the direct person target",
            code=PlannerValidationCode.INVALID_SELF_TARGET,
        )
    relational = _validate_relational_reference(raw.get("relational_reference"), label=label)
    semantic_set = _validate_semantic_set_intent(
        raw.get("semantic_set"), label=label, allowed_member_types=capabilities["types"]
    )
    collection_subject = raw.get("collection_subject")
    if collection_subject not in {None, "self", "query"}:
        raise RequestPlanningError(
            f"{label} collection subject is invalid",
            code=PlannerValidationCode.INVALID_SELECTION_FIELDS,
        )
    if collection_subject is not None and label != "RetrievalPlan":
        raise RequestPlanningError(
            f"{label} collection subject requires retrieval",
            code=PlannerValidationCode.SELECTION_MODE_CONFLICT,
        )
    if relational is not None and (
        entity is not None or self_target is not None or link_scope is not None or raw_filters
    ):
        raise RequestPlanningError(
            f"{label} relational reference conflicts with direct selection",
            code=PlannerValidationCode.RELATIONAL_REFERENCE_CONFLICT,
        )
    if relational is not None and semantic_set is not None:
        raise RequestPlanningError(
            f"{label} semantic set conflicts with relational reference",
            code=PlannerValidationCode.RELATIONAL_REFERENCE_CONFLICT,
        )
    if semantic_set is not None and (
        entity is not None or self_target is not None or link_scope is not None or raw_filters
    ):
        raise RequestPlanningError(
            f"{label} semantic set conflicts with direct selection",
            code=PlannerValidationCode.SELECTION_MODE_CONFLICT,
        )
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
        collection_subject=collection_subject,
    )


def _validate_semantic_set_intent(
    raw: Any, *, label: str, allowed_member_types: Sequence[str]
) -> SemanticSetIntent | None:
    """Accept bounded set wording while rejecting planner-supplied canonical authority."""
    if raw is None:
        return None
    required = {
        "subject_kind",
        "subject_query",
        "member_query",
        "explicit_qualifiers",
        "asks_exhaustive",
    }
    if not isinstance(raw, dict) or set(raw) not in (required, required | {"member_type"}):
        raise RequestPlanningError(
            f"{label} semantic set fields are invalid",
            code=PlannerValidationCode.INVALID_SEMANTIC_SET_FIELDS,
        )
    subject_kind = raw["subject_kind"]
    subject_query = raw["subject_query"]
    member_query = raw["member_query"]
    qualifiers = raw["explicit_qualifiers"]
    exhaustive = raw["asks_exhaustive"]
    member_type = raw.get("member_type")
    if (
        subject_kind not in {"self", "query"}
        or not isinstance(member_query, str)
        or not member_query.strip()
        or not isinstance(qualifiers, str)
        or not isinstance(exhaustive, bool)
        or (member_type is not None and member_type not in allowed_member_types)
        or (subject_kind == "self" and subject_query is not None)
        or (
            subject_kind == "query"
            and (not isinstance(subject_query, str) or not subject_query.strip())
        )
    ):
        raise RequestPlanningError(
            f"{label} semantic set is invalid",
            code=PlannerValidationCode.INVALID_SEMANTIC_SET_INVARIANT,
        )
    for value in (subject_query, member_query, qualifiers):
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
            raise RequestPlanningError(
                f"{label} semantic set wording is unsafe",
                code=PlannerValidationCode.UNSAFE_SEMANTIC_SET_WORDING,
            )
    return SemanticSetIntent(
        subject_kind=subject_kind,
        subject_query=subject_query.strip() if isinstance(subject_query, str) else None,
        member_query=member_query.strip(),
        explicit_qualifiers=qualifiers.strip(),
        asks_exhaustive=exhaustive,
        member_type=member_type,
    )


def _validate_reference_selection(
    raw: Any,
    schema: Mapping[str, Any],
    capabilities: Mapping[str, Any],
) -> SelectionCriteria:
    """Validate the compact semantic lookup contract used by fact references.

    References may use the same bounded relationship anchor as a singular write target when their
    identity is defined by current canonical membership. They still cannot request graph traversal,
    direct self-binding, collection semantics, or a complete member set.
    """
    base_keys = {"entity", "query", "type", "filters"}
    if not isinstance(raw, dict) or set(raw) not in (
        base_keys,
        {*base_keys, "relational_reference"},
    ):
        raise RequestPlanningError("KnowledgeReference selection fields are invalid")
    selector = _validate_note_selector(
        {key: raw[key] for key in base_keys},
        schema,
        capabilities,
        label="KnowledgeReference selection",
    )
    relational = _validate_relational_reference(
        raw.get("relational_reference"), label="KnowledgeReference selection"
    )
    if relational is not None and relational.members != "one":
        raise RequestPlanningError(
            "KnowledgeReference relational reference must select one identity"
        )
    if relational is not None and (selector.entity is not None or selector.filters):
        raise RequestPlanningError(
            "KnowledgeReference relational reference conflicts with direct selection",
            code=PlannerValidationCode.RELATIONAL_REFERENCE_CONFLICT,
        )
    return SelectionCriteria(
        entity=selector.entity,
        query=selector.query,
        type=selector.type,
        filters=selector.filters,
        link_scope=None,
        self_target=None,
        relational_reference=relational,
        semantic_set=None,
        collection_subject=None,
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
    *,
    allow_temporal_reference_links: bool = False,
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
        _validate_knowledge_unit(
            raw,
            schema,
            retrieval_capabilities,
            write_capabilities,
            allow_temporal_reference_links=allow_temporal_reference_links,
        )
        for raw in raw_units
    )
    units = _lower_reference_selections(units)
    for index, unit in enumerate(units):
        for reference in unit.references:
            if (
                reference.target_index is None
                or reference.target_index >= len(units)
                or reference.target_index == index
            ):
                raise RequestPlanningError(
                    "KnowledgeUnit reference target is invalid",
                    code=PlannerValidationCode.INVALID_REFERENCE,
                )
    bulk_indexes = {index for index, unit in enumerate(units) if unit.cardinality == "all_matching"}
    for _index, unit in enumerate(units):
        if unit.cardinality == "all_matching" and unit.references:
            raise RequestPlanningError(
                "all_matching KnowledgeUnit cannot contain references",
                code=PlannerValidationCode.INVALID_REFERENCE,
            )
        if any(reference.target_index in bulk_indexes for reference in unit.references):
            raise RequestPlanningError(
                "KnowledgeReference cannot target an all_matching unit",
                code=PlannerValidationCode.INVALID_REFERENCE,
            )
    referenced_targets = {
        reference.target_index
        for unit in units
        for reference in unit.references
        if reference.target_index is not None
    }
    for index, unit in enumerate(units):
        has_payload = bool(
            unit.properties or unit.tag_changes or unit.facts or unit.destination_type
        )
        if unit.intent in {"amend", "remove"} and not has_payload:
            raise RequestPlanningError(
                "KnowledgeUnit amend and remove intents require mutation payload",
                code=PlannerValidationCode.INVALID_MUTATION,
            )
        if unit.intent == "record" and not has_payload and index not in referenced_targets:
            raise RequestPlanningError(
                "KnowledgeUnit record intent requires mutation payload unless referenced",
                code=PlannerValidationCode.INVALID_MUTATION,
            )
    return WriteAction(units=units)


def _lower_reference_selections(units: tuple[KnowledgeUnit, ...]) -> tuple[KnowledgeUnit, ...]:
    """Lower provider semantic reference selections into existing internal unit indexes.

    Provider output describes what a reference means. Core keeps the established execution contract
    by turning each unmatched selection into one internal existing-identity lookup unit. An exact
    same-request target is reused when it is unique, so dependency semantics remain deterministic
    without asking the model to count unit indexes.
    """
    lowered_units: list[KnowledgeUnit] = []
    synthetic_units: list[KnowledgeUnit] = []
    synthetic_selections: list[SelectionCriteria] = []

    for source_index, unit in enumerate(units):
        lowered_references: list[KnowledgeReference] = []
        for reference in unit.references:
            if reference.selection is None:
                lowered_references.append(reference)
                continue
            matching_indexes = [
                index
                for index, candidate in enumerate(units)
                if index != source_index
                and candidate.cardinality == "one"
                and candidate.target == reference.selection
            ]
            if len(matching_indexes) > 1:
                raise RequestPlanningError(
                    "KnowledgeReference selection matches multiple write units",
                    code=PlannerValidationCode.INVALID_REFERENCE,
                )
            if matching_indexes:
                target_index = matching_indexes[0]
            else:
                synthetic_offset = next(
                    (
                        index
                        for index, selection in enumerate(synthetic_selections)
                        if selection == reference.selection
                    ),
                    None,
                )
                if synthetic_offset is None:
                    synthetic_offset = len(synthetic_units)
                    synthetic_selections.append(reference.selection)
                    synthetic_units.append(
                        KnowledgeUnit(
                            target=reference.selection,
                            intent="record",
                            properties=(),
                            tag_changes=(),
                            facts=(),
                            references=(),
                            cardinality="one",
                            destination_type=None,
                            reference_lookup_only=True,
                        )
                    )
                target_index = len(units) + synthetic_offset
            lowered_references.append(
                KnowledgeReference(target_index, reference.role, reference.mention)
            )
        lowered_units.append(replace(unit, references=tuple(lowered_references)))

    return (*lowered_units, *synthetic_units)


@_validation_boundary(PlannerValidationStage.KNOWLEDGE_UNIT)
def _validate_knowledge_unit(
    unit: Any,
    schema: Mapping[str, Any],
    retrieval_capabilities: Mapping[str, Any],
    write_capabilities: Mapping[str, Any],
    *,
    allow_temporal_reference_links: bool = False,
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
    if (
        target.relational_reference is not None
        and target.relational_reference.members == "complete_set"
        and " ".join(target.query.split()).casefold()
        != " ".join(target.relational_reference.reference.split()).casefold()
    ):
        raise RequestPlanningError(
            "Complete-set relational reference must cover the complete target wording",
            code=PlannerValidationCode.RELATIONAL_REFERENCE_CONFLICT,
        )
    cardinality = unit.get("cardinality", "one")
    if cardinality not in {"one", "all_matching"}:
        raise RequestPlanningError(
            "KnowledgeUnit cardinality is invalid",
            stage=PlannerValidationStage.KNOWLEDGE_UNIT,
            code=PlannerValidationCode.INVALID_CARDINALITY,
        )
    if cardinality == "all_matching" and target.entity is not None:
        raise RequestPlanningError(
            "all_matching KnowledgeUnit target.entity must be null",
            code=PlannerValidationCode.INVALID_CARDINALITY,
        )
    if cardinality == "all_matching" and target.self_target is not None:
        raise RequestPlanningError(
            "self_target requires one direct target",
            code=PlannerValidationCode.INVALID_CARDINALITY,
        )
    if cardinality == "all_matching" and target.relational_reference is not None:
        raise RequestPlanningError(
            "relational member sets use one source unit",
            code=PlannerValidationCode.INVALID_CARDINALITY,
        )
    intent = unit["intent"]
    if intent not in WRITE_INTENTS:
        raise RequestPlanningError("KnowledgeUnit intent is invalid")

    destination_type = unit.get("destination_type")
    if destination_type is not None and destination_type not in write_capabilities["types"]:
        raise RequestPlanningError("KnowledgeUnit destination_type is invalid")
    if destination_type is not None and (cardinality != "one" or intent != "amend"):
        raise RequestPlanningError(
            "Type migration requires intent=amend and cardinality=one",
            code=PlannerValidationCode.INVALID_MUTATION,
        )

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
        raise RequestPlanningError(
            "KnowledgeUnit facts must be unique non-empty strings",
            code=PlannerValidationCode.INVALID_MUTATION,
        )
    if any("\n" in fact or "\r" in fact or "<!-- odyssey:fact" in fact for fact in raw_facts):
        raise RequestPlanningError(
            "KnowledgeUnit facts must be single-line and must not contain Odyssey fact markers",
            code=PlannerValidationCode.INVALID_MUTATION,
        )
    if intent == "delete" and (raw_properties or tag_changes or raw_facts):
        raise RequestPlanningError(
            "KnowledgeUnit delete intent requires empty properties, tag_changes, and facts",
            code=PlannerValidationCode.INVALID_MUTATION,
        )

    raw_references = unit["references"]
    if not isinstance(raw_references, list):
        raise RequestPlanningError("KnowledgeUnit references must be a list")
    references: list[KnowledgeReference] = []
    for reference in raw_references:
        if not isinstance(reference, dict):
            raise RequestPlanningError(
                "KnowledgeUnit reference is invalid",
                code=PlannerValidationCode.INVALID_REFERENCE,
            )
        keys = set(reference)
        if keys not in (
            {"target_index", "role", "mention"},
            {"selection", "role", "mention"},
        ):
            raise RequestPlanningError(
                "KnowledgeUnit reference is invalid",
                code=PlannerValidationCode.INVALID_REFERENCE,
            )
        if (
            not isinstance(reference["role"], str)
            or not reference["role"].strip()
            or not isinstance(reference["mention"], str)
            or not reference["mention"].strip()
            or "[[" in reference["mention"]
            or "]]" in reference["mention"]
        ):
            raise RequestPlanningError(
                "KnowledgeUnit reference is invalid",
                code=PlannerValidationCode.INVALID_REFERENCE,
            )
        target_index: int | None = None
        selection: SelectionCriteria | None = None
        if "target_index" in reference:
            raw_target_index = reference["target_index"]
            if (
                not isinstance(raw_target_index, int)
                or isinstance(raw_target_index, bool)
                or raw_target_index < 0
            ):
                raise RequestPlanningError(
                    "KnowledgeUnit reference is invalid",
                    code=PlannerValidationCode.INVALID_REFERENCE,
                )
            target_index = raw_target_index
        else:
            selection = _validate_reference_selection(
                reference["selection"], schema, retrieval_capabilities
            )
        references.append(
            KnowledgeReference(
                target_index=target_index,
                role=reference["role"].strip(),
                mention=reference["mention"].strip(),
                selection=selection,
            )
        )
    if any(
        reference.selection is not None and reference.selection == target
        for reference in references
    ):
        raise RequestPlanningError(
            "KnowledgeReference cannot select its own KnowledgeUnit target",
            code=PlannerValidationCode.INVALID_REFERENCE,
        )
    marker_indexes = _validate_fact_reference_markers(
        raw_facts, len(references), allow_temporal_reference_links=allow_temporal_reference_links
    )
    for reference_index in range(len(references)):
        if reference_index not in marker_indexes:
            raise RequestPlanningError(
                "KnowledgeReference has no fact occurrence marker",
                code=PlannerValidationCode.INVALID_REFERENCE,
            )
    if target.relational_reference is not None and _query_repeats_new_fact(
        target.query, raw_facts, references
    ):
        raise RequestPlanningError(
            "Relational write target query must describe only the selected subject",
            code=PlannerValidationCode.RELATIONAL_REFERENCE_CONFLICT,
        )
    return KnowledgeUnit(
        target=target,
        intent=intent,
        properties=properties,
        tag_changes=tag_changes,
        facts=tuple(_canonicalize_calendar_day_links(fact.strip()) for fact in raw_facts),
        references=tuple(references),
        cardinality=cardinality,
        destination_type=destination_type,
    )


def _query_repeats_new_fact(
    query: str, facts: Sequence[str], references: Sequence[KnowledgeReference]
) -> bool:
    """Return whether a relational target query copied the new fact payload."""
    normalized_query = " ".join(query.split()).casefold()
    for fact in facts:
        rendered = fact
        for index, reference in enumerate(references):
            rendered = rendered.replace(f"{{{{ref:{index}}}}}", reference.mention)
        normalized_fact = " ".join(rendered.split()).casefold().strip(" .!?;:")
        if len(normalized_fact) >= 8 and normalized_fact in normalized_query:
            return True
    return False


def _canonicalize_calendar_day_links(fact: str) -> str:
    """Replace provider-supplied Calendar aliases with Core's canonical date label."""
    return _CALENDAR_DAY_LINK_PATTERN.sub(
        lambda match: calendar_day_wikilink(match.group(1)),
        fact,
    )


@_validation_boundary(PlannerValidationStage.REFERENCE, PlannerValidationCode.INVALID_REFERENCE)
def _validate_fact_reference_markers(
    facts: Sequence[Any], reference_count: int, *, allow_temporal_reference_links: bool = False
) -> set[int]:
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
            if not allow_temporal_reference_links:
                raise RequestPlanningError("Planner facts must not contain Markdown wikilinks")
            remainder = fact
            for match in _CALENDAR_DAY_LINK_PATTERN.finditer(fact):
                try:
                    normalize_iso_date(match.group(1))
                except TemporalValueError as error:
                    raise RequestPlanningError(
                        "Planner Calendar Day wikilink date is invalid"
                    ) from error
            remainder = _CALENDAR_DAY_LINK_PATTERN.sub("", remainder)
            if "[[" in remainder or "]]" in remainder:
                raise RequestPlanningError(
                    "Only canonical Calendar Day wikilinks are allowed in this Core path"
                )
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
