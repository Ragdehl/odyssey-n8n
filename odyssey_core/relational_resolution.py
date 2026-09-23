"""Resolve planner-preserved relational intent against current canonical Markdown."""

from __future__ import annotations

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

MAX_SOURCE_FACT_CANDIDATES = 32
_WIKILINK_DISPLAY = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


class RelationalResolutionError(RuntimeError):
    """Signal that one relational identity or complete member set cannot be authorized."""


@dataclass(frozen=True, slots=True)
class ResolvedRelationalReference:
    """Carry a current source fact locator and its exact grounded target identities."""

    source: CanonicalIdentity
    evidence_source: CanonicalIdentity
    fact_locator: str
    direction: EvidenceDirection
    targets: tuple[CanonicalIdentity, ...]


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
    if not candidates or len(candidates) > MAX_SOURCE_FACT_CANDIDATES:
        raise RelationalResolutionError("relational_evidence_unavailable")
    repeated_literal_mention = tuple(
        fact
        for fact, _direction in candidates
        if relation.reference.casefold() in fact.text.casefold()
    )
    if len(repeated_literal_mention) > 1:
        raise RelationalResolutionError("relational_evidence_ambiguous")
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
    selected = validate_contextual_decision(
        decision, frozenset(fact.locator for fact, _direction in candidates)
    )
    if selected.outcome != "RESOLVED" or selected.id is None:
        raise RelationalResolutionError("relational_evidence_ambiguous")
    selected_fact, direction = next(
        (fact, direction) for fact, direction in candidates if fact.locator == selected.id
    )
    projection = projector.project_targets(selected_fact.source.id, selected.id)
    if projection.status is not TargetProjectionStatus.COMPLETE or projection.source is None:
        raise RelationalResolutionError("relational_evidence_incomplete")
    if direction is EvidenceDirection.INCOMING:
        if not any(target.id == source_id for target in projection.targets):
            raise RelationalResolutionError("relational_evidence_incomplete")
        targets = (projection.source,)
    else:
        targets = projection.targets
    if relation.members == "one" and len(targets) != 1:
        raise RelationalResolutionError("relational_singular_ambiguous")
    if selection.type is not None and any(target.type != selection.type for target in targets):
        raise RelationalResolutionError("relational_target_type_mismatch")
    source = incoming_projection.entity if incoming_projection is not None else projection.source
    return ResolvedRelationalReference(source, projection.source, selected.id, direction, targets)


def _humanize_fact_links(text: str) -> str:
    """Show a model the visible linked fact wording without vault-relative path components."""
    return _WIKILINK_DISPLAY.sub(
        lambda match: (match.group(2) or PurePosixPath(match.group(1)).name).strip(), text
    )
