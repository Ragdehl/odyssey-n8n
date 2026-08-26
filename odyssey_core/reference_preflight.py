"""Non-persisting Phase 16.5B target identity preflight."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from .request_planning import KnowledgeUnit, WriteAction
from .storage import VaultRepository
from .write_target import WriteTargetDecision, WriteTargetOutcome, decide_write_target


class ReferencePreflightError(RuntimeError):
    """Indicate that a target identity or creation path cannot be safely preallocated."""


@dataclass(frozen=True, slots=True)
class UnitTargetPreflight:
    """Describe the immutable target identity decision for one ordered knowledge unit."""

    unit_index: int
    outcome: WriteTargetOutcome
    stable_id: str | None = None
    canonical_name: str | None = None
    path: str | None = None
    candidate_note_ids: tuple[str, ...] = ()
    reason: str | None = None


def allocate_stable_id() -> str:
    """Return a full random UUID for a newly authorized canonical note."""
    return str(uuid4())


def preflight_write_action(
    action: WriteAction,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    semantic_limit: int,
    id_allocator: Callable[[], str] = allocate_stable_id,
) -> tuple[UnitTargetPreflight, ...]:
    """Decide every ordered unit once and preallocate safe CREATE identities without writing.

    Existing targets reuse the authoritative note ID, path, and metadata name. Authorized record
    targets receive an injectable full UUID and a creation-time ``<name> - <uuid>.md`` path.
    References must consume this returned table by ``target_index``; this function never resolves
    a unit per occurrence and never invokes a writer or persistence primitive.

    Args:
        action: Validated ordered write action to preflight.
        repository: Authoritative Markdown repository used for resolution and collision checks.
        schema: Canonical note schema.
        semantic_index: Existing local semantic candidate index.
        embedder: Existing local query embedder.
        contextual_reasoner: Injected contextual resolver boundary.
        semantic_limit: Explicit semantic candidate budget.
        id_allocator: Zero-argument full-ID allocator, injectable for deterministic tests.

    Returns:
        One immutable target result per action unit, in unit order.

    Raises:
        ValueError: If the action or allocator contract is malformed.
        ReferencePreflightError: If an allocated ID/path is unsafe or collides.
    """
    if not isinstance(action, WriteAction):
        raise ValueError("Reference preflight requires a WriteAction")
    results: list[UnitTargetPreflight] = []
    allocated_paths: set[str] = set()
    existing_paths = set(repository.list_markdown_paths())
    for unit_index, unit in enumerate(action.units):
        decision = decide_write_target(
            unit,
            repository=repository,
            schema=schema,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            semantic_limit=semantic_limit,
        )
        results.append(
            _materialize_decision(
                unit_index,
                unit,
                decision,
                repository=repository,
                schema=schema,
                existing_paths=existing_paths,
                allocated_paths=allocated_paths,
                id_allocator=id_allocator,
            )
        )
    return tuple(results)


def _materialize_decision(
    unit_index: int,
    unit: KnowledgeUnit,
    decision: WriteTargetDecision,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    existing_paths: set[str],
    allocated_paths: set[str],
    id_allocator: Callable[[], str],
) -> UnitTargetPreflight:
    """Enrich one target decision with authoritative existing or preallocated identity data."""
    if decision.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION:
        return UnitTargetPreflight(
            unit_index,
            decision.outcome,
            candidate_note_ids=decision.candidate_note_ids,
            reason=decision.reason,
        )
    if decision.outcome is WriteTargetOutcome.UPDATE:
        assert decision.existing_note_id is not None
        path, name = _find_existing_identity(repository, schema, decision.existing_note_id)
        return UnitTargetPreflight(
            unit_index, decision.outcome, decision.existing_note_id, name, path
        )
    name = unit.target.entity or unit.target.query
    if not isinstance(name, str) or not name.strip():
        raise ReferencePreflightError("CREATE target has no canonical human-readable name")
    stable_id = id_allocator()
    if (
        not isinstance(stable_id, str)
        or not stable_id.strip()
        or "/" in stable_id
        or "\\" in stable_id
    ):
        raise ReferencePreflightError("CREATE allocator returned an unsafe stable ID")
    path = f"{_safe_creation_name(name)} - {stable_id}.md"
    if path in existing_paths or path in allocated_paths:
        raise ReferencePreflightError(f"CREATE path already exists: {path}")
    allocated_paths.add(path)
    return UnitTargetPreflight(unit_index, decision.outcome, stable_id, name.strip(), path)


def _find_existing_identity(
    repository: VaultRepository, schema: dict[str, Any], stable_id: str
) -> tuple[str, str]:
    """Find and validate the authoritative path and canonical name for an existing ID."""
    for path in repository.list_markdown_paths():
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError) as error:
            raise ReferencePreflightError(f"Cannot inspect existing note: {path}") from error
        if note.metadata.get("id") == stable_id:
            name = note.metadata.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ReferencePreflightError(f"Existing note has no canonical name: {path}")
            return path, name
    raise ReferencePreflightError(f"Resolved note ID is no longer present: {stable_id}")


def _safe_creation_name(name: str) -> str:
    """Validate the human name used in a creation-time filename label."""
    value = name.strip()
    if not value or any(character in value for character in ("/", "\\", "\x00")):
        raise ReferencePreflightError("Canonical name cannot safely form a Markdown filename")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ReferencePreflightError("Canonical name contains unsafe control characters")
    return value
