"""Non-persisting Phase 16.5B target identity preflight."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from .notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from .observability import SpanRecorder
from .relationship_evidence import (
    RelationshipEvidenceProjector,
    TargetProjectionStatus,
)
from .request_planning import KnowledgeUnit, WriteAction
from .storage import VaultRepository
from .write_target import WriteTargetDecision, WriteTargetOutcome, decide_write_target


class ReferencePreflightError(RuntimeError):
    """Indicate that a target identity or creation path cannot be safely preallocated."""


class RelationshipWritePreflightError(ReferencePreflightError):
    """Indicate that current relationship evidence cannot safely authorize a shared-fact write."""


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
    reference_only: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedRelationshipMember:
    """Bind one no-write member unit to a stable ID from deterministic relationship evidence."""

    unit_index: int
    stable_id: str


@dataclass(frozen=True, slots=True)
class RelationshipWriteBinding:
    """Describe one current source fact and its exact reference-only member bindings.

    This is Core-internal write preparation data. The source ID and locator are re-grounded against
    current Markdown before any target ID is admitted to the ordinary preflight table. Member stable
    IDs must exactly match the re-grounded complete target set; their unit order is independent of
    literal-link order in the source fact.
    """

    source_unit_index: int
    evidence_source_id: str
    fact_locator: str
    members: tuple[ResolvedRelationshipMember, ...]


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
    authenticated_actor: AuthenticatedActorContext | None = None,
    self_binding_repository: SelfBindingRepository | None = None,
    span_recorder: SpanRecorder | None = None,
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
    return _preflight_write_action(
        action,
        repository=repository,
        schema=schema,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=contextual_reasoner,
        semantic_limit=semantic_limit,
        id_allocator=id_allocator,
        authenticated_actor=authenticated_actor,
        self_binding_repository=self_binding_repository,
        span_recorder=span_recorder,
    )


def _preflight_write_action(
    action: WriteAction,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    semantic_limit: int,
    id_allocator: Callable[[], str],
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    span_recorder: SpanRecorder | None,
    _validated_reference_targets: Mapping[int, str] | None = None,
) -> tuple[UnitTargetPreflight, ...]:
    """Implement ordinary preflight with private relationship-validated no-write targets only."""
    if not isinstance(action, WriteAction):
        raise ValueError("Reference preflight requires a WriteAction")
    results: list[UnitTargetPreflight] = []
    allocated_paths: set[str] = set()
    existing_paths = set(repository.list_markdown_paths())
    resolved_targets = dict(_validated_reference_targets or {})
    if any(
        not isinstance(index, int)
        or isinstance(index, bool)
        or index < 0
        or not isinstance(stable_id, str)
        or not stable_id
        for index, stable_id in resolved_targets.items()
    ) or any(index >= len(action.units) for index in resolved_targets):
        raise ReferencePreflightError("Validated relationship reference targets are invalid")
    for unit_index, unit in enumerate(action.units):
        if unit.cardinality == "all_matching":
            raise ReferencePreflightError(
                "all_matching units cannot use single-identity reference preflight"
            )
        if unit_index in resolved_targets:
            if not _is_reference_only_unit(unit):
                raise ReferencePreflightError(
                    "Validated relationship target must be a structurally reference-only unit"
                )
            path, name = _find_existing_identity(repository, schema, resolved_targets[unit_index])
            results.append(
                UnitTargetPreflight(
                    unit_index,
                    WriteTargetOutcome.UPDATE,
                    resolved_targets[unit_index],
                    name,
                    path,
                    reference_only=True,
                )
            )
            continue
        target_kwargs = {
            "repository": repository,
            "schema": schema,
            "semantic_index": semantic_index,
            "embedder": embedder,
            "contextual_reasoner": contextual_reasoner,
            "semantic_limit": semantic_limit,
            "authenticated_actor": authenticated_actor,
            "self_binding_repository": self_binding_repository,
        }
        decision = (
            span_recorder.invoke(
                f"preflight.unit[{unit_index}].target", decide_write_target, unit, **target_kwargs
            )
            if span_recorder is not None
            else decide_write_target(unit, **target_kwargs)
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


def preflight_relationship_write_action(
    action: WriteAction,
    binding: RelationshipWriteBinding,
    *,
    relationship_projector: RelationshipEvidenceProjector,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    semantic_limit: int,
    id_allocator: Callable[[], str] = allocate_stable_id,
    authenticated_actor: AuthenticatedActorContext | None = None,
    self_binding_repository: SelfBindingRepository | None = None,
    span_recorder: SpanRecorder | None = None,
) -> tuple[UnitTargetPreflight, ...]:
    """Re-ground a relationship fact and produce one ordinary preflight table for its write.

    The fact-bearing source still uses normal write-target preflight, then must resolve to the exact
    current evidence source as an UPDATE. Member units receive only current, complete direct targets
    and may never CREATE or carry a mutation payload.
    """
    if not isinstance(action, WriteAction) or not isinstance(binding, RelationshipWriteBinding):
        raise ValueError("Relationship write preflight requires validated action and binding")
    if (
        not isinstance(binding.source_unit_index, int)
        or isinstance(binding.source_unit_index, bool)
        or not 0 <= binding.source_unit_index < len(action.units)
        or not isinstance(binding.evidence_source_id, str)
        or not binding.evidence_source_id
        or not isinstance(binding.fact_locator, str)
        or not binding.fact_locator
    ):
        raise RelationshipWritePreflightError("Relationship write has no natural source unit")
    if not binding.members or not all(
        isinstance(member, ResolvedRelationshipMember) for member in binding.members
    ):
        raise RelationshipWritePreflightError("Relationship member bindings are invalid")
    member_indices = tuple(member.unit_index for member in binding.members)
    member_ids = tuple(member.stable_id for member in binding.members)
    if (
        len(set(member_indices)) != len(member_indices)
        or len(set(member_ids)) != len(member_ids)
        or binding.source_unit_index in member_indices
        or any(
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index < len(action.units)
            or not isinstance(stable_id, str)
            or not stable_id
            for index, stable_id in zip(member_indices, member_ids, strict=True)
        )
    ):
        raise RelationshipWritePreflightError("Relationship member bindings are invalid")
    projection = relationship_projector.project_targets(
        binding.evidence_source_id, binding.fact_locator
    )
    if projection.status is not TargetProjectionStatus.COMPLETE or projection.source is None:
        raise RelationshipWritePreflightError(
            "Relationship evidence is stale, unavailable, or incomplete"
        )
    projected_ids = tuple(target.id for target in projection.targets)
    if (
        len(projected_ids) != len(member_ids)
        or len(set(projected_ids)) != len(projected_ids)
        or frozenset(projected_ids) != frozenset(member_ids)
    ):
        raise RelationshipWritePreflightError(
            "Relationship member set does not match current evidence"
        )
    source_unit = action.units[binding.source_unit_index]
    if _is_reference_only_unit(source_unit):
        raise RelationshipWritePreflightError("Relationship write source has no mutation payload")
    referenced_member_indexes = tuple(
        reference.target_index for reference in source_unit.references
    )
    if len(referenced_member_indexes) != len(set(referenced_member_indexes)) or set(
        referenced_member_indexes
    ) != set(member_indices):
        raise RelationshipWritePreflightError(
            "Relationship source references do not match member units"
        )
    preflight = _preflight_write_action(
        action,
        repository=repository,
        schema=schema,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=contextual_reasoner,
        semantic_limit=semantic_limit,
        id_allocator=id_allocator,
        authenticated_actor=authenticated_actor,
        self_binding_repository=self_binding_repository,
        span_recorder=span_recorder,
        _validated_reference_targets=dict(zip(member_indices, member_ids, strict=True)),
    )
    source = preflight[binding.source_unit_index]
    if source.outcome is not WriteTargetOutcome.UPDATE or source.stable_id != projection.source.id:
        raise RelationshipWritePreflightError(
            "Natural relationship source is not the current evidence note"
        )
    return preflight


def _is_reference_only_unit(unit: KnowledgeUnit) -> bool:
    """Return whether a unit can only provide an existing reference target and never mutate."""
    return (
        unit.intent == "record"
        and unit.cardinality == "one"
        and not unit.properties
        and not unit.tag_changes
        and not unit.facts
        and not unit.references
        and unit.destination_type is None
        and unit.target.link_scope is None
        and unit.target.self_target is None
    )


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
    return UnitTargetPreflight(unit_index, decision.outcome, stable_id, name, path)


def _find_existing_identity(
    repository: VaultRepository, schema: dict[str, Any], stable_id: str
) -> tuple[str, str]:
    """Find and validate the authoritative path and canonical name for an existing ID."""
    matches: list[tuple[str, str]] = []
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
            matches.append((path, name))
    if not matches:
        raise ReferencePreflightError(f"Resolved note ID is no longer present: {stable_id}")
    if len(matches) > 1:
        raise ReferencePreflightError(f"Stable note ID is duplicated: {stable_id}")
    return matches[0]


def _safe_creation_name(name: str) -> str:
    """Return a portable creation-time filename label without changing canonical metadata name."""
    value = name.strip()
    if not value:
        raise ReferencePreflightError("Canonical name cannot safely form a Markdown filename")
    # These characters are invalid on Windows and/or parsed as structural Obsidian wikilink syntax.
    value = re.sub(r'[<>:"/\\|?*#^\[\]%]', "_", value)
    value = value.rstrip(" .")
    if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ReferencePreflightError("Canonical name contains unsafe control characters")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(0, 10)),
        *(f"LPT{index}" for index in range(0, 10)),
    }
    device_stem, separator, extension = value.partition(".")
    if device_stem.upper() in reserved:
        value = f"{device_stem}_{separator}{extension}" if separator else f"{device_stem}_"
    return value
