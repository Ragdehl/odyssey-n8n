"""Non-executing source-grounded fact candidates for Router v1 (inactive).

The candidate proposal is NOT an executable RoutePlan, a Core KnowledgeUnit,
or an identity/fact-write authority. Runtime still consumes Router v0. This
closed boundary allows later provider adapters and local semantic tests without
changing today's provider prompt or canonical mutation policy.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .router import RouterError

MAX_MESSAGE_CHARS = 4096
MAX_CANDIDATES = 26
MAX_ANCHORS_PER_CANDIDATE = 8
MAX_SCOPES_PER_CANDIDATE = 16
MAX_INHERITANCE_PER_CANDIDATE = 16
MAX_ANCHOR_CHARS = 400

# Source roles are grammatical/contextual hints, never NoteSchema or Core target types.
SOURCE_ROLES = frozenset(
    {
        "subject",
        "participants",
        "predicate",
        "predicate_relation",
        "object",
        "date",
        "date_scope",
        "time",
        "time_approx",
        "time_relation",
        "location",
        "polarity",
        "condition",
        "modality",
        "order",
        "transaction",
        "reference",
        "replacement",
    }
)
CANDIDATE_KINDS = frozenset(
    {
        "occurrence",
        "property",
        "relationship",
        "purchase_item",
        "plan",
        "negative",
        "conditional",
        "task",
    }
)
CANDIDATE_STATES = frozenset({"candidate", "ambiguous_identity"})
# Candidate-level source relationships, NOT mutation or Note authorities.
SOURCE_RELATION_KINDS = frozenset(
    {
        "independent_assertion",
        "attribute_of",
        "purpose_of",
        "condition_of",
        "shared_predicate",
        "unresolved",
    }
)
DEPENDENT_SOURCE_RELATIONS = frozenset(
    {"attribute_of", "purpose_of", "condition_of", "shared_predicate"}
)


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    """Identify one exact occurrence of original user text with local offsets.

    Offsets are computed locally. No provider supplied byte/character offset can
    be used to claim provenance or canonical authority.
    """

    text: str
    occurrence: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SourceRole:
    """Attach a non-authoritative grammatical/context role to an anchored phrase."""

    role: str
    anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class SourceInheritance:
    """Describe a proposed source-context dependency, never a write dependency."""

    role: str
    from_unit: int  # 1-based request-local candidate ordinal, NOT route index.


@dataclass(frozen=True, slots=True)
class FactCandidate:
    """Carry one independently interpretable assertion and its exact source evidence."""

    candidate_id: str
    kind: str
    anchors: tuple[SourceAnchor, ...]
    scopes: tuple[SourceRole, ...]
    inheritance: tuple[SourceInheritance, ...]
    state: str


@dataclass(frozen=True, slots=True)
class CandidateSourceRelation:
    """Untrusted source-only semantic dependency, locally grounded in text."""

    unit: int  # 1-based ordinal of a candidate, not a route or Core target.
    kind: str
    parent_unit: int  # 0 means no parent; never a write dependency.
    evidence: SourceAnchor


@dataclass(frozen=True, slots=True)
class FactCandidateProposal:
    """Hold validated request-local candidates without execution or write authority."""

    source: str
    candidates: tuple[FactCandidate, ...]
    semantic_relations: tuple[CandidateSourceRelation, ...] = ()
    contract_version: int = 1


def _keys(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    """Require an exact mapping field set so extra authority cannot be smuggled in."""
    if not isinstance(value, Mapping) or set(value) != expected:
        raise RouterError(f"Invalid {label} fields")
    return value


def _bounded_array(value: Any, *, label: str, maximum: int, nonempty: bool) -> list[Any]:
    """Validate list shape and cardinality before following nested provider data."""
    if not isinstance(value, list) or len(value) > maximum or (nonempty and not value):
        raise RouterError(f"Invalid {label} count")
    return value


def _occurrence_offset(source: str, text: str, occurrence: int) -> int:
    """Return the requested exact (potentially overlapping) source occurrence."""
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text) > MAX_ANCHOR_CHARS
        or not isinstance(occurrence, int)
        or isinstance(occurrence, bool)
        or not 0 <= occurrence < MAX_MESSAGE_CHARS
    ):
        raise RouterError("Invalid source anchor")
    start = -1
    for _ in range(occurrence + 1):
        start = source.find(text, start + 1)
        if start < 0:
            raise RouterError("Source anchor does not match requested occurrence")
    return start


def resolve_source_anchor(source: str, raw: Mapping[str, Any]) -> SourceAnchor:
    """Resolve the provider's text + occurrence through immutable original source."""
    anchor = _keys(raw, {"text", "occurrence"}, label="source anchor")
    text = anchor["text"]
    ordinal = anchor["occurrence"]
    start = _occurrence_offset(source, text, ordinal)
    return SourceAnchor(text=text, occurrence=ordinal, start=start, end=start + len(text))


def _anchored_candidate(source: str, raw: Mapping[str, Any], index: int) -> FactCandidate:
    """Validate one proposed semantic unit without inferring identities or dates."""
    raw = _keys(
        raw,
        {"kind", "anchors", "scoped_source", "inheritance", "state"},
        label="candidate",
    )
    kind, state = raw["kind"], raw["state"]
    if (
        not isinstance(kind, str)
        or not isinstance(state, str)
        or kind not in CANDIDATE_KINDS
        or state not in CANDIDATE_STATES
    ):
        raise RouterError("Unknown fact-candidate kind or state")
    anchors = tuple(
        resolve_source_anchor(source, item)
        for item in _bounded_array(
            raw["anchors"],
            label="source anchors",
            maximum=MAX_ANCHORS_PER_CANDIDATE,
            nonempty=True,
        )
    )
    if len({(a.start, a.end) for a in anchors}) != len(anchors):
        raise RouterError("Duplicated source anchor on one fact candidate")
    scopes: list[SourceRole] = []
    for item in _bounded_array(
        raw["scoped_source"],
        label="scopes",
        maximum=MAX_SCOPES_PER_CANDIDATE,
        nonempty=False,
    ):
        scope = _keys(item, {"role", "anchor"}, label="scope")
        role = scope["role"]
        if not isinstance(role, str) or role not in SOURCE_ROLES:
            raise RouterError("Unknown source context role")
        scopes.append(SourceRole(role, resolve_source_anchor(source, scope["anchor"])))
    # One original word span cannot independently be both the event verb
    # and its event object/qualifier. An LLM can cite an exact substring yet
    # assign an incoherent role; never repair this by guessing source words.
    predicates = {(r.anchor.start, r.anchor.end) for r in scopes if r.role == "predicate"}
    complements = {
        (r.anchor.start, r.anchor.end) for r in scopes if r.role in {"object", "transaction"}
    }
    if predicates & complements:
        raise RouterError("Contradictory predicate and complement source roles")
    inheritance: list[SourceInheritance] = []
    for item in _bounded_array(
        raw["inheritance"],
        label="inheritance",
        maximum=MAX_INHERITANCE_PER_CANDIDATE,
        nonempty=False,
    ):
        dependency = _keys(item, {"role", "from_unit"}, label="inheritance")
        role, predecessor = dependency["role"], dependency["from_unit"]
        if not isinstance(role, str) or role not in SOURCE_ROLES:
            raise RouterError("Unknown inherited context role")
        # This initial v1 representation inherits from earlier units. A later
        # shared lexical scope may itself point backward in the source string.
        if (
            not isinstance(predecessor, int)
            or isinstance(predecessor, bool)
            or not 1 <= predecessor < index
        ):
            raise RouterError("Invalid source dependency: predecessor must be earlier")
        inheritance.append(SourceInheritance(role, predecessor))
    if len({(edge.role, edge.from_unit) for edge in inheritance}) != len(inheritance):
        raise RouterError("Duplicate source-context inheritance")
    return FactCandidate(
        candidate_id=f"candidate-{index}",
        kind=kind,
        anchors=anchors,
        scopes=tuple(scopes),
        inheritance=tuple(inheritance),
        state=state,
    )


def validate_fact_candidate_proposal(
    source: str, payload: Mapping[str, Any]
) -> FactCandidateProposal:
    """Fail closed on ungrounded, ambiguous-shaped, or authority-bearing proposals.

    Args:
        source: The unchanged current user message, not a prior conversation turn.
        payload: Closed semantic-unit JSON generated by an untrusted interpreter.

    Returns:
        Validated request-local candidates with locally resolved source offsets.

    Raises:
        RouterError: When the input, any source occurrence, role, predecessor, or
            proposal field is malformed. Nothing is executed or persisted.
    """
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_MESSAGE_CHARS:
        raise RouterError("Fact source request is invalid or too long")
    envelope = _keys(payload, {"version", "units"}, label="fact candidate proposal")
    if type(envelope["version"]) is not int or envelope["version"] != 1:
        raise RouterError("Unsupported fact candidate proposal version")
    rows = _bounded_array(
        envelope["units"], label="fact candidates", maximum=MAX_CANDIDATES, nonempty=True
    )
    units = tuple(
        _anchored_candidate(source, item, index) for index, item in enumerate(rows, start=1)
    )
    # A model may repeat an identical proposed assertion as a separate unit.
    # Source sharing is valid (F09/F11), but exact same-kind/state/evidence
    # repetition has no independently grounded identity and cannot authorize
    # double accounting downstream. Repeated *source occurrences* stay distinct.
    signatures = {
        (
            unit.kind,
            unit.state,
            tuple(sorted((anchor.start, anchor.end) for anchor in unit.anchors)),
            tuple(sorted((role.role, role.anchor.start, role.anchor.end) for role in unit.scopes)),
            tuple(sorted((edge.role, edge.from_unit) for edge in unit.inheritance)),
        )
        for unit in units
    }
    if len(signatures) != len(units):
        raise RouterError("Duplicate fact candidates for identical source evidence")
    return FactCandidateProposal(source, units)


def validate_semantic_fact_candidate_proposal(
    source: str, payload: Mapping[str, Any]
) -> FactCandidateProposal:
    """Validate v2 source semantics without trusting them to authorize writes.

    The v1 validator and all historical model receipts remain untouched.
    Dependencies refer only to prior source candidate ordinals; no forward
    guessing or cross-request source identity is possible.
    """
    envelope = _keys(
        payload, {"version", "units", "semantic_relations"}, label="semantic candidate proposal"
    )
    if type(envelope["version"]) is not int or envelope["version"] != 2:
        raise RouterError("Unsupported semantic candidate proposal version")
    original = validate_fact_candidate_proposal(source, {"version": 1, "units": envelope["units"]})
    rows = _bounded_array(
        envelope["semantic_relations"],
        label="source semantic relations",
        maximum=MAX_CANDIDATES,
        nonempty=True,
    )
    if len(rows) != len(original.candidates):
        raise RouterError("Semantic relations must cover every source candidate")
    relations = []
    for expected_unit, raw in enumerate(rows, start=1):
        relation = _keys(
            raw,
            {"unit", "kind", "parent_unit", "evidence"},
            label="semantic relation",
        )
        kind, parent, unit = relation["kind"], relation["parent_unit"], relation["unit"]
        if (
            type(unit) is not int
            or unit != expected_unit
            or not isinstance(kind, str)
            or kind not in SOURCE_RELATION_KINDS
            or type(parent) is not int
            or not 0 <= parent < unit
            or (
                (kind == "independent_assertion" and parent != 0)
                or (kind in DEPENDENT_SOURCE_RELATIONS and parent == 0)
            )
        ):
            raise RouterError("Semantic relation is not source-grounded or acyclic")
        evidence = resolve_source_anchor(source, relation["evidence"])
        own = original.candidates[unit - 1]
        if (evidence.start, evidence.end) not in {
            (a.start, a.end) for a in (*own.anchors, *(s.anchor for s in own.scopes))
        }:
            raise RouterError("Semantic relation witness is not grounded in its own candidate")
        relations.append(CandidateSourceRelation(unit, kind, parent, evidence))
    return FactCandidateProposal(
        original.source,
        original.candidates,
        tuple(relations),
        contract_version=2,
    )


def semantic_fact_candidate_json_schema() -> dict[str, Any]:
    """Strict opt-in v2 provider schema; v1 remains byte-for-byte unchanged."""
    schema = fact_candidate_json_schema()
    relation = {
        "type": "object",
        "properties": {
            "unit": {"type": "integer", "minimum": 1, "maximum": MAX_CANDIDATES},
            "kind": {"type": "string", "enum": sorted(SOURCE_RELATION_KINDS)},
            "parent_unit": {"type": "integer", "minimum": 0, "maximum": MAX_CANDIDATES},
            "evidence": schema["properties"]["units"]["items"]["properties"]["anchors"]["items"],
        },
        "required": ["unit", "kind", "parent_unit", "evidence"],
        "additionalProperties": False,
    }
    schema["properties"]["version"]["enum"] = [2]
    schema["properties"]["semantic_relations"] = {
        "type": "array",
        "items": relation,
        "minItems": 1,
        "maxItems": MAX_CANDIDATES,
    }
    schema["required"].append("semantic_relations")
    return schema


def fact_candidate_json_schema() -> dict[str, Any]:
    """Build a strict structured-output proposal schema, without Core write fields."""
    anchor = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "maxLength": MAX_ANCHOR_CHARS},
            "occurrence": {"type": "integer", "minimum": 0},
        },
        "required": ["text", "occurrence"],
        "additionalProperties": False,
    }
    scoped = {
        "type": "object",
        "properties": {"role": {"type": "string", "enum": sorted(SOURCE_ROLES)}, "anchor": anchor},
        "required": ["role", "anchor"],
        "additionalProperties": False,
    }
    edge = {
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": sorted(SOURCE_ROLES)},
            "from_unit": {"type": "integer", "minimum": 1},
        },
        "required": ["role", "from_unit"],
        "additionalProperties": False,
    }
    unit = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": sorted(CANDIDATE_KINDS)},
            "anchors": {
                "type": "array",
                "items": anchor,
                "minItems": 1,
                "maxItems": MAX_ANCHORS_PER_CANDIDATE,
            },
            "scoped_source": {
                "type": "array",
                "items": scoped,
                "maxItems": MAX_SCOPES_PER_CANDIDATE,
            },
            "inheritance": {
                "type": "array",
                "items": edge,
                "maxItems": MAX_INHERITANCE_PER_CANDIDATE,
            },
            "state": {"type": "string", "enum": sorted(CANDIDATE_STATES)},
        },
        "required": ["kind", "anchors", "scoped_source", "inheritance", "state"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "version": {"type": "integer", "enum": [1]},
            "units": {"type": "array", "items": unit, "minItems": 1, "maxItems": MAX_CANDIDATES},
        },
        "required": ["version", "units"],
        "additionalProperties": False,
    }


def _inherited_source_anchor(
    proposal: FactCandidateProposal, edge: SourceInheritance
) -> SourceAnchor | None:
    """Follow only same-role original text across source-context inheritance.

    A role transition like report subject -> message object stays in the validated
    candidate plan but is not presented as a verified or direct same-role link.
    """
    prior = proposal.candidates[edge.from_unit - 1]
    for scope in prior.scopes:
        if scope.role == edge.role:
            return scope.anchor
    for earlier in prior.inheritance:
        if earlier.role == edge.role:
            return _inherited_source_anchor(proposal, earlier)
    return None


def as_candidate_preview(proposal: FactCandidateProposal) -> dict[str, Any]:
    """Project source-grounded candidates for the *local-only* existing preview.

    Only the browser's preview subset of roles is shown. This projection does NOT
    enter normal request_detail or indicate a verified Core identity or saved note.
    """
    allowed = {
        "subject",
        "participants",
        "object",
        "location",
        "time",
        "date",
        "predicate",
        "condition",
    }
    candidates = []
    for item in proposal.candidates:
        roles = [
            {
                "role": scope.role,
                "source": scope.anchor.text[:160],
                "occurrence": scope.anchor.occurrence,
                "provenance": "explicit",
                "authority": None,
            }
            for scope in item.scopes
            if scope.role in allowed and len(scope.anchor.text) <= 160
        ]
        explicit_roles = {scope.role for scope in item.scopes}
        for edge in item.inheritance:
            if edge.role not in allowed or edge.role in explicit_roles:
                continue
            original = _inherited_source_anchor(proposal, edge)
            if original is not None and len(original.text) <= 160:
                roles.append(
                    {
                        "role": edge.role,
                        "source": original.text,
                        "occurrence": original.occurrence,
                        "provenance": "inherited",
                        "authority": None,
                    }
                )
        roles = roles[:8]
        first = next((a for a in item.anchors if len(a.text) <= 240), None)
        if first is None or not roles:
            continue
        candidates.append(
            {
                "id": item.candidate_id,
                "source": first.text,
                "occurrence": first.occurrence,
                "roles": roles,
                "dependency_target": None,
            }
        )
    return {"version": 1, "user_message": proposal.source, "candidates": candidates}


# Proposed v2 model teaching is opt-in and preserves every v1 instruction.
# A clean local/provider gate must precede changing any runtime default.
FACT_CANDIDATE_PROMPT_V2_EXTENSION = (
    " Additional v2 source-semantics rules: Split independent properties "
    "by their subjects even when one plural verb/predicate is shared: "
    "each fact must be independently correctable for that subject. "
    "For example, 'El coche y la moto están en el garaje' expresses two "
    "independent location properties, each with its own subject source "
    "anchor and an exact shared predicate source role. By contrast, "
    "'Ana y Bea se conocieron' expresses ONE mutual relationship event, "
    "not two independent meeting events. A single coherent action with "
    "two named participants is ONE occurrence, retaining each separately "
    "identifiable original name as source evidence; explicit sequencing "
    "like 'después con' produces TWO occurrences. Never infer simultaneity. "
    "Use role 'date' for exact lexical calendar days (ayer, hoy, mañana, "
    "named weekdays or concrete dates), NOT 'time' or 'date_scope'; "
    "use 'time' for clock/daypart phrases and 'time_approx' for approximate "
    "times. Never compute or rewrite a date: cite original literal spans. "
    "Use role 'reference' for pronouns such as él, ella, ellos, ellas "
    "in source, even when they are grammatical participants; keep "
    "ambiguous_identity if multiple people remain plausible. Explicit "
    "named participants retain the 'participants' role and exact original "
    "name spans, distinct from an unresolved pronoun reference. "
    "A forthcoming described activity or event ('mañana iré ...') is "
    "'occurrence' at the source segmentation layer; use 'plan' only when "
    "the assertion itself describes a proposal, intention, uncertainty "
    "or a planning decision rather than an event being described. "
    "Each independent candidate should anchor its own subject, object "
    "or action span, while shared predicates/dates are cited through "
    "exact scoped_source or typed inheritance; do not collapse multiple "
    "subjects into one 'relationship' merely because they share grammar. "
    "Keep source quotations minimal and contiguous when possible, "
    "without creating new content, identity links, or Core writing policy."
)


FACT_CANDIDATE_PROMPT_V3_EXTENSION = (
    " Additional kind decision rule: The JSON kind 'relationship' is for "
    "one mutual or reciprocal relationship fact between two parties, "
    "including one-time mutual encounters expressed as reciprocal verbs. "
    "For example 'Julia y Pedro se conocieron en Sevilla' is exactly ONE "
    "candidate with kind='relationship', NOT kind='occurrence'. "
    "By contrast 'Julia habló con Pedro y Ana' describes ONE speech "
    "occurrence with two conversation participants, NOT a relationship "
    "between those two participants. 'Julia y Pedro viven en Sevilla' "
    "describes TWO independent property candidates, not a relationship. "
    "Semantic kind depends on whether the statement asserts a link "
    "between the people, independently of the verb's tense or duration. "
    "All source roles, ambiguity and exact original quoting rules remain "
    "unchanged; never create canonical identities, plans, or writes."
)


# New opt-in extension; V3 remains byte-for-byte immutable for all existing
# frozen provider contracts and their hash-pinned model-budget regressions.
FACT_CANDIDATE_PROMPT_V4_EXTENSION = (
    "Predicate/verb source text is NOT a transaction qualifier or object. "
    "For a purchase, cite the verb only as predicate; label independently "
    "quoted noun phrases or distinct qualifiers as object or transaction. "
    "A transaction qualifier is optional when the object already contains "
    "the full relevant qualification. Never reuse an identical source span "
    "both as predicate and transaction/object, or invent extra source roles. "
)


# Experimental semantic classification improvement. V4 remains byte-for-byte
# unchanged so prior model receipts and all historical gates are comparable.
# Router still cannot select Note types or authorize a Core write.
FACT_CANDIDATE_PROMPT_V5_EXTENSION = (
    " General source-meaning safeguards for the CURRENT message: "
    "A source-level TASK is an intended user-owned action to track, perform, "
    "schedule or remember, including terse infinitive TODOs and imperatives. "
    "A descriptive state of an existing thing requiring maintenance, repair, "
    "painting or another intervention is a PROPERTY/need of that thing, "
    "NOT automatically an instruction to create a task, unless the speaker "
    "is actually asking for that action to be tracked or performed. "
    "Never infer an app command from the mere presence of an infinitive "
    "or a need/requirement verb. Keep the explicit source modality separately "
    "without converting it into a to-do lifecycle. "
    "Object pronouns can refer to preceding named entities just as subject "
    "pronouns do: preserve the exact source span as both its grammatical "
    "object role and a 'reference' role whenever the word actually refers "
    "back to an entity (in any language). Keep the source role and literal "
    "offset; never substitute a guessed canonical name. If more than one "
    "plausible referent remains, mark that candidate ambiguous_identity. "
    "If the original source has one unambiguous explicit antecedent, mark "
    "the candidate 'candidate', not ambiguous_identity, but leave Core to "
    "prove canonical binding before writing. Never inherit the OLD subject "
    "as the NEW grammatical subject when a reference changes its role. "
    "For explicit denial of an event, classify negative meaning as kind "
    "'negative' rather than a positive occurrence with a decorative "
    "polarity. A coordinated positive counterstatement after a denial is "
    "an independent affirmative candidate; keep its positive predicate, "
    "actor/object and any inherited day separately, and preserve the "
    "source contrast in exact scope roles when warranted. "
    "Always anchor actual predicate/object or subject words independently. "
    "Do not let task names, clause grouping or canonical identity decisions "
    "leak into the Router candidate classification."
)


FACT_CANDIDATE_PROMPT_V6_EXTENSION = (
    " For each candidate, additionally return exactly one semantic_relations entry "
    "for strict JSON version 2. Classify whether this is an independent assertion "
    "or a source attribute/purpose/condition/shared predicate of an EARLIER "
    "candidate. For a dependent relation use the earlier source-unit index, "
    "not a Core write dependency or canonical identity. Use parent_unit 0 "
    "ONLY for independent_assertion or unresolved without a proven parent. "
    "Keep qualifiers, subordinate aims, circumstances and descriptors attached "
    "to their parent assertion even if they contain a verb or a date; do not "
    "promote them merely because words can be quoted separately. "
    "Preserve genuinely independent statements, including clauses sharing a "
    "predicate, as separate candidates where needed, and express their shared "
    "lexical scope as shared_predicate. If the relation is uncertain mark "
    "unresolved; never guess a canonical target, app instruction or Markdown. "
    "The evidence field must exactly repeat one anchor or scope quotation "
    "from that candidate with the same occurrence index; return one relation "
    "per candidate ordered by its 1-based unit index. "
    "These are SOURCE-ONLY proposals, not route permissions or explanations."
)


class OpenAIFactCandidateRouter:
    """Opt-in, non-executing Router v1 proposal adapter with an injected provider.

    It is intentionally NOT used by ``odyssey_runtime.routing``. A live model
    regression and reviewed adapter to Temporal/Core must precede activation.
    """

    def __init__(self, client: Any, *, prompt_revision: str = "v1") -> None:
        """Select a reviewed source-only teaching revision without changing Router v0."""
        if prompt_revision not in {"v1", "v2", "v3", "v4", "v5", "v6"}:
            raise ValueError("Unknown fact-candidate prompt revision")
        self._client = client
        self._prompt_revision = prompt_revision
        self.last_usage: Any | None = None
        self.last_error_category: str | None = None

    def propose(
        self,
        source: str,
        *,
        boundary_feedback: object | None = None,
    ) -> FactCandidateProposal:
        """Ask Luna once for source-only proposed units, then fail closed locally.

        Args:
            source: Complete unchanged current message. Conversation and personal
                Notes are intentionally not supplied in this v1 interpretation.

        Returns:
            Non-executable, source-anchored candidates, NOT Router v0 routes.

        Raises:
            RouterError: Invalid source, provider error, malformed output or
                failed local source validation. No write or route is attempted.
        """
        if not isinstance(source, str) or not source.strip() or len(source) > MAX_MESSAGE_CHARS:
            raise RouterError("Fact source request is invalid or too long")
        from .router import ROUTER_MODEL, ROUTER_REASONING_EFFORT

        revision_instruction = ""
        if boundary_feedback is not None:
            from odyssey_core.source_boundary_review import (
                BOUNDARY_REVIEW_REASONS,
                CoreSourceBoundaryReview,
            )

            if (
                self._prompt_revision != "v6"
                or not isinstance(boundary_feedback, CoreSourceBoundaryReview)
                or boundary_feedback.decision != "revise"
                or type(boundary_feedback.boundary_index) is not int
                or not 1 <= boundary_feedback.boundary_index < MAX_CANDIDATES
                or boundary_feedback.reason not in BOUNDARY_REVIEW_REASONS
                or boundary_feedback.source_digest
                != hashlib.sha256(source.encode("utf-8")).hexdigest()
            ):
                raise RouterError("Unverified Core boundary feedback cannot revise Router")
            # Only an enum and ordinal, not a free-form prompt or internal
            # reasoning. The dispatcher binds the partition digest separately.
            revision_instruction = (
                " Reconsider the source segmentation at proposed route boundary "
                f"{boundary_feedback.boundary_index}: "
                f"{boundary_feedback.reason}. Preserve every independent "
                "assertion and all exact source anchors. Do not discard "
                "dependent content, invent units, change the original message, "
                "or supply canonical write instructions. This is the one "
                "permitted correction attempt; return complete source v2 JSON."
            )

        self.last_usage = None
        self.last_error_category = None
        try:
            reply = self._client.responses.create(
                model=ROUTER_MODEL,
                reasoning={"effort": ROUTER_REASONING_EFFORT},
                store=False,
                max_output_tokens=4096,
                input=[
                    {
                        "role": "system",
                        "content": (
                            (
                                "Interpret only the original CURRENT request as source-grounded "
                                "semantic units, including dependent attributes, circumstances "
                                "and purposes. "
                                if self._prompt_revision == "v6"
                                else "Interpret only the original CURRENT request as independently manageable "
                                "semantic fact candidates. "
                            )
                            + "Return strict JSON version "
                            + ("2" if self._prompt_revision == "v6" else "1")
                            + ". Each candidate "
                            "uses one or more original exact quoted substrings as anchors, with "
                            "zero-based occurrence indices for duplicate substrings. No rewriting of "
                            "source, invented text or resolved Note identity. Source roles are only "
                            "grammatical/context scopes; they are NOT Core targets, canonical fact "
                            "types, or proof of identity. Preserve shared or omitted source context "
                            "as typed inheritance from EARLIER semantic units, using one-based "
                            "unit indices; inherited source context is NOT a Core write dependency. "
                            "A later source phrase may supply time/date wording to an earlier unit: "
                            "anchor it to its actual position, never convert it to an ISO date. "
                            "Keep polarity, condition, correction, modality, transaction, object, "
                            "and participants independently scoped. Mutual relationships form one "
                            "unit; independent properties and purchase items may form separate units "
                            "while sharing a transaction. Mark ambiguous_identity where a referent "
                            "cannot be safely established from the source. Do not select NoteSchema "
                            "types, create Notes, plan Core writes, bind identities, execute apps, "
                            "normalize dates, or return Markdown."
                        )
                        + (
                            FACT_CANDIDATE_PROMPT_V2_EXTENSION
                            if self._prompt_revision in {"v2", "v3", "v4", "v5", "v6"}
                            else ""
                        )
                        + (
                            FACT_CANDIDATE_PROMPT_V3_EXTENSION
                            if self._prompt_revision in {"v3", "v4", "v5", "v6"}
                            else ""
                        )
                        + (
                            FACT_CANDIDATE_PROMPT_V4_EXTENSION
                            if self._prompt_revision in {"v4", "v5", "v6"}
                            else ""
                        )
                        + (
                            FACT_CANDIDATE_PROMPT_V5_EXTENSION
                            if self._prompt_revision in {"v5", "v6"}
                            else ""
                        )
                        + (
                            FACT_CANDIDATE_PROMPT_V6_EXTENSION
                            if self._prompt_revision == "v6"
                            else ""
                        )
                        + revision_instruction,
                    },
                    {"role": "user", "content": source},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": (
                            "odyssey_fact_candidate_proposal_v2"
                            if self._prompt_revision == "v6"
                            else "odyssey_fact_candidate_proposal_v1"
                        ),
                        "strict": True,
                        "schema": (
                            semantic_fact_candidate_json_schema()
                            if self._prompt_revision == "v6"
                            else fact_candidate_json_schema()
                        ),
                    }
                },
            )
        except Exception as error:
            self.last_error_category = type(error).__name__[:100]
            raise RouterError("Fact candidate provider call failed") from error
        self.last_usage = getattr(reply, "usage", None)
        if getattr(reply, "status", None) != "completed":
            self.last_error_category = "IncompleteProviderResponse"
            raise RouterError("Fact candidate response incomplete")
        try:
            import json

            raw = json.loads(reply.output_text)
        except (TypeError, ValueError, AttributeError) as error:
            self.last_error_category = "MalformedProviderJSON"
            raise RouterError("Fact candidate output is not valid JSON") from error
        try:
            if self._prompt_revision == "v6":
                return validate_semantic_fact_candidate_proposal(source, raw)
            return validate_fact_candidate_proposal(source, raw)
        except (RouterError, TypeError, ValueError) as error:
            self.last_error_category = "InvalidSourceEvidence"
            raise RouterError("Fact candidate output lacks grounded source evidence") from error

    def revise(self, source: str, feedback: object) -> FactCandidateProposal:
        """One revised untrusted proposal; ONLY the dispatcher sets retry cap."""
        if self._prompt_revision != "v6":
            raise RouterError("Source boundary revision is opt-in v6 only")
        return self.propose(source, boundary_feedback=feedback)
