"""Bounded, Markdown-grounded semantic set selection for one canonical anchor."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from odyssey_core.identity_boundary import (
    AuthenticatedActorContext,
    SelfBindingError,
    SelfBindingRepository,
)
from odyssey_core.relationship_evidence import (
    CanonicalFact,
    EvidenceDirection,
    RelationshipEvidenceError,
    RelationshipEvidenceProjector,
)
from odyssey_core.request_planning import SemanticSetIntent
from odyssey_core.resolution import ExistingEntityOutcome, ExistingEntityResolution
from odyssey_core.storage import VaultRepository

# The candidate payload stays within the established 16 KiB note-result snapshot ceiling.  Sixty-four
# facts and members bound adversarial fragmentation while still exceeding normal retrieval limits.
MAX_SEMANTIC_SET_SOURCE_NOTES = 16
MAX_SEMANTIC_SET_FACTS = 64
MAX_SEMANTIC_SET_SOURCE_BYTES = 16 * 1024
MAX_SEMANTIC_SET_MEMBERS = 64

_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]+)?\]\]")


class SemanticSetOutcome(StrEnum):
    """Describe a bounded semantic-set resolution outcome without final prose."""

    ANSWERABLE = "ANSWERABLE"
    AMBIGUOUS_REFERENCE = "AMBIGUOUS_REFERENCE"
    AMBIGUOUS_SET_SCOPE = "AMBIGUOUS_SET_SCOPE"
    INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"
    NO_RELEVANT_EVIDENCE = "NO_RELEVANT_EVIDENCE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    OPERATIONAL_FAILURE = "OPERATIONAL_FAILURE"


class SemanticSetCompleteness(StrEnum):
    """State what the validated canonical scan establishes about a returned set."""

    COMPLETE_WITHIN_SCANNED_SCOPE = "COMPLETE_WITHIN_SCANNED_SCOPE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN_SCOPE = "UNKNOWN_SCOPE"


@dataclass(frozen=True, slots=True)
class SemanticSetBounds:
    """Set explicit deterministic scan and output ceilings for semantic-set evidence."""

    source_notes: int = MAX_SEMANTIC_SET_SOURCE_NOTES
    facts: int = MAX_SEMANTIC_SET_FACTS
    source_bytes: int = MAX_SEMANTIC_SET_SOURCE_BYTES
    members: int = MAX_SEMANTIC_SET_MEMBERS


DEFAULT_SEMANTIC_SET_BOUNDS = SemanticSetBounds()


@dataclass(frozen=True, slots=True)
class SemanticSetCandidate:
    """Expose an opaque candidate ID paired with Core-owned canonical provenance."""

    id: str
    fact: CanonicalFact
    direction: EvidenceDirection


@dataclass(frozen=True, slots=True)
class SemanticSetCandidateView:
    """Expose only an opaque ID and visible fact text to the selector boundary."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class SetMemberOccurrence:
    """Identify one exact candidate-fact text or link occurrence selected by a selector."""

    candidate_id: str
    kind: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SetEvidenceSelection:
    """Represent a bounded selector proposal expressed only in supplied candidate IDs."""

    supplied_fact_ids: tuple[str, ...]
    member_occurrences: tuple[SetMemberOccurrence, ...]
    scope_uncertain: bool = False


@dataclass(frozen=True, slots=True)
class SemanticSetSelectionRequest:
    """Supply a selector with bounded candidate wording and no canonical identity authority."""

    intent: SemanticSetIntent
    candidates: tuple[SemanticSetCandidateView, ...]


class SemanticSetSelector(Protocol):
    """Describe the injectable selection boundary for current bounded candidate facts."""

    def select(self, request: SemanticSetSelectionRequest) -> SetEvidenceSelection:
        """Choose supplied candidate occurrences or declare semantic scope uncertainty."""


@dataclass(frozen=True, slots=True)
class SetEvidenceProvenance:
    """Preserve enough current canonical information to re-ground one returned member."""

    source_note_id: str
    fact_locator: str
    source_hash: str
    start: int
    end: int
    kind: str


@dataclass(frozen=True, slots=True)
class IdentitySetMember:
    """Represent a member grounded by one validated literal wikilink occurrence."""

    stable_id: str
    evidence: SetEvidenceProvenance


@dataclass(frozen=True, slots=True)
class LiteralSetMember:
    """Represent a member grounded by exact visible canonical fact text."""

    value: str
    evidence: SetEvidenceProvenance


SetMember = IdentitySetMember | LiteralSetMember


@dataclass(frozen=True, slots=True)
class GroundedSemanticSet:
    """Return one anchor's re-grounded members and the declared scan completeness."""

    anchor_stable_id: str
    members: tuple[SetMember, ...]
    completeness: SemanticSetCompleteness
    scanned_source_note_count: int
    scanned_fact_count: int
    serialized_source_bytes: int


@dataclass(frozen=True, slots=True)
class SemanticSetResolution:
    """Return a structured semantic-set outcome without exposing selector internals."""

    outcome: SemanticSetOutcome
    grounded_set: GroundedSemanticSet | None = None
    candidate_count: int = 0
    reason: str | None = None


def enumerate_semantic_set_candidates(
    projector: RelationshipEvidenceProjector, anchor_id: str, *, bounds: SemanticSetBounds
) -> tuple[SemanticSetCandidate, ...] | SemanticSetResolution:
    """Enumerate every direct and literal one-hop incoming candidate before selection.

    The projector rereads canonical Markdown. Any exceeded limit returns an incomplete result before
    a selector can see a truncated scope.
    """
    try:
        direct = tuple(
            SemanticSetCandidate("", fact, EvidenceDirection.DIRECT)
            for fact in projector.facts_for_source(anchor_id)
        )
        projection = projector.project_entity_evidence_candidates(anchor_id)
    except RelationshipEvidenceError:
        return SemanticSetResolution(
            SemanticSetOutcome.OPERATIONAL_FAILURE, reason="canonical_scan"
        )
    if projection is None:
        return SemanticSetResolution(
            SemanticSetOutcome.AMBIGUOUS_REFERENCE, reason="anchor_missing"
        )
    incoming = tuple(
        SemanticSetCandidate("", item.fact, EvidenceDirection.INCOMING)
        for item in projection.incoming
    )
    unique: dict[tuple[str, str], SemanticSetCandidate] = {}
    for item in (*direct, *incoming):
        unique.setdefault((item.fact.source.id, item.fact.locator), item)
    ordered = tuple(
        sorted(unique.values(), key=lambda item: (item.fact.source.path, item.fact.locator))
    )
    sources = {item.fact.source.id for item in ordered}
    serialized = sum(
        len(
            (item.fact.source.id + "\0" + item.fact.locator + "\0" + item.fact.text).encode("utf-8")
        )
        for item in ordered
    )
    if (
        len(sources) > bounds.source_notes
        or len(ordered) > bounds.facts
        or serialized > bounds.source_bytes
    ):
        return SemanticSetResolution(
            SemanticSetOutcome.INCOMPLETE_EVIDENCE,
            candidate_count=len(ordered),
            reason="candidate_scope_bound",
        )
    return tuple(
        SemanticSetCandidate(f"candidate-{index}", item.fact, item.direction)
        for index, item in enumerate(ordered)
    )


def resolve_semantic_set(
    intent: SemanticSetIntent,
    *,
    anchor_id: str,
    repository: VaultRepository,
    schema: dict,
    selector: SemanticSetSelector,
    bounds: SemanticSetBounds = DEFAULT_SEMANTIC_SET_BOUNDS,
) -> SemanticSetResolution:
    """Select and re-ground one bounded semantic set for an already resolved canonical anchor.

    Args:
        intent: Planner wording with no canonical IDs or fact locators.
        anchor_id: Core-resolved stable identity for the one source anchor.
        repository: Authoritative Markdown repository.
        schema: Active canonical note schema.
        selector: Injected candidate-only semantic selection boundary.
        bounds: Explicit scan and result ceilings.

    Returns:
        A grounded set or a fail-closed structured outcome.
    """
    if not isinstance(anchor_id, str) or not anchor_id:
        raise ValueError("Semantic-set anchor ID must be non-empty")
    projector = RelationshipEvidenceProjector(repository, schema)
    candidates = enumerate_semantic_set_candidates(projector, anchor_id, bounds=bounds)
    if isinstance(candidates, SemanticSetResolution):
        return candidates
    if not candidates:
        return SemanticSetResolution(SemanticSetOutcome.NO_RELEVANT_EVIDENCE)
    try:
        selection = selector.select(
            SemanticSetSelectionRequest(
                intent,
                tuple(
                    SemanticSetCandidateView(candidate.id, candidate.fact.text)
                    for candidate in candidates
                ),
            )
        )
        _validate_selection(selection, candidates, bounds)
    except (TypeError, ValueError):
        return SemanticSetResolution(
            SemanticSetOutcome.OPERATIONAL_FAILURE, reason="invalid_selection"
        )
    if selection.scope_uncertain:
        return SemanticSetResolution(
            SemanticSetOutcome.AMBIGUOUS_SET_SCOPE,
            candidate_count=len(candidates),
        )
    if not selection.member_occurrences:
        return SemanticSetResolution(
            SemanticSetOutcome.NO_RELEVANT_EVIDENCE,
            candidate_count=len(candidates),
        )
    grounded = _ground_selection(projector, anchor_id, candidates, selection, bounds)
    if isinstance(grounded, SemanticSetResolution):
        return grounded
    return SemanticSetResolution(
        SemanticSetOutcome.ANSWERABLE,
        grounded,
        candidate_count=len(candidates),
    )


def serialize_semantic_set_candidate_payload(
    intent: SemanticSetIntent, candidates: Sequence[SemanticSetCandidate]
) -> bytes:
    """Serialize the exact selector-visible candidate payload for deterministic budget evidence."""
    return json.dumps(
        {
            "anchor_kind": intent.anchor_kind,
            "anchor_query": intent.anchor_query,
            "group_query": intent.group_query,
            "explicit_qualifiers": intent.explicit_qualifiers,
            "asks_exhaustive": intent.asks_exhaustive,
            "candidates": [{"id": item.id, "text": item.fact.text} for item in candidates],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def resolve_semantic_set_anchor(
    intent: SemanticSetIntent,
    *,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    existing_resolver: Callable[[str], ExistingEntityResolution],
) -> tuple[SemanticSetOutcome, str | None]:
    """Resolve a self or existing intent anchor through existing identity authority."""
    if intent.anchor_kind == "self":
        if authenticated_actor is None or self_binding_repository is None:
            return SemanticSetOutcome.AMBIGUOUS_REFERENCE, None
        try:
            return (
                SemanticSetOutcome.ANSWERABLE,
                self_binding_repository.resolve(authenticated_actor.stable_user_id).person_note_id,
            )
        except SelfBindingError:
            return SemanticSetOutcome.AMBIGUOUS_REFERENCE, None
    assert intent.anchor_query is not None
    resolution = existing_resolver(intent.anchor_query)
    if resolution.outcome is not ExistingEntityOutcome.RESOLVED or resolution.id is None:
        return SemanticSetOutcome.AMBIGUOUS_REFERENCE, None
    return SemanticSetOutcome.ANSWERABLE, resolution.id


def _validate_selection(
    selection: SetEvidenceSelection,
    candidates: Sequence[SemanticSetCandidate],
    bounds: SemanticSetBounds,
) -> None:
    """Reject selector output that exceeds the supplied candidates or exact-span rules."""
    if (
        not isinstance(selection, SetEvidenceSelection)
        or not isinstance(selection.scope_uncertain, bool)
        or len(selection.member_occurrences) > bounds.members
    ):
        raise ValueError("Semantic-set selection exceeds bounds")
    candidate_ids = {candidate.id for candidate in candidates}
    selected_ids = set(selection.supplied_fact_ids)
    if (
        len(selected_ids) != len(selection.supplied_fact_ids)
        or not selected_ids <= candidate_ids
        or not all(isinstance(item, str) and item for item in selection.supplied_fact_ids)
    ):
        raise ValueError("Semantic-set selection includes unknown candidates")
    previous: dict[str, list[tuple[int, int]]] = {}
    occurrences: set[tuple[str, str, int, int]] = set()
    lookup = {candidate.id: candidate for candidate in candidates}
    for occurrence in selection.member_occurrences:
        if (
            not isinstance(occurrence, SetMemberOccurrence)
            or occurrence.candidate_id not in selected_ids
            or occurrence.kind not in {"literal", "link"}
            or not isinstance(occurrence.start, int)
            or not isinstance(occurrence.end, int)
        ):
            raise ValueError("Semantic-set member occurrence is invalid")
        text = lookup[occurrence.candidate_id].fact.text
        if occurrence.start < 0 or occurrence.end <= occurrence.start or occurrence.end > len(text):
            raise ValueError("Semantic-set occurrence is outside its fact")
        key = (occurrence.candidate_id, occurrence.kind, occurrence.start, occurrence.end)
        if key in occurrences:
            raise ValueError("Semantic-set occurrence is duplicated")
        occurrences.add(key)
        spans = previous.setdefault(occurrence.candidate_id, [])
        if any(occurrence.start < end and start < occurrence.end for start, end in spans):
            raise ValueError("Semantic-set occurrences overlap")
        spans.append((occurrence.start, occurrence.end))
        if occurrence.kind == "link" and not any(
            match.start() == occurrence.start and match.end() == occurrence.end
            for match in _LINK.finditer(text)
        ):
            raise ValueError("Semantic-set link occurrence is unsupported")


def _ground_selection(
    projector: RelationshipEvidenceProjector,
    anchor_id: str,
    candidates: Sequence[SemanticSetCandidate],
    selection: SetEvidenceSelection,
    bounds: SemanticSetBounds,
) -> GroundedSemanticSet | SemanticSetResolution:
    """Re-read every selected source and construct identity/literal members from exact spans."""
    lookup = {candidate.id: candidate for candidate in candidates}
    current_facts: dict[tuple[str, str], CanonicalFact] = {}
    for candidate in candidates:
        facts = projector.facts_for_source(candidate.fact.source.id)
        current = next((fact for fact in facts if fact.locator == candidate.fact.locator), None)
        if current is None or current.source.source_hash != candidate.fact.source.source_hash:
            return SemanticSetResolution(SemanticSetOutcome.STALE_EVIDENCE, reason="source_changed")
        current_facts[(candidate.fact.source.id, candidate.fact.locator)] = current
    identities: set[str] = set()
    literals: set[tuple[str, str, int, int]] = set()
    members: list[SetMember] = []
    for occurrence in selection.member_occurrences:
        candidate = lookup[occurrence.candidate_id]
        fact = current_facts[(candidate.fact.source.id, candidate.fact.locator)]
        evidence = SetEvidenceProvenance(
            fact.source.id,
            fact.locator,
            fact.source.source_hash,
            occurrence.start,
            occurrence.end,
            occurrence.kind,
        )
        if occurrence.kind == "literal":
            value = fact.text[occurrence.start : occurrence.end]
            if not value.strip():
                return SemanticSetResolution(
                    SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="empty_literal"
                )
            key = (value, fact.source.id, occurrence.start, occurrence.end)
            if key not in literals:
                literals.add(key)
                members.append(LiteralSetMember(value, evidence))
            continue
        identity = projector.resolve_link_occurrence(
            fact.source.id, fact.locator, occurrence.start, occurrence.end
        )
        if identity is None:
            return SemanticSetResolution(
                SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="identity_link"
            )
        if identity.id not in identities:
            identities.add(identity.id)
            members.append(IdentitySetMember(identity.id, evidence))
    if len(members) > bounds.members:
        return SemanticSetResolution(SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="member_bound")
    facts = tuple(current_facts.values())
    return GroundedSemanticSet(
        anchor_id,
        tuple(members),
        SemanticSetCompleteness.COMPLETE_WITHIN_SCANNED_SCOPE,
        len({fact.source.id for fact in facts}),
        len(facts),
        sum(
            len((fact.source.id + "\0" + fact.locator + "\0" + fact.text).encode("utf-8"))
            for fact in facts
        ),
    )
