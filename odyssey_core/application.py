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

from .atomic_facts import AtomicFactError, parse_atomic_facts
from .bulk_update import BulkUpdateResult, execute_bulk_update
from .clarification import ClarificationChoice, evidence_digest
from .clarification_presentation import ClarificationPresentation
from .context import ContextPackage, get_context
from .fact_selection import AtomicFactSelector
from .git_history import GitHistoryResult, GitHistorySnapshot, HistoryRecorder, HistoryStatus
from .identity_boundary import AuthenticatedActorContext, SelfBindingError, SelfBindingRepository
from .materialization import (
    BoundedNoteWriter,
    materialize_calendar_day_record,
    materialize_create,
    materialize_delete,
    materialize_type_migration,
    materialize_update,
    rollback_created_reference,
)
from .notes import NoteFormatError, parse_note, validate_note
from .observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalStage,
    ProviderCallEvidence,
    SpanRecorder,
    normalize_provider_usage,
)
from .persistence import ActorInput
from .reference_binding import (
    PendingReference,
    bind_canonical_reference_mentions,
    render_reference_facts,
)
from .reference_preflight import (
    RelationshipWritePreflightError,
    UnitTargetPreflight,
    _find_existing_identity,
    _preflight_write_action,
    allocate_stable_id,
    current_identity_guard,
    is_reference_only_unit,
    preflight_complete_set_reference_action,
    preflight_relational_target_write_action,
    preflight_relationship_write_action,
    preflight_write_action,
    prepare_complete_set_reference_action,
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
from .resolution import ExistingEntityOutcome, resolve_existing_entity
from .semantic_sets import (
    SemanticSetOutcome,
    SemanticSetResolution,
    resolve_semantic_set,
)
from .storage import VaultRepository
from .temporal import CALENDAR_DAY_TYPE
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


class WritePreflightGuardError(ValueError):
    """Reject a resolved write when domain-owned current-state invariants do not authorize it."""

    def __init__(self, code: str) -> None:
        if not isinstance(code, str) or not code:
            raise ValueError("Write preflight guard code must be non-empty")
        super().__init__(code)
        self.code = code


class WritePreflightGuard(Protocol):
    """Validate domain state only after Core has resolved immutable write targets."""

    def __call__(
        self,
        action: WriteAction,
        preflight: tuple[UnitTargetPreflight, ...],
        repository: VaultRepository,
        schema: dict[str, Any],
    ) -> None:
        """Raise WritePreflightGuardError to fail closed before any mutation."""


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
    clarification: ClarificationPresentation | None = None


@dataclass(frozen=True, slots=True)
class CanonicalReferenceEvidence:
    """Keep one private, post-persistence canonical reference handoff candidate.

    This is Core-internal evidence for a later dependent-route handoff.  It is deliberately not
    presentation evidence: the stable IDs and content guards are never serialized by the runtime.
    ``source_content_guard`` proves the exact fact-bearing source Note still has the persisted
    reference; ``canonical_content_guard`` separately protects the referenced Note identity.
    """

    action_index: int
    source_unit_index: int
    source_reference_index: int
    source_mention: str
    stable_note_id: str
    note_type: str
    canonical_name: str
    source_note_id: str
    source_content_guard: str
    canonical_content_guard: str


@dataclass(frozen=True, slots=True)
class DependentReferenceGuard:
    """Authorize one dependent marker only while its predecessor evidence remains current."""

    mention: str
    evidence: CanonicalReferenceEvidence

    def __call__(
        self,
        action: WriteAction,
        preflight: tuple[UnitTargetPreflight, ...],
        repository: VaultRepository,
        schema: dict[str, Any],
    ) -> None:
        """Recheck predecessor guards and require a fact-bearing marker bound to its exact ID."""
        if not _dependent_evidence_is_current(self.evidence, repository, schema):
            raise WritePreflightGuardError("ROUTE_DEPENDENCY_CANONICAL_EVIDENCE_STALE")
        for unit in action.units:
            if unit.reference_lookup_only:
                continue
            for reference_index, reference in enumerate(unit.references):
                if (
                    reference.mention != self.mention
                    or reference.target_index is None
                    or not any(f"{{{{ref:{reference_index}}}}}" in fact for fact in unit.facts)
                ):
                    continue
                target = next(
                    (item for item in preflight if item.unit_index == reference.target_index), None
                )
                if (
                    target is not None
                    and target.stable_id == self.evidence.stable_note_id
                    and target.canonical_name == self.evidence.canonical_name
                ):
                    return
        raise WritePreflightGuardError("ROUTE_DEPENDENCY_REFERENCE_MARKER_REQUIRED")


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
    candidate_note_ids: tuple[str, ...] = ()
    relational_evidence_guard: str | None = None
    clarification: ClarificationPresentation | None = None
    # Internal-only; runtime serializers intentionally do not project this field.
    canonical_reference_evidence: tuple[CanonicalReferenceEvidence, ...] = ()
    # Read-only evidence for a set mention expanded into multiple proven member links.
    observed_set_members: tuple[tuple[str, str], ...] = ()


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
    # Presentation-only bounded execution provenance, never Core mutation authority.
    execution_flow: Mapping[str, Any] | None = None
    # Core-private dependent-route input. Never add this to public delivery/presentation payloads.
    canonical_reference_evidence: tuple[CanonicalReferenceEvidence, ...] = ()


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
    clarification_choice: ClarificationChoice | None = None,
    write_preflight_guard: WritePreflightGuard | None = None,
    progress_callback: Callable[[str, Mapping[str, object]], None] | None = None,
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

    def notify_progress(stage: str, payload: Mapping[str, object] | None = None) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(stage, payload or {})
        except Exception:
            # UX progress is observational and must never change Core semantics.
            return

    notify_progress("planner.started")
    planner_started = monotonic()
    provider_recorder = _ProviderCallRecorder(monotonic, planner_started)
    try:
        if getattr(planner, "is_local_replay", False):
            plan = planner.plan(user_request)
        else:
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
    references: list[str] = []
    for planned_action in plan.actions:
        for unit in getattr(planned_action, "units", ()):
            for reference in getattr(unit, "references", ()):
                mention = getattr(reference, "mention", None)
                if isinstance(mention, str) and mention.strip() and mention not in references:
                    references.append(mention.strip())
    notify_progress(
        "planner.ready",
        {"references": tuple(references[:6]), "action_count": len(plan.actions)},
    )
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
        notify_progress(f"action.{action.kind}.started", {"ordinal": action_index + 1})
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
        measured_semantic_set_selector = (
            _MeasuredSemanticSetSelector(semantic_set_selector, provider_recorder)
            if callable(getattr(semantic_set_selector, "select", None))
            else semantic_set_selector
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
                semantic_set_selector=measured_semantic_set_selector,
                clarification_choice=clarification_choice,
                allow_multiple_notes=plan.presentation_intent != "answer",
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
                measured_semantic_set_selector,
                authenticated_actor,
                self_binding_repository,
                action_spans,
                clarification_choice,
                write_preflight_guard,
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
    try:
        semantic_flow = _project_execution_flow(plan, actions, repository, schema)
    except Exception:
        # Diagnostics are strictly optional and must never block canonical
        # writes, partial completion, Git history or pending-work durability.
        semantic_flow = None
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
        execution_flow=semantic_flow,
        note_set_selection=(
            plan.actions[0].plan
            if plan.presentation_intent != "answer" and isinstance(plan.actions[0], RetrieveAction)
            else None
        ),
        canonical_reference_evidence=_unique_canonical_reference_evidence(actions),
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


def _unique_canonical_reference_evidence(
    actions: list[ActionResult],
) -> tuple[CanonicalReferenceEvidence, ...]:
    """Reject all duplicate canonical targets across a request rather than choosing one occurrence."""
    candidates = tuple(item for action in actions for item in action.canonical_reference_evidence)
    counts: dict[str, int] = {}
    for item in candidates:
        counts[item.stable_note_id] = counts.get(item.stable_note_id, 0) + 1
    return tuple(item for item in candidates if counts[item.stable_note_id] == 1)


def _project_execution_flow(
    plan: RequestPlan,
    results: Sequence[ActionResult],
    repository: VaultRepository,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Describe validated intentions and actually resolved canonical links for DEV inspection.

    This is a read-only observational projection. It cannot affect write authority,
    and a failed name lookup never changes the mutation or fabricates an identity.
    """
    planned: list[dict[str, str]] = []
    writes: list[dict[str, str]] = []
    entities_by_key: dict[tuple[str, str], dict[str, str]] = {}
    link_ids: set[str] = set()
    candidates: list[tuple[str, str, str | None]] = []
    for action, outcome in zip(plan.actions[:8], results[:8], strict=False):
        if isinstance(action, WriteAction):
            unit_results = {unit.unit_index: unit for unit in outcome.unit_results}
            set_members: dict[str, list[str]] = {}
            for mention, stable_id in outcome.observed_set_members:
                set_members.setdefault(mention, []).append(stable_id)
            for mention, member_ids in set_members.items():
                if len(member_ids) != len(set(member_ids)):
                    continue
                for stable_id in member_ids:
                    link_ids.add(stable_id)
                    candidates.append((mention[:120], "person", stable_id))
            for unit_index, unit in enumerate(action.units[:8]):
                selection = unit.target
                target = selection.entity or selection.query
                if unit.reference_lookup_only:
                    continue
                planned.append(
                    {
                        "operation": unit.intent[:32],
                        "type": (selection.type or "nota")[:40],
                        "target": target[:160],
                        "fact": (unit.facts[0] if unit.facts else "")[:240],
                    }
                )
                observed = unit_results.get(unit_index)
                if observed is not None:
                    writes.append(
                        {
                            "status": observed.status.value,
                            "operation": (observed.operation or unit.intent)[:48],
                            "target": target[:160],
                        }
                    )
                if (
                    observed is not None
                    and observed.status is UnitStatus.SUCCEEDED
                    and observed.stable_note_id
                    and selection.type not in {None, "calendar_day"}
                    and target.strip()
                ):
                    link_ids.add(observed.stable_note_id)
                    candidates.append(
                        (target.strip()[:120], (selection.type or "")[:40], observed.stable_note_id)
                    )
                for reference in unit.references[:8]:
                    mention = reference.mention.strip()[:120]
                    if not mention:
                        continue
                    target_index = reference.target_index
                    linked = unit_results.get(target_index) if target_index is not None else None
                    stable_id = (
                        linked.stable_note_id
                        if linked and linked.status is UnitStatus.SUCCEEDED
                        else None
                    )
                    if stable_id:
                        link_ids.add(stable_id)
                    reference_type = (
                        action.units[target_index].target.type
                        if target_index is not None and 0 <= target_index < len(action.units)
                        else (reference.selection.type if reference.selection else None)
                    )
                    if mention not in set_members:
                        candidates.append((mention, (reference_type or "")[:40], stable_id))
        elif isinstance(action, RetrieveAction):
            planned.append(
                {
                    "operation": "retrieve",
                    "type": (action.plan.type or "nota")[:40],
                    "target": action.plan.query[:160],
                    "fact": "",
                }
            )
        elif isinstance(action, DelegateAction):
            planned.append(
                {"operation": "delegate", "type": "", "target": action.request[:160], "fact": ""}
            )
    names: dict[str, str] = {}
    if link_ids:
        # Scan once for at most eight Core-confirmed stable IDs; do not use stale
        # search indexes or derive a name from an ID, filename or model output.
        from .notes import NoteFormatError, NoteValidationError, parse_note, validate_note
        from .storage import NoteUnavailableError, VaultAccessError

        try:
            for path in repository.list_markdown_paths():
                try:
                    note = parse_note(repository.read_text(path))
                    validate_note(note, schema)
                except (NoteFormatError, NoteValidationError, NoteUnavailableError):
                    continue
                stable_id = note.metadata.get("id")
                if stable_id not in link_ids:
                    continue
                name = note.metadata.get("name")
                if isinstance(name, str) and 0 < len(name) <= 160:
                    if stable_id in names:
                        # Duplicate IDs do not authorize a canonical display name.
                        names[stable_id] = ""
                    else:
                        names[stable_id] = name
        except (VaultAccessError, OSError):
            pass
    for mention, kind, stable_id in candidates[:8]:
        key = (mention, stable_id or "")
        if key in entities_by_key:
            continue
        mapped = names.get(stable_id, "") if stable_id else ""
        entities_by_key[key] = {
            "mention": mention,
            "name": mapped,
            "status": "resolved" if mapped else "unresolved",
            "type": kind,
        }
    return {
        "plan": planned[:8],
        "entities": list(entities_by_key.values())[:8],
        "writes": writes[:8],
    }


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
    clarification_choice: ClarificationChoice | None = None,
    allow_multiple_notes: bool = False,
) -> ActionResult:
    """Execute retrieval, restricting relational intent to its exact current member identities."""
    if action.plan.link_scope is not None:
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.DEFERRED,
            reason="UNSUPPORTED_RETRIEVAL_LINK_SCOPE",
        )
    if action.result_shape == "collection" or action.plan.semantic_set is not None:
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
                query=action.plan.query,
                repository=repository,
                schema=schema,
                selector=semantic_set_selector,
                collection_subject=action.plan.collection_subject,
                authenticated_actor=authenticated_actor,
                self_binding_repository=self_binding_repository,
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
    if action.plan.entity is not None and not allow_multiple_notes:
        try:
            resolution = spans.invoke(
                "singular_identity_resolution",
                resolve_existing_entity,
                action.plan.entity,
                action.plan.query,
                type=action.plan.type,
                repository=repository,
                schema=schema,
                semantic_index=semantic_index,
                embedder=embedder,
                contextual_reasoner=contextual_reasoner,
                semantic_limit=semantic_limit,
            )
        except Exception as error:
            return ActionResult(
                action_index, action.kind, ActionStatus.FAILED, reason=_safe_reason(error)
            )
        if resolution.offers_clarification:
            if clarification_choice is None:
                return ActionResult(
                    action_index,
                    action.kind,
                    ActionStatus.DEFERRED,
                    reason="ambiguous_existing_target",
                    candidate_note_ids=resolution.candidate_ids,
                    clarification=resolution.clarification,
                )
            still_offered = clarification_choice.stable_id in resolution.candidate_ids
        elif resolution.outcome is ExistingEntityOutcome.RESOLVED:
            still_offered = (
                resolution.id == clarification_choice.stable_id if clarification_choice else True
            )
        else:
            return ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                reason="unresolved_existing_target",
            )
        if not still_offered:
            return ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                reason="clarification_scope_changed",
            )
        allowed_note_ids = frozenset(
            {clarification_choice.stable_id if clarification_choice else resolution.id}
        )
    if clarification_choice is not None and action.plan.relational_reference is None:
        if (
            action.result_shape != "single"
            or action.plan.entity is None
            or action.plan.relational_reference is not None
            or action.plan.self_target is not None
            or action.plan.link_scope is not None
        ):
            return ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                reason="clarification_scope_changed",
            )
        try:
            if (
                current_identity_guard(repository, schema, clarification_choice.stable_id)
                != clarification_choice.evidence_guard
            ):
                raise ValueError("clarification evidence changed")
        except Exception:
            return ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                reason="clarification_evidence_changed",
            )
        allowed_note_ids = frozenset({clarification_choice.stable_id})
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
                semantic_set_selector=semantic_set_selector,
                allow_identity_clarification=True,
                chosen_identity_id=(
                    clarification_choice.stable_id if clarification_choice is not None else None
                ),
                expected_evidence_guard=(
                    clarification_choice.source_evidence_guard
                    if clarification_choice is not None
                    else None
                ),
            )
        except RelationalResolutionError as error:
            return ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                reason=str(error),
                candidate_note_ids=error.candidate_ids,
                relational_evidence_guard=error.evidence_guard,
                clarification=error.clarification,
            )
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
        if clarification_choice is not None:
            if clarification_choice.stable_id not in allowed_note_ids:
                return ActionResult(
                    action_index,
                    action.kind,
                    ActionStatus.DEFERRED,
                    reason="clarification_scope_changed",
                )
            try:
                if (
                    clarification_choice.source_evidence_guard is not None
                    and resolved.evidence_guard != clarification_choice.source_evidence_guard
                ):
                    raise ValueError("relational source evidence changed")
                if (
                    current_identity_guard(repository, schema, clarification_choice.stable_id)
                    != clarification_choice.evidence_guard
                ):
                    raise ValueError("clarification evidence changed")
            except Exception:
                return ActionResult(
                    action_index,
                    action.kind,
                    ActionStatus.DEFERRED,
                    reason="clarification_evidence_changed",
                )
            allowed_note_ids = frozenset({clarification_choice.stable_id})
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


def _single_relational_reference_helper_index(action: WriteAction) -> int | None:
    """Allow one fact-bearing consumer and its sole, factless relational identity helper.

    This is a general dependency shape, not a special case for a family relationship
    or a Calendar Day. Independent writes cannot be replayed by a scalar choice.
    """
    if len(action.units) != 2:
        return None
    helpers = [
        index
        for index, unit in enumerate(action.units)
        if is_reference_only_unit(unit)
        and unit.target.relational_reference is not None
        and unit.target.relational_reference.members == "one"
    ]
    if len(helpers) != 1:
        return None
    helper = helpers[0]
    consumer = action.units[1 - helper]
    if (
        not consumer.facts
        or consumer.target.relational_reference is not None
        or not consumer.references
        or any(reference.target_index != helper for reference in consumer.references)
    ):
        return None
    return helper


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
    semantic_set_selector: Any | None,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    spans: SpanRecorder,
    clarification_choice: ClarificationChoice | None = None,
    write_preflight_guard: WritePreflightGuard | None = None,
) -> ActionResult:
    """Execute one write action without reopening target decisions or reference binding."""
    complete_set_references = tuple(
        (unit_index, reference_index, reference)
        for unit_index, unit in enumerate(action.units)
        for reference_index, reference in enumerate(unit.references)
        if reference.selection is not None
        and reference.selection.relational_reference is not None
        and reference.selection.relational_reference.members == "complete_set"
    )
    has_relational_target = any(
        unit.target.relational_reference is not None and not unit.reference_lookup_only
        for unit in action.units
    )
    if complete_set_references and has_relational_target:
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.DEFERRED,
            reason="UNSUPPORTED_MIXED_RELATIONAL_WRITE_SHAPE",
        )
    if has_relational_target:
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
            semantic_set_selector,
            authenticated_actor,
            self_binding_repository,
            spans,
            clarification_choice,
        )
    relational_helper = _single_relational_reference_helper_index(action)
    chosen_helper_id: str | None = None
    if clarification_choice is not None and relational_helper is not None:
        # Re-ground only the selected, previously offered dependency. No provider
        # may reinterpret the user's choice or silently change the evidence set.
        try:
            resolved_helper = spans.invoke(
                "relational_resolution",
                resolve_relational_reference,
                action.units[relational_helper].target,
                repository=repository,
                schema=schema,
                semantic_index=semantic_index,
                embedder=embedder,
                contextual_reasoner=contextual_reasoner,
                semantic_limit=semantic_limit,
                authenticated_actor=authenticated_actor,
                self_binding_repository=self_binding_repository,
                semantic_set_selector=semantic_set_selector,
                chosen_identity_id=clarification_choice.stable_id,
                expected_evidence_guard=clarification_choice.source_evidence_guard,
            )
            if not _relational_clarification_still_valid(
                resolved_helper, clarification_choice, repository, schema
            ):
                return ActionResult(
                    action_index,
                    action.kind,
                    ActionStatus.DEFERRED,
                    reason="clarification_evidence_changed",
                )
            chosen_helper_id = clarification_choice.stable_id
        except RelationalResolutionError as error:
            return ActionResult(action_index, action.kind, ActionStatus.DEFERRED, reason=str(error))

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
        if clarification_choice is not None and chosen_helper_id is None:
            kwargs["clarification_choice"] = clarification_choice
        executable = action
        set_bindings = ()
        executable_ordinals = unit_ordinals
        if complete_set_references:
            resolved_references = {}
            for unit_index, reference_index, reference in complete_set_references:
                if reference.selection is None:
                    raise RelationshipWritePreflightError(
                        "Complete-set fact reference has no semantic selection"
                    )
                try:
                    resolved_references[(unit_index, reference_index)] = spans.invoke(
                        "relational_resolution",
                        resolve_relational_reference,
                        reference.selection,
                        repository=repository,
                        schema=schema,
                        semantic_index=semantic_index,
                        embedder=embedder,
                        contextual_reasoner=contextual_reasoner,
                        semantic_limit=semantic_limit,
                        authenticated_actor=authenticated_actor,
                        self_binding_repository=self_binding_repository,
                        semantic_set_selector=semantic_set_selector,
                    )
                except RelationalResolutionError as error:
                    if not error.evidence_absent:
                        raise
                    resolved_references[(unit_index, reference_index)] = None
            original_count = len(action.units)
            executable, set_bindings = prepare_complete_set_reference_action(
                action, resolved_references
            )
            executable_ordinals = (
                *unit_ordinals,
                *(((),) * (len(executable.units) - original_count)),
            )
            if set_bindings:
                preflight = spans.invoke(
                    "preflight",
                    preflight_complete_set_reference_action,
                    executable,
                    set_bindings,
                    relationship_projector=RelationshipEvidenceProjector(repository, schema),
                    repository=repository,
                    schema=schema,
                    semantic_index=semantic_index,
                    embedder=embedder,
                    contextual_reasoner=contextual_reasoner,
                    semantic_limit=semantic_limit,
                    authenticated_actor=authenticated_actor,
                    self_binding_repository=self_binding_repository,
                    span_recorder=spans,
                    semantic_set_selector=semantic_set_selector,
                    **kwargs,
                )
            else:
                preflight = spans.invoke(
                    "preflight",
                    preflight_write_action,
                    executable,
                    repository=repository,
                    schema=schema,
                    semantic_index=semantic_index,
                    embedder=embedder,
                    contextual_reasoner=contextual_reasoner,
                    semantic_limit=semantic_limit,
                    authenticated_actor=authenticated_actor,
                    self_binding_repository=self_binding_repository,
                    span_recorder=spans,
                    semantic_set_selector=semantic_set_selector,
                    **kwargs,
                )
        else:
            if chosen_helper_id is not None and relational_helper is not None:
                # Private preflight override only after both canonical relation
                # and chosen identity guards were checked above.
                kwargs["id_allocator"] = id_allocator or allocate_stable_id
                kwargs["_validated_reference_targets"] = {relational_helper: chosen_helper_id}
            preflight = spans.invoke(
                "preflight",
                _preflight_write_action if chosen_helper_id is not None else preflight_write_action,
                executable,
                repository=repository,
                schema=schema,
                semantic_index=semantic_index,
                embedder=embedder,
                contextual_reasoner=contextual_reasoner,
                semantic_limit=semantic_limit,
                authenticated_actor=authenticated_actor,
                self_binding_repository=self_binding_repository,
                span_recorder=spans,
                semantic_set_selector=semantic_set_selector,
                **kwargs,
            )
        if write_preflight_guard is not None:
            spans.invoke(
                "domain_preflight_guard",
                write_preflight_guard,
                executable,
                preflight,
                repository,
                schema,
            )
        evidence_action = executable
        executable = bind_canonical_reference_mentions(executable, preflight)
        rendering = spans.invoke("reference_render", render_reference_facts, executable, preflight)
    except WritePreflightGuardError as error:
        return ActionResult(action_index, action.kind, ActionStatus.DEFERRED, reason=error.code)
    except RelationalResolutionError as error:
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.DEFERRED,
            reason=str(error),
            candidate_note_ids=error.candidate_ids,
            relational_evidence_guard=error.evidence_guard,
            clarification=error.clarification,
        )
    except RelationshipWritePreflightError as error:
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
        executable_ordinals,
        fact_selector,
        spans,
    )
    reference_evidence = _collect_persisted_reference_evidence(
        action_index,
        evidence_action,
        preflight,
        rendering.rendered_facts,
        results,
        executable_ordinals,
        request_id,
        repository,
        schema,
    )
    if (
        relational_helper is not None
        and clarification_choice is None
        and all(result.status is UnitStatus.DEFERRED for result in results)
        and results[relational_helper].reason
        in {"relational_evidence_ambiguous", "relational_singular_ambiguous"}
    ):
        # A factless reference helper can be the only ambiguous dependency.
        # Promote its verified options to the action's existing clarification
        # contract without flattening or moving the consumer's original facts.
        try:
            spans.invoke(
                "relational_resolution",
                resolve_relational_reference,
                action.units[relational_helper].target,
                repository=repository,
                schema=schema,
                semantic_index=semantic_index,
                embedder=embedder,
                contextual_reasoner=contextual_reasoner,
                semantic_limit=semantic_limit,
                authenticated_actor=authenticated_actor,
                self_binding_repository=self_binding_repository,
                semantic_set_selector=semantic_set_selector,
                allow_identity_clarification=True,
            )
        except RelationalResolutionError as error:
            if (
                str(error) in {"relational_evidence_ambiguous", "relational_singular_ambiguous"}
                and 1 < len(error.candidate_ids) <= 4
                and error.clarification is not None
            ):
                return ActionResult(
                    action_index,
                    action.kind,
                    ActionStatus.DEFERRED,
                    unit_results=tuple(results),
                    reason=str(error),
                    candidate_note_ids=error.candidate_ids,
                    relational_evidence_guard=error.evidence_guard,
                    clarification=error.clarification,
                )
    return ActionResult(
        action_index,
        action.kind,
        _action_status(results),
        unit_results=tuple(results),
        canonical_reference_evidence=reference_evidence,
        observed_set_members=tuple(
            (
                action.units[binding.source_unit_index]
                .references[binding.source_reference_index]
                .mention,
                member.stable_id,
            )
            for binding in set_bindings
            if results[binding.source_unit_index].status is UnitStatus.SUCCEEDED
            and all(
                results[item.unit_index].status is UnitStatus.SUCCEEDED
                and results[item.unit_index].stable_note_id == item.stable_id
                for item in binding.members
            )
            for member in binding.members
        ),
    )


def _relational_clarification_still_valid(
    resolved: Any,
    choice: ClarificationChoice,
    repository: VaultRepository,
    schema: dict[str, Any],
) -> bool:
    """Revalidate the chosen identity and relationship guard before mutation."""
    return (
        len(resolved.targets) == 1
        and resolved.targets[0].id == choice.stable_id
        and resolved.evidence_guard == choice.source_evidence_guard
        and current_identity_guard(repository, schema, choice.stable_id) == choice.evidence_guard
    )


def _prepare_relational_write_preflight(
    action: WriteAction,
    unit: KnowledgeUnit,
    resolved: Any,
    relational_index: int,
    unit_ordinals: tuple[tuple[int, ...], ...],
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    semantic_limit: int,
    id_allocator: Callable[[], str] | None,
    semantic_set_selector: Any | None,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    spans: SpanRecorder,
) -> tuple[WriteAction, tuple[UnitTargetPreflight, ...], tuple[tuple[int, ...], ...]]:
    """Prepare either shared-fact or singular-target relational preflight outside execution flow."""
    relation = unit.target.relational_reference
    if relation is None:
        raise RelationshipWritePreflightError("Relationship target is unavailable")
    projector = RelationshipEvidenceProjector(repository, schema)
    kwargs: dict[str, Any] = {}
    if id_allocator is not None:
        kwargs["id_allocator"] = id_allocator
    common = {
        "relationship_projector": projector,
        "repository": repository,
        "schema": schema,
        "semantic_index": semantic_index,
        "embedder": embedder,
        "contextual_reasoner": contextual_reasoner,
        "semantic_limit": semantic_limit,
        "authenticated_actor": authenticated_actor,
        "self_binding_repository": self_binding_repository,
        "span_recorder": spans,
        "semantic_set_selector": semantic_set_selector,
        **kwargs,
    }
    if relation.members == "complete_set":
        if len(action.units) != 1:
            raise RelationshipWritePreflightError("Shared relationship fact must be one unit")
        executable, binding = prepare_relationship_shared_fact_action(unit, resolved)
        preflight = spans.invoke(
            "preflight", preflight_relationship_write_action, executable, binding, **common
        )
        ordinals = (unit_ordinals[0], *(((),) * len(resolved.targets)))
        return executable, preflight, ordinals
    preflight = spans.invoke(
        "preflight",
        preflight_relational_target_write_action,
        action,
        resolved,
        target_unit_index=relational_index,
        **common,
    )
    return action, preflight, unit_ordinals


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
    semantic_set_selector: Any | None,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    spans: SpanRecorder,
    clarification_choice: ClarificationChoice | None = None,
) -> ActionResult:
    """Route one relational write through current evidence and relationship-only preflight."""
    relational_indexes = tuple(
        index
        for index, candidate in enumerate(action.units)
        if candidate.target.relational_reference is not None and not candidate.reference_lookup_only
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
            semantic_set_selector=semantic_set_selector,
            fallback_identity_clarification=relation.members == "one",
            refine_singular_with_query=True,
            chosen_identity_id=(
                clarification_choice.stable_id if clarification_choice is not None else None
            ),
            expected_evidence_guard=(
                clarification_choice.source_evidence_guard
                if clarification_choice is not None
                else None
            ),
        )
        if clarification_choice is not None and not _relational_clarification_still_valid(
            resolved, clarification_choice, repository, schema
        ):
            return ActionResult(
                action_index,
                action.kind,
                ActionStatus.DEFERRED,
                reason="clarification_evidence_changed",
            )
        executable, preflight, ordinals = _prepare_relational_write_preflight(
            action,
            unit,
            resolved,
            relational_index,
            unit_ordinals,
            repository=repository,
            schema=schema,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            semantic_limit=semantic_limit,
            id_allocator=id_allocator,
            semantic_set_selector=semantic_set_selector,
            authenticated_actor=authenticated_actor,
            self_binding_repository=self_binding_repository,
            spans=spans,
        )
        evidence_action = executable
        executable = bind_canonical_reference_mentions(executable, preflight)
        rendering = spans.invoke("reference_render", render_reference_facts, executable, preflight)
        if rendering.pending_references:
            raise RelationshipWritePreflightError("Relationship member binding is incomplete")
    except RelationalResolutionError as error:
        if error.evidence_absent and relation.members == "one" and clarification_choice is None:
            fallback_unit = replace(
                unit,
                target=replace(unit.target, relational_reference=None),
            )
            fallback_action = replace(
                action,
                units=tuple(
                    fallback_unit if index == relational_index else candidate
                    for index, candidate in enumerate(action.units)
                ),
            )
            return _execute_write(
                action_index,
                fallback_action,
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
                semantic_set_selector,
                authenticated_actor,
                self_binding_repository,
                spans,
            )
        return ActionResult(
            action_index,
            action.kind,
            ActionStatus.DEFERRED,
            reason=str(error),
            candidate_note_ids=error.candidate_ids,
            relational_evidence_guard=error.evidence_guard,
            clarification=error.clarification,
        )
    except RelationshipWritePreflightError as error:
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
        # Complete-set expansion creates Core-private reference-only member helpers.  Their
        # generated references cannot become a cross-route antecedent.
        reference_evidence: tuple[CanonicalReferenceEvidence, ...] = ()
    else:
        reference_evidence = _collect_persisted_reference_evidence(
            action_index,
            evidence_action,
            preflight,
            rendering.rendered_facts,
            results,
            ordinals,
            request_id,
            repository,
            schema,
        )
    return ActionResult(
        action_index,
        action.kind,
        _action_status(results),
        unit_results=tuple(results),
        canonical_reference_evidence=reference_evidence,
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


def _collect_persisted_reference_evidence(
    action_index: int,
    action: WriteAction,
    preflight: tuple[UnitTargetPreflight, ...],
    rendered_facts: tuple[tuple[str, ...], ...],
    results: list[UnitResult],
    unit_ordinals: tuple[tuple[int, ...], ...],
    request_id: str,
    repository: VaultRepository,
    schema: dict[str, Any],
) -> tuple[CanonicalReferenceEvidence, ...]:
    """Return only uniquely grounded references proven in a newly persisted source fact.

    The result is intentionally empty on any malformed, stale, duplicate, alias, helper, or
    partial mapping.  It is a fail-closed bridge between the write executor and a future
    dependent-route handoff, not a second identity resolver or a presentation projection.
    """
    if (
        len(preflight) != len(action.units)
        or len(rendered_facts) != len(action.units)
        or len(results) != len(action.units)
        or len(unit_ordinals) != len(action.units)
        or len({result.unit_index for result in results}) != len(results)
        or any(result.unit_index != index for index, result in enumerate(results))
    ):
        return ()
    evidence: list[CanonicalReferenceEvidence] = []
    for source_index, (unit, source_result, source_facts, ordinals) in enumerate(
        zip(action.units, results, rendered_facts, unit_ordinals, strict=True)
    ):
        if (
            source_result.status is not UnitStatus.SUCCEEDED
            or not source_result.materially_affected
            or not source_result.stable_note_id
            or unit.reference_lookup_only
            or len(source_facts) != len(unit.facts)
            or len(ordinals) != len(source_facts)
        ):
            continue
        source = _persisted_source_note(
            repository, schema, source_result.stable_note_id, source_facts, request_id, ordinals
        )
        if source is None:
            continue
        source_note_id, source_guard = source
        for reference_index, reference in enumerate(unit.references):
            target_index = reference.target_index
            if target_index is None or not 0 <= target_index < len(preflight):
                continue
            target = preflight[target_index]
            if (
                target.outcome not in {WriteTargetOutcome.UPDATE, WriteTargetOutcome.CREATE}
                or target.stable_id is None
                or not target.canonical_name
                # Alias-derived links are not a stable antecedent contract in this slice.
                or reference.mention != target.canonical_name
                or not _reference_is_materially_rendered(
                    unit.facts, source_facts, reference_index, target.canonical_name
                )
            ):
                continue
            canonical = _current_canonical_reference(repository, schema, target.stable_id)
            if canonical is None:
                continue
            note_type, canonical_name, canonical_guard = canonical
            if canonical_name != target.canonical_name:
                continue
            evidence.append(
                CanonicalReferenceEvidence(
                    action_index=action_index,
                    source_unit_index=source_index,
                    source_reference_index=reference_index,
                    source_mention=reference.mention,
                    stable_note_id=target.stable_id,
                    note_type=note_type,
                    canonical_name=canonical_name,
                    source_note_id=source_note_id,
                    source_content_guard=source_guard,
                    canonical_content_guard=canonical_guard,
                )
            )
    counts: dict[str, int] = {}
    for item in evidence:
        counts[item.stable_note_id] = counts.get(item.stable_note_id, 0) + 1
    return tuple(item for item in evidence if counts[item.stable_note_id] == 1)


def _persisted_source_note(
    repository: VaultRepository,
    schema: dict[str, Any],
    stable_note_id: str,
    rendered_facts: tuple[str, ...],
    request_id: str,
    ordinals: tuple[int, ...],
) -> tuple[str, str] | None:
    """Verify the source Note still contains every request-addressed rendered fact."""
    try:
        path, _name = _find_existing_identity(repository, schema, stable_note_id)
        markdown = repository.read_text(path)
        note = parse_note(markdown)
        validate_note(note, schema)
        persisted = parse_atomic_facts(note.content)
    except (AtomicFactError, NoteFormatError, OSError, ValueError, RuntimeError, AttributeError):
        return None
    expected = set(zip(rendered_facts, ordinals, strict=True))
    actual = {(fact.text, fact.ordinal) for fact in persisted if fact.request_id == request_id}
    if not expected.issubset(actual):
        return None
    return stable_note_id, evidence_digest(markdown)


def _reference_is_materially_rendered(
    source_facts: tuple[str, ...],
    rendered_facts: tuple[str, ...],
    reference_index: int,
    canonical_name: str,
) -> bool:
    """Require the exact reference marker to have produced a durable wikilink in a source fact."""
    marker = f"{{{{ref:{reference_index}}}}}"
    expected_display = f"|{canonical_name}]]"
    return any(
        marker in source and marker not in rendered and expected_display in rendered
        for source, rendered in zip(source_facts, rendered_facts, strict=True)
    )


def _current_canonical_reference(
    repository: VaultRepository, schema: dict[str, Any], stable_note_id: str
) -> tuple[str, str, str] | None:
    """Load one unique active canonical identity and its current full-content guard."""
    try:
        path, canonical_name = _find_existing_identity(repository, schema, stable_note_id)
        markdown = repository.read_text(path)
        note = parse_note(markdown)
        validate_note(note, schema)
        note_type = note.metadata.get("type")
        if (
            note.metadata.get("id") != stable_note_id
            or note.metadata.get("deleted") is True
            or not isinstance(note_type, str)
            or not note_type
        ):
            return None
    except (NoteFormatError, OSError, ValueError, RuntimeError, AttributeError):
        return None
    return note_type, canonical_name, evidence_digest(markdown)


def _dependent_evidence_is_current(
    evidence: CanonicalReferenceEvidence, repository: VaultRepository, schema: dict[str, Any]
) -> bool:
    """Verify the original source and canonical target guards before a dependent mutation."""
    try:
        source_guard = current_identity_guard(repository, schema, evidence.source_note_id)
    except Exception:
        return False
    if source_guard != evidence.source_content_guard:
        return False
    current = _current_canonical_reference(repository, schema, evidence.stable_note_id)
    return current == (
        evidence.note_type,
        evidence.canonical_name,
        evidence.canonical_content_guard,
    )


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
                clarification=target.clarification,
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
            if unit.target.type == CALENDAR_DAY_TYPE:
                persisted = spans.invoke(
                    f"unit[{index}].materialize",
                    materialize_calendar_day_record,
                    unit,
                    target,
                    repository=repository,
                    schema=schema,
                    actor=actor,
                    now=now,
                    rendered_facts=rendered_facts[index],
                    request_id=request_id,
                    fact_ordinals=unit_ordinals[index],
                )
            elif target.outcome is WriteTargetOutcome.CREATE:
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
    _rollback_orphan_reference_creates(action, preflight, results, repository, schema)
    return [results[index] for index in range(len(action.units))]


def _rollback_orphan_reference_creates(
    action: WriteAction,
    preflight: tuple[UnitTargetPreflight, ...],
    results: dict[int, UnitResult],
    repository: VaultRepository,
    schema: dict[str, Any],
) -> None:
    """Rollback new reference helpers unless at least one consuming source fact succeeded."""
    consumers: dict[int, set[int]] = {index: set() for index, _ in enumerate(action.units)}
    for source_index, unit in enumerate(action.units):
        for reference in unit.references:
            consumers[reference.target_index].add(source_index)

    for target_index, unit in enumerate(action.units):
        target = preflight[target_index]
        result = results.get(target_index)
        if (
            not unit.reference_lookup_only
            or target.outcome is not WriteTargetOutcome.CREATE
            or result is None
            or result.status is not UnitStatus.SUCCEEDED
            or result.operation != "CREATED"
        ):
            continue
        if any(
            (source_result := results.get(source_index)) is not None
            and source_result.status is UnitStatus.SUCCEEDED
            and source_result.materially_affected
            for source_index in consumers[target_index]
        ):
            continue
        try:
            rollback_created_reference(target, repository=repository, schema=schema)
        except Exception as error:
            results[target_index] = UnitResult(
                target_index,
                UnitStatus.FAILED,
                operation="CREATE",
                stable_note_id=target.stable_id,
                reason=f"REFERENCE_CREATE_ROLLBACK_FAILED: {_safe_reason(error)}",
            )
        else:
            results[target_index] = UnitResult(
                target_index,
                UnitStatus.DEFERRED,
                reason="DEPENDENT_FACT_NOT_WRITTEN",
                materially_affected=False,
            )


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
            target = preflight[reference.target_index]
            if target.outcome is WriteTargetOutcome.CREATE or (
                target.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION and target.reference_only
            ):
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


class _MeasuredSemanticSetSelector:
    """Record one bounded collection-selection call without exposing its candidate text."""

    def __init__(self, provider: Any, recorder: _ProviderCallRecorder) -> None:
        self._provider = provider
        self._recorder = recorder

    def select(self, request: Any) -> Any:
        """Select supplied fact occurrences and retain usage-only operational evidence."""
        return self._recorder.invoke(
            "semantic_set_selector", self._provider, self._provider.select, request
        )
