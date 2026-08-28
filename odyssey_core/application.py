"""Executable composition of validated Odyssey request plans.

This module owns request-level coordination only. Identity selection, reference binding,
materialization, and bulk membership remain in their existing Phase 13--16 boundaries.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from .bulk_update import BulkUpdateResult, execute_bulk_update
from .context import ContextPackage, get_context
from .materialization import (
    BoundedNoteWriter,
    materialize_create,
    materialize_delete,
    materialize_type_migration,
    materialize_update,
)
from .reference_binding import PendingReference, render_reference_facts
from .reference_preflight import UnitTargetPreflight, preflight_write_action
from .request_planning import (
    DelegateAction,
    RequestPlan,
    RetrieveAction,
    WriteAction,
)
from .storage import VaultRepository
from .write_target import WriteTargetDecision, WriteTargetOutcome


class RequestPlanner(Protocol):
    """Describe the validated planning boundary used by an application request."""

    def plan(self, request: str) -> RequestPlan:
        """Return one validated plan for a raw non-empty user request."""


class ApplicationStatus(StrEnum):
    """Describe the aggregate completion state of one logical request."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    NEEDS_ATTENTION = "needs_attention"
    FAILED = "failed"


class ActionStatus(StrEnum):
    """Describe the outcome of one ordered RequestPlan action."""

    COMPLETED = "completed"
    DEFERRED = "deferred"
    FAILED = "failed"


class UnitStatus(StrEnum):
    """Describe the outcome of one ordered write unit."""

    SUCCEEDED = "succeeded"
    DEFERRED = "deferred"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DependencyEvidence:
    """Explain why one source unit could not safely execute.

    Attributes:
        source_unit_index: Ordered unit that was withheld.
        target_unit_index: Referenced prerequisite unit, when applicable.
        reason: Stable bounded explanation for deferral.
        candidate_stable_ids: Safe candidate identities retained for later attention.
    """

    source_unit_index: int
    target_unit_index: int | None
    reason: str
    candidate_stable_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnitResult:
    """Preserve one single-cardinality write outcome without exposing raw exceptions."""

    unit_index: int
    status: UnitStatus
    operation: str | None = None
    stable_note_id: str | None = None
    reason: str | None = None
    candidates: tuple[str, ...] = ()
    dependencies: tuple[DependencyEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Preserve typed evidence for one action in original planner order."""

    action_index: int
    kind: str
    status: ActionStatus
    retrieval: ContextPackage | None = None
    unit_results: tuple[UnitResult, ...] = ()
    bulk_result: BulkUpdateResult | None = None
    delegated_request: str | None = None
    delegated_selection: Any | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ApplicationResult:
    """Return stable, serializable evidence for execution of one user request."""

    request_id: str
    status: ApplicationStatus
    action_results: tuple[ActionResult, ...]
    affected_stable_note_ids: tuple[str, ...]
    planning_error: str | None = None


def allocate_request_id() -> str:
    """Return one strong request correlation identifier for a logical application call."""
    return str(uuid4())


def execute_request(
    user_request: str,
    *,
    planner: RequestPlanner,
    repository: VaultRepository,
    schema: dict[str, Any],
    context_index: Any,
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    actor: str,
    now: str,
    context_limit: int,
    writer: BoundedNoteWriter | None = None,
    request_id_factory: Callable[[], str] = allocate_request_id,
    preflight_id_allocator: Callable[[], str] | None = None,
    semantic_limit: int = 10,
) -> ApplicationResult:
    """Plan and execute one raw request through existing Odyssey Core primitives.

    Args:
        user_request: Raw non-empty request passed unchanged to the injected planner.
        planner: Validated RequestPlan producer; it is the only planning boundary called here.
        repository: Authoritative Markdown vault.
        schema: Active canonical schema.
        context_index: Existing rebuildable retrieval index.
        semantic_index: Existing write-target candidate index.
        embedder: Existing retrieval and resolution embedding boundary.
        contextual_reasoner: Existing bounded contextual resolver.
        actor: Persistence lifecycle actor.
        now: Explicit persistence lifecycle timestamp.
        context_limit: Explicit positive retrieval result budget.
        writer: Optional bounded UPDATE writer.
        request_id_factory: Injected one-per-request ID generator.
        preflight_id_allocator: Optional deterministic CREATE ID allocator.
        semantic_limit: Existing bounded semantic-resolution candidate budget.

    Returns:
        One stable request result. Planning failures return no action results and perform no writes.

    Raises:
        ValueError: If boundary inputs are structurally invalid.
        TypeError: If the planner returns a value other than RequestPlan.
    """
    if not isinstance(user_request, str) or not user_request.strip():
        raise ValueError("user_request must be a non-empty string")
    request_id = request_id_factory()
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id_factory must return a non-empty string")
    try:
        plan = planner.plan(user_request)
    except Exception as error:
        return ApplicationResult(
            request_id,
            ApplicationStatus.FAILED,
            (),
            (),
            _safe_reason(error),
        )
    if not isinstance(plan, RequestPlan):
        raise TypeError("planner must return a RequestPlan")

    actions: list[ActionResult] = []
    affected: list[str] = []
    for action_index, action in enumerate(plan.actions):
        if isinstance(action, RetrieveAction):
            result = _execute_retrieve(
                action_index, action, repository, schema, context_index, embedder, context_limit
            )
        elif isinstance(action, WriteAction):
            result = _execute_write(
                action_index,
                action,
                repository,
                schema,
                semantic_index,
                embedder,
                contextual_reasoner,
                actor,
                now,
                writer,
                semantic_limit,
                preflight_id_allocator,
            )
        elif isinstance(action, DelegateAction):
            result = ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                delegated_request=action.request,
                delegated_selection=action.selection,
                reason="DELEGATED_CAPABILITY",
            )
        else:  # RequestPlan validation should make this unreachable.
            raise TypeError("RequestPlan contains an unsupported action type")
        actions.append(result)
        affected.extend(_affected_ids(result))
    return ApplicationResult(request_id, _overall_status(actions), tuple(actions), tuple(affected))


def _execute_retrieve(
    action_index: int,
    action: RetrieveAction,
    repository: VaultRepository,
    schema: dict[str, Any],
    context_index: Any,
    embedder: Any,
    context_limit: int,
) -> ActionResult:
    """Execute one ordinary retrieval or preserve unsupported graph intent as deferred evidence."""
    if action.plan.link_scope is not None:
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.DEFERRED,
            reason="UNSUPPORTED_RETRIEVAL_LINK_SCOPE",
        )
    try:
        context = get_context(
            repository,
            schema,
            context_index,
            embedder,
            query=action.plan.query,
            limit=context_limit,
            type=action.plan.type,
            filters=action.plan.filters,
        )
    except Exception as error:
        return ActionResult(
            action_index, action.kind, ActionStatus.FAILED, reason=_safe_reason(error)
        )
    return ActionResult(action_index, action.kind, ActionStatus.COMPLETED, retrieval=context)


def _execute_write(
    action_index: int,
    action: WriteAction,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    actor: str,
    now: str,
    writer: BoundedNoteWriter | None,
    semantic_limit: int,
    id_allocator: Callable[[], str] | None,
) -> ActionResult:
    """Execute one write action without reopening target decisions or reference binding."""
    cardinalities = {unit.cardinality for unit in action.units}
    if len(cardinalities) != 1:
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.DEFERRED,
            unit_results=tuple(
                UnitResult(index, UnitStatus.DEFERRED, reason="UNSUPPORTED_MIXED_CARDINALITY")
                for index, _ in enumerate(action.units)
            ),
            reason="UNSUPPORTED_MIXED_CARDINALITY",
        )
    if cardinalities == {"all_matching"}:
        return _execute_bulk(action_index, action, repository, schema, actor, now, writer)
    try:
        kwargs: dict[str, Any] = {}
        if id_allocator is not None:
            kwargs["id_allocator"] = id_allocator
        preflight = preflight_write_action(
            action,
            repository=repository,
            schema=schema,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            semantic_limit=semantic_limit,
            **kwargs,
        )
        rendering = render_reference_facts(action, preflight)
    except Exception as error:
        return ActionResult(
            action_index, action.kind, ActionStatus.FAILED, reason=_safe_reason(error)
        )
    results = _execute_single_units(
        action,
        preflight,
        rendering.pending_references,
        rendering.rendered_facts,
        repository,
        schema,
        actor,
        now,
        writer,
    )
    return ActionResult(
        action_index, action.kind, _action_status(results), unit_results=tuple(results)
    )


def _execute_bulk(
    action_index: int,
    action: WriteAction,
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: str,
    now: str,
    writer: BoundedNoteWriter | None,
) -> ActionResult:
    """Execute one or more independent all-matching updates through the existing bulk primitive."""
    if len(action.units) != 1:
        return ActionResult(
            action_index, action.kind, ActionStatus.DEFERRED, reason="UNSUPPORTED_MULTI_UNIT_BULK"
        )
    try:
        result = execute_bulk_update(
            action.units[0],
            repository=repository,
            schema=schema,
            actor=actor,
            now=now,
            writer=writer,
        )
    except Exception as error:
        return ActionResult(
            action_index, action.kind, ActionStatus.FAILED, reason=_safe_reason(error)
        )
    status = (
        ActionStatus.COMPLETED
        if result.status in {"SUCCESS", "EMPTY_SET"}
        else (ActionStatus.FAILED if result.status == "FAILURE" else ActionStatus.DEFERRED)
    )
    return ActionResult(action_index, action.kind, status, bulk_result=result)


def _execute_single_units(
    action: WriteAction,
    preflight: tuple[UnitTargetPreflight, ...],
    pending: tuple[PendingReference, ...],
    rendered_facts: tuple[tuple[str, ...], ...],
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: str,
    now: str,
    writer: BoundedNoteWriter | None,
) -> list[UnitResult]:
    """Run safe units in deterministic dependency order while preserving independent outcomes."""
    pending_by_source: dict[int, list[PendingReference]] = {}
    for item in pending:
        pending_by_source.setdefault(item.source_unit_index, []).append(item)
    dependencies = _create_dependencies(action, preflight)
    results: dict[int, UnitResult] = {}
    for index, target in enumerate(preflight):
        if target.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION:
            results[index] = UnitResult(
                index,
                UnitStatus.DEFERRED,
                reason=target.reason,
                candidates=target.candidate_note_ids,
            )
        elif index in pending_by_source:
            items = pending_by_source[index]
            results[index] = UnitResult(
                index,
                UnitStatus.DEFERRED,
                reason="REFERENCE_DEPENDENCY_UNRESOLVED",
                candidates=tuple(
                    candidate for item in items for candidate in item.candidate_stable_ids
                ),
                dependencies=tuple(
                    DependencyEvidence(
                        index,
                        item.target_unit_index,
                        item.reason,
                        item.candidate_stable_ids,
                    )
                    for item in items
                ),
            )
    for cycle_index in _cyclic_nodes(dependencies):
        if cycle_index not in results:
            results[cycle_index] = UnitResult(
                cycle_index,
                UnitStatus.DEFERRED,
                reason="CYCLIC_CREATE_DEPENDENCY",
                dependencies=(DependencyEvidence(cycle_index, None, "CYCLIC_CREATE_DEPENDENCY"),),
            )
    for index in _topological_order(dependencies):
        if index in results:
            continue
        failed_dependency = next(
            (
                dep
                for dep in dependencies[index]
                if dep in results and results[dep].status is not UnitStatus.SUCCEEDED
            ),
            None,
        )
        if failed_dependency is not None:
            results[index] = UnitResult(
                index,
                UnitStatus.DEFERRED,
                reason="DEPENDENCY_FAILED",
                dependencies=(DependencyEvidence(index, failed_dependency, "DEPENDENCY_FAILED"),),
            )
            continue
        unit = action.units[index]
        target = preflight[index]
        decision = WriteTargetDecision(target.outcome, existing_note_id=target.stable_id)
        try:
            if target.outcome is WriteTargetOutcome.CREATE:
                persisted = materialize_create(
                    unit,
                    target,
                    unit_index=index,
                    repository=repository,
                    schema=schema,
                    actor=actor,
                    now=now,
                    rendered_facts=rendered_facts[index],
                )
            elif unit.intent == "delete":
                persisted = materialize_delete(
                    unit, decision, repository=repository, schema=schema, actor=actor, now=now
                )
            elif unit.destination_type is not None:
                persisted = materialize_type_migration(
                    unit, decision, repository=repository, schema=schema, actor=actor, now=now
                )
            else:
                persisted = materialize_update(
                    unit,
                    decision,
                    repository=repository,
                    schema=schema,
                    actor=actor,
                    now=now,
                    writer=writer,
                    rendered_facts=rendered_facts[index],
                )
        except Exception as error:
            results[index] = UnitResult(
                index,
                UnitStatus.FAILED,
                operation=target.outcome.value,
                stable_note_id=target.stable_id,
                reason=_safe_reason(error),
            )
        else:
            results[index] = UnitResult(
                index,
                UnitStatus.SUCCEEDED,
                operation=persisted.operation.value,
                stable_note_id=persisted.id,
            )
    return [results[index] for index in range(len(action.units))]


def _create_dependencies(
    action: WriteAction, preflight: tuple[UnitTargetPreflight, ...]
) -> dict[int, set[int]]:
    """Return only source-to-new-CREATE prerequisites; existing notes require no mutation dependency."""
    dependencies = {index: set() for index, _ in enumerate(action.units)}
    for source, unit in enumerate(action.units):
        for reference in unit.references:
            if preflight[reference.target_index].outcome is WriteTargetOutcome.CREATE:
                dependencies[source].add(reference.target_index)
    return dependencies


def _topological_order(dependencies: dict[int, set[int]]) -> tuple[int, ...]:
    """Return a stable dependency-first order, leaving cyclic nodes for explicit deferral."""
    cyclic = set(_cyclic_nodes(dependencies))
    remaining = {node: set(edges) for node, edges in dependencies.items()}
    for node in cyclic:
        remaining.pop(node, None)
    for edges in remaining.values():
        edges.difference_update(cyclic)
    ordered: list[int] = []
    while ready := sorted(node for node, edges in remaining.items() if not edges):
        for node in ready:
            ordered.append(node)
            remaining.pop(node)
        for edges in remaining.values():
            edges.difference_update(ready)
    return tuple(ordered)


def _cyclic_nodes(dependencies: dict[int, set[int]]) -> tuple[int, ...]:
    """Return only CREATE-cycle members, leaving downstream nodes as failed dependents."""
    visiting: list[int] = []
    visited: set[int] = set()
    cyclic: set[int] = set()

    def visit(node: int) -> None:
        """Mark the precise back-edge segment reached while walking one dependency chain."""
        if node in visiting:
            cyclic.update(visiting[visiting.index(node) :])
            return
        if node in visited:
            return
        visiting.append(node)
        for dependency in dependencies[node]:
            visit(dependency)
        visiting.pop()
        visited.add(node)

    for node in sorted(dependencies):
        visit(node)
    return tuple(sorted(cyclic))


def _action_status(results: list[UnitResult]) -> ActionStatus:
    """Summarize ordered unit outcomes without hiding partial success."""
    statuses = {result.status for result in results}
    if statuses == {UnitStatus.SUCCEEDED}:
        return ActionStatus.COMPLETED
    if UnitStatus.SUCCEEDED in statuses:
        return ActionStatus.DEFERRED
    if UnitStatus.DEFERRED in statuses:
        return ActionStatus.DEFERRED
    return ActionStatus.FAILED


def _overall_status(actions: list[ActionResult]) -> ApplicationStatus:
    """Summarize request outcomes with a distinct attention state for purely deferred work."""
    statuses = {action.status for action in actions}
    if statuses == {ActionStatus.COMPLETED}:
        return ApplicationStatus.COMPLETED
    if ActionStatus.COMPLETED in statuses or any(_affected_ids(action) for action in actions):
        return ApplicationStatus.PARTIAL
    if ActionStatus.DEFERRED in statuses:
        return ApplicationStatus.NEEDS_ATTENTION
    return ApplicationStatus.FAILED


def _affected_ids(result: ActionResult) -> tuple[str, ...]:
    """Extract successful note identities from one action result in deterministic order."""
    ids = [
        item.stable_note_id
        for item in result.unit_results
        if item.status is UnitStatus.SUCCEEDED and item.stable_note_id
    ]
    if result.bulk_result is not None:
        ids.extend(item.stable_id for item in result.bulk_result.succeeded)
    return tuple(ids)


def _safe_reason(error: Exception) -> str:
    """Return a bounded exception summary suitable for a future adapter result."""
    reason = str(error).strip()
    return (reason or type(error).__name__)[:300]
