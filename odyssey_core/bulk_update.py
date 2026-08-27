"""Fail-closed deterministic bulk UPDATE execution for Phase 16.7A."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .context import ContextRetrievalError, find_filtered_note_ids
from .materialization import BoundedNoteWriter, MaterializationError, materialize_update
from .persistence import EntityPersistenceResult
from .request_planning import KnowledgeUnit
from .storage import VaultRepository
from .write_target import WriteTargetDecision, WriteTargetOutcome


class UnsupportedBulkSelectionError(MaterializationError):
    """Indicate that a bulk unit lacks an executable deterministic membership boundary."""


@dataclass(frozen=True, slots=True)
class BulkUpdateSuccess:
    """Associate one successful materialization result with its stable note ID."""

    stable_id: str
    result: EntityPersistenceResult


@dataclass(frozen=True, slots=True)
class BulkUpdateFailure:
    """Associate one failed independent materialization with its stable note ID and reason."""

    stable_id: str
    error_type: str
    reason: str


@dataclass(frozen=True, slots=True)
class BulkUpdateResult:
    """Report a frozen bulk selection and independent per-note outcomes."""

    requested_cardinality: str
    selected_note_ids: tuple[str, ...]
    succeeded: tuple[BulkUpdateSuccess, ...]
    failed: tuple[BulkUpdateFailure, ...]
    status: str


def execute_bulk_update(
    unit: KnowledgeUnit,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: str,
    now: str,
    writer: BoundedNoteWriter | None = None,
) -> BulkUpdateResult:
    """Execute one deterministic all-matching UPDATE independently for every selected note.

    Membership is derived only from validated authoritative Markdown metadata, canonical type, and
    canonical filters. The complete stable-ID set is frozen before the first write. For example, a
    ``person`` unit with a birth-date range updates every matching person in lexical ID order, while
    a query such as ``related to Odyssey`` is rejected because query text is not membership authority.

    Args:
        unit: Validated all-matching KnowledgeUnit containing the same mutation for each note.
        repository: Authoritative Markdown vault used for selection and materialization.
        schema: Canonical note schema used by deterministic filtering and per-note validation.
        actor: Application identity recorded by persistence for each successful note.
        now: Explicit lifecycle timestamp recorded by persistence.
        writer: Optional bounded writer reused per note when free-text reconciliation is needed.

    Returns:
        A typed result with frozen IDs, status, and per-ID successes or failures. Unsupported
        selection returns zero selected IDs and zero writes.

    Raises:
        ValueError: If the unit is not a KnowledgeUnit or required execution inputs are malformed.
        ContextRetrievalError: If authoritative note inspection cannot fail safely.
    """
    try:
        _validate_bulk_contract(unit)
    except UnsupportedBulkSelectionError:
        return _unsupported(unit, "UNSUPPORTED_BULK_SELECTION")
    if unit.intent == "delete":
        return _unsupported(unit, "UNSUPPORTED_BULK_DELETE")
    try:
        selected_note_ids = tuple(
            sorted(
                find_filtered_note_ids(
                    repository,
                    schema,
                    unit.target.filters,
                    note_type=unit.target.type,
                )
            )
        )
    except ContextRetrievalError:
        raise
    if not selected_note_ids:
        return BulkUpdateResult("all_matching", (), (), (), "EMPTY_SET")

    succeeded: list[BulkUpdateSuccess] = []
    failed: list[BulkUpdateFailure] = []
    for stable_id in selected_note_ids:
        decision = WriteTargetDecision(
            WriteTargetOutcome.UPDATE,
            existing_note_id=stable_id,
        )
        try:
            result = materialize_update(
                unit,
                decision,
                repository=repository,
                schema=schema,
                actor=actor,
                now=now,
                writer=writer,
            )
        except Exception as error:  # Independent targets must not hide prior successes.
            failed.append(BulkUpdateFailure(stable_id, type(error).__name__, _safe_reason(error)))
        else:
            succeeded.append(BulkUpdateSuccess(stable_id, result))
    status = "SUCCESS" if not failed else ("PARTIAL_SUCCESS" if succeeded else "FAILURE")
    return BulkUpdateResult(
        "all_matching", selected_note_ids, tuple(succeeded), tuple(failed), status
    )


def _validate_bulk_contract(unit: KnowledgeUnit) -> None:
    """Reject bulk requests that are not bounded by deterministic current capabilities."""
    if not isinstance(unit, KnowledgeUnit):
        raise ValueError("Bulk update requires a KnowledgeUnit")
    if unit.cardinality != "all_matching":
        raise ValueError("Bulk update requires all_matching cardinality")
    if unit.target.entity is not None:
        raise UnsupportedBulkSelectionError("UNSUPPORTED_BULK_SELECTION: entity is singular")
    if unit.target.link_scope is not None:
        raise UnsupportedBulkSelectionError("UNSUPPORTED_BULK_SELECTION: link_scope is unsupported")
    if unit.target.type is None and not unit.target.filters:
        raise UnsupportedBulkSelectionError(
            "UNSUPPORTED_BULK_SELECTION: deterministic scope missing"
        )


def _unsupported(unit: KnowledgeUnit, status: str) -> BulkUpdateResult:
    """Return an explicit zero-write result for a recognized but unsupported bulk operation."""
    return BulkUpdateResult(unit.cardinality, (), (), (), status)


def _safe_reason(error: Exception) -> str:
    """Return a bounded failure reason without serializing arbitrary provider or note content."""
    reason = str(error).strip()
    return reason[:300] if reason else type(error).__name__
