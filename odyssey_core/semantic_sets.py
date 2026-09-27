"""Bounded, Markdown-grounded semantic set selection from current canonical fact blocks."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol

from odyssey_core.identity_boundary import (
    AuthenticatedActorContext,
    SelfBindingError,
    SelfBindingRepository,
)
from odyssey_core.relationship_evidence import (
    CanonicalFact,
    RelationshipEvidenceError,
    RelationshipEvidenceProjector,
)
from odyssey_core.request_planning import SemanticSetIntent
from odyssey_core.storage import VaultRepository

# These are per-selector-batch payload limits.  Core traverses the full eligible Markdown inventory
# in stable batches and separately bounds the final response members.
MAX_SEMANTIC_SET_SOURCE_NOTES = 64
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
    """Set explicit selector-batch payload and final collection output ceilings."""

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

    query: str
    intent: SemanticSetIntent | None
    candidates: tuple[SemanticSetCandidateView, ...]
    typed_member_count: int | None = None


class SemanticSetSelector(Protocol):
    """Describe the injectable selection boundary for current bounded candidate facts."""

    def select(self, request: SemanticSetSelectionRequest) -> SetEvidenceSelection:
        """Choose supplied candidate occurrences or declare semantic scope uncertainty."""


class OpenAILunaSemanticSetSelector:
    """Select exact occurrences from bounded visible facts without assigning canonical authority."""

    model = "gpt-5.6-luna"
    reasoning_effort = "low"

    def __init__(self) -> None:
        """Keep provider telemetry local to the latest selector call."""
        self.last_call = False
        self.last_usage: dict[str, int] | None = None

    def select(self, request: SemanticSetSelectionRequest) -> SetEvidenceSelection:
        """Request only supplied fact IDs and exact text spans for the lossless query."""
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("Collection selector credentials are unavailable")
        self.last_call = True
        self.last_usage = None
        payload = {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": 8192,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Select only members directly supported by the supplied current fact text "
                        "for the complete user query. Return all supported members, including "
                        "literal values and exact wikilink occurrences. Use only supplied candidate "
                        "IDs and zero-based exact character spans. Do not infer relationships, "
                        "identities, members, or completeness beyond these facts. If the intended "
                        "scope is genuinely uncertain, set scope_uncertain=true. Multiple supported "
                        "members are results, not ambiguity."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "query": request.query,
                            "candidates": [asdict(candidate) for candidate in request.candidates],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "odyssey_collection_occurrences",
                    "strict": True,
                    "schema": semantic_set_selection_schema(),
                }
            },
        }
        provider_request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(provider_request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
            from odyssey_core.observability import normalize_provider_usage

            self.last_usage = normalize_provider_usage(body)
            text = next(
                content["text"]
                for item in body["output"]
                if item.get("type") == "message"
                for content in item["content"]
                if content.get("type") == "output_text"
            )
            return parse_semantic_set_selection(json.loads(text))
        except (
            urllib.error.URLError,
            TimeoutError,
            KeyError,
            StopIteration,
            json.JSONDecodeError,
        ) as error:
            raise ValueError("Collection selector response was unusable") from error


def semantic_set_selection_schema() -> dict:
    """Constrain the selector to bounded candidate IDs and exact occurrence coordinates."""
    return {
        "type": "object",
        "properties": {
            "supplied_fact_ids": {"type": "array", "items": {"type": "string"}},
            "member_occurrences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "kind": {"type": "string", "enum": ["literal", "link"]},
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                    },
                    "required": ["candidate_id", "kind", "start", "end"],
                    "additionalProperties": False,
                },
            },
            "scope_uncertain": {"type": "boolean"},
        },
        "required": ["supplied_fact_ids", "member_occurrences", "scope_uncertain"],
        "additionalProperties": False,
    }


def parse_semantic_set_selection(value: object) -> SetEvidenceSelection:
    """Reject malformed selector output before Core checks candidate membership and spans."""
    if not isinstance(value, dict) or set(value) != {
        "supplied_fact_ids",
        "member_occurrences",
        "scope_uncertain",
    }:
        raise ValueError("Collection selector output fields are invalid")
    ids, occurrences, uncertain = (
        value["supplied_fact_ids"],
        value["member_occurrences"],
        value["scope_uncertain"],
    )
    if (
        not isinstance(ids, list)
        or not all(isinstance(item, str) for item in ids)
        or not isinstance(occurrences, list)
        or not isinstance(uncertain, bool)
        or len(ids) > MAX_SEMANTIC_SET_FACTS
        or len(occurrences) > MAX_SEMANTIC_SET_MEMBERS
    ):
        raise ValueError("Collection selector output exceeds its closed bounds")
    parsed = []
    for item in occurrences:
        if (
            not isinstance(item, dict)
            or set(item) != {"candidate_id", "kind", "start", "end"}
            or not isinstance(item["candidate_id"], str)
            or item["kind"] not in {"literal", "link"}
            or type(item["start"]) is not int
            or type(item["end"]) is not int
        ):
            raise ValueError("Collection selector occurrence fields are invalid")
        parsed.append(SetMemberOccurrence(**item))
    return SetEvidenceSelection(tuple(ids), tuple(parsed), uncertain)


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
    display_name: str = ""


@dataclass(frozen=True, slots=True)
class LiteralSetMember:
    """Represent a member grounded by exact visible canonical fact text."""

    value: str
    evidence: SetEvidenceProvenance


SetMember = IdentitySetMember | LiteralSetMember


@dataclass(frozen=True, slots=True)
class GroundedSemanticSet:
    """Return re-grounded members and declared scan completeness."""

    subject_kind: str | None
    subject_query: str | None
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
    projector: RelationshipEvidenceProjector, *, bounds: SemanticSetBounds
) -> tuple[SemanticSetCandidate, ...] | SemanticSetResolution:
    """Enumerate the full current canonical inventory before bounded batch selection.

    The limits in ``bounds`` constrain one selector payload, never the number of facts that can be
    considered for a collection. This public helper retains its historical signature while the
    resolver below partitions its complete result into deterministic batches.
    """
    try:
        ordered = projector.all_visible_facts()
    except RelationshipEvidenceError:
        return SemanticSetResolution(
            SemanticSetOutcome.OPERATIONAL_FAILURE, reason="canonical_scan"
        )
    del bounds
    return tuple(
        SemanticSetCandidate(f"candidate-{index}", fact) for index, fact in enumerate(ordered)
    )


def resolve_semantic_set(
    intent: SemanticSetIntent | None = None,
    *,
    query: str | None = None,
    repository: VaultRepository,
    schema: dict,
    selector: SemanticSetSelector,
    bounds: SemanticSetBounds = DEFAULT_SEMANTIC_SET_BOUNDS,
    collection_subject: str | None = None,
    authenticated_actor: AuthenticatedActorContext | None = None,
    self_binding_repository: SelfBindingRepository | None = None,
) -> SemanticSetResolution:
    """Select and re-ground one bounded collection from its complete query and current facts.

    Args:
        intent: Historical planner wording, accepted only for old validated plans.
        repository: Authoritative Markdown repository.
        schema: Active canonical note schema.
        selector: Injected candidate-only semantic selection boundary.
        bounds: Explicit scan and result ceilings.

    Returns:
        A grounded set or a fail-closed structured outcome.
    """
    if query is None:
        query = _effective_query(intent) if intent is not None else None
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Collection query must be non-empty")
    if collection_subject not in {None, "self", "query"}:
        raise ValueError("Collection subject is invalid")
    projector = RelationshipEvidenceProjector(repository, schema)
    typed_member_ids: frozenset[str] | None = None
    if intent is not None and intent.member_type is not None:
        try:
            typed_member_ids = frozenset(projector.note_ids_of_type(intent.member_type))
        except RelationshipEvidenceError:
            return SemanticSetResolution(
                SemanticSetOutcome.OPERATIONAL_FAILURE, reason="typed_scope"
            )
    candidates = _eligible_candidates(
        projector,
        bounds=bounds,
        collection_subject=collection_subject,
        authenticated_actor=authenticated_actor,
        self_binding_repository=self_binding_repository,
    )
    if isinstance(candidates, SemanticSetResolution):
        return candidates
    if not candidates:
        return SemanticSetResolution(SemanticSetOutcome.NO_RELEVANT_EVIDENCE)
    inventory = _inventory(candidates)
    batches = _candidate_batches(candidates, bounds)
    if isinstance(batches, SemanticSetResolution):
        return batches
    members: list[SetMember] = []
    identity_ids: set[str] = set()
    literal_occurrences: set[tuple[str, str, int, int]] = set()
    selected_any = False
    for batch in batches:
        try:
            selection = selector.select(
                SemanticSetSelectionRequest(
                    query=query,
                    intent=intent,
                    candidates=tuple(
                        SemanticSetCandidateView(candidate.id, candidate.fact.text)
                        for candidate in batch
                    ),
                    typed_member_count=len(typed_member_ids)
                    if typed_member_ids is not None
                    else None,
                )
            )
            _validate_selection(selection, batch, bounds)
        except (TypeError, ValueError):
            return SemanticSetResolution(
                SemanticSetOutcome.OPERATIONAL_FAILURE, reason="invalid_selection"
            )
        except Exception:
            return SemanticSetResolution(
                SemanticSetOutcome.OPERATIONAL_FAILURE, reason="selector_failure"
            )
        if selection.scope_uncertain:
            return SemanticSetResolution(
                SemanticSetOutcome.AMBIGUOUS_SET_SCOPE,
                candidate_count=len(candidates),
            )
        if not selection.member_occurrences:
            continue
        selected_any = True
        grounded = _ground_selection(
            projector, intent, batch, selection, bounds, typed_member_ids=typed_member_ids
        )
        if isinstance(grounded, SemanticSetResolution):
            return grounded
        for member in grounded.members:
            if isinstance(member, IdentitySetMember):
                if member.stable_id in identity_ids:
                    continue
                identity_ids.add(member.stable_id)
            else:
                key = (
                    member.value,
                    member.evidence.source_note_id,
                    member.evidence.start,
                    member.evidence.end,
                )
                if key in literal_occurrences:
                    continue
                literal_occurrences.add(key)
            members.append(member)
            if len(members) > bounds.members:
                return SemanticSetResolution(
                    SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="member_bound"
                )
    try:
        current = _eligible_facts(
            projector,
            collection_subject=collection_subject,
            authenticated_actor=authenticated_actor,
            self_binding_repository=self_binding_repository,
        )
    except (RelationshipEvidenceError, SelfBindingError):
        return SemanticSetResolution(
            SemanticSetOutcome.OPERATIONAL_FAILURE, reason="canonical_scan"
        )
    if _inventory(current) != inventory:
        return SemanticSetResolution(SemanticSetOutcome.STALE_EVIDENCE, reason="inventory_changed")
    if not selected_any:
        return SemanticSetResolution(
            SemanticSetOutcome.NO_RELEVANT_EVIDENCE, candidate_count=len(candidates)
        )
    source_count = len({candidate.fact.source.id for candidate in candidates})
    source_bytes = sum(_candidate_bytes(candidate) for candidate in candidates)
    grounded_set = GroundedSemanticSet(
        collection_subject or (intent.subject_kind if intent is not None else None),
        intent.subject_query if intent is not None else None,
        tuple(members),
        SemanticSetCompleteness.COMPLETE_WITHIN_SCANNED_SCOPE,
        source_count,
        len(candidates),
        source_bytes,
    )
    return SemanticSetResolution(
        SemanticSetOutcome.ANSWERABLE,
        grounded_set,
        candidate_count=len(candidates),
    )


def _eligible_candidates(
    projector: RelationshipEvidenceProjector,
    *,
    bounds: SemanticSetBounds,
    collection_subject: str | None,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
) -> tuple[SemanticSetCandidate, ...] | SemanticSetResolution:
    """Expose the complete narrow candidate inventory for query or authenticated-self scope."""
    del bounds
    try:
        facts = _eligible_facts(
            projector,
            collection_subject=collection_subject,
            authenticated_actor=authenticated_actor,
            self_binding_repository=self_binding_repository,
        )
    except SelfBindingError:
        return SemanticSetResolution(
            SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="self_unavailable"
        )
    except RelationshipEvidenceError:
        return SemanticSetResolution(
            SemanticSetOutcome.OPERATIONAL_FAILURE, reason="canonical_scan"
        )
    return tuple(
        SemanticSetCandidate(f"candidate-{index}", fact) for index, fact in enumerate(facts)
    )


def _eligible_facts(
    projector: RelationshipEvidenceProjector,
    *,
    collection_subject: str | None,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
) -> tuple[CanonicalFact, ...]:
    """Return all facts in deterministic generic or authenticated-self collection scope."""
    if collection_subject != "self":
        return projector.all_visible_facts()
    if authenticated_actor is None or self_binding_repository is None:
        raise SelfBindingError("Authenticated self binding is unavailable")
    self_id = self_binding_repository.resolve(authenticated_actor.stable_user_id).person_note_id
    direct = projector.facts_for_source(self_id)
    projection = projector.project_entity_evidence_candidates(self_id)
    incoming = () if projection is None else tuple(item.fact for item in projection.incoming)
    unique = {(fact.source.id, fact.locator): fact for fact in (*direct, *incoming)}
    return tuple(sorted(unique.values(), key=lambda fact: (fact.source.path, fact.locator)))


def _candidate_bytes(candidate: SemanticSetCandidate) -> int:
    """Measure one Core-owned selector candidate payload contribution."""
    fact = candidate.fact
    return len((fact.source.id + "\0" + fact.locator + "\0" + fact.text).encode("utf-8"))


def _candidate_batches(
    candidates: Sequence[SemanticSetCandidate], bounds: SemanticSetBounds
) -> tuple[tuple[SemanticSetCandidate, ...], ...] | SemanticSetResolution:
    """Partition a complete inventory into stable payload-bounded selector batches."""
    if min(bounds.source_notes, bounds.facts, bounds.source_bytes) < 1:
        return SemanticSetResolution(
            SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="selector_batch_bounds"
        )
    if bounds.members < 0:
        raise ValueError("Semantic-set member bound cannot be negative")
    batches: list[tuple[SemanticSetCandidate, ...]] = []
    batch: list[SemanticSetCandidate] = []
    source_ids: set[str] = set()
    serialized = 0
    for candidate in candidates:
        size = _candidate_bytes(candidate)
        if size > bounds.source_bytes:
            return SemanticSetResolution(
                SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="evidence_item_too_large"
            )
        adds_source = candidate.fact.source.id not in source_ids
        if batch and (
            len(batch) == bounds.facts
            or serialized + size > bounds.source_bytes
            or (adds_source and len(source_ids) == bounds.source_notes)
        ):
            batches.append(tuple(batch))
            batch, source_ids, serialized = [], set(), 0
        batch.append(candidate)
        source_ids.add(candidate.fact.source.id)
        serialized += size
    if batch:
        batches.append(tuple(batch))
    return tuple(batches)


def _inventory(
    candidates: Sequence[SemanticSetCandidate] | Sequence[CanonicalFact],
) -> tuple[tuple[str, str, str], ...]:
    """Bind a completed scan to exact source revisions and fact locators."""
    facts = (item.fact if isinstance(item, SemanticSetCandidate) else item for item in candidates)
    return tuple((fact.source.id, fact.source.source_hash, fact.locator) for fact in facts)


def _effective_query(intent: SemanticSetIntent) -> str:
    """Provide legacy callers a lossless local query until they pass SelectionCriteria.query."""
    return " ".join(item for item in (intent.member_query, intent.explicit_qualifiers) if item)


def serialize_semantic_set_candidate_payload(
    intent: SemanticSetIntent | None,
    candidates: Sequence[SemanticSetCandidate],
    *,
    query: str = "",
) -> bytes:
    """Serialize the exact selector-visible candidate payload for deterministic budget evidence."""
    payload = {
        "query": query,
        "candidates": [{"id": item.id, "text": item.fact.text} for item in candidates],
    }
    if intent is not None:
        payload.update(
            subject_kind=intent.subject_kind,
            subject_query=intent.subject_query,
            member_query=intent.member_query,
            explicit_qualifiers=intent.explicit_qualifiers,
            asks_exhaustive=intent.asks_exhaustive,
            member_type=intent.member_type,
        )
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


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
    intent: SemanticSetIntent | None,
    candidates: Sequence[SemanticSetCandidate],
    selection: SetEvidenceSelection,
    bounds: SemanticSetBounds,
    *,
    typed_member_ids: frozenset[str] | None,
) -> GroundedSemanticSet | SemanticSetResolution:
    """Re-read every selected source and construct identity/literal members from exact spans."""
    lookup = {candidate.id: candidate for candidate in candidates}
    current_facts = dict(
        projector.re_ground_facts(
            (candidate.fact.source.id, candidate.fact.locator) for candidate in candidates
        )
    )
    for candidate in candidates:
        current = current_facts.get((candidate.fact.source.id, candidate.fact.locator))
        if current is None or current.source.source_hash != candidate.fact.source.source_hash:
            return SemanticSetResolution(SemanticSetOutcome.STALE_EVIDENCE, reason="source_changed")
    identities: set[str] = set()
    literals: set[tuple[str, str, int, int]] = set()
    members: list[SetMember] = []
    link_occurrences = tuple(
        occurrence for occurrence in selection.member_occurrences if occurrence.kind == "link"
    )
    identities_by_occurrence = iter(
        projector.resolve_link_occurrences(
            (
                lookup[occurrence.candidate_id].fact.source.id,
                lookup[occurrence.candidate_id].fact.locator,
                occurrence.start,
                occurrence.end,
            )
            for occurrence in link_occurrences
        )
    )
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
        identity = next(identities_by_occurrence)
        if identity is None:
            return SemanticSetResolution(
                SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="identity_link"
            )
        if typed_member_ids is not None and identity.id not in typed_member_ids:
            return SemanticSetResolution(
                SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="member_type_mismatch"
            )
        if identity.id not in identities:
            identities.add(identity.id)
            members.append(IdentitySetMember(identity.id, evidence, identity.name))
    if len(members) > bounds.members:
        return SemanticSetResolution(SemanticSetOutcome.INCOMPLETE_EVIDENCE, reason="member_bound")
    facts = tuple(current_facts.values())
    return GroundedSemanticSet(
        intent.subject_kind if intent is not None else None,
        intent.subject_query if intent is not None else None,
        tuple(members),
        SemanticSetCompleteness.COMPLETE_WITHIN_SCANNED_SCOPE,
        len({fact.source.id for fact in facts}),
        len(facts),
        sum(
            len((fact.source.id + "\0" + fact.locator + "\0" + fact.text).encode("utf-8"))
            for fact in facts
        ),
    )
