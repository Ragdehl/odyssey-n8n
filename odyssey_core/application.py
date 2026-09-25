"""Executable composition of validated Odyssey request plans.

This module owns request-level coordination only. Identity selection, reference binding,
materialization, and bulk membership remain in their existing Phase 13--16 boundaries.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from time import perf_counter
from typing import Any, Protocol, cast
from uuid import uuid4

from .bulk_update import BulkUpdateResult, execute_bulk_update
from .context import ContextPackage, get_context
from .fact_selection import AtomicFactSelector
from .git_history import GitHistoryResult, GitHistorySnapshot, HistoryRecorder, HistoryStatus
from .identity_boundary import AuthenticatedActorContext, SelfBindingError, SelfBindingRepository
from .materialization import (
    BoundedNoteWriter,
    materialize_create,
    materialize_delete,
    materialize_type_migration,
    materialize_update,
)
from .observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalStage,
    ProviderCallEvidence,
    SpanRecorder,
    normalize_provider_usage,
)
from .persistence import ActorInput
from .reference_binding import PendingReference, render_reference_facts
from .reference_preflight import (
    RelationshipWritePreflightError,
    UnitTargetPreflight,
    preflight_relational_target_write_action,
    preflight_relationship_write_action,
    preflight_write_action,
    prepare_relationship_shared_fact_action,
)
from .relational_resolution import RelationalResolutionError, resolve_relational_reference
from .relationship_evidence import RelationshipEvidenceProjector
from .request_planning import (
    DelegateAction,
    KnowledgeUnit,
    PlannerClarification,
    PlannerResult,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
)
from .semantic_sets import (
    SemanticSetOutcome,
    SemanticSetResolution,
    resolve_semantic_set,
)
from .storage import VaultRepository
from .write_target import WriteTargetDecision, WriteTargetOutcome


class RequestPlanner(Protocol):
    """Describe the validated planning boundary used by an application request."""

    def plan(
        self, request: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> PlannerResult:
        """Return one validated plan or closed clarification for a raw request."""


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
class PendingWorkStatus:
    """Describe whether incomplete post-plan work was made durable.

    A completed request needs no record. An incomplete request always reports whether its record was
    persisted, allowing callers to distinguish execution evidence from a later storage failure.
    """

    required: bool = False
    persisted: bool = False
    record_id: str | None = None
    error: str | None = None


class PendingWorkRecorder(Protocol):
    """Describe the small create-only pending-work boundary used after execution."""

    def record(
        self, *, user_request: str, plan: RequestPlan, result: ApplicationResult, created_at: str
    ) -> str:
        """Persist one incomplete validated request and return its durable record ID."""


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
    materially_affected: bool = True


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
    semantic_set: SemanticSetResolution | None = None


@dataclass(frozen=True, slots=True)
class ApplicationResult:
    """Return stable, serializable evidence for execution of one user request."""

    request_id: str
    status: ApplicationStatus
    action_results: tuple[ActionResult, ...]
    affected_stable_note_ids: tuple[str, ...]
    planning_error: str | None = None
    clarification_code: str | None = None
    pending_work: PendingWorkStatus = PendingWorkStatus()
    history: GitHistoryResult = GitHistoryResult.disabled()
    operational: OperationalEvidence = OperationalEvidence()
    presentation_intent: str = "answer"
    note_set_selection: SelectionCriteria | None = None
    note_result_snapshot: Mapping[str, Any] | None = None


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
    actor: ActorInput,
    now: str,
    context_limit: int,
    writer: BoundedNoteWriter | None = None,
    fact_selector: AtomicFactSelector | None = None,
    request_id_factory: Callable[[], str] = allocate_request_id,
    authenticated_actor: AuthenticatedActorContext | None = None,
    self_binding_repository: SelfBindingRepository | None = None,
    preflight_id_allocator: Callable[[], str] | None = None,
    semantic_limit: int = 10,
    semantic_set_selector: Any = None,
    pending_recorder: PendingWorkRecorder | None = None,
    history_recorder: HistoryRecorder | None = None,
    monotonic: Callable[[], float] = perf_counter,
    conversation_context: Sequence[Mapping[str, str]] = (),
) -> ApplicationResult:
    """Plan and execute one raw request through existing Odyssey Core primitives.

    Args:
        user_request: Raw non-empty request passed unchanged to the injected planner.
        planner: Validated PlannerResult producer; it is the only planning boundary called here.
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
        authenticated_actor: Optional normalized actor context from the trusted integration
            boundary; raw headers, JWTs, and provider credentials are not accepted.
        preflight_id_allocator: Optional deterministic CREATE ID allocator.
        semantic_limit: Existing bounded semantic-resolution candidate budget.
        semantic_set_selector: Optional bounded candidate-only semantic-set selector. When absent,
            semantic-set plans defer rather than falling through to ordinary ranked retrieval.
        pending_recorder: Optional create-only durable pending-work recorder.
        history_recorder: Optional request-level local Git history recorder.
        conversation_context: Bounded visible recent turns used only by the planner to resolve
            continuity; Core never passes this text to canonical retrieval or mutation boundaries.

    Returns:
        One stable request result. Clarifications and planning failures perform no actions or writes.

    Raises:
        ValueError: If boundary inputs are structurally invalid.
        TypeError: If the planner returns a value other than PlannerResult.
    """
    started = monotonic()
    stages: list[OperationalStage] = []
    if not isinstance(user_request, str) or not user_request.strip():
        raise ValueError("user_request must be a non-empty string")
    request_id = request_id_factory()
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id_factory must return a non-empty string")
    if authenticated_actor is not None and not isinstance(
        authenticated_actor, AuthenticatedActorContext
    ):
        raise ValueError("authenticated actor context is invalid")
    planner_started = monotonic()
    provider_recorder = _ProviderCallRecorder(monotonic, planner_started)
    try:
        plan = (
            provider_recorder.invoke(
                "planner", planner, planner.plan, user_request, conversation_context
            )
            if conversation_context
            else provider_recorder.invoke("planner", planner, planner.plan, user_request)
        )
    except Exception as error:
        stages.append(
            OperationalStage(
                "planner",
                OperationalOutcome.FAILED,
                _elapsed_ms(planner_started, monotonic()),
                model=getattr(planner, "model", None),
                reasoning_effort=getattr(planner, "reasoning_effort", None),
                usage=normalize_provider_usage(getattr(planner, "last_usage", None)),
                error_category=type(error).__name__,
                provider_calls=_planner_attempts(planner, provider_recorder.calls),
                start_offset_ms=_elapsed_ms(started, planner_started),
                substeps=getattr(planner, "last_spans", ()),
            )
        )
        return _with_operational(
            ApplicationResult(
                request_id,
                ApplicationStatus.FAILED,
                (),
                (),
                _safe_reason(error),
                history=(
                    GitHistoryResult(HistoryStatus.NOT_ATTEMPTED, reason="planning failed")
                    if history_recorder is not None
                    else GitHistoryResult.disabled()
                ),
            ),
            stages,
            started,
            monotonic,
        )
    planner_duration_ms = _elapsed_ms(planner_started, monotonic())
    if isinstance(plan, PlannerClarification):
        stages.append(
            OperationalStage(
                "planner",
                OperationalOutcome.COMPLETED,
                planner_duration_ms,
                model=getattr(planner, "model", None),
                reasoning_effort=getattr(planner, "reasoning_effort", None),
                usage=normalize_provider_usage(getattr(planner, "last_usage", None)),
                provider_calls=_planner_attempts(planner, provider_recorder.calls),
                start_offset_ms=_elapsed_ms(started, planner_started),
                substeps=getattr(planner, "last_spans", ()),
            )
        )
        stages.append(OperationalStage("pending", OperationalOutcome.SKIPPED))
        return _with_operational(
            ApplicationResult(
                request_id,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                clarification_code=plan.code,
                history=(
                    GitHistoryResult(HistoryStatus.NOT_ATTEMPTED, reason="clarification requested")
                    if history_recorder is not None
                    else GitHistoryResult.disabled()
                ),
            ),
            stages,
            started,
            monotonic,
        )
    if not isinstance(plan, RequestPlan):
        raise TypeError("planner must return a PlannerResult")
    planner_calls = _planner_attempts(planner, provider_recorder.calls)

    history_snapshot: GitHistorySnapshot | None = None
    history_error: str | None = None
    if history_recorder is not None:
        history_started = monotonic()
        try:
            history_snapshot = history_recorder.begin(request_id)
        except Exception as error:
            history_error = _safe_reason(error)
            stages.append(
                _stage("git", OperationalOutcome.FAILED, history_started, monotonic, error, started)
            )

    actions: list[ActionResult] = []
    affected: list[str] = []
    next_fact_ordinal = 0
    for action_index, action in enumerate(plan.actions):
        provider_start = len(provider_recorder.calls)
        action_started = monotonic()
        provider_recorder.origin = action_started
        action_spans = SpanRecorder(action_started, monotonic)
        measured_embedder = _MeasuredEmbedder(embedder, action_spans)
        measured_contextual_reasoner = (
            _MeasuredContextualReasoner(contextual_reasoner, provider_recorder)
            if callable(getattr(contextual_reasoner, "resolve", None))
            else contextual_reasoner
        )
        measured_writer = (
            _MeasuredWriter(writer, provider_recorder)
            if callable(getattr(writer, "write", None))
            else writer
        )
        measured_fact_selector = (
            _MeasuredFactSelector(fact_selector, provider_recorder)
            if callable(getattr(fact_selector, "select", None))
            else fact_selector
        )
        if isinstance(action, RetrieveAction):
            result = _execute_retrieve(
                action_index,
                action,
                repository,
                schema,
                context_index,
                measured_embedder,
                context_limit,
                authenticated_actor,
                self_binding_repository,
                action_spans,
                semantic_index=semantic_index,
                contextual_reasoner=measured_contextual_reasoner,
                semantic_limit=semantic_limit,
                semantic_set_selector=semantic_set_selector,
            )
        elif isinstance(action, WriteAction):
            unit_ordinals: tuple[tuple[int, ...], ...] = tuple(
                tuple(range(start, start + len(unit.facts)))
                for start, unit in _fact_ordinal_starts(action, next_fact_ordinal)
            )
            next_fact_ordinal += sum(len(unit.facts) for unit in action.units)
            result = _execute_write(
                action_index,
                action,
                repository,
                schema,
                semantic_index,
                measured_embedder,
                measured_contextual_reasoner,
                actor,
                now,
                measured_writer,
                semantic_limit,
                preflight_id_allocator,
                request_id,
                unit_ordinals,
                measured_fact_selector,
                authenticated_actor,
                self_binding_repository,
                action_spans,
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
        stages.append(
            OperationalStage(
                f"action.{action.kind}",
                _action_operational_outcome(result.status),
                _elapsed_ms(action_started, monotonic()),
                provider_calls=tuple(provider_recorder.calls[provider_start:]),
                start_offset_ms=_elapsed_ms(started, action_started),
                substeps=action_spans.spans,
            )
        )
    planner_stage = OperationalStage(
        "planner",
        OperationalOutcome.COMPLETED,
        planner_duration_ms,
        model=getattr(planner, "model", None),
        reasoning_effort=getattr(planner, "reasoning_effort", None),
        usage=normalize_provider_usage(getattr(planner, "last_usage", None)),
        provider_calls=planner_calls,
        start_offset_ms=_elapsed_ms(started, planner_started),
        substeps=getattr(planner, "last_spans", ()),
    )
    stages.insert(0, planner_stage)
    result = ApplicationResult(
        request_id,
        _overall_status(actions),
        tuple(actions),
        tuple(affected),
        history=(
            GitHistoryResult(HistoryStatus.FAILED, reason=history_error)
            if history_error is not None
            else GitHistoryResult.disabled()
        ),
        presentation_intent=plan.presentation_intent,
        note_set_selection=(
            plan.actions[0].plan
            if plan.presentation_intent != "answer" and isinstance(plan.actions[0], RetrieveAction)
            else None
        ),
    )
    if history_recorder is not None and history_error is None and history_snapshot is not None:
        history_started = monotonic()
        try:
            history = history_recorder.record(
                request_id=request_id,
                snapshot=history_snapshot,
                affected_stable_note_ids=result.affected_stable_note_ids,
                repository=repository,
                schema=schema,
            )
        except Exception as error:
            history = GitHistoryResult(HistoryStatus.FAILED, reason=_safe_reason(error))
            history_outcome = OperationalOutcome.FAILED
            history_error_category = type(error).__name__
        else:
            history_outcome = (
                OperationalOutcome.COMPLETED
                if history.status in {HistoryStatus.COMMITTED, HistoryStatus.NO_CHANGES}
                else OperationalOutcome.SKIPPED
            )
            history_error_category = None
        stages.append(
            OperationalStage(
                "git",
                history_outcome,
                _elapsed_ms(history_started, monotonic()),
                error_category=history_error_category,
                start_offset_ms=_elapsed_ms(started, history_started),
            )
        )
        result = replace(result, history=history)
    if not any(action.status is not ActionStatus.COMPLETED for action in actions):
        stages.append(OperationalStage("pending", OperationalOutcome.SKIPPED))
        return _with_operational(result, stages, started, monotonic)
    if pending_recorder is None:
        stages.append(OperationalStage("pending", OperationalOutcome.UNAVAILABLE))
        return _with_operational(
            replace(
                result,
                pending_work=PendingWorkStatus(
                    required=True, error="pending recorder is not configured"
                ),
            ),
            stages,
            started,
            monotonic,
        )
    pending_started = monotonic()
    try:
        record_id = pending_recorder.record(
            user_request=user_request, plan=plan, result=result, created_at=now
        )
    except Exception as error:
        stages.append(
            _stage("pending", OperationalOutcome.FAILED, pending_started, monotonic, error, started)
        )
        return _with_operational(
            replace(
                result,
                pending_work=PendingWorkStatus(required=True, error=_safe_reason(error)),
            ),
            stages,
            started,
            monotonic,
        )
    stages.append(
        OperationalStage(
            "pending",
            OperationalOutcome.COMPLETED,
            _elapsed_ms(pending_started, monotonic()),
            start_offset_ms=_elapsed_ms(started, pending_started),
        )
    )
    return _with_operational(
        replace(
            result,
            pending_work=PendingWorkStatus(required=True, persisted=True, record_id=record_id),
        ),
        stages,
        started,
        monotonic,
    )


def _execute_retrieve(
    action_index: int,
    action: RetrieveAction,
    repository: VaultRepository,
    schema: dict[str, Any],
    context_index: Any,
    embedder: Any,
    context_limit: int,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    spans: SpanRecorder,
    semantic_index: Any = None,
    contextual_reasoner: Any = None,
    semantic_limit: int = 10,
    semantic_set_selector: Any = None,
) -> ActionResult:
    """Execute retrieval, restricting relational intent to its exact current member identities."""
    if action.plan.link_scope is not None:
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.DEFERRED,
            reason="UNSUPPORTED_RETRIEVAL_LINK_SCOPE",
        )
    if action.plan.semantic_set is not None:
        if not callable(getattr(semantic_set_selector, "select", None)):
            return ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                reason="semantic_set_selector_unavailable",
            )
        try:
            semantic_set = spans.invoke(
                "semantic_set_resolution",
                resolve_semantic_set,
                action.plan.semantic_set,
                repository=repository,
                schema=schema,
                selector=semantic_set_selector,
            )
        except Exception as error:
            return ActionResult(
                action_index, action.kind, ActionStatus.FAILED, reason=_safe_reason(error)
            )
        if semantic_set.outcome is not SemanticSetOutcome.ANSWERABLE:
            return ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                semantic_set=semantic_set,
                reason=semantic_set.outcome.value,
            )
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.COMPLETED,
            semantic_set=semantic_set,
        )
    allowed_note_ids: frozenset[str] | None = None
    if action.plan.relational_reference is not None:
        try:
            resolved = spans.invoke(
                "relational_resolution",
                resolve_relational_reference,
                action.plan,
                repository=repository,
                schema=schema,
                semantic_index=semantic_index,
                embedder=embedder,
                contextual_reasoner=contextual_reasoner,
                semantic_limit=semantic_limit,
                authenticated_actor=authenticated_actor,
                self_binding_repository=self_binding_repository,
            )
        except RelationalResolutionError as error:
            return ActionResult(action_index, action.kind, ActionStatus.DEFERRED, reason=str(error))
        except Exception as error:
            return ActionResult(
                action_index, action.kind, ActionStatus.FAILED, reason=_safe_reason(error)
            )
        allowed_note_ids = frozenset(target.id for target in resolved.targets)
        if not allowed_note_ids:
            return ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                reason="relational_evidence_incomplete",
            )
    if action.plan.self_target is not None:
        if action.plan.self_target != "self":
            return ActionResult(
                action_index, action.kind, ActionStatus.DEFERRED, reason="self_identity_unavailable"
            )
        if authenticated_actor is None or self_binding_repository is None:
            return ActionResult(
                action_index, action.kind, ActionStatus.DEFERRED, reason="self_identity_unavailable"
            )
        try:
            binding = self_binding_repository.resolve(authenticated_actor.stable_user_id)
        except SelfBindingError:
            return ActionResult(
                action_index, action.kind, ActionStatus.DEFERRED, reason="self_identity_unavailable"
            )
        allowed_note_ids = frozenset({binding.person_note_id})
    try:
        context_kwargs: dict[str, Any] = {}
        if allowed_note_ids is not None:
            context_kwargs["allowed_note_ids"] = allowed_note_ids
        context = spans.invoke(
            "retrieval",
            get_context,
            repository,
            schema,
            context_index,
            embedder,
            query=action.plan.query,
            limit=context_limit,
            type=action.plan.type,
            filters=action.plan.filters,
            **context_kwargs,
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
    actor: ActorInput,
    now: str,
    writer: BoundedNoteWriter | None,
    semantic_limit: int,
    id_allocator: Callable[[], str] | None,
    request_id: str,
    unit_ordinals: tuple[tuple[int, ...], ...],
    fact_selector: AtomicFactSelector | None,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    spans: SpanRecorder,
) -> ActionResult:
    """Execute one write action without reopening target decisions or reference binding."""
    if any(unit.target.relational_reference is not None for unit in action.units):
        return _execute_relational_write(
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
            id_allocator,
            request_id,
            unit_ordinals,
            fact_selector,
            authenticated_actor,
            self_binding_repository,
            spans,
        )
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
        return _execute_bulk(
            action_index,
            action,
            repository,
            schema,
            actor,
            now,
            writer,
            request_id,
            unit_ordinals[0],
        )
    try:
        kwargs: dict[str, Any] = {}
        if id_allocator is not None:
            kwargs["id_allocator"] = id_allocator
        preflight = spans.invoke(
            "preflight",
            preflight_write_action,
            action,
            repository=repository,
            schema=schema,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            semantic_limit=semantic_limit,
            authenticated_actor=authenticated_actor,
            self_binding_repository=self_binding_repository,
            span_recorder=spans,
            **kwargs,
        )
        rendering = spans.invoke("reference_render", render_reference_facts, action, preflight)
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
        request_id,
        unit_ordinals,
        fact_selector,
        spans,
    )
    return ActionResult(
        action_index, action.kind, _action_status(results), unit_results=tuple(results)
    )


def _execute_relational_write(
    action_index: int,
    action: WriteAction,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    actor: ActorInput,
    now: str,
    writer: BoundedNoteWriter | None,
    semantic_limit: int,
    id_allocator: Callable[[], str] | None,
    request_id: str,
    unit_ordinals: tuple[tuple[int, ...], ...],
    fact_selector: AtomicFactSelector | None,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    spans: SpanRecorder,
) -> ActionResult:
    """Route one relational write through current evidence and relationship-only preflight."""
    relational_indexes = tuple(
        index
        for index, candidate in enumerate(action.units)
        if candidate.target.relational_reference is not None
    )
    if len(relational_indexes) != 1 or any(
        candidate.cardinality != "one" for candidate in action.units
    ):
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.DEFERRED,
            reason="UNSUPPORTED_RELATIONAL_WRITE_SHAPE",
        )
    relational_index = relational_indexes[0]
    unit = action.units[relational_index]
    relation = unit.target.relational_reference
    if relation is None:
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.DEFERRED,
            reason="UNSUPPORTED_RELATIONAL_WRITE_SHAPE",
        )
    try:
        resolved = spans.invoke(
            "relational_resolution",
            resolve_relational_reference,
            unit.target,
            repository=repository,
            schema=schema,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            semantic_limit=semantic_limit,
            authenticated_actor=authenticated_actor,
            self_binding_repository=self_binding_repository,
        )
        projector = RelationshipEvidenceProjector(repository, schema)
        kwargs: dict[str, Any] = {}
        if id_allocator is not None:
            kwargs["id_allocator"] = id_allocator
        if relation.members == "complete_set":
            if len(action.units) != 1:
                raise RelationshipWritePreflightError("Shared relationship fact must be one unit")
            executable, binding = prepare_relationship_shared_fact_action(unit, resolved)
            preflight = spans.invoke(
                "preflight",
                preflight_relationship_write_action,
                executable,
                binding,
                relationship_projector=projector,
                repository=repository,
                schema=schema,
                semantic_index=semantic_index,
                embedder=embedder,
                contextual_reasoner=contextual_reasoner,
                semantic_limit=semantic_limit,
                authenticated_actor=authenticated_actor,
                self_binding_repository=self_binding_repository,
                span_recorder=spans,
                **kwargs,
            )
            ordinals = (unit_ordinals[0], *(((),) * len(resolved.targets)))
        else:
            executable = action
            ordinals = unit_ordinals
            preflight = spans.invoke(
                "preflight",
                preflight_relational_target_write_action,
                action,
                resolved,
                target_unit_index=relational_index,
                relationship_projector=projector,
                repository=repository,
                schema=schema,
                semantic_index=semantic_index,
                embedder=embedder,
                contextual_reasoner=contextual_reasoner,
                semantic_limit=semantic_limit,
                authenticated_actor=authenticated_actor,
                self_binding_repository=self_binding_repository,
                span_recorder=spans,
                **kwargs,
            )
        rendering = spans.invoke("reference_render", render_reference_facts, executable, preflight)
        if rendering.pending_references:
            raise RelationshipWritePreflightError("Relationship member binding is incomplete")
    except (RelationalResolutionError, RelationshipWritePreflightError) as error:
        return ActionResult(action_index, action.kind, ActionStatus.DEFERRED, reason=str(error))
    except Exception as error:
        return ActionResult(
            action_index, action.kind, ActionStatus.FAILED, reason=_safe_reason(error)
        )
    results = _execute_single_units(
        executable,
        preflight,
        rendering.pending_references,
        rendering.rendered_facts,
        repository,
        schema,
        actor,
        now,
        writer,
        request_id,
        ordinals,
        fact_selector,
        spans,
    )
    if relation.members == "complete_set":
        results = results[:1]
    return ActionResult(
        action_index,
        action.kind,
        _action_status(results),
        unit_results=tuple(results),
    )


def _execute_bulk(
    action_index: int,
    action: WriteAction,
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: ActorInput,
    now: str,
    writer: BoundedNoteWriter | None,
    request_id: str,
    fact_ordinals: tuple[int, ...],
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
            request_id=request_id,
            fact_ordinals=fact_ordinals,
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
    actor: ActorInput,
    now: str,
    writer: BoundedNoteWriter | None,
    request_id: str,
    unit_ordinals: tuple[tuple[int, ...], ...],
    fact_selector: AtomicFactSelector | None,
    spans: SpanRecorder,
) -> list[UnitResult]:
    """Run safe units in deterministic dependency order while preserving independent outcomes."""
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
        if target.reference_only:
            results[index] = UnitResult(
                index,
                UnitStatus.SUCCEEDED,
                operation="REFERENCE_BOUND",
                stable_note_id=target.stable_id,
                materially_affected=False,
            )
            continue
        decision = WriteTargetDecision(target.outcome, existing_note_id=target.stable_id)
        try:
            if target.outcome is WriteTargetOutcome.CREATE:
                persisted = spans.invoke(
                    f"unit[{index}].materialize",
                    materialize_create,
                    unit,
                    target,
                    unit_index=index,
                    repository=repository,
                    schema=schema,
                    actor=actor,
                    now=now,
                    rendered_facts=rendered_facts[index],
                    request_id=request_id,
                    fact_ordinals=unit_ordinals[index],
                )
            elif unit.intent == "delete":
                persisted = spans.invoke(
                    f"unit[{index}].materialize",
                    materialize_delete,
                    unit,
                    decision,
                    repository=repository,
                    schema=schema,
                    actor=actor,
                    now=now,
                )
            elif unit.destination_type is not None:
                persisted = spans.invoke(
                    f"unit[{index}].materialize",
                    materialize_type_migration,
                    unit,
                    decision,
                    repository=repository,
                    schema=schema,
                    actor=actor,
                    now=now,
                )
            else:
                persisted = spans.invoke(
                    f"unit[{index}].materialize",
                    materialize_update,
                    unit,
                    decision,
                    repository=repository,
                    schema=schema,
                    actor=actor,
                    now=now,
                    writer=writer,
                    rendered_facts=rendered_facts[index],
                    request_id=request_id,
                    fact_ordinals=unit_ordinals[index],
                    fact_selector=fact_selector,
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


def _fact_ordinal_starts(action: WriteAction, start: int) -> tuple[tuple[int, KnowledgeUnit], ...]:
    """Return each unit paired with its request-plan fact-ordinal start."""
    pairs: list[tuple[int, KnowledgeUnit]] = []
    current = start
    for unit in action.units:
        pairs.append((current, unit))
        current += len(unit.facts)
    return tuple(pairs)


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
        if item.status is UnitStatus.SUCCEEDED and item.materially_affected and item.stable_note_id
    ]
    if result.bulk_result is not None:
        ids.extend(item.stable_id for item in result.bulk_result.succeeded)
    return tuple(ids)


def _safe_reason(error: Exception) -> str:
    """Return a bounded exception summary suitable for a future adapter result."""
    reason = str(error).strip()
    return (reason or type(error).__name__)[:300]


def _elapsed_ms(started: float, finished: float) -> float:
    """Convert one monotonic interval into a non-negative millisecond duration."""
    return max(0.0, (finished - started) * 1000)


def _stage(
    name: str,
    outcome: OperationalOutcome,
    started: float,
    monotonic: Callable[[], float],
    error: Exception | None = None,
    origin: float | None = None,
) -> OperationalStage:
    """Build one bounded failure-aware stage measurement without exception details."""
    return OperationalStage(
        name,
        outcome,
        _elapsed_ms(started, monotonic()),
        error_category=type(error).__name__ if error is not None else None,
        start_offset_ms=_elapsed_ms(origin, started) if origin is not None else None,
    )


def _action_operational_outcome(status: ActionStatus) -> OperationalOutcome:
    """Map typed action status into the public operational outcome vocabulary."""
    return {
        ActionStatus.COMPLETED: OperationalOutcome.COMPLETED,
        ActionStatus.DEFERRED: OperationalOutcome.SKIPPED,
        ActionStatus.FAILED: OperationalOutcome.FAILED,
    }[status]


def _with_operational(
    result: ApplicationResult,
    stages: list[OperationalStage],
    started: float,
    monotonic: Callable[[], float],
) -> ApplicationResult:
    """Attach bounded stage and total timing evidence without changing request semantics."""
    return cast(
        ApplicationResult,
        replace(
            result,
            operational=OperationalEvidence(
                total_duration_ms=_elapsed_ms(started, monotonic()), stages=tuple(stages)
            ),
        ),
    )


@dataclass
class _ProviderCallRecorder:
    """Collect bounded evidence for provider calls made during one Core request."""

    monotonic: Callable[[], float]
    origin: float
    calls: tuple[ProviderCallEvidence, ...] = ()

    def invoke(self, name: str, provider: Any, operation: Callable[..., Any], *args: Any) -> Any:
        """Invoke one provider operation and retain only safe boundary metadata."""
        started = self.monotonic()
        try:
            result = operation(*args)
        except Exception as error:
            self.calls += (
                self._evidence(provider, name, OperationalOutcome.FAILED, started, error),
            )
            raise
        self.calls += (self._evidence(provider, name, OperationalOutcome.COMPLETED, started),)
        return result

    def _evidence(
        self,
        provider: Any,
        name: str,
        outcome: OperationalOutcome,
        started: float,
        error: Exception | None = None,
    ) -> ProviderCallEvidence:
        """Build one provider record without retaining request, prompt, or response data."""
        return ProviderCallEvidence(
            name=name,
            outcome=outcome,
            duration_ms=_elapsed_ms(started, self.monotonic()),
            model=getattr(provider, "model", None),
            reasoning_effort=getattr(provider, "reasoning_effort", None),
            usage=normalize_provider_usage(getattr(provider, "last_usage", None)),
            error_category=(
                _bounded_evidence_string(getattr(provider, "last_error_category", None))
                or (type(error).__name__ if error is not None else None)
            ),
            validation_stage=_bounded_evidence_string(
                getattr(provider, "last_validation_stage", None)
            ),
            validation_code=_bounded_evidence_string(
                getattr(provider, "last_validation_code", None)
            ),
            attempt_count=_bounded_non_negative_int(getattr(provider, "last_attempt_count", None)),
            response_id=_bounded_evidence_string(getattr(provider, "last_response_id", None)),
            provider_status=_bounded_evidence_string(
                getattr(provider, "last_provider_status", None)
            ),
            incomplete_reason=_bounded_evidence_string(
                getattr(provider, "last_incomplete_reason", None)
            ),
            output_text_chars=_bounded_non_negative_int(
                getattr(provider, "last_output_text_chars", None)
            ),
            output_text_bytes=_bounded_non_negative_int(
                getattr(provider, "last_output_text_bytes", None)
            ),
            parse_status=_bounded_evidence_string(getattr(provider, "last_parse_status", None)),
            result_kind=_bounded_evidence_string(getattr(provider, "last_result_kind", None)),
            result_counts=_bounded_result_counts(getattr(provider, "last_result_counts", None)),
            start_offset_ms=_elapsed_ms(self.origin, started),
            ordinal=len(self.calls) + 1,
            substeps=getattr(provider, "last_spans", ()),
            input_sizes=getattr(provider, "last_input_sizes", None),
        )


def _planner_attempts(
    planner: Any, recorded: tuple[ProviderCallEvidence, ...]
) -> tuple[ProviderCallEvidence, ...]:
    """Prefer the planner's individual provider attempts over its outer invocation wrapper."""
    attempts = getattr(planner, "last_provider_calls", None)
    if (
        isinstance(attempts, tuple)
        and attempts
        and all(isinstance(call, ProviderCallEvidence) for call in attempts)
    ):
        return attempts
    return recorded


def _bounded_non_negative_int(value: Any) -> int | None:
    """Retain one bounded non-negative operational counter."""
    return value if isinstance(value, int) and 0 <= value <= 1_000_000_000 else None


def _bounded_evidence_string(value: Any) -> str | None:
    """Retain one short metadata value without arbitrary provider prose."""
    if not isinstance(value, str) or not value or len(value) > 128:
        return None
    return value


def _bounded_result_counts(value: Any) -> dict[str, int] | None:
    """Retain only a small mapping of structural planner-result counters."""
    if not isinstance(value, dict) or len(value) > 16:
        return None
    counts: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key or len(key) > 32:
            return None
        bounded = _bounded_non_negative_int(count)
        if bounded is None:
            return None
        counts[key] = bounded
    return counts


class _MeasuredEmbedder:
    """Measure repeated local embedding calls without changing their inputs or results."""

    def __init__(self, embedder: Any, spans: SpanRecorder) -> None:
        self._embedder = embedder
        self._spans = spans
        self._query_count = 0
        self._document_count = 0

    def __getattr__(self, name: str) -> Any:
        """Forward model metadata and other read-only embedder attributes."""
        return getattr(self._embedder, name)

    def embed_queries(self, texts: Any) -> Any:
        """Retain one span per query embedding invocation."""
        ordinal = self._query_count
        self._query_count += 1
        return self._spans.invoke(
            f"embedding.query[{ordinal}]", self._embedder.embed_queries, texts
        )

    def embed_documents(self, texts: Any) -> Any:
        """Retain one span per document embedding invocation."""
        ordinal = self._document_count
        self._document_count += 1
        return self._spans.invoke(
            f"embedding.documents[{ordinal}]", self._embedder.embed_documents, texts
        )


class _MeasuredContextualReasoner:
    """Measure calls through an injected contextual-resolution provider."""

    def __init__(self, provider: Any, recorder: _ProviderCallRecorder) -> None:
        self._provider = provider
        self._recorder = recorder

    def resolve(self, request: Any) -> Any:
        """Resolve one target through the provider and record its bounded evidence."""
        return self._recorder.invoke(
            "contextual_resolution", self._provider, self._provider.resolve, request
        )


class _MeasuredWriter:
    """Measure calls through an injected bounded note writer."""

    def __init__(self, provider: Any, recorder: _ProviderCallRecorder) -> None:
        self._provider = provider
        self._recorder = recorder

    def write(self, request: Any) -> Any:
        """Write one bounded note operation and record its provider evidence."""
        return self._recorder.invoke("writer", self._provider, self._provider.write, request)


class _MeasuredFactSelector:
    """Measure calls through an injected atomic-fact selector."""

    def __init__(self, provider: Any, recorder: _ProviderCallRecorder) -> None:
        self._provider = provider
        self._recorder = recorder

    def select(self, *args: Any, **kwargs: Any) -> Any:
        """Select one bounded fact locator and record its provider evidence."""
        return self._recorder.invoke(
            "fact_selector", self._provider, self._provider.select, *args, **kwargs
        )
