"""Safe Phase 16.1 write-target selection over validated planning and resolution contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from odyssey_core.context import find_filtered_note_ids
from odyssey_core.contextual import ContextualReasoner
from odyssey_core.request_planning import KnowledgeUnit
from odyssey_core.resolution import ExistingEntityOutcome, resolve_existing_entity
from odyssey_core.semantic import SemanticEntityIndex, TextEmbedder
from odyssey_core.storage import VaultRepository


class WriteTargetOutcome(Enum):
    """Represent the only safe Phase 16.1 target decisions."""

    UPDATE = "UPDATE"
    CREATE = "CREATE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


@dataclass(frozen=True, slots=True)
class WriteTargetDecision:
    """Describe one non-persisting target decision for a validated knowledge unit.

    Attributes:
        outcome: Whether later work may update, create, or must clarify.
        existing_note_id: Selected stable note ID only for ``UPDATE``.
        target_type: Canonical type only for ``CREATE``.
        reason: Small stable explanation for a non-update decision.
    """

    outcome: WriteTargetOutcome
    existing_note_id: str | None = None
    target_type: str | None = None
    reason: str | None = None


def decide_write_target(
    unit: KnowledgeUnit,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: SemanticEntityIndex,
    embedder: TextEmbedder,
    contextual_reasoner: ContextualReasoner,
    semantic_limit: int,
) -> WriteTargetDecision:
    """Resolve one validated write target and authorize only safe later work.

    ``target.entity`` is privileged exact identity wording; otherwise the planner's target query
    is passed through the existing layered resolver, allowing contextual identities to accumulate.
    Target filters are evaluated against current validated notes before resolution, so they can only
    narrow candidates. This function never allocates an ID/path, invokes persistence, or executes
    a delegated action.

    Args:
        unit: One Phase 15 validated semantic write unit.
        repository: Authoritative Markdown vault used by existing resolution.
        schema: Canonical schema defining current types and filters.
        semantic_index: Existing Phase 10 semantic candidate index.
        embedder: Existing local query embedder.
        contextual_reasoner: Existing injected Phase 11 reasoner boundary.
        semantic_limit: Explicit Phase 11 semantic candidate budget.

    Returns:
        Immutable UPDATE, CREATE, or NEEDS_CLARIFICATION authorization only.

    Raises:
        ValueError: If the supposedly validated unit or resolver inputs are malformed.
        ExistingEntityResolutionError: If existing identity evidence cannot be safely inspected.
    """
    if not isinstance(unit, KnowledgeUnit):
        raise ValueError("Write target requires a validated KnowledgeUnit")
    target = unit.target
    if target.link_scope is not None:
        return _clarification("unsupported_link_scope")
    canonical_types = _canonical_types(schema)
    if target.type is not None and target.type not in canonical_types:
        return _clarification("invalid_target_type")
    reference = target.entity or target.query
    if not isinstance(reference, str) or not reference.strip() or not isinstance(target.query, str):
        return _clarification("invalid_target")
    allowed_ids = None
    if target.filters:
        allowed_ids = find_filtered_note_ids(
            repository, schema, target.filters, note_type=target.type
        )
    resolution = resolve_existing_entity(
        reference,
        target.query,
        type=target.type,
        repository=repository,
        schema=schema,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=contextual_reasoner,
        semantic_limit=semantic_limit,
        allowed_candidate_ids=allowed_ids,
    )
    if resolution.outcome is ExistingEntityOutcome.RESOLVED:
        assert resolution.id is not None
        return WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id=resolution.id)
    if resolution.outcome is ExistingEntityOutcome.AMBIGUOUS:
        return _clarification("ambiguous_existing_target")
    if resolution.has_ambiguous_exact_evidence:
        return _clarification("ambiguous_existing_target")
    if unit.intent == "record" and target.type is not None:
        return WriteTargetDecision(WriteTargetOutcome.CREATE, target_type=target.type)
    return _clarification("unresolved_existing_target")


def _canonical_types(schema: dict[str, Any]) -> frozenset[str]:
    """Return the current canonical type IDs or reject an unusable schema."""
    try:
        types = frozenset(item["id"] for item in schema["types"])
    except (KeyError, TypeError):
        raise ValueError("Supplied schema is not usable") from None
    if not types or not all(isinstance(note_type, str) and note_type for note_type in types):
        raise ValueError("Supplied schema is not usable")
    return types


def _clarification(reason: str) -> WriteTargetDecision:
    """Build a fail-closed clarification decision without asserting an identity."""
    return WriteTargetDecision(WriteTargetOutcome.NEEDS_CLARIFICATION, reason=reason)
