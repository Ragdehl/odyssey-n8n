"""Resolve planner-preserved relational intent against current canonical Markdown."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from odyssey_core.contextual import (
    ContextualCandidate,
    ContextualResolutionRequest,
    validate_contextual_decision,
)
from odyssey_core.identity_boundary import (
    AuthenticatedActorContext,
    SelfBindingError,
    SelfBindingRepository,
)
from odyssey_core.relationship_evidence import (
    CanonicalFact,
    CanonicalIdentity,
    EvidenceDirection,
    RelationshipEvidenceProjector,
    TargetProjectionStatus,
)
from odyssey_core.request_planning import SelectionCriteria
from odyssey_core.resolution import ExistingEntityOutcome, resolve_existing_entity
from odyssey_core.storage import VaultRepository

_WIKILINK_DISPLAY = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


class RelationalResolutionError(RuntimeError):
    """Signal that one relational identity or complete member set cannot be authorized."""

    def __init__(
        self, reason: str, candidate_ids: tuple[str, ...] = (), evidence_guard: str | None = None
    ) -> None:
        """Carry only Core-grounded bounded identity options when clarification is safe."""
        super().__init__(reason)
        self.candidate_ids = candidate_ids
        self.evidence_guard = evidence_guard


@dataclass(frozen=True, slots=True)
class ResolvedRelationalReference:
    """Carry a current source fact locator and its exact grounded target identities."""

    source: CanonicalIdentity
    evidence_source: CanonicalIdentity
    fact_locator: str
    direction: EvidenceDirection
    targets: tuple[CanonicalIdentity, ...]
    evidence_guard: str


def resolve_relational_reference(
    selection: SelectionCriteria,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    semantic_limit: int,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    allow_identity_clarification: bool = False,
) -> ResolvedRelationalReference:
    """Resolve one source and one fact through existing identity and contextual boundaries.

    The contextual decision selects only a supplied current fact locator. Core reprojects that
    locator and admits only a complete one-hop target set of the requested cardinality. No model
    output can supply or replace a stable member ID.
    """
    relation = selection.relational_reference
    if relation is None:
        raise ValueError("Selection has no relational reference")
    projector = RelationshipEvidenceProjector(repository, schema)
    if relation.source_kind == "self":
        if authenticated_actor is None or self_binding_repository is None:
            raise RelationalResolutionError("relational_source_unavailable")
        try:
            source_id = self_binding_repository.resolve(
                authenticated_actor.stable_user_id
            ).person_note_id
        except SelfBindingError as error:
            raise RelationalResolutionError("relational_source_unavailable") from error
    else:
        assert relation.source_query is not None
        source_resolution = resolve_existing_entity(
            relation.source_query,
            selection.query,
            repository=repository,
            schema=schema,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            semantic_limit=semantic_limit,
        )
        if source_resolution.outcome is not ExistingEntityOutcome.RESOLVED:
            raise RelationalResolutionError("relational_source_unresolved")
        assert source_resolution.id is not None
        source_id = source_resolution.id
    outgoing = tuple(
        (fact, EvidenceDirection.OUTGOING) for fact in projector.facts_for_source(source_id)
    )
    incoming_projection = projector.project_entity_evidence_candidates(source_id)
    incoming = (
        tuple((item.fact, EvidenceDirection.INCOMING) for item in incoming_projection.incoming)
        if incoming_projection is not None and relation.members == "one"
        else ()
    )
    candidates: tuple[tuple[CanonicalFact, EvidenceDirection], ...] = (*outgoing, *incoming)
    if not candidates:
        raise RelationalResolutionError("relational_evidence_unavailable")
    evidence_guard = _candidate_evidence_guard(candidates)
    decision, _usage = contextual_reasoner.resolve(
        ContextualResolutionRequest(
            reference=relation.reference,
            context=selection.query,
            entity_type="canonical_fact",
            candidates=tuple(
                ContextualCandidate(fact.locator, _humanize_fact_links(fact.text))
                for fact, _direction in candidates
            ),
        )
    )
    # Mutations retain their existing stricter preflight: repeating the literal
    # relation in more than one fact is not enough authority to edit either.
    # Retrieval may instead offer grounded bounded identities through the
    # established clarification continuation.
    if (
        not allow_identity_clarification
        and sum(
            relation.reference.casefold() in fact.text.casefold() for fact, _direction in candidates
        )
        > 1
    ):
        raise RelationalResolutionError(
            "relational_evidence_ambiguous", evidence_guard=evidence_guard
        )
    selected = validate_contextual_decision(
        decision, frozenset(fact.locator for fact, _direction in candidates)
    )
    if selected.outcome != "RESOLVED" or selected.id is None:
        grounded: list[str] = []
        for fact, direction in candidates:
            if relation.reference.casefold() not in fact.text.casefold():
                continue
            projection = projector.project_targets(fact.source.id, fact.locator)
            if projection.status is not TargetProjectionStatus.COMPLETE:
                continue
            targets = (
                (projection.source,)
                if direction is EvidenceDirection.INCOMING and projection.source is not None
                else projection.targets
            )
            for target in targets:
                if target is not None and target.id not in grounded:
                    grounded.append(target.id)
        options = tuple(grounded)
        if allow_identity_clarification and relation.members == "one" and 1 < len(options) <= 4:
            raise RelationalResolutionError(
                "relational_evidence_ambiguous", options, evidence_guard
            )
        raise RelationalResolutionError(
            "relational_evidence_ambiguous", evidence_guard=evidence_guard
        )
    selected_fact, direction = next(
        (fact, direction) for fact, direction in candidates if fact.locator == selected.id
    )
    projection = projector.project_targets(selected_fact.source.id, selected.id)
    if projection.status is not TargetProjectionStatus.COMPLETE or projection.source is None:
        raise RelationalResolutionError(
            "relational_evidence_incomplete", evidence_guard=evidence_guard
        )
    if direction is EvidenceDirection.INCOMING:
        if not any(target.id == source_id for target in projection.targets):
            raise RelationalResolutionError(
                "relational_evidence_incomplete", evidence_guard=evidence_guard
            )
        targets = (projection.source,)
    else:
        targets = projection.targets
    if relation.members == "one" and len(targets) != 1:
        options = tuple(target.id for target in targets)
        raise RelationalResolutionError(
            "relational_singular_ambiguous",
            options if allow_identity_clarification and 1 < len(options) <= 4 else (),
            evidence_guard,
        )
    if selection.type is not None and any(target.type != selection.type for target in targets):
        raise RelationalResolutionError(
            "relational_target_type_mismatch", evidence_guard=evidence_guard
        )
    source = incoming_projection.entity if incoming_projection is not None else projection.source
    return ResolvedRelationalReference(
        source, projection.source, selected.id, direction, targets, evidence_guard
    )


def _candidate_evidence_guard(
    candidates: tuple[tuple[CanonicalFact, EvidenceDirection], ...],
) -> str:
    """Hash the exact current candidate locator/revision scope without retaining its text."""
    payload = "\n".join(
        f"{fact.source.id}\0{fact.source.source_hash}\0{fact.locator}\0{direction.value}"
        for fact, direction in candidates
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _humanize_fact_links(text: str) -> str:
    """Show a model the visible linked fact wording without vault-relative path components."""
    return _WIKILINK_DISPLAY.sub(
        lambda match: (match.group(2) or PurePosixPath(match.group(1)).name).strip(), text
    )
