"""Explicit production dependency composition for the Odyssey runtime bridge."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from threading import Condition, RLock, Thread
from time import perf_counter, thread_time
from typing import Any, cast
from zoneinfo import ZoneInfo

from odyssey_apps import (
    ApplicationCatalog,
    ApplicationDescriptor,
    ApplicationRegistry,
    OpenAIApplicationRouter,
)
from odyssey_apps.calendar import CalendarApplication, CalendarQueryService
from odyssey_apps.events import EVENT_SCHEMA_EXTENSION
from odyssey_apps.events.execution import bound_occurrence, execute_event_candidate
from odyssey_apps.events.interpretation import EventInterpretationError, EventOperation
from odyssey_apps.events.mutations import EventMutationService
from odyssey_apps.events.provider import EventCandidate, OpenAIEventInterpreter
from odyssey_apps.events.queries import event_note_snapshot, explicit_event_query_hint
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TASK_TYPE,
    CanonicalSessionEvidence,
    CanonicalSessionEvidenceError,
    OpenAITaskInterpreter,
    TaskCorePlanner,
    TaskDependentTarget,
    TaskDependentTargetError,
    TaskDirectMutationError,
    TaskDirectMutationService,
    TaskInterpretation,
    TaskInterpretationError,
    TaskLifecycleGuard,
    TaskOperation,
    TaskPersonReference,
    TaskPersonReferenceSet,
    TaskQueryError,
    TaskQueryService,
    TaskScopedEvidence,
    TaskScopedExecution,
    TaskScopedInterpretation,
    TaskWorkSessionService,
    WorkSessionError,
    WorkSessionMutationResult,
    WorkSessionSnapshot,
    compose_scoped_task_domain_interpretation,
    compose_task_domain_interpretation,
    compose_work_session_activity_date,
    compose_work_session_times,
    prepare_dependent_subtask_title,
    prove_created_session,
)
from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    DependentReferenceGuard,
    DependentReferenceSetGuard,
    UnitResult,
    UnitStatus,
    WritePreflightGuard,
    allocate_request_id,
    execute_request,
)
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.candidate_pending_state import (
    CandidatePendingRepository,
    CandidatePendingStateError,
)
from odyssey_core.clarification import (
    ClarificationChoice,
    ClarificationClassifier,
    ClarificationOption,
    LocalClarificationStore,
    OpenAILunaClarificationClassifier,
    PendingClarification,
    resolve_clarification_reply,
)
from odyssey_core.context import ContextFilter, ContextIndex, ContextIndexError
from odyssey_core.contextual import OpenAIContextualReasoner
from odyssey_core.contextual_calibration import load_contextual_calibration_examples
from odyssey_core.conversations import MAIN_CONVERSATION_ID
from odyssey_core.cost_aware_planning import LunaFirstRequestPlanner
from odyssey_core.direct_note_mutations import (
    DirectNoteMutationError,
    DirectNoteMutationService,
)
from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.fact_selection import OpenAILunaFactSelector
from odyssey_core.git_history import GitHistoryRecorder
from odyssey_core.identity_boundary import (
    AuthenticatedActorContext,
    ExternalPrincipal,
    IdentityMappingRepository,
    SelfBindingRepository,
)
from odyssey_core.local_conversations import ConversationRootResolver, LocalConversationStore
from odyssey_core.materialization import OpenAILunaWriter
from odyssey_core.note_queries import (
    BacklinkPage,
    NoteCapabilities,
    NoteDetail,
    NotePage,
    NotesQueryError,
    NotesQueryService,
)
from odyssey_core.note_result_snapshots import NoteResultSnapshot, affected_notes_snapshot
from odyssey_core.observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalSpan,
    OperationalStage,
    ProviderCallEvidence,
    SpanRecorder,
    normalize_provider_usage,
)
from odyssey_core.pending_work import PendingWorkError, PendingWorkRepository
from odyssey_core.persistence import ActorInput
from odyssey_core.plural_task_readback import guard_plural_task_readback
from odyssey_core.reference_preflight import ReferencePreflightError, current_identity_guard
from odyssey_core.request_planning import (
    OpenAIRequestPlanner as GPT56RequestPlanner,
)
from odyssey_core.request_planning import (
    PlannerClarification,
    RequestDisposition,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
    request_disposition,
    validate_request_plan,
)
from odyssey_core.resolution import ExistingEntityOutcome, resolve_existing_entity
from odyssey_core.schema_types import planning_schema_for_capability
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex, SemanticIndexError
from odyssey_core.semantic_sets import OpenAILunaSemanticSetSelector
from odyssey_core.source_boundary_review import OpenAICoreSourceBoundaryReviewer
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal import calendar_day_link_dates, materialized_day_link_index_ids
from odyssey_core.temporal_interpretation import (
    OpenAITemporalInterpreter,
    TemporalInterpretation,
    TemporalInterpreterError,
)
from odyssey_core.temporal_resolution import TemporalResolutionKind
from odyssey_core.verified_source_inventory import verified_context_source_inventory
from odyssey_runtime.application_bindings import bind_registered_executors

from .candidate_route_dispatch import execute_candidate_routed_message
from .context_planner_ports import OpenAILunaContextPlannerFactory
from .conversation_chat import deployed_chat_help_capabilities
from .conversation_entry import evaluate_conversation_entry
from .conversation_error import diagnose_trusted_execution_graph, explain_trusted_product_failure
from .conversation_gateway import ConversationGateError, OpenAIConversationGateway
from .delivery_results import DeliveryResultError, LocalDeliveryResultStore
from .dev_hot_path_diagnostics import timed_dev_hot_path
from .execution_checkpoints import CheckpointOutcome, LocalExecutionCheckpointStore
from .hybrid_group_compiler import compile_hybrid_candidate_bundle
from .progress import ProductProgressStore
from .routing import (
    ApplicationExecutor,
    ApplicationRouter,
    DependentRouteHandoff,
    PreparedExecution,
    RoutePreparer,
    execute_routed_request,
    is_route_execution_id,
)
from .serialization import application_result_to_response, operational_to_response


@dataclass(frozen=True)
class _ScopedTaskRouteExecutor:
    """Expose the dispatcher-required scoped entrypoint, never the legacy 4-arg fallback."""

    execute_scoped: Callable[..., TaskScopedExecution]


def _combined_write_preflight_guard(
    first: WritePreflightGuard | None, second: WritePreflightGuard | None
) -> WritePreflightGuard | None:
    """Preserve every app/Core guard when a dependent route adds its integrity guard."""
    if first is None:
        return second
    if second is None:
        return first

    def combined(action, preflight, repository, schema):  # type: ignore[no-untyped-def]
        first(action, preflight, repository, schema)
        second(action, preflight, repository, schema)

    return combined


def _dependent_relational_helper_index(action: Mapping[str, Any]) -> int | None:
    """Identify one bounded, reference-only relation with one dependent fact write.

    A scalar choice cannot resume unrelated units or other unresolved references.
    Only already validated Core actions pass this narrower continuation boundary.
    """
    if action.get("kind") != "write":
        return None
    units = action.get("units")
    if not isinstance(units, list) or len(units) != 2:
        return None
    helpers = [
        i
        for i, unit in enumerate(units)
        if isinstance(unit, dict)
        and isinstance(unit.get("target"), dict)
        and isinstance(unit["target"].get("relational_reference"), dict)
        and unit["target"]["relational_reference"].get("members") == "one"
        and unit.get("intent") == "record"
        and not unit.get("facts")
        and not unit.get("properties")
        and not unit.get("tag_changes")
        and not unit.get("references")
        and unit.get("destination_type") is None
        and unit.get("cardinality", "one") == "one"
    ]
    if len(helpers) != 1:
        return None
    helper = helpers[0]
    consumer = units[1 - helper]
    references = consumer.get("references") if isinstance(consumer, dict) else None
    if (
        not isinstance(references, list)
        or not references
        or not consumer.get("facts")
        or consumer.get("target", {}).get("relational_reference") is not None
        or any(not isinstance(ref, dict) or ref.get("target_index") != helper for ref in references)
    ):
        return None
    return helper


ProgressReporter = Callable[[str, Mapping[str, object]], None]
_PROGRESS_REPORTER: ContextVar[ProgressReporter | None] = ContextVar(
    "odyssey_progress_reporter", default=None
)


def _emit_progress(stage: str, payload: Mapping[str, object] | None = None) -> None:
    reporter = _PROGRESS_REPORTER.get()
    if reporter is not None:
        reporter(stage, payload or {})


_WORK_SESSION_RESOLUTION_PHASES = (
    "exact_lookup",
    "semantic_search",
    "candidate_validation",
    "relationship_context",
    "provider_evidence",
    "contextual_provider",
    "decision_validation",
)


def _work_session_resolution_substeps(recorder: SpanRecorder | None) -> tuple[OperationalSpan, ...]:
    """Emit only recognized nested spans; never inflate parent stage totals."""
    if recorder is None:
        return ()
    return tuple(span for span in recorder.spans if span.name in _WORK_SESSION_RESOLUTION_PHASES)


_VAULT_REPOSITORY_TYPE = VaultRepository

_EVENTS_DESCRIPTOR = ApplicationDescriptor(
    id="events",
    routing_description=(
        "structured calendar events, school activities, appointments, meetings, "
        "multi-day occurrences, explicit rescheduling and cancellation; not Tasks or reminders"
    ),
    dependencies=("temporal",),
)

_TASKS_DESCRIPTOR = ApplicationDescriptor(
    id="tasks",
    routing_description=(
        "task lifecycle, scheduling, completion, obligations, explicit work sessions, actual time "
        "tracking, and recording what was done during a work session"
    ),
    dependencies=("temporal",),
)


def _enabled_application_ids() -> tuple[str, ...]:
    """Read explicit application adoption without silently enabling new production behavior."""
    raw = os.environ.get("ODYSSEY_ENABLED_APPLICATIONS", "").strip()
    if not raw:
        return ()
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    if len(values) != len(set(values)):
        raise ValueError("ODYSSEY_ENABLED_APPLICATIONS must not contain duplicates")
    return values


def _chat_c4_model_advisory_enabled() -> bool:
    """Allow diagnostic C4 advice only when DEV already has a C3 gateway.

    Instantiating a C3 gateway solely for C4 would accidentally activate the
    C3 front-door classifier; C4's deterministic guidance is independent.
    """
    return (
        os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV"
        and os.environ.get("ODYSSEY_CHAT_C3_ENABLED") == "1"
        and os.environ.get("ODYSSEY_CHAT_C4_ENABLED") == "1"
        and os.environ.get("ODYSSEY_CHAT_C4_MODEL_ADVISORY_ENABLED") == "1"
    )


def _c4_graph_gateway_from_environment() -> OpenAIConversationGateway | None:
    """Enable C4 AI only for DEV C4; lack of a provider must not stop Core.

    C4 has its own gateway so a DEV runtime with C3 disabled does not
    inadvertently activate conversational classification on every request.
    """
    if (
        os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
        or os.environ.get("ODYSSEY_CHAT_C4_ENABLED") != "1"
    ):
        return None
    try:
        return OpenAIConversationGateway.from_environment()
    except ConversationGateError:
        # Provider unavailable: the immutable Core result and existing
        # evidence-grounded fallback still work, with no speculative retry.
        return None


# Preserve the existing runtime composition injection seam while changing its production target.
# Runtime tests and downstream composition overrides can keep patching this symbol; it now points to
# the validated Luna-first planner rather than the former Sol-only planner.
OpenAIRequestPlanner = LunaFirstRequestPlanner


class _FixedRequestPlanner:
    """Replay one locally validated incomplete action without another planner decision."""

    is_local_replay = True

    def __init__(self, plan: RequestPlan) -> None:
        """Retain the revalidated plan for a single continuation execution."""
        self._plan = plan

    def plan(self, request: str, conversation_context: object = ()) -> RequestPlan:
        """Return only the saved validated action; never inspect a new model response."""
        del request, conversation_context
        return self._plan


class NotesTelemetryError(RuntimeError):
    """Carry content-free failed Notes timing while preserving its HTTP failure class."""

    def __init__(self, operational: OperationalEvidence, *, bad_request: bool) -> None:
        super().__init__("intelligent Notes execution failed")
        self.operational = operational
        self.bad_request = bad_request


class DerivedIndexRefreshCoordinator:
    """Maintain derived indexes asynchronously with a strict reader barrier.

    Ordinary updates refresh immediately. A schema backfill can hold only its
    *derived* index updates briefly, combining several already-committed Core/Git
    notes in one verified refresh. The first pending backfill write starts a
    fixed maximum wait: continuous writes cannot prolong it. A reader or an
    ordinary mutation flushes pending work immediately. Neither source writes
    nor local Git history are batched by this coordinator.
    """

    def __init__(
        self,
        refresh: Callable[[Sequence[str]], None],
        *,
        backfill_window_s: float = 6.0,
        backfill_flush_threshold: int = 8,
    ) -> None:
        if (
            not isinstance(backfill_window_s, (int, float))
            or isinstance(backfill_window_s, bool)
            or not 0 < backfill_window_s <= 10
            or type(backfill_flush_threshold) is not int
            or not 2 <= backfill_flush_threshold <= 64
        ):
            raise ValueError("Invalid bounded backfill index refresh window")
        self._refresh = refresh
        self._backfill_window_s = float(backfill_window_s)
        self._backfill_flush_threshold = backfill_flush_threshold
        self._condition = Condition()
        self._pending: set[str] = set()
        # Failed IDs remain unresolved until an actual later refresh includes
        # them and succeeds. A subsequent unrelated successful refresh must
        # never turn a partial derived index into a falsely clean one.
        self._failed_ids: set[str] = set()
        self._flush_deadline: float | None = None
        self._flush_requested = False
        self._requested_generation = 0
        self._completed_generation = 0
        self._last_error: Exception | None = None
        self._worker: Thread | None = None

    def schedule(self, note_ids: Sequence[str]) -> int:
        """Schedule ordinary changed IDs without an intentional batching delay."""
        return self._queue(note_ids, backfill=False)

    def schedule_backfill(self, note_ids: Sequence[str]) -> int:
        """Coalesce source-committed backfill IDs for a bounded index-only window."""
        return self._queue(note_ids, backfill=True)

    def _queue(self, note_ids: Sequence[str], *, backfill: bool) -> int:
        bounded = tuple(dict.fromkeys(note_ids))
        if not bounded or any(not isinstance(note_id, str) or not note_id for note_id in bounded):
            raise ValueError("index refresh scheduling requires stable note IDs")
        with self._condition:
            if backfill and self._flush_deadline is None:
                self._flush_deadline = perf_counter() + self._backfill_window_s
            self._pending.update(bounded)
            self._requested_generation += 1
            generation = self._requested_generation
            if not backfill or len(self._pending) >= self._backfill_flush_threshold:
                self._flush_requested = True
            if self._worker is None or not self._worker.is_alive():
                self._worker = Thread(
                    target=self._run,
                    name="odyssey-index-refresh",
                    daemon=True,
                )
                self._worker.start()
            self._condition.notify_all()
            return generation

    def wait_until_clean(self) -> None:
        """Flush pending backfill promptly, then refuse stale/failed derived reads."""
        with self._condition:
            target = self._requested_generation
            if self._completed_generation < target and self._pending:
                self._flush_requested = True
                self._condition.notify_all()
            while self._completed_generation < target:
                self._condition.wait()
            if self._last_error is not None:
                raise RuntimeError("derived index refresh failed") from self._last_error

    def _run(self) -> None:
        while True:
            with self._condition:
                while True:
                    if not self._pending:
                        self._condition.wait()
                        continue
                    remaining = (
                        None
                        if self._flush_deadline is None
                        else self._flush_deadline - perf_counter()
                    )
                    if self._flush_requested or remaining is not None and remaining <= 0:
                        break
                    self._condition.wait(timeout=remaining)
                note_ids = tuple(sorted(self._pending | self._failed_ids))
                self._pending.clear()
                generation = self._requested_generation
                self._flush_deadline = None
                self._flush_requested = False
            error: Exception | None = None
            try:
                self._refresh(note_ids)
            except Exception as caught:  # Preserve fail-closed state for the next reader.
                error = caught
            with self._condition:
                self._completed_generation = max(self._completed_generation, generation)
                if error is not None:
                    self._failed_ids.update(note_ids)
                    self._last_error = error
                else:
                    self._failed_ids.difference_update(note_ids)
                    if not self._failed_ids:
                        self._last_error = None
                self._condition.notify_all()


def _emit_dev_index_refresh_diagnostic(
    *,
    outcome: str,
    note_count: int,
    duration_ms: float,
    stages_ms: Mapping[str, float],
    stages_cpu_ms: Mapping[str, float] | None = None,
    context_embedded_notes: int | None = None,
    failure_stage: str | None = None,
    failure_class: str | None = None,
) -> None:
    """Report bounded DEV performance without note IDs, paths or user contents."""
    if (
        os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
        or os.environ.get("ODYSSEY_LIGHT_SOURCE_V1") != "1"
    ):
        return
    event: dict[str, object] = {
        "outcome": outcome,
        "note_count": note_count,
        "duration_ms": round(max(0.0, duration_ms), 1),
        "stages_ms": {stage: round(max(0.0, duration), 1) for stage, duration in stages_ms.items()},
    }
    if stages_cpu_ms is not None:
        event["stages_cpu_ms"] = {
            stage: round(max(0.0, duration), 1) for stage, duration in stages_cpu_ms.items()
        }
    if context_embedded_notes is not None:
        event["context_embedded_notes"] = context_embedded_notes
    if failure_stage is not None:
        event["failure_stage"] = failure_stage
    if failure_class is not None:
        event["failure_class"] = failure_class
    # systemd's journal is not guaranteed to be persisted on small/local hosts.
    # Keep the same content-free record in a small, root-scoped derived log.
    # A full or read-only disk must never turn a completed index into a failure.
    record = "odyssey_dev_index_refresh " + json.dumps(event, sort_keys=True)
    root_value = os.environ.get("ODYSSEY_RUNTIME_ROOT")
    if root_value:
        try:
            root = Path(root_value).resolve()
            if root.is_dir() and not root.is_relative_to(Path("/data/odyssey").resolve()):
                target = root / "index-refresh-events.jsonl"
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(target, flags, 0o600)
                try:
                    if stat.S_ISREG(os.fstat(fd).st_mode):
                        if os.fstat(fd).st_size > 262_144:
                            os.ftruncate(fd, 0)
                        os.write(fd, (record + "\n").encode("utf-8"))
                finally:
                    os.close(fd)
        except (OSError, ValueError):
            pass
    try:
        print(record, file=sys.stderr, flush=True)
    except OSError:
        pass


@dataclass(slots=True)
class RuntimeComposition:
    """Own one long-lived assembly of providers, repositories, indexes, and Core execution."""

    core_execute: Callable[..., ApplicationResult]
    refresh_indexes: Callable[[], None]
    refresh_affected_indexes: Callable[[Sequence[str]], None] | None = None
    schedule_index_refresh: Callable[[Sequence[str]], int] | None = None
    await_index_refresh: Callable[[], None] | None = None
    refresh_task_lifecycle_indexes: Callable[[str, str], None] | None = None
    application_catalog: ApplicationCatalog = field(default_factory=ApplicationCatalog.empty)
    application_router: ApplicationRouter | None = None
    application_executors: Mapping[str, ApplicationExecutor] = field(default_factory=dict)
    temporal_executor: ApplicationExecutor | None = None
    route_preparers: Mapping[str, RoutePreparer] = field(default_factory=dict)
    identity_mapping_repository: IdentityMappingRepository | None = None
    conversation_root_resolver: ConversationRootResolver | None = None
    notes_service: NotesQueryService | None = None
    calendar_application: CalendarApplication | None = None
    notes_embedder: object | None = None
    pending_recorder: PendingWorkRepository | None = None
    vault_repository: VaultRepository | None = None
    canonical_schema: dict[str, object] | None = None
    # User schema proposals are read-only in the active runtime. Confirm/publish
    # requires a separate authenticated rollout and consistent schema/index swap.
    user_schema_registry: object | None = None
    user_schema_revision: int | None = None
    schema_activation_enabled: bool = False
    # Strictly read-only LLM design hints; activation still needs user click.
    schema_suggestion_service: object | None = None
    # Optional local, read-only retrospective scan. Trusted host selects one
    # profile/vault root and passes authenticated/local-profile identity.
    schema_scan_factory: Callable[[str], object] | None = None
    # Private DEV-only property enrichment; each request requires the SAME
    # authenticated actor's durable approval for this property/revision.
    schema_backfill_factory: Callable[[str], object] | None = None
    # Semantic interpretation is an independently gated, trusted runtime
    # adapter. No browser-supplied provider or value can authorize a write.
    schema_backfill_interpreter: object | None = None
    schema_backfill_call_limit: int | None = None
    clarification_classifier: ClarificationClassifier | None = None
    intelligent_notes_execute: (
        Callable[[str, Sequence[object]], NotePage | tuple[NotePage, OperationalEvidence]] | None
    ) = None
    direct_notes_mutations: DirectNoteMutationService | None = None
    direct_task_mutations: TaskDirectMutationService | None = None
    work_session_service: TaskWorkSessionService | None = None
    product_progress_store: ProductProgressStore | None = None
    execution_checkpoint_store_factory: Callable[[Path], LocalExecutionCheckpointStore] | None = (
        None
    )
    notes_mutation_actor: (
        Callable[[AuthenticatedActorContext | None, ExternalPrincipal | None], object] | None
    ) = None
    hybrid_candidate_execute: (
        Callable[[str, str, AuthenticatedActorContext | None, str | None], ApplicationResult] | None
    ) = None
    hybrid_read_execute: (
        Callable[[str, str, AuthenticatedActorContext, str], ApplicationResult | None] | None
    ) = None
    # Off by default, even on DEV. Enable only after opt-in complete-source
    # multi-mutation acceptance: a crash after a Task CREATE and before the
    # HTTP receipt must never re-run the same logical request automatically.
    full_source_mutation_guard: bool = False
    # Optional DEV-only conversational entry, disabled in normal compositions.
    # The injected gateway only classifies/answers and cannot authorize Core writes.
    conversation_gateway: OpenAIConversationGateway | None = None
    conversation_deployed_capabilities: frozenset[str] = frozenset()
    # C4 stays separately off even on a DEV instance running C3.
    conversation_error_guidance_enabled: bool = False
    # The deterministic Core reason code fully determines the public C4 hint.
    # Optional live-model advisory remains available for bounded diagnostics
    # but must be explicitly requested and never changes canonical authority.
    conversation_error_model_advisory_enabled: bool = False
    # C4 diagnosis reuses the existing OpenAI gateway but is independent of
    # the C3 conversational router. A model explanation is never write authority.
    conversation_graph_gateway: OpenAIConversationGateway | None = None
    monotonic: Callable[[], float] = perf_counter
    _execute_lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _conversation_lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def execute_product(
        self,
        user_request: str,
        request_id: str | None = None,
        conversation_id: str | None = None,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Execute one delivery once and replay a durable completed mutation result.

        Product deliveries are serialized because Git and multi-note mutation are not concurrent
        write authorities. The HTTP adapter remains concurrent, so Notes, conversation, and health
        reads do not wait behind planning. A completed mutation result is persisted before the
        response is written, allowing a same-ID retry after a lost connection to recover without
        another planner or mutation pass.
        """
        actor = self._resolve_actor(authenticated_actor, external_principal)
        checkpoint_store = self._checkpoint_store(actor)
        # A replay is a verified read of an existing delivery, not a new
        # execution. Do not register a fake "starting" milestone or reset its
        # in-memory donut until after the durable same-ID replay check.
        store: LocalDeliveryResultStore | None = None
        fingerprint: str | None = None
        if request_id is not None and conversation_id is not None:
            if self.conversation_root_resolver is None:
                raise ValueError("conversation root resolver is unavailable")
            store = LocalDeliveryResultStore(
                self.conversation_root_resolver.resolve(actor) / "delivery-results"
            )
            fingerprint = store.fingerprint(user_request, conversation_id)
        clarification_store = (
            LocalClarificationStore(self.conversation_root_resolver.resolve(actor), conversation_id)
            if conversation_id is not None and self.conversation_root_resolver is not None
            else None
        )
        with (
            self._execute_lock,
            clarification_store.locked() if clarification_store is not None else nullcontext(),
        ):
            if store is not None and fingerprint is not None:
                replay = store.load(request_id, fingerprint)
                if replay is not None:
                    replay["delivery_replayed"] = True
                    # Replay only READS the previously committed delivery.
                    # The original terminal checkpoint already records the
                    # durable write; appending it again invents an event and
                    # inflates the timeline on every n8n retry.
                    return replay
                # A previous E3 or C3 attempt may have crashed after its
                # irreversible claim but before the immutable reply receipt.
                # Never reclassify the same delivery as a new Core write.
                claim = store.inspect_mutation_claim(request_id, fingerprint)
                if claim["state"] == "unresolved_attempt":
                    raise DeliveryResultError("delivery has unresolved prior attempt")
            self._record_checkpoint(
                checkpoint_store, request_id, "starting", CheckpointOutcome.MILESTONE_OBSERVED
            )
            if request_id is not None and self.product_progress_store is not None:
                self.product_progress_store.begin(actor, request_id)
            candidate_response = self._handle_candidate_pending_reply(
                actor,
                conversation_id,
                request_id,
                user_request,
            )
            if candidate_response is not None:
                if store is not None and fingerprint is not None:
                    store.save(
                        request_id, fingerprint, candidate_response, _current_time()["timestamp"]
                    )
                self._record_terminal_checkpoint(
                    checkpoint_store,
                    request_id,
                    candidate_response,
                    store,
                    fingerprint,
                    force_replay=True,
                )
                return candidate_response
            pending = clarification_store.read() if clarification_store is not None else None
            if pending is not None:
                decision = resolve_clarification_reply(
                    user_request,
                    pending.options,
                    self.clarification_classifier,
                    pending.original_request,
                )
                if decision == "UNRESOLVED":
                    self._append_clarification_reply(
                        actor, conversation_id, request_id, user_request
                    )
                    response = self._pending_clarification_response(request_id, pending)
                    if store is not None and fingerprint is not None:
                        store.save(request_id, fingerprint, response, _current_time()["timestamp"])
                    self._record_terminal_checkpoint(
                        checkpoint_store,
                        request_id,
                        response,
                        store,
                        fingerprint,
                        force_replay=True,
                    )
                    return response
                clarification_store.clear()
                if decision == "CANCEL":
                    self._append_clarification_reply(
                        actor, conversation_id, request_id, user_request
                    )
                    response = self._control_response(request_id, "CANCEL")
                    if store is not None and fingerprint is not None:
                        store.save(request_id, fingerprint, response, _current_time()["timestamp"])
                    self._record_terminal_checkpoint(
                        checkpoint_store,
                        request_id,
                        response,
                        store,
                        fingerprint,
                        force_replay=True,
                    )
                    return response
                if decision != "NEW_REQUEST":
                    option_index = next(
                        index
                        for index, option in enumerate(pending.options)
                        if option.id == decision
                    )
                    try:
                        resumed_plan = self._validated_resume_plan(pending)
                    except (ValueError, KeyError, TypeError, PendingWorkError):
                        self._append_clarification_reply(
                            actor, conversation_id, request_id, user_request
                        )
                        response = self._control_response(request_id, "STALE_CLARIFICATION")
                        if store is not None and fingerprint is not None:
                            store.save(
                                request_id, fingerprint, response, _current_time()["timestamp"]
                            )
                        self._record_terminal_checkpoint(
                            checkpoint_store,
                            request_id,
                            response,
                            store,
                            fingerprint,
                            force_replay=True,
                        )
                        return response
                    choice = ClarificationChoice(
                        decision,
                        pending.evidence_guards[option_index],
                        pending.source_evidence_guard,
                    )
                    result = self._execute_with_progress(
                        actor,
                        request_id,
                        user_request,
                        request_id,
                        conversation_id,
                        AuthenticatedActorContext(actor),
                        None,
                        resume_plan=resumed_plan,
                        clarification_choice=choice,
                        original_request=pending.original_request,
                    )
                    response = self._finish_product_result(
                        result,
                        store,
                        fingerprint,
                        clarification_store,
                        force_replay=True,
                        actor=actor,
                        conversation_id=conversation_id,
                        source_text=pending.original_request,
                    )
                    self._record_terminal_checkpoint(
                        checkpoint_store,
                        request_id,
                        response,
                        store,
                        fingerprint,
                        force_replay=True,
                    )
                    return response
            # This gate is reached only AFTER existing Core/v2 clarification
            # handling; a pending choice can never become an unrelated CHAT.
            if (
                self.conversation_gateway is not None
                and request_id is not None
                and conversation_id == MAIN_CONVERSATION_ID
            ):
                if store is None or fingerprint is None:
                    raise ValueError("Conversational delivery requires durable replay")
                with timed_dev_hot_path(request_id, "conversation.entry"):
                    conversational = self._conversation_product_reply(
                        actor, user_request, request_id, store, fingerprint
                    )
                if conversational is not None:
                    store.save(
                        request_id, fingerprint, conversational, _current_time()["timestamp"]
                    )
                    # An unconfirmed claim can never be silently replayed, but
                    # this matching committed receipt may release its claim.
                    store.finish_mutation_claim(request_id)
                    self._record_terminal_checkpoint(
                        checkpoint_store,
                        request_id,
                        conversational,
                        store,
                        fingerprint,
                        force_replay=True,
                    )
                    return conversational
            if self.full_source_mutation_guard:
                if (
                    store is None
                    or fingerprint is None
                    or request_id is None
                    or self.hybrid_candidate_execute is None
                ):
                    raise ValueError("Guarded full-source mutation requires an isolated delivery")
                # Atomic durable claim before ANY semantic model or physical
                # Core/Tasks write. A later uncertain crash leaves the claim
                # until explicit reconciliation, never a blind second CREATE.
                store.claim_mutation(request_id, fingerprint)
            result = self._execute_with_progress(
                actor,
                request_id,
                user_request,
                request_id,
                conversation_id,
                AuthenticatedActorContext(actor)
                if authenticated_actor is not None or external_principal is not None
                else None,
                None,
            )
            with timed_dev_hot_path(request_id or "", "runtime.finish_product"):
                response = self._finish_product_result(
                    result,
                    store,
                    fingerprint,
                    clarification_store,
                    actor=actor,
                    conversation_id=conversation_id,
                    source_text=user_request,
                )
            if self.full_source_mutation_guard:
                assert store is not None and request_id is not None
                # Never remove the claim until a durable immutable replay
                # receipt exists; on readback/save failure keep it locked.
                store.finish_mutation_claim(request_id)
            self._record_terminal_checkpoint(
                checkpoint_store, request_id, response, store, fingerprint
            )
            return response

    def _conversation_product_reply(
        self,
        actor: str,
        source: str,
        request_id: str,
        store: LocalDeliveryResultStore,
        fingerprint: str,
    ) -> dict[str, object] | None:
        """Reuse the existing durable conversation for a non-writing C1–C3 answer.

        Return None only on an explicit ROUTER decision. An unavailable or
        ambiguous interpreter must NEVER fall through into a possible write.
        n8n remains responsible for persisting the assistant's visible answer.
        """
        if self.conversation_gateway is None:
            return None
        transcript = self._conversation_store(actor)
        try:
            # Never hold the global conversation lock across network LLM calls.
            # The outer product execution lock serializes requests; transcript
            # reads validate atomic snapshots and never grant identities.
            entry = evaluate_conversation_entry(
                self.conversation_gateway,
                transcript,
                original_message=source,
                request_id=request_id,
                now=datetime.fromisoformat(_current_time()["timestamp"]),
                deployed_capabilities=self.conversation_deployed_capabilities,
            )
        except (ConversationGateError, ValueError, OSError):
            entry = None
        if entry is not None and entry.route == "ROUTER":
            return None
        # This is the one-way boundary: after Chat is selected, reserve the
        # durable delivery ID BEFORE appending the user turn. If an error or
        # crash intervenes, a retry is blocked rather than reclassifying that
        # same ID into a possible Core write.
        store.claim_mutation(request_id, fingerprint)
        with self._conversation_lock:
            # A user turn must exist before the n8n assistant finalizer can
            # persist its matching result. Duplicate ID/text is idempotent.
            transcript.append_turn(
                request_id=request_id,
                role="user",
                text=source,
                created_at=_current_time()["timestamp"],
            )
        if entry is None:
            status, kind, message = (
                "needs_attention",
                "cannot_answer",
                "No he podido interpretar el mensaje con seguridad. Reformúlalo.",
            )
        elif entry.route == "CLARIFY":
            status, kind, message = (
                "needs_attention",
                "clarification",
                "Necesito que concretes a qué te refieres para continuar.",
            )
        else:
            assert entry.reply is not None
            answer = entry.reply.product_response(request_id)
            status, kind, message = answer["status"], answer["kind"], answer["message"]
        return {
            "request_id": request_id,
            "status": status,
            "product_outcome": "ANSWER" if status == "completed" else "CANNOT_ANSWER",
            "conversation_reply": {"status": status, "kind": kind, "message": message},
            "actions": [],
            "affected_stable_note_ids": [],
        }

    def _execute_with_progress(
        self,
        actor: str,
        request_id: str | None,
        *args: object,
        **kwargs: object,
    ) -> ApplicationResult:
        """Run one product execution with a transient user-safe progress reporter bound to it."""
        checkpoint_store = self._checkpoint_store(actor)
        if request_id is None or (self.product_progress_store is None and checkpoint_store is None):
            return self.execute(*args, **kwargs)
        token = _PROGRESS_REPORTER.set(
            lambda stage, payload: self._record_execution_progress(
                actor, request_id, stage, payload, checkpoint_store
            )
        )
        try:
            result = self.execute(*args, **kwargs)
            if self.product_progress_store is not None:
                self.product_progress_store.update(actor, request_id, "finalizing", 94)
            self._record_checkpoint(
                checkpoint_store, request_id, "finalizing", CheckpointOutcome.MILESTONE_OBSERVED
            )
            return result
        except Exception:
            self._record_checkpoint(
                checkpoint_store,
                request_id,
                "failed_or_unknown",
                CheckpointOutcome.FAILED_OR_UNKNOWN,
            )
            raise
        finally:
            _PROGRESS_REPORTER.reset(token)

    def _record_execution_progress(
        self,
        actor: str,
        request_id: str,
        stage: str,
        payload: Mapping[str, object],
        checkpoint_store: LocalExecutionCheckpointStore | None,
    ) -> None:
        """Fan out one existing milestone to transient progress and optional diagnostics."""
        self._record_progress_event(actor, request_id, stage, payload)
        self._record_checkpoint(
            checkpoint_store, request_id, stage, CheckpointOutcome.MILESTONE_OBSERVED
        )

    def _checkpoint_store(self, actor: str) -> LocalExecutionCheckpointStore | None:
        """Construct the optional root-bound diagnostic store without affecting delivery."""
        if (
            self.execution_checkpoint_store_factory is None
            or self.conversation_root_resolver is None
        ):
            return None
        try:
            return self.execution_checkpoint_store_factory(
                self.conversation_root_resolver.resolve(actor) / "execution-checkpoints"
            )
        except Exception:
            return None

    @staticmethod
    def _record_checkpoint(
        store: LocalExecutionCheckpointStore | None,
        request_id: str | None,
        stage: str,
        outcome: CheckpointOutcome,
    ) -> None:
        """Best-effort diagnostics only; failures never alter application execution."""
        if store is None or request_id is None:
            return
        try:
            store.record(request_id, stage, outcome, _current_time()["timestamp"])
        except Exception:
            return

    def _record_terminal_checkpoint(
        self,
        checkpoint_store: LocalExecutionCheckpointStore | None,
        request_id: str | None,
        response: Mapping[str, object],
        store: LocalDeliveryResultStore | None,
        fingerprint: str | None,
        *,
        force_replay: bool = False,
    ) -> None:
        """State completion honestly after the authoritative delivery save has returned."""
        persisted = (
            store is not None
            and fingerprint is not None
            and (
                force_replay
                or response.get("product_outcome") == "CLARIFY"
                or bool(response.get("affected_stable_note_ids"))
                or self.hybrid_candidate_execute is not None
            )
        )
        self._record_checkpoint(
            checkpoint_store,
            request_id,
            "delivery.result_persisted" if persisted else "processing.returned",
            CheckpointOutcome.RESULT_PERSISTED
            if persisted
            else CheckpointOutcome.PROCESSING_RETURNED,
        )

    def _record_progress_event(
        self,
        actor: str,
        request_id: str,
        stage: str,
        payload: Mapping[str, object],
    ) -> None:
        """Translate internal milestones into one bounded latest-only UX snapshot."""
        if self.product_progress_store is None:
            return
        progress_by_stage = {
            "routing.started": 8,
            "routing.boundary_review_started": 14,
            "routing.boundary_review_ready": 18,
            "routing.boundary_review_required": 18,
            "routing.ready": 18,
            "temporal.started": 28,
            "temporal.ready": 42,
            "planner.started": 50,
            "planner.ready": 68,
            "action.retrieve.started": 76,
            "action.delegate.started": 78,
            "action.write.started": 84,
        }
        progress = progress_by_stage.get(stage)
        if progress is None:
            from odyssey_core.stage_presentation import progress_stage_view

            if progress_stage_view(stage) is None:
                return
            # A new App reports its observed lifecycle, NOT a fabricated
            # percentage. Keep the latest proven coarse milestone intact.
            previous = self.product_progress_store.read(actor, request_id)
            progress = previous.progress if previous is not None else 0
        details: tuple[str, ...] = ()
        if stage == "routing.ready":
            route_count = payload.get("route_count")
            if isinstance(route_count, int) and route_count > 1:
                details = (str(route_count),)
        elif stage == "temporal.ready":
            values = payload.get("values")
            if isinstance(values, tuple):
                details = tuple(value for value in values if isinstance(value, str))[:6]
        elif stage == "planner.ready":
            references = payload.get("references")
            if isinstance(references, tuple):
                details = tuple(value for value in references if isinstance(value, str))[:6]
        self.product_progress_store.update(actor, request_id, stage, progress, details)

    def product_progress(
        self,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Return the latest transient progress visible to the same authenticated actor."""
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("request_id must be non-empty")
        actor = self._resolve_actor(authenticated_actor, external_principal)
        snapshot = (
            self.product_progress_store.read(actor, request_id)
            if self.product_progress_store is not None
            else None
        )
        if snapshot is None:
            return {
                "version": 1,
                "request_id": request_id,
                "stage": "starting",
                "progress": 0,
                "details": [],
                "sequence": 0,
                "complete": False,
            }
        return snapshot.to_response()

    def _finish_product_result(
        self,
        result: ApplicationResult,
        store: LocalDeliveryResultStore | None,
        fingerprint: str | None,
        clarification_store: LocalClarificationStore | None,
        *,
        force_replay: bool = False,
        actor: str | None = None,
        conversation_id: str | None = None,
        source_text: str = "",
    ) -> dict[str, object]:
        """Persist one safely completed delivery and replay it without re-execution.

        The DEV hybrid seam is deliberately stricter than v0: once it returns a
        typed result, including a no-write failure, the same actor/conversation
        delivery must not be semantically interpreted again. Transport
        exceptions never reach this method and therefore remain retryable.
        """
        response = application_result_to_response(result)
        # This optional C4 interpretation is strictly post-Core, uses the
        # existing read-only Luna gateway and never alters write authorization.
        # Unknown mutation count remains UNKNOWN, not an invented zero.
        if self.conversation_error_guidance_enabled:
            try:
                advice = explain_trusted_product_failure(
                    result,
                    response,
                    (
                        self.conversation_gateway
                        if self.conversation_error_model_advisory_enabled
                        else None
                    ),
                )
                if advice is not None:
                    response["error_guidance"] = advice
            except Exception:
                # A failed optional explanation must never turn a completed
                # Core result into a replayable transport failure.
                pass
        # One read-only ledger joins existing observed operational stages,
        # route statuses, physical Core receipts and actor-root checkpoints.
        # It never makes or retries a mutation decision.
        from .execution_ledger import project_execution_ledger

        checkpoint = None
        if actor is not None:
            diagnostic_store = self._checkpoint_store(actor)
            if diagnostic_store is not None:
                try:
                    checkpoint = diagnostic_store.load(result.request_id)
                except Exception:
                    checkpoint = None
        try:
            response["execution_ledger"] = project_execution_ledger(result, checkpoint)
        except (ValueError, TypeError, KeyError, AttributeError):
            # A failed optional projection after a canonical write must not
            # turn a verified delivery into a retryable transport failure.
            pass
        if response["product_outcome"] == "CLARIFY":
            candidate_view = self._candidate_pending_view(
                actor,
                conversation_id,
                result.pending_work.record_id
                if result.pending_work.persisted and result.pending_work.record_id is not None
                else result.request_id,
            )
            view = candidate_view
            if view is None:
                view = self._clarification_view(result)
            response["clarification"] = view
            if clarification_store is not None and candidate_view is None:
                pending = self._pending_decision(result, view)
                if pending is not None:
                    clarification_store.replace(pending)
                elif result.clarification_code is None:
                    # A choice with no bounded safe options cannot be resumed in this v1.
                    # Keep the specific product reason so the UI can explain what was unresolved.
                    response["product_outcome"] = "CANNOT_ANSWER"
        # The old C4 reason map remains a fallback. The AI reads the observed
        # E2 ledger (including early Router/refusal stages) and explains it.
        # Existing verified Core choice lists have precedence: never invent
        # a competing model-driven identity dialogue.
        if (
            self.conversation_graph_gateway is not None
            and isinstance(response.get("execution_ledger"), dict)
            and not (
                isinstance(response.get("clarification"), dict)
                and isinstance(response["clarification"].get("options"), list)
                and len(response["clarification"]["options"]) >= 2
            )
        ):
            try:
                diagnosis = diagnose_trusted_execution_graph(
                    result,
                    response,
                    response["execution_ledger"],
                    self.conversation_graph_gateway,
                    original_message=source_text,
                )
                if diagnosis is not None:
                    response["error_diagnosis"] = diagnosis
            except Exception:
                # A failed optional diagnosis cannot invalidate the original
                # immutable Core response or permit a fresh write.
                pass
        if (
            store is not None
            and fingerprint is not None
            and (
                force_replay
                or result.affected_stable_note_ids
                or response["product_outcome"] == "CLARIFY"
                or self.hybrid_candidate_execute is not None
            )
        ):
            store.save(result.request_id, fingerprint, response, _current_time()["timestamp"])
        return response

    def _candidate_pending_repository(self, actor: str | None) -> CandidatePendingRepository | None:
        """Bind v2 source pending state only for the explicit authenticated hybrid seam."""
        if (
            actor is None
            or self.hybrid_candidate_execute is None
            or self.conversation_root_resolver is None
            or self.vault_repository is None
            or self.canonical_schema is None
        ):
            return None
        root = self.conversation_root_resolver.resolve(actor) / "pending"
        if not root.is_dir() or root.is_symlink():
            return None
        return CandidatePendingRepository(root)

    def _candidate_pending_view(
        self, actor: str | None, conversation_id: str | None, request_id: str
    ) -> dict[str, object] | None:
        """Project one durable v2 choice without granting its selected value write authority."""
        if conversation_id is None:
            return None
        try:
            repository = self._candidate_pending_repository(actor)
            if repository is None:
                return None
            record = repository.read(request_id)
            if record["conversation_id"] != conversation_id or record["status"] != "open":
                return None
            options = record["options"]
            # v2 never truncates an ambiguity into a misleading choice list.
            if not 1 < len(options) <= 4:
                options = []
            pending = record["pending"]
            return {
                "request_id": record["request_id"],
                "requested_reference": pending[0]["reference_text"],
                "explanation": (
                    "No puedo identificar con seguridad a "
                    f"«{pending[0]['reference_text']}». Elige una persona o cancela."
                    if pending[0]["reference_text"] and options
                    else "La parte pendiente conserva su fuente original y requiere revisión."
                ),
                "options": [{"id": item["id"], "label": item["label"]} for item in options],
            }
        except (CandidatePendingStateError, OSError, ValueError, KeyError, TypeError):
            return None

    def _candidate_reply_is_immediate(
        self, actor: str, repository: CandidatePendingRepository, conversation_id: str
    ) -> bool:
        """Require the exact source delivery immediately before its assistant clarification.

        The browser durably appends its assistant clarification before the human
        chooses a person. The decision must still be bound to the original outer
        request ID, rather than merely the last text or a prior unresolved turn.
        """
        open_ids = repository.open_requests(conversation_id)
        if not open_ids:
            return False
        with self._conversation_lock:
            turns = self._conversation_store(actor).load_main_page(limit=3)["turns"]
        if not turns:
            return False
        last = turns[-1]
        if last["role"] == "assistant":
            if (
                len(turns) < 2
                or turns[-2]["role"] != "user"
                or turns[-2]["request_id"] != last["request_id"]
            ):
                return False
            user_turn = turns[-2]
        else:
            user_turn = last
        outer_request_id = user_turn["request_id"]
        return user_turn["role"] == "user" and any(
            user_turn["text"] == repository.read(record_id)["original_request"]
            and (
                outer_request_id == record_id or is_route_execution_id(outer_request_id, record_id)
            )
            for record_id in open_ids
        )

    def _handle_candidate_pending_reply(
        self,
        actor: str,
        conversation_id: str | None,
        request_id: str | None,
        user_request: str,
    ) -> dict[str, object] | None:
        """Consume a v2 selection/cancel before v1 or hybrid routing, never execute it.

        A ``NEW_REQUEST`` deliberately returns ``None`` so the ordinary enabled
        hybrid route receives the new source.  It can never fall back to v0
        while this composition has the hybrid seam enabled.
        """
        if conversation_id is None or request_id is None:
            return None
        try:
            repository = self._candidate_pending_repository(actor)
            if repository is None or not repository.open_requests(conversation_id):
                return None
            reply = repository.reply(
                conversation_id=conversation_id,
                reply=user_request,
                answer_id=request_id,
                vault=self.vault_repository,
                schema=cast(dict[str, Any], self.canonical_schema),
                immediate_followup=self._candidate_reply_is_immediate(
                    actor, repository, conversation_id
                ),
                classifier=self.clarification_classifier,
            )
        except CandidatePendingStateError:
            return self._control_response(request_id, "STALE_CANDIDATE_PENDING")
        if reply.outcome == "new_request":
            return None
        self._append_clarification_reply(actor, conversation_id, request_id, user_request)
        if reply.outcome == "choice_recorded":
            # Re-check under the repository lock before making even the
            # non-executing acknowledgement visible to the caller.
            review = repository.selected_for_core_review(
                conversation_id=conversation_id,
                request_id=cast(str, reply.request_id),
                vault=self.vault_repository,
                schema=cast(dict[str, Any], self.canonical_schema),
            )
            if review.outcome != "choice_ready_for_core_review":
                return self._control_response(request_id, "STALE_CANDIDATE_SELECTION")
            return {
                **self._control_response(request_id, "CANDIDATE_SELECTION_RECORDED"),
                "status": "needs_attention",
                "product_outcome": "CANNOT_ANSWER",
                "product_reason": "CONTINUATION_REVIEW_REQUIRED",
                "selected_pending_request_id": reply.request_id,
            }
        if reply.outcome == "cancelled":
            return self._control_response(request_id, "CANDIDATE_CANCELLED")
        if reply.outcome == "unresolved":
            view = self._candidate_pending_view(actor, conversation_id, cast(str, reply.request_id))
            if view is not None:
                return {
                    "request_id": request_id,
                    "status": "needs_attention",
                    "product_outcome": "CLARIFY",
                    "product_reason": "AMBIGUOUS_REFERENCE",
                    "clarification": view,
                    "actions": [],
                    "affected_stable_note_ids": [],
                    "operational": {"total_duration_ms": 0.0, "stages": []},
                }
        controls = {
            "explicit_request_required": "CANDIDATE_EXPLICIT_REQUEST_REQUIRED",
            "multiple_or_no_pending": "CANDIDATE_AMBIGUOUS_PENDING",
            "needs_core_options": "CANDIDATE_OPTIONS_UNAVAILABLE",
            "stale_choice": "STALE_CANDIDATE_SELECTION",
            "stale_written_facts": "STALE_CANDIDATE_FACTS",
            "already_selected": "CANDIDATE_ALREADY_SELECTED",
            "already_closed": "CANDIDATE_ALREADY_CLOSED",
            "unavailable": "CANDIDATE_UNAVAILABLE",
        }
        return self._control_response(
            request_id, controls.get(reply.outcome, "CANDIDATE_UNRESOLVED")
        )

    def _pending_decision(
        self, result: ApplicationResult, view: dict[str, object]
    ) -> PendingClarification | None:
        """Accept only one previously grounded ambiguous write unit for safe continuation."""
        if (
            self.pending_recorder is None
            or self.vault_repository is None
            or self.canonical_schema is None
            or not result.pending_work.persisted
            or result.pending_work.record_id is None
            or not isinstance(view["options"], list)
            or not 1 < len(view["options"]) <= 4
        ):
            return None
        try:
            record = self.pending_recorder.read(result.pending_work.record_id)
            record_id = result.pending_work.record_id
            routed = record["request_id"] == record_id and is_route_execution_id(
                result.request_id, record_id
            )
            if not routed and (
                record["request_id"] != result.request_id
                or result.affected_stable_note_ids
                or len(result.action_results) != 1
            ):
                return None
            if routed and (
                result.clarification_code is not None or self._ambiguous_action_count(result) != 1
            ):
                return None
            incomplete = record["incomplete_actions"]
            if len(incomplete) != 1:
                return None
            action = incomplete[0]["planned_action"]
            execution = incomplete[0]["execution_result"]
            source_guard: str | None = None
            relational = False
            if action["kind"] == "write":
                helper_index = _dependent_relational_helper_index(action)
                relational = (
                    len(action["units"]) == 1
                    and action["units"][0]["target"].get("relational_reference") is not None
                ) or helper_index is not None
                helper_results = execution.get("unit_results", [])
                safe_helper = (
                    helper_index is None
                    or len(helper_results) == 2
                    and helper_results[helper_index].get("status") == "deferred"
                    and helper_results[helper_index].get("reason")
                    in {"relational_evidence_ambiguous", "relational_singular_ambiguous"}
                    and helper_results[1 - helper_index].get("reason") == "DEPENDENCY_FAILED"
                )
                action_level = (
                    relational
                    and safe_helper
                    and execution["reason"]
                    in {
                        "relational_evidence_ambiguous",
                        "relational_singular_ambiguous",
                    }
                )
                if action_level:
                    candidates = execution["candidate_note_ids"]
                    source_guard = execution.get("relational_evidence_guard")
                elif (
                    len(action["units"]) != 1
                    or len(execution["unit_results"]) != 1
                    or execution["unit_results"][0]["reason"] != "ambiguous_existing_target"
                ):
                    return None
                else:
                    candidates = execution["unit_results"][0]["candidates"]
            elif action["kind"] == "retrieve":
                relational = action["plan"].get("relational_reference") is not None
                ordinary = (
                    action["plan"].get("entity") is not None
                    and execution["reason"] == "ambiguous_existing_target"
                )
                if action["result_shape"] != "single" or not (
                    ordinary
                    or relational
                    and execution["reason"]
                    in {"relational_evidence_ambiguous", "relational_singular_ambiguous"}
                ):
                    return None
                candidates = execution["candidate_note_ids"]
                source_guard = execution.get("relational_evidence_guard") if relational else None
            else:
                return None
            options = tuple(ClarificationOption(**item) for item in view["options"])
            if tuple(option.id for option in options) != tuple(candidates):
                return None
            guards = []
            for option in options:
                guards.append(
                    current_identity_guard(self.vault_repository, self.canonical_schema, option.id)
                )
            if relational and (
                not isinstance(source_guard, str)
                or re.fullmatch(r"[0-9a-f]{64}", source_guard) is None
            ):
                return None
            return PendingClarification(
                record["user_request"],
                record["request_id"],
                record_id,
                options,
                tuple(guards),
                source_guard,
                view.get("requested_reference"),
                view.get("explanation"),
            )
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            OSError,
            PendingWorkError,
            ReferencePreflightError,
        ):
            return None

    @staticmethod
    def _ambiguous_action_count(result: ApplicationResult) -> int:
        """Count action-level ambiguities so one scalar clarification cannot hide siblings."""
        ambiguous_reasons = {
            "ambiguous_existing_target",
            "relational_evidence_ambiguous",
            "relational_singular_ambiguous",
        }
        return sum(
            action.reason in ambiguous_reasons
            or any(unit.reason == "ambiguous_existing_target" for unit in action.unit_results)
            for action in result.action_results
        )

    def _validated_resume_plan(self, pending: PendingClarification) -> RequestPlan:
        """Revalidate the one incomplete action; completed work is never replayed."""
        if self.pending_recorder is None or self.canonical_schema is None:
            raise ValueError("pending continuation is unavailable")
        record = self.pending_recorder.read(pending.pending_record_id)
        if (
            record["request_id"] != pending.original_request_id
            or record["user_request"] != pending.original_request
            or record["affected_stable_note_ids"]
            or len(record["incomplete_actions"]) != 1
        ):
            raise ValueError("pending continuation is not singular")
        action = record["incomplete_actions"][0]["planned_action"]
        evidence = record["incomplete_actions"][0]["execution_result"]
        candidate_ids = tuple(option.id for option in pending.options)
        if action.get("kind") == "write":
            helper_index = _dependent_relational_helper_index(action)
            relational = (
                len(action.get("units", ())) == 1
                and action["units"][0].get("target", {}).get("relational_reference") is not None
            ) or helper_index is not None
            unit_results = evidence.get("unit_results", [])
            safe_helper = (
                helper_index is None
                or len(unit_results) == 2
                and unit_results[helper_index].get("status") == "deferred"
                and unit_results[helper_index].get("reason")
                in {"relational_evidence_ambiguous", "relational_singular_ambiguous"}
                and unit_results[1 - helper_index].get("reason") == "DEPENDENCY_FAILED"
            )
            safe = (
                relational
                and safe_helper
                and evidence.get("reason")
                in {"relational_evidence_ambiguous", "relational_singular_ambiguous"}
                and tuple(evidence.get("candidate_note_ids", ())) == candidate_ids
                and evidence.get("relational_evidence_guard") == pending.source_evidence_guard
            ) or (
                len(action.get("units", ())) == 1
                and len(evidence.get("unit_results", ())) == 1
                and evidence["unit_results"][0].get("reason") == "ambiguous_existing_target"
                and tuple(evidence["unit_results"][0].get("candidates", ())) == candidate_ids
            )
        elif action.get("kind") == "retrieve":
            relational = action.get("plan", {}).get("relational_reference") is not None
            safe = (
                action.get("result_shape") == "single"
                and (
                    (
                        action.get("plan", {}).get("entity") is not None
                        and evidence.get("reason") == "ambiguous_existing_target"
                    )
                    or (
                        relational
                        and evidence.get("reason")
                        in {"relational_evidence_ambiguous", "relational_singular_ambiguous"}
                    )
                )
                and tuple(evidence.get("candidate_note_ids", ())) == candidate_ids
            )
            if relational and (
                not isinstance(pending.source_evidence_guard, str)
                or evidence.get("relational_evidence_guard") != pending.source_evidence_guard
            ):
                safe = False
        else:
            safe = False
        if evidence.get("status") != "deferred" or not safe:
            raise ValueError("pending continuation is not one supported decision")
        # This was already a Core-validated action when it was persisted. Temporal
        # may have added canonical Calendar Day links to its facts afterwards.
        # Revalidate that narrow internal form without admitting ordinary wikilinks.
        linked_dates: list[str] = []
        authorized_dates: list[str] = []
        if action["kind"] == "write":
            for unit in action["units"]:
                target = unit["target"]
                if target.get("type") == "calendar_day":
                    authorized_dates.append(target["query"])
                for fact in unit["facts"]:
                    linked_dates.extend(calendar_day_link_dates(fact))
            authorized_dates.extend(linked_dates)
        plan = validate_request_plan(
            {"actions": [action], "limitations": record["planner_limitations"]},
            self.canonical_schema,
            allow_temporal_reference_links=bool(linked_dates),
            authorized_calendar_dates=tuple(dict.fromkeys(authorized_dates)),
        )
        if len(plan.actions) != 1 or not isinstance(plan.actions[0], WriteAction | RetrieveAction):
            raise ValueError("pending continuation is unsupported")
        if action["kind"] == "write":
            helper_index = _dependent_relational_helper_index(action)
            if helper_index is not None:
                # Internal reference-only helpers are derived by Core lowering. The
                # pending JSON stores their stable structure, not the private flag.
                # Restore it only for the previously verified two-unit dependency.
                original_write = plan.actions[0]
                assert isinstance(original_write, WriteAction)
                units = list(original_write.units)
                units[helper_index] = replace(units[helper_index], reference_lookup_only=True)
                plan = replace(plan, actions=(replace(original_write, units=tuple(units)),))
        return plan

    def _append_clarification_reply(
        self, actor: str, conversation_id: str | None, request_id: str | None, text: str
    ) -> None:
        """Retain the visible reply even when no Core execution is needed."""
        if conversation_id is not None:
            with self._conversation_lock:
                self._conversation_store(actor).append_turn(
                    request_id=request_id or allocate_request_id(),
                    role="user",
                    text=text,
                    created_at=_current_time()["timestamp"],
                )

    @staticmethod
    def _control_response(request_id: str | None, control: str) -> dict[str, object]:
        """Return a bounded non-executing product response for cancellation or stale state."""
        return {
            "request_id": request_id,
            "status": "completed" if control == "CANCEL" else "needs_attention",
            "product_outcome": "ANSWER" if control == "CANCEL" else "CANNOT_ANSWER",
            "product_reason": None if control == "CANCEL" else "STALE_EVIDENCE",
            "product_control": control,
            "actions": [],
            "affected_stable_note_ids": [],
            "operational": {"total_duration_ms": 0.0, "stages": []},
        }

    @staticmethod
    def _pending_clarification_response(
        request_id: str | None, pending: PendingClarification
    ) -> dict[str, object]:
        """Ask again with exactly the same bounded options and original request intact."""
        return {
            "request_id": request_id,
            "status": "needs_attention",
            "product_outcome": "CLARIFY",
            "product_reason": "AMBIGUOUS_REFERENCE",
            "clarification": {
                "request_id": pending.original_request_id,
                "reason": "AMBIGUOUS_REFERENCE",
                "requested_reference": pending.requested_reference,
                "explanation": pending.explanation,
                "options": [
                    {
                        "id": item.id,
                        "label": item.label,
                        **(
                            {"note_type": item.note_type, "evidence": item.evidence}
                            if item.note_type and item.evidence
                            else {}
                        ),
                    }
                    for item in pending.options
                ],
            },
            "actions": [],
            "affected_stable_note_ids": [],
            "operational": {"total_duration_ms": 0.0, "stages": []},
        }

    def _clarification_view(self, result: ApplicationResult) -> dict[str, object]:
        """Project only current, bounded, actor-local option labels for one unresolved decision."""
        presentation = next(
            (
                action.clarification or (unit.clarification if unit is not None else None)
                for action in result.action_results
                for unit in action.unit_results or (None,)
                if action.clarification is not None
                or unit is not None
                and unit.clarification is not None
            ),
            None,
        )
        candidates = next(
            (
                action.candidate_note_ids or (unit.candidates if unit is not None else ())
                for action in result.action_results
                for unit in action.unit_results or (None,)
                if action.reason
                in {
                    "ambiguous_existing_target",
                    "relational_evidence_ambiguous",
                    "relational_singular_ambiguous",
                }
                or unit is not None
                and unit.reason == "ambiguous_existing_target"
            ),
            (),
        )
        options: list[dict[str, str]] = []
        if presentation is not None and tuple(
            candidate.id for candidate in presentation.candidates
        ) == tuple(candidates):
            options = [
                {
                    "id": candidate.id,
                    "label": candidate.label,
                    "note_type": candidate.note_type,
                    "evidence": candidate.evidence,
                }
                for candidate in presentation.candidates
            ]
        elif self.notes_service is not None and 1 < len(candidates) <= 4:
            try:
                for note_id in candidates:
                    note = self.notes_service.detail(note_id).note
                    options.append({"id": note.id, "label": note.name})
            except (NotesQueryError, ValueError):
                options = []
        return {
            "request_id": result.request_id,
            "reason": "AMBIGUOUS_REFERENCE"
            if options
            else "AMBIGUOUS_SET_SCOPE"
            if any(
                action.semantic_set is not None
                and action.semantic_set.outcome.value == "AMBIGUOUS_SET_SCOPE"
                for action in result.action_results
            )
            else result.clarification_code or "AMBIGUOUS_REFERENCE",
            "options": options,
            "requested_reference": presentation.requested_reference
            if presentation is not None
            else None,
            "explanation": presentation.explanation if presentation is not None else None,
            "pending_record_id": result.pending_work.record_id
            if result.pending_work.persisted
            else None,
        }

    def notes(
        self,
        operation: str,
        payload: dict[str, object],
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Serialize the entire delivery/replay handshake for direct mutations.

        Do not hold the writer lock for ordinary Notes reads.  Every direct
        mutation has a mandatory request_id: this general envelope guard also
        covers new registered operations without extending a capability switch.
        Use a reentrant lock because the established domain execution blocks
        already coordinate through the same writer boundary.
        """
        if isinstance(payload, dict) and "request_id" in payload:
            with self._execute_lock:
                return self._notes_unlocked(
                    operation, payload, authenticated_actor, external_principal
                )
        return self._notes_unlocked(operation, payload, authenticated_actor, external_principal)

    def _notes_unlocked(
        self,
        operation: str,
        payload: dict[str, object],
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Execute one typed Notes operation for the authenticated actor boundary.

        Actor resolution occurs even though current local-first Notes storage is root-bound. This
        preserves the existing outer isolation contract and prevents a route from bypassing it.
        """
        resolved_actor = self._resolve_actor(authenticated_actor, external_principal)
        if self.notes_service is None:
            raise ValueError("Notes service is unavailable")
        if (
            operation in {"query", "backlinks", "intelligent"}
            and self.await_index_refresh is not None
        ):
            self.await_index_refresh()
        if operation == "schema_scan":
            if (
                (authenticated_actor is None and external_principal is None)
                or self.schema_scan_factory is None
                or self.user_schema_registry is None
                or self.user_schema_revision is None
                or self.canonical_schema is None
            ):
                raise ValueError("Local schema scan is unavailable")
            if set(payload) != {
                "scan_kind",
                "target_type_id",
                "property_id",
                "expected_revision",
                "action",
            }:
                raise ValueError("Invalid local schema scan request")
            if (
                payload["action"] not in {"advance", "status"}
                or payload["scan_kind"] not in {"discover_type", "backfill_property"}
                or not isinstance(payload["target_type_id"], str)
                or type(payload["expected_revision"]) is not int
                or payload["expected_revision"] != self.user_schema_revision
                or (
                    payload["property_id"] is not None
                    and not isinstance(payload["property_id"], str)
                )
            ):
                raise ValueError("Invalid local schema scan arguments")
            from odyssey_core.schema_retrospection_jobs import LocalSchemaScanJobs

            jobs = self.schema_scan_factory(resolved_actor)
            if not isinstance(jobs, LocalSchemaScanJobs):
                raise ValueError("Local schema scan store is unavailable")
            # Stable per-actor/profile target key; no browser storage, global
            # queue or server-generated arbitrary task ID to remember.
            job_id = hashlib.sha256(
                json.dumps(
                    {
                        "revision": payload["expected_revision"],
                        "kind": payload["scan_kind"],
                        "target": payload["target_type_id"],
                        "property": payload["property_id"],
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()[:48]
            if payload["action"] == "status":
                progress = jobs.read(job_id)
                if progress is None:
                    return {"kind": "schema_scan", "status": "not_started"}
                if (
                    progress.kind != payload["scan_kind"]
                    or progress.target_type_id != payload["target_type_id"]
                    or progress.property_id != payload["property_id"]
                ):
                    raise ValueError("Local schema scan target mismatch")
            else:
                progress = jobs.advance(
                    job_id=job_id,
                    schema=self.canonical_schema,
                    kind=payload["scan_kind"],
                    target_type_id=payload["target_type_id"],
                    property_id=payload["property_id"],
                    limit=20,
                )
            # A progress receipt contains no source text/names, candidate
            # identities or authorization to change canonical Notes.
            return {
                "kind": "schema_scan",
                "status": "complete" if progress.complete else "scanning",
                "scanned_paths": progress.scanned_paths,
                "eligible_notes": progress.eligible_notes,
                "skipped_existing_values": progress.skipped_existing_values,
                "legacy_sources": progress.legacy_sources,
            }
        if operation == "schema_backfill":
            if (
                (authenticated_actor is None and external_principal is None)
                or self.user_schema_registry is None
                or self.user_schema_revision is None
                or self.schema_backfill_factory is None
            ):
                raise ValueError("Local schema backfill is unavailable")
            if set(payload) != {"target_type_id", "property_id", "expected_revision", "action"} or (
                payload["action"]
                not in {
                    "stage",
                    "status",
                    "advance",
                    "stage_followup",
                    "status_followup",
                    "advance_followup",
                }
                or not isinstance(payload["target_type_id"], str)
                or not isinstance(payload["property_id"], str)
                or type(payload["expected_revision"]) is not int
                or payload["expected_revision"] != self.user_schema_revision
            ):
                raise ValueError("Invalid schema backfill arguments")
            from .schema_backfill_jobs import LocalBackfillJob
            from .user_schema_registry import UserSchemaRegistry

            registry = self.user_schema_registry
            if not isinstance(
                registry, UserSchemaRegistry
            ) or not registry.confirmed_backfill_property(
                resolved_actor,
                expected_revision=payload["expected_revision"],
                type_id=payload["target_type_id"],
                property_id=payload["property_id"],
            ):
                raise ValueError("Schema property enrichment was not approved by actor")
            worker = self.schema_backfill_factory(resolved_actor)
            if not isinstance(worker, LocalBackfillJob):
                raise ValueError("Local backfill worker is unavailable")
            job_id = hashlib.sha256(
                json.dumps(
                    {
                        "revision": payload["expected_revision"],
                        "type": payload["target_type_id"],
                        "property": payload["property_id"],
                        "operation": "local_property_backfill",
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()[:48]
            is_followup = payload["action"].endswith("_followup")
            followup_id = hashlib.sha256(f"semantic-followup-v1:{job_id}".encode()).hexdigest()[:48]
            if is_followup and self.schema_backfill_interpreter is None:
                raise ValueError("Semantic follow-up requires an enabled trusted model")
            budget_job_id = followup_id if is_followup else job_id
            # Trust only this actor-bound, signed local allowance. This is a
            # request-count ceiling, not a promise of exact provider dollars.
            interpreter = None
            if self.schema_backfill_interpreter is not None:
                if self.schema_backfill_call_limit is None:
                    raise ValueError("Semantic campaign requires a trusted call cap")
                from .schema_semantic_budget import (
                    BudgetedSemanticInterpreter,
                    SemanticCallLedger,
                )

                interpreter = BudgetedSemanticInterpreter(
                    interpreter=self.schema_backfill_interpreter,
                    ledger=SemanticCallLedger(
                        worker=worker,
                        campaign_id=budget_job_id,
                        limit=self.schema_backfill_call_limit,
                    ),
                )
            # Preserve V1 journals already staged before this deployment.
            # For NEW campaigns in a >10k-physical-note vault, use a sealed
            # actor-bound sequence of small V1 journals; never truncate V1.
            # The same confirmed property is checked above on EVERY action.
            from odyssey_core import schema_retrospection as scan_limits

            from . import schema_backfill_campaign as campaign_contract

            campaign = campaign_contract.LocalBackfillCampaign(
                worker=worker, segment_size=campaign_contract._DEFAULT_SEGMENT_SIZE
            )
            legacy = worker.status(job_id)
            saved_campaign = campaign.status(job_id)
            if legacy is not None and saved_campaign is not None:
                raise ValueError("Conflicting local backfill campaign and legacy journal")
            if is_followup:
                # Explicit user action against the already authenticated,
                # previously confirmed property; never reopen old signed proof.
                original = saved_campaign if saved_campaign is not None else legacy
                if original is None or original["status"] != "awaiting_ai":
                    raise ValueError("No completed deferred campaign is available")
                origin_kind = "campaign" if saved_campaign is not None else "legacy"
                if payload["action"] == "stage_followup":
                    result = campaign.stage_followup(
                        campaign_id=followup_id,
                        original_id=job_id,
                        origin_kind=origin_kind,
                        type_id=payload["target_type_id"],
                        property_id=payload["property_id"],
                    )
                elif payload["action"] == "status_followup":
                    result = campaign.status(followup_id)
                    if result is None:
                        return {"kind": "schema_backfill", "status": "not_started"}
                else:
                    result = campaign.advance(
                        campaign_id=followup_id,
                        type_id=payload["target_type_id"],
                        property_id=payload["property_id"],
                        actor={"human": resolved_actor, "app": "odyssey-schema-backfill"},
                        now=_current_time()["timestamp"],
                        interpreter=interpreter,
                    )
                return {
                    "kind": "schema_backfill",
                    **result,
                    **interpreter.ledger.status(),
                    "phase": "semantic_followup",
                }
            use_campaign = saved_campaign is not None or (
                legacy is None
                and len(worker.repository.note_version_snapshot()) > scan_limits._MAX_PROGRESS_IDS
            )
            if payload["action"] == "stage":
                result = (
                    campaign.stage(
                        campaign_id=job_id,
                        type_id=payload["target_type_id"],
                        property_id=payload["property_id"],
                    )
                    if use_campaign
                    else worker.stage(
                        job_id=job_id,
                        type_id=payload["target_type_id"],
                        property_id=payload["property_id"],
                    )
                )
            elif payload["action"] == "status":
                result = campaign.status(job_id) if use_campaign else legacy
                if result is None:
                    return {"kind": "schema_backfill", "status": "not_started"}
            else:
                # Deterministic evidence uses Core directly. Source-bound
                # semantic review is available ONLY under the trusted, separate
                # DEV flag and the same confirmed actor/property authority.
                actor = {"human": resolved_actor, "app": "odyssey-schema-backfill"}
                now = _current_time()["timestamp"]
                result = (
                    campaign.advance(
                        campaign_id=job_id,
                        type_id=payload["target_type_id"],
                        property_id=payload["property_id"],
                        actor=actor,
                        now=now,
                        interpreter=None,  # First pass is always deterministic.
                    )
                    if use_campaign
                    else worker.advance(
                        job_id=job_id,
                        type_id=payload["target_type_id"],
                        property_id=payload["property_id"],
                        actor=actor,
                        now=now,
                        interpreter=None,  # No charge before explicit follow-up.
                    )
                )
            return {
                "kind": "schema_backfill",
                **result,
                **(interpreter.ledger.status() if interpreter is not None else {}),
            }
        if operation in {"schema_confirm", "schema_status"}:
            if (
                authenticated_actor is None
                and external_principal is None
                or self.user_schema_registry is None
                or (operation == "schema_confirm" and not self.schema_activation_enabled)
            ):
                raise ValueError("Schema activation is unavailable")
            from .user_schema_registry import SchemaConfirmation, UserSchemaRegistry

            registry = self.user_schema_registry
            if not isinstance(registry, UserSchemaRegistry):
                raise ValueError("Schema activation registry is unavailable")
            if operation == "schema_status":
                if not payload:
                    return {
                        "revision": registry.snapshot()[0],
                        "status": "ready",
                        "can_confirm": self.schema_activation_enabled,
                    }
                if set(payload) != {"request_id"} or not isinstance(payload["request_id"], str):
                    raise ValueError("Schema activation status request is invalid")
                return registry.activation_status(resolved_actor, payload["request_id"])
            if set(payload) != {"change", "expected_revision", "proposal_hash", "request_id"}:
                raise ValueError("Schema confirmation payload is invalid")
            if (
                not isinstance(payload["change"], dict)
                or not isinstance(payload["expected_revision"], int)
                or isinstance(payload["expected_revision"], bool)
                or not isinstance(payload["proposal_hash"], str)
                or not isinstance(payload["request_id"], str)
            ):
                raise ValueError("Schema confirmation payload is invalid")
            return registry.request_activation(
                payload["change"],
                SchemaConfirmation(
                    actor_id=resolved_actor,
                    request_id=payload["request_id"],
                    expected_revision=payload["expected_revision"],
                    proposal_hash=payload["proposal_hash"],
                ),
            )
        if operation == "schema_review":
            if (
                (authenticated_actor is None and external_principal is None)
                or self.user_schema_registry is None
                or self.schema_suggestion_service is None
            ):
                raise ValueError("Final schema review is unavailable")
            if set(payload) != {"message", "change", "expected_revision", "proposal_hash"}:
                raise ValueError("Final schema review payload is invalid")
            from .schema_suggestion import SchemaSuggestionService, review_schema_change
            from .user_schema_registry import UserSchemaRegistry

            if not isinstance(
                self.schema_suggestion_service, SchemaSuggestionService
            ) or not isinstance(self.user_schema_registry, UserSchemaRegistry):
                raise ValueError("Final schema review service is invalid")
            return review_schema_change(
                self.schema_suggestion_service,
                source=payload["message"],
                change=payload["change"],
                expected_revision=payload["expected_revision"],
                proposal_hash=payload["proposal_hash"],
                registry=self.user_schema_registry,
            )
        if operation == "schema_suggest":
            if (
                (authenticated_actor is None and external_principal is None)
                or self.user_schema_registry is None
                or self.schema_suggestion_service is None
            ):
                raise ValueError("Conversational schema assistant is unavailable")
            if set(payload) != {"message", "expected_revision"}:
                raise ValueError("Schema conversation payload is invalid")
            from .schema_suggestion import SchemaSuggestionService
            from .user_schema_registry import UserSchemaRegistry

            if (
                not isinstance(self.schema_suggestion_service, SchemaSuggestionService)
                or not isinstance(self.user_schema_registry, UserSchemaRegistry)
                or not isinstance(payload["message"], str)
            ):
                raise ValueError("Schema conversation service is invalid")
            return self.schema_suggestion_service.suggest(
                payload["message"],
                self.user_schema_registry,
                expected_revision=payload["expected_revision"],
            )
        if operation == "schema_preview":
            # The runtime's ordinary fallback `odyssey-runtime` is not an
            # authenticated user. Previewing schema changes requires one
            # validated principal even though this operation is read-only.
            if authenticated_actor is None and external_principal is None:
                raise ValueError("Schema preview requires authenticated actor")
            if self.user_schema_registry is None:
                raise ValueError("User schema preview is disabled")
            if set(payload) != {"change", "expected_revision"}:
                raise ValueError("Schema preview payload is invalid")
            expected_revision = payload["expected_revision"]
            change = payload["change"]
            if (
                not isinstance(expected_revision, int)
                or isinstance(expected_revision, bool)
                or expected_revision < 0
                or not isinstance(change, dict)
            ):
                raise ValueError("Schema preview payload is invalid")
            from .user_schema_registry import UserSchemaRegistry

            if not isinstance(self.user_schema_registry, UserSchemaRegistry):
                raise ValueError("Schema registry is unavailable")
            proposal = self.user_schema_registry.preview(
                change, expected_revision=expected_revision
            )
            kind = next(
                item
                for item in proposal.effective_schema["types"]
                if item["id"] == proposal.affected_type_id
            )
            return {
                "revision": proposal.revision,
                "next_revision": proposal.next_revision,
                "proposal_hash": proposal.proposal_hash,
                "operation": proposal.operation,
                "affected_type_id": proposal.affected_type_id,
                "type_preview": kind,
            }
        if operation == "capabilities":
            if payload:
                raise ValueError("Notes capabilities payload is invalid")
            return _notes_to_response(self.notes_service.capabilities())
        if operation == "query":
            return _notes_to_response(
                self.notes_service.query(
                    mode=str(payload.get("mode", "feed")),
                    query=str(payload.get("query", "")),
                    filters=payload.get("filters", ()),
                    sort=str(payload.get("sort", "relevance")),
                    page_size=payload.get("page_size", 20),
                    cursor=payload.get("cursor"),
                    snapshot_ids=payload.get("snapshot_ids", ()),
                    as_of=payload.get("as_of"),
                    embedder=self.notes_embedder if payload.get("mode") == "intelligent" else None,
                )
            )
        if operation == "detail":
            if set(payload) != {"note_id"} or not isinstance(payload["note_id"], str):
                raise ValueError("Notes detail payload is invalid")
            detail = self.notes_service.detail(payload["note_id"])
            response = _notes_to_response(detail)
            if detail.note.type == TASK_TYPE and self.work_session_service is not None:
                response["work_sessions"] = [
                    _work_session_to_response(item)
                    for item in self.work_session_service.list_for_task(detail.note.id)
                ]
            return response
        if operation == "backlinks":
            allowed = {"note_id", "page_size", "cursor"}
            if set(payload) - allowed or not isinstance(payload.get("note_id"), str):
                raise ValueError("Notes backlinks payload is invalid")
            return _notes_to_response(
                self.notes_service.backlinks(
                    payload["note_id"],
                    page_size=payload.get("page_size", 20),
                    cursor=payload.get("cursor"),
                )
            )
        if operation in {
            "work_session_start",
            "work_session_stop",
            "work_session_edit",
            "work_session_delete",
            "work_session_activity_add",
            "work_session_activity_edit",
            "work_session_activity_delete",
        }:
            if self.work_session_service is None or self.notes_mutation_actor is None:
                raise ValueError("Work Session service is unavailable")
            request_id = payload.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("Work Session request ID is invalid")
            replay = self._load_notes_mutation_replay(
                resolved_actor, operation, payload, request_id
            )
            if replay is not None:
                return replay
            actor = self.notes_mutation_actor(authenticated_actor, external_principal)
            now = _current_time()["timestamp"]
            with self._execute_lock:
                if operation == "work_session_start":
                    if set(payload) != {
                        "note_id",
                        "expected_revision",
                        "expected_source_hash",
                        "request_id",
                    } or not isinstance(payload.get("note_id"), str):
                        raise ValueError("Work Session start payload is invalid")
                    result = self.work_session_service.start(
                        task_id=payload["note_id"],
                        started_at=now,
                        expected_task_revision=cast(int, payload.get("expected_revision")),
                        expected_task_source_hash=cast(str, payload.get("expected_source_hash")),
                        request_id=request_id,
                        actor=actor,
                        now=now,
                    )
                elif operation == "work_session_stop":
                    if set(payload) != {
                        "session_id",
                        "expected_revision",
                        "expected_source_hash",
                        "request_id",
                    } or not isinstance(payload.get("session_id"), str):
                        raise ValueError("Work Session stop payload is invalid")
                    result = self.work_session_service.stop(
                        session_id=payload["session_id"],
                        ended_at=now,
                        expected_revision=cast(int, payload.get("expected_revision")),
                        expected_source_hash=cast(str, payload.get("expected_source_hash")),
                        request_id=request_id,
                        actor=actor,
                        now=now,
                    )
                elif operation == "work_session_delete":
                    if set(payload) != {
                        "session_id",
                        "expected_revision",
                        "expected_source_hash",
                        "request_id",
                    } or not isinstance(payload.get("session_id"), str):
                        raise ValueError("Work Session deletion payload is invalid")
                    result = self.work_session_service.delete(
                        session_id=payload["session_id"],
                        expected_revision=cast(int, payload.get("expected_revision")),
                        expected_source_hash=cast(str, payload.get("expected_source_hash")),
                        request_id=request_id,
                        actor=actor,
                        now=now,
                    )
                elif operation == "work_session_edit":
                    if (
                        set(payload)
                        != {
                            "session_id",
                            "started_at",
                            "ended_at",
                            "expected_revision",
                            "expected_source_hash",
                            "request_id",
                        }
                        or not isinstance(payload.get("session_id"), str)
                        or not isinstance(payload.get("started_at"), str)
                        or (
                            payload.get("ended_at") is not None
                            and not isinstance(payload.get("ended_at"), str)
                        )
                    ):
                        raise ValueError("Work Session edit payload is invalid")
                    result = self.work_session_service.edit(
                        session_id=payload["session_id"],
                        started_at=payload["started_at"],
                        ended_at=cast(str | None, payload.get("ended_at")),
                        expected_revision=cast(int, payload.get("expected_revision")),
                        expected_source_hash=cast(str, payload.get("expected_source_hash")),
                        request_id=request_id,
                        actor=actor,
                        now=now,
                    )
                elif operation == "work_session_activity_add":
                    if (
                        set(payload)
                        != {
                            "session_id",
                            "text",
                            "expected_revision",
                            "expected_source_hash",
                            "request_id",
                        }
                        or not isinstance(payload.get("session_id"), str)
                        or not isinstance(payload.get("text"), str)
                    ):
                        raise ValueError("Work Session activity payload is invalid")
                    result = self.work_session_service.add_activity(
                        session_id=payload["session_id"],
                        text=payload["text"],
                        expected_revision=cast(int, payload.get("expected_revision")),
                        expected_source_hash=cast(str, payload.get("expected_source_hash")),
                        request_id=request_id,
                        actor=actor,
                        now=now,
                    )
                elif operation == "work_session_activity_edit":
                    if (
                        set(payload)
                        != {
                            "session_id",
                            "activity_id",
                            "text",
                            "expected_revision",
                            "expected_source_hash",
                            "request_id",
                        }
                        or not isinstance(payload.get("session_id"), str)
                        or not isinstance(payload.get("activity_id"), str)
                        or not isinstance(payload.get("text"), str)
                    ):
                        raise ValueError("Work Session activity edit payload is invalid")
                    result = self.work_session_service.edit_activity(
                        session_id=payload["session_id"],
                        activity_id=payload["activity_id"],
                        text=payload["text"],
                        expected_revision=cast(int, payload.get("expected_revision")),
                        expected_source_hash=cast(str, payload.get("expected_source_hash")),
                        request_id=request_id,
                        actor=actor,
                        now=now,
                    )
                else:
                    if (
                        set(payload)
                        != {
                            "session_id",
                            "activity_id",
                            "expected_revision",
                            "expected_source_hash",
                            "request_id",
                        }
                        or not isinstance(payload.get("session_id"), str)
                        or not isinstance(payload.get("activity_id"), str)
                    ):
                        raise ValueError("Work Session activity deletion payload is invalid")
                    result = self.work_session_service.delete_activity(
                        session_id=payload["session_id"],
                        activity_id=payload["activity_id"],
                        expected_revision=cast(int, payload.get("expected_revision")),
                        expected_source_hash=cast(str, payload.get("expected_source_hash")),
                        request_id=request_id,
                        actor=actor,
                        now=now,
                    )
            # Session list projection is AFTER the canonical mutation. A
            # broken optional read must preserve the physically written ID.
            try:
                work_sessions = [
                    _work_session_to_response(item)
                    for item in self.work_session_service.list_for_task(result.task_id)
                ]
                projection_failed = False
            except Exception:
                work_sessions = []
                projection_failed = True
            response = {
                "kind": "mutation",
                "operation": result.operation,
                "note_id": result.task_id,
                "history": {"status": result.history.status.value},
                "work_sessions": work_sessions,
            }
            if projection_failed:
                response["partial"] = {
                    "physical_write": True,
                    "reason": "POSTWRITE_PROJECTION_UNAVAILABLE",
                }
            return self._save_notes_mutation_replay(
                resolved_actor, operation, payload, request_id, response
            )
        if operation in {"delete_fact", "delete_note", "task_status", "task_subtask_create"}:
            if self.direct_notes_mutations is None or self.notes_mutation_actor is None:
                raise ValueError("Notes mutation service is unavailable")
            if self.await_index_refresh is not None:
                self.await_index_refresh()
            request_id = payload.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("Notes mutation request ID is invalid")
            replay = self._load_notes_mutation_replay(
                resolved_actor, operation, payload, request_id
            )
            if replay is not None:
                return replay
            common = {
                "note_id": payload.get("note_id"),
                "expected_revision": payload.get("expected_revision"),
                "expected_source_hash": payload.get("expected_source_hash"),
                "request_id": request_id,
                "actor": self.notes_mutation_actor(authenticated_actor, external_principal),
                "now": _current_time()["timestamp"],
            }
            with self._execute_lock:
                try:
                    if operation == "delete_fact":
                        if set(payload) != {
                            "note_id",
                            "fact_locator",
                            "expected_revision",
                            "expected_source_hash",
                            "request_id",
                        } or not isinstance(payload.get("fact_locator"), str):
                            raise ValueError("Notes fact deletion payload is invalid")
                        result = self.direct_notes_mutations.delete_fact(
                            **common, fact_locator=payload["fact_locator"]
                        )
                    elif operation == "delete_note":
                        if set(payload) != {
                            "note_id",
                            "expected_revision",
                            "expected_source_hash",
                            "request_id",
                        }:
                            raise ValueError("Notes deletion payload is invalid")
                        if self.work_session_service is not None:
                            detail = self.notes_service.detail(cast(str, payload.get("note_id")))
                            if (
                                detail.note.type == TASK_TYPE
                                and self.work_session_service.list_for_task(detail.note.id)
                            ):
                                raise WorkSessionError("WORK_SESSION_HISTORY_PRESENT")
                        result = self.direct_notes_mutations.delete_note(**common)
                    elif operation == "task_status":
                        if self.direct_task_mutations is None:
                            raise ValueError("Task mutation service is unavailable")
                        if set(payload) != {
                            "note_id",
                            "completed",
                            "expected_revision",
                            "expected_source_hash",
                            "request_id",
                        } or not isinstance(payload.get("completed"), bool):
                            raise ValueError("Task status payload is invalid")
                        result = self.direct_task_mutations.set_completed(
                            **common, completed=payload["completed"]
                        )
                    else:
                        if self.direct_task_mutations is None:
                            raise ValueError("Task mutation service is unavailable")
                        if (
                            set(payload)
                            != {
                                "parent_note_id",
                                "title",
                                "expected_revision",
                                "expected_source_hash",
                                "request_id",
                            }
                            or not isinstance(payload.get("parent_note_id"), str)
                            or not isinstance(payload.get("title"), str)
                        ):
                            raise ValueError("Task subtask creation payload is invalid")
                        result = self.direct_task_mutations.create_subtask(
                            parent_note_id=payload["parent_note_id"],
                            title=payload["title"],
                            expected_revision=cast(int, payload["expected_revision"]),
                            expected_source_hash=cast(str, payload["expected_source_hash"]),
                            request_id=request_id,
                            actor=common["actor"],
                            now=cast(str, common["now"]),
                        )
                except (DirectNoteMutationError, TaskDirectMutationError, WorkSessionError):
                    raise
                index_refresh_failed = False
                try:
                    if self.schedule_index_refresh is not None:
                        self.schedule_index_refresh((result.note_id,))
                    elif (
                        operation == "task_status"
                        and self.refresh_task_lifecycle_indexes is not None
                    ):
                        try:
                            self.refresh_task_lifecycle_indexes(
                                result.path, cast(str, payload["expected_source_hash"])
                            )
                        except (ContextIndexError, SemanticIndexError, ValueError):
                            self.refresh_indexes()
                    elif self.refresh_affected_indexes is not None:
                        self.refresh_affected_indexes((result.note_id,))
                    else:
                        self.refresh_indexes()
                except Exception:
                    # The original Core receipt remains valid; the index is
                    # rebuildable and must never make a real WRITE vanish.
                    index_refresh_failed = True
            response = {
                "kind": "mutation",
                "operation": result.operation,
                "note_id": result.note_id,
                "history": {"status": result.history.status.value},
            }
            if operation == "task_status":
                response.update(
                    {
                        "mutation": {
                            "revision": result.revision,
                            "source_hash": result.source_hash,
                        },
                        "status": result.status,
                        "completed_at": result.completed_at,
                    }
                )
            elif operation == "task_subtask_create":
                response.update(
                    {
                        "child": {
                            "id": result.note_id,
                            "name": result.name,
                            "status": result.status,
                        }
                    }
                )
            if index_refresh_failed:
                response["partial"] = {
                    "physical_write": True,
                    "reason": "INDEX_REFRESH_UNAVAILABLE",
                }
            return self._save_notes_mutation_replay(
                resolved_actor, operation, payload, request_id, response
            )
        if operation == "intelligent":
            if (
                self.intelligent_notes_execute is None
                or set(payload) - {"query", "filters", "page_size", "cursor", "sort"}
                or not isinstance(payload.get("query"), str)
                or not isinstance(payload.get("filters", ()), list)
            ):
                raise NotesQueryError("Intelligent Notes planning is unavailable")
            if payload.get("cursor") is not None:
                raise NotesQueryError("Intelligent Notes pages do not re-plan")
            execution = self.intelligent_notes_execute(payload["query"], payload.get("filters", ()))
            if isinstance(execution, tuple):
                page, operational = execution
                return {
                    **_notes_to_response(page),
                    "operational": operational_to_response(operational),
                }
            return _notes_to_response(execution)
        raise ValueError("Notes operation is unsupported")

    def calendar(
        self,
        operation: str,
        payload: dict[str, object],
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Execute one deterministic Calendar projection for the authenticated actor boundary."""
        self._resolve_actor(authenticated_actor, external_principal)
        if self.calendar_application is None:
            raise ValueError("Calendar application is unavailable")
        return self.calendar_application.query(operation, payload)

    def execute(
        self,
        user_request: str,
        request_id: str | None = None,
        conversation_id: str | None = None,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
        *,
        resume_plan: RequestPlan | None = None,
        clarification_choice: ClarificationChoice | None = None,
        original_request: str | None = None,
    ) -> ApplicationResult:
        """Execute one request and refresh derived indexes after affected mutations.

        Args:
            user_request: Raw request accepted by the Core application boundary.
            request_id: Optional identity supplied by the delivery boundary and reused by retries.

        Returns:
            The typed Core ApplicationResult after any required derived-index refresh.
        """
        if authenticated_actor is not None and external_principal is not None:
            raise ValueError("authenticated actor and external principal are mutually exclusive")
        if external_principal is not None:
            if self.identity_mapping_repository is None:
                raise ValueError("external principal mapping is unavailable")
            authenticated_actor = self.identity_mapping_repository.resolve_existing(
                external_principal
            )
            authenticated_actor = AuthenticatedActorContext(authenticated_actor.stable_user_id)
        if conversation_id is not None and self.conversation_root_resolver is None:
            raise ValueError("conversation root resolver is unavailable")
        if conversation_id is not None:
            resolved_actor = (
                authenticated_actor.stable_user_id
                if authenticated_actor is not None
                else "odyssey-runtime"
            )
            request_id = request_id or allocate_request_id()
            if conversation_id != MAIN_CONVERSATION_ID:
                raise ValueError("only the main conversation is available")
            with self._conversation_lock:
                self._conversation_store(resolved_actor).append_turn(
                    request_id=request_id,
                    role="user",
                    text=user_request,
                    created_at=_current_time()["timestamp"],
                )
        elif self.application_router is not None:
            request_id = request_id or allocate_request_id()
        started = self.monotonic()
        pre_stages: list[OperationalStage] = []
        if self.await_index_refresh is not None:
            barrier_started = self.monotonic()
            self.await_index_refresh()
            pre_stages.append(
                OperationalStage(
                    "index_barrier",
                    OperationalOutcome.COMPLETED,
                    max(0.0, (self.monotonic() - barrier_started) * 1000),
                    start_offset_ms=max(0.0, (barrier_started - started) * 1000),
                )
            )
        core_started = self.monotonic()
        if resume_plan is not None:
            if original_request is None or clarification_choice is None:
                raise ValueError("clarification continuation is incomplete")
            result = self.core_execute(
                original_request,
                request_id,
                authenticated_actor,
                conversation_id,
                resume_plan,
                clarification_choice,
            )
        elif self.hybrid_candidate_execute is not None:
            if request_id is None:  # Defensive narrowing for the durable route locator.
                raise ValueError("hybrid candidate execution requires an outer request ID")
            if authenticated_actor is None or conversation_id is None:
                result = ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    clarification_code="HYBRID_AUTHENTICATED_CONVERSATION_REQUIRED",
                )
            else:
                read_result = (
                    self.hybrid_read_execute(
                        user_request, request_id, authenticated_actor, conversation_id
                    )
                    if self.hybrid_read_execute is not None
                    else None
                )
                result = read_result or self.hybrid_candidate_execute(
                    user_request, request_id, authenticated_actor, conversation_id
                )
        elif self.application_router is not None:
            if request_id is None:  # Kept explicit for type narrowing and defensive clarity.
                raise ValueError("routed execution requires an outer request ID")
            result = execute_routed_request(
                user_request=user_request,
                outer_request_id=request_id,
                router=self.application_router,
                catalog=self.application_catalog,
                core_execute=self.core_execute,
                application_executors=self.application_executors,
                temporal_execute=self.temporal_executor,
                route_preparers=self.route_preparers,
                authenticated_actor=authenticated_actor,
                conversation_context=self._routing_conversation_context(
                    authenticated_actor, conversation_id, request_id
                ),
                progress_callback=_emit_progress,
            )
        elif conversation_id is None:
            if authenticated_actor is None:
                result = self.core_execute(user_request, request_id)
            else:
                result = self.core_execute(user_request, request_id, authenticated_actor)
        elif authenticated_actor is None:
            result = self.core_execute(user_request, request_id, None, conversation_id)
        else:
            result = self.core_execute(
                user_request, request_id, authenticated_actor, conversation_id
            )
        core_offset_ms = max(0.0, (core_started - started) * 1000)
        stages = [
            *pre_stages,
            *[
                replace(
                    stage,
                    start_offset_ms=(
                        stage.start_offset_ms + core_offset_ms
                        if stage.start_offset_ms is not None
                        else None
                    ),
                )
                for stage in result.operational.stages
            ],
        ]
        if result.affected_stable_note_ids:
            refresh_started = self.monotonic()
            try:
                if self.schedule_index_refresh is not None:
                    self.schedule_index_refresh(result.affected_stable_note_ids)
                    stage_name = "index_refresh.schedule"
                else:
                    if self.refresh_affected_indexes is not None:
                        self.refresh_affected_indexes(result.affected_stable_note_ids)
                    else:
                        self.refresh_indexes()
                    stage_name = "index_refresh"
            except Exception as error:
                stages.append(
                    OperationalStage(
                        "index_refresh.schedule"
                        if self.schedule_index_refresh is not None
                        else "index_refresh",
                        OperationalOutcome.FAILED,
                        max(0.0, (self.monotonic() - refresh_started) * 1000),
                        error_category=type(error).__name__,
                        start_offset_ms=max(0.0, (refresh_started - started) * 1000),
                    )
                )
                failed = cast(
                    ApplicationResult,
                    replace(
                        result,
                        operational=replace(
                            result.operational,
                            total_duration_ms=max(0.0, (self.monotonic() - started) * 1000),
                            stages=tuple(stages),
                        ),
                    ),
                )
                return self._attach_note_result_snapshot(failed)
            stages.append(
                OperationalStage(
                    stage_name,
                    OperationalOutcome.COMPLETED,
                    max(0.0, (self.monotonic() - refresh_started) * 1000),
                    start_offset_ms=max(0.0, (refresh_started - started) * 1000),
                )
            )
        result = self._attach_note_result_snapshot(result)
        return cast(
            ApplicationResult,
            replace(
                result,
                operational=replace(
                    result.operational,
                    total_duration_ms=max(0.0, (self.monotonic() - started) * 1000),
                    stages=tuple(stages),
                ),
            ),
        )

    def _routing_conversation_context(
        self,
        authenticated_actor: AuthenticatedActorContext | None,
        conversation_id: str | None,
        request_id: str,
    ) -> Sequence[Mapping[str, str]]:
        """Return bounded prior turns for routing while excluding the just-appended outer message."""
        if conversation_id is None:
            return ()
        actor = (
            authenticated_actor.stable_user_id
            if authenticated_actor is not None
            else "odyssey-runtime"
        )
        with self._conversation_lock:
            return self._conversation_store(actor).recent_context(exclude_request_id=request_id)

    def _attach_note_result_snapshot(self, result: ApplicationResult) -> ApplicationResult:
        """Build bounded durable membership from Core-authorized search or mutation evidence.

        Mutation membership comes directly from the Core application result and must never be
        re-searched. A note-set plan remains delegated to the Notes service so this adapter does
        not recreate filtering or ranking at the request, workflow, or browser boundary.
        """
        if result.affected_stable_note_ids:
            try:
                snapshot = affected_notes_snapshot(
                    result.affected_stable_note_ids, _current_time()["timestamp"]
                )
            except ValueError:
                return result
            return replace(result, note_result_snapshot=snapshot.to_payload())
        if (
            result.presentation_intent == "answer"
            or result.note_set_selection is None
            or self.notes_service is None
            or self.notes_embedder is None
        ):
            return result
        selection = result.note_set_selection
        try:
            page = self._note_set_page(selection)
            snapshot = NoteResultSnapshot(
                query=selection.query,
                filters=tuple(
                    {"field": item.field, "op": item.op, "value": item.value}
                    for item in [*selection.filters, *self._type_filter(selection)]
                ),
                sort=page.sort,
                ranking_version=page.ranking_version,
                executed_at=page.as_of,
                note_ids=tuple(item.id for item in page.items),
                total=page.total,
                truncated=page.total > len(page.items),
            )
        except (NotesQueryError, ValueError):
            # A malformed or stale derived projection must never become result-set authority.
            # The normal Core action evidence remains available, but no affordance is emitted.
            return result
        return replace(result, note_result_snapshot=snapshot.to_payload())

    def _note_set_page(self, selection: SelectionCriteria) -> NotePage:
        """Return up to the snapshot bound using the single canonical Notes query service."""
        assert self.notes_service is not None
        filters = [*selection.filters, *self._type_filter(selection)]
        first = self.notes_service.query(
            mode="intelligent",
            query=selection.query,
            filters=filters,
            sort="relevance",
            page_size=40,
            embedder=cast(object, self.notes_embedder),
        )
        if first.total <= len(first.items) or first.next_cursor is None:
            return first
        second = self.notes_service.query(
            mode="intelligent",
            query=selection.query,
            filters=filters,
            sort="relevance",
            page_size=24,
            cursor=first.next_cursor,
            embedder=cast(object, self.notes_embedder),
        )
        return replace(first, items=first.items + second.items, next_cursor=second.next_cursor)

    @staticmethod
    def _type_filter(selection: SelectionCriteria) -> tuple[ContextFilter, ...]:
        """Project the planner's canonical type criterion into the shared filter contract."""
        if selection.type is None:
            return ()
        return (ContextFilter("type", "eq", selection.type),)

    def create_conversation(
        self,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Create one durable conversation for the trusted actor at this boundary."""
        del authenticated_actor, external_principal
        raise ValueError("only the main conversation is available")

    def embedding_presence(
        self,
        session_id: str,
        state: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """DEV-only browser presence: schedule ONNX loading without delaying UI.

        This is a performance signal, never identity/knowledge evidence.
        """
        from odyssey_runtime.isolated_embeddings import IsolatedFastEmbedTextEmbedder

        if (
            os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
            or not isinstance(self.notes_embedder, IsolatedFastEmbedTextEmbedder)
            or (authenticated_actor is None and external_principal is None)
        ):
            raise ValueError("Embedding presence is unavailable")
        actor = self._resolve_actor(authenticated_actor, external_principal)
        self.notes_embedder.presence(actor, session_id, state)
        return {"ok": True}

    def main_conversation(
        self,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
        *,
        limit: int | None = None,
        before: str | None = None,
    ) -> dict[str, object]:
        """Return the one durable main conversation for the trusted actor."""
        actor = self._resolve_actor(authenticated_actor, external_principal)
        with self._conversation_lock:
            store = self._conversation_store(actor)
            store.load_or_create_main(now=_current_time()["timestamp"])
            return store.load_main_page(limit=40 if limit is None else limit, before=before)

    def list_conversations(
        self,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> list[dict[str, object]]:
        """List bounded durable conversations owned by the trusted actor."""
        del authenticated_actor, external_principal
        raise ValueError("conversation lists are unavailable")

    def load_conversation(
        self,
        conversation_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Load one actor-owned durable conversation for browser resume."""
        actor = self._resolve_actor(authenticated_actor, external_principal)
        if conversation_id != MAIN_CONVERSATION_ID:
            raise ValueError("only the main conversation is available")
        with self._conversation_lock:
            return self._conversation_store(actor).load_main_page()

    def persist_product_assistant_response(
        self,
        response: dict[str, object],
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Persist the EXACT n8n-rendered assistant text before HTTP response.

        The browser must no longer be the only component responsible for
        persisting a visible reply. Only an already persisted user delivery
        under the same authenticated actor and request_id can be answered.
        Core Markdown remains untouched; this stores transcript state only.
        """
        from odyssey_core.conversations import ConversationError

        if not isinstance(response, dict) or not set(response) <= {
            "request_id",
            "status",
            "kind",
            "message",
            "request_detail",
            "note_result_snapshot",
            "collection_members",
            "clarification",
        }:
            raise ConversationError("assistant product response is invalid")
        request_id = response.get("request_id")
        status = response.get("status")
        message = response.get("message")
        if (
            not isinstance(request_id, str)
            or not isinstance(status, str)
            or status not in {"completed", "partial", "needs_attention", "failed"}
            or response.get("kind")
            not in {
                "answer",
                "acknowledgement",
                "clarification",
                "cannot_answer",
                "empty",
                "error",
                "note_set",
            }
            or not isinstance(message, str)
            or not message.strip()
        ):
            raise ConversationError("assistant product response is invalid")
        actor = self._resolve_actor(authenticated_actor, external_principal)
        with self._conversation_lock:
            store = self._conversation_store(actor)
            store.load_or_create_main(now=_current_time()["timestamp"])
            if not store.has_turn(request_id, "user"):
                raise ConversationError("assistant without a matching user delivery")
            existing = store.find_turn(request_id, "assistant")
            if existing is not None:
                # The original n8n-rendered reply is already durable. Its
                # optional timings/detail may differ on E3 replay, but the
                # immutable visible content and status MUST match exactly.
                # Return the first persisted diagnostics/snapshot rather than
                # a fresh variant; never rewrite the original transcript.
                if existing["text"] != message or existing.get("status") != status:
                    raise ConversationError("request ID has a conflicting assistant result")
                return {
                    **{
                        key: value
                        for key, value in response.items()
                        if key not in ("request_detail", "note_result_snapshot")
                    },
                    **(
                        {"request_detail": existing["request_detail"]}
                        if "request_detail" in existing
                        else {}
                    ),
                    **(
                        {"note_result_snapshot": existing["note_result_snapshot"]}
                        if "note_result_snapshot" in existing
                        else {}
                    ),
                    "conversation_persisted": True,
                    "conversation_diagnostics_preserved": existing.get("request_detail")
                    is not None,
                }
            detail = response.get("request_detail")
            # The E2 execution ledger is a live, bounded transport diagnostic,
            # NOT part of the strict persisted transcript schema. Store the
            # canonical flow/stages unchanged, omitting only this known extra
            # field; unknown fields still fail closed in ConversationStore.
            durable_detail = (
                {key: value for key, value in detail.items() if key != "execution_ledger"}
                if isinstance(detail, dict)
                else detail
            )
            optional = {
                "request_detail": durable_detail,
                "note_result_snapshot": response.get("note_result_snapshot"),
            }
            try:
                store.append_turn(
                    request_id=request_id,
                    role="assistant",
                    text=message,
                    status=status,
                    created_at=_current_time()["timestamp"],
                    **optional,
                )
                diagnostics_preserved = True
            except ConversationError:
                # The original content must survive a diagnostic mismatch,
                # but a conflicting already-persisted response must still
                # fail; never overwrite an immutable turn.
                if store.has_turn(request_id, "assistant"):
                    raise
                store.append_turn(
                    request_id=request_id,
                    role="assistant",
                    text=message,
                    status=status,
                    created_at=_current_time()["timestamp"],
                )
                diagnostics_preserved = False
        return {
            **response,
            "conversation_persisted": True,
            "conversation_diagnostics_preserved": diagnostics_preserved,
        }

    def append_conversation_turn(
        self,
        conversation_id: str,
        request_id: str,
        role: str,
        text: str,
        status: str | None = None,
        request_detail: dict[str, object] | None = None,
        note_result_snapshot: dict[str, object] | None = None,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Persist one visible turn idempotently for the trusted actor."""
        actor = self._resolve_actor(authenticated_actor, external_principal)
        if conversation_id != MAIN_CONVERSATION_ID:
            raise ValueError("only the main conversation is available")
        with self._conversation_lock:
            return self._conversation_store(actor).append_turn(
                request_id=request_id,
                role=role,
                text=text,
                created_at=_current_time()["timestamp"],
                status=status,
                request_detail=request_detail,
                note_result_snapshot=note_result_snapshot,
            )

    def recent_conversation_context(
        self,
        conversation_id: str,
        request_id: str | None = None,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> list[dict[str, str]]:
        """Return the bounded recent main-conversation window for one planner pass."""
        actor = self._resolve_actor(authenticated_actor, external_principal)
        if conversation_id != MAIN_CONVERSATION_ID:
            raise ValueError("only the main conversation is available")
        with self._conversation_lock:
            return self._conversation_store(actor).recent_context(exclude_request_id=request_id)

    def _conversation_store(self, actor: str) -> LocalConversationStore:
        """Resolve a trusted actor before constructing its root-bound local store."""
        if self.conversation_root_resolver is None:
            raise ValueError("conversation root resolver is unavailable")
        return LocalConversationStore(self.conversation_root_resolver.resolve(actor))

    def _notes_mutation_result_store(
        self, actor: str
    ) -> tuple[LocalDeliveryResultStore, Path] | None:
        """Return actor-isolated replay state for direct Notes mutations.

        Lightweight/disposable compositions intentionally omit a conversation
        root resolver; those retain their existing functional behavior without
        pretending a durable replay guarantee exists.
        """
        if self.conversation_root_resolver is None:
            return None
        root = self.conversation_root_resolver.resolve(actor)
        return LocalDeliveryResultStore(root / "notes-mutation-results"), root

    def _load_notes_mutation_replay(
        self, actor: str, operation: str, payload: Mapping[str, object], request_id: str
    ) -> dict[str, object] | None:
        store_root = self._notes_mutation_result_store(actor)
        if store_root is None:
            return None
        store, root = store_root
        try:
            record = store.load(request_id, store.mutation_fingerprint(operation, payload, root))
        except DeliveryResultError as error:
            raise ValueError("Notes mutation replay is unavailable") from error
        if record is None:
            # Create a durable actor-local reservation BEFORE executing the
            # mutation. A crash after the Markdown write but before the final
            # result can no longer cause a blind second write.
            try:
                store.claim_mutation(
                    request_id, store.mutation_fingerprint(operation, payload, root)
                )
            except DeliveryResultError as error:
                raise ValueError("Notes mutation has an unresolved previous attempt") from error
            return None
        response = record.get("notes_response")
        if set(record) != {"request_id", "notes_response"} or not isinstance(response, dict):
            raise ValueError("Notes mutation replay is invalid")
        return dict(response)

    def _save_notes_mutation_replay(
        self,
        actor: str,
        operation: str,
        payload: Mapping[str, object],
        request_id: str,
        response: dict[str, object],
    ) -> dict[str, object]:
        store_root = self._notes_mutation_result_store(actor)
        if store_root is None:
            return response
        store, root = store_root
        try:
            store.save(
                request_id,
                store.mutation_fingerprint(operation, payload, root),
                {"request_id": request_id, "notes_response": response},
                _current_time()["timestamp"],
            )
            store.finish_mutation_claim(request_id)
        except (DeliveryResultError, OSError, ValueError, TypeError):
            # A physical mutation has already completed; the optional index
            # refresh may also have failed, but the Markdown write is known. Do
            # not flatten that fact into an apparent no-write error, and never
            # claim this response is replay-safe when its durable receipt failed.
            return {
                **response,
                "partial": {
                    "physical_write": True,
                    "reason": "MUTATION_REPLAY_RESULT_UNAVAILABLE",
                },
            }
        return response

    def _resolve_actor(
        self,
        authenticated_actor: AuthenticatedActorContext | None,
        external_principal: ExternalPrincipal | None,
    ) -> str:
        if authenticated_actor is not None and external_principal is not None:
            raise ValueError("authenticated actor and external principal are mutually exclusive")
        if external_principal is not None:
            if self.identity_mapping_repository is None:
                raise ValueError("external principal mapping is unavailable")
            authenticated_actor = self.identity_mapping_repository.resolve_existing(
                external_principal
            )
        return (
            authenticated_actor.stable_user_id
            if authenticated_actor is not None
            else "odyssey-runtime"
        )


_USER_SCHEMA_PROTECTED_ROOT = Path("/data/odyssey")


def build_runtime_from_environment() -> RuntimeComposition:
    """Build all schema consumers and derived indexes under one boot-time lease.

    The serving boundary then acquires a shared lease and checks revision.
    If a publisher wins the tiny gap after this factory returns, serve fails
    safely before exposing the stale runtime; neither can rebuild indexes
    against a live newer generation.
    """
    schema_enabled = os.environ.get("ODYSSEY_USER_SCHEMA_ENABLED", "0")
    if schema_enabled not in {"0", "1"}:
        raise ValueError("User schema registry flag is invalid")
    # A feature rejected for PROD or disabled user schemas must fail BEFORE
    # the legacy pending-root mkdir, registry lease or any filesystem touch.
    scan_enabled = os.environ.get("ODYSSEY_SCHEMA_SCAN_ENABLED", "0")
    if scan_enabled not in {"0", "1"}:
        raise ValueError("Local schema scan flag is invalid")
    if scan_enabled == "1" and (
        schema_enabled != "1" or os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
    ):
        raise ValueError("Local schema scan requires isolated DEV user registry")
    # Private writes are independent of scan previews; never enable through
    # a read-only scan flag or a user-supplied browser field.
    backfill_enabled = os.environ.get("ODYSSEY_SCHEMA_BACKFILL_ENABLED", "0")
    if backfill_enabled not in {"0", "1"}:
        raise ValueError("Local schema backfill flag is invalid")
    if backfill_enabled == "1" and (
        schema_enabled != "1"
        or scan_enabled != "1"
        or os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
        or os.environ.get("ODYSSEY_SCHEMA_CONFIRM_ENABLED") != "1"
    ):
        raise ValueError("Local schema backfill requires explicitly confirmed isolated DEV")
    if backfill_enabled == "1" and _path_env(
        "ODYSSEY_VAULT_ROOT", "/data/odyssey/vault"
    ).resolve().is_relative_to(_USER_SCHEMA_PROTECTED_ROOT):
        raise ValueError("Local schema backfill cannot target protected PROD storage")
    semantic_enabled = os.environ.get("ODYSSEY_SCHEMA_SEMANTIC_BACKFILL_ENABLED", "0")
    if semantic_enabled not in {"0", "1"}:
        raise ValueError("Semantic schema backfill flag is invalid")
    if semantic_enabled == "1" and (
        backfill_enabled != "1" or os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
    ):
        raise ValueError("Semantic schema backfill requires approved isolated DEV backfill")
    if semantic_enabled == "1" and not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Semantic schema backfill provider is unavailable")
    raw_call_limit = os.environ.get("ODYSSEY_SCHEMA_SEMANTIC_CALL_LIMIT", "")
    if semantic_enabled == "1" and (
        not raw_call_limit.isascii()
        or not raw_call_limit.isdecimal()
        or not 1 <= int(raw_call_limit) <= 36
    ):
        raise ValueError("Semantic schema backfill requires a bounded host call allowance")
    # Reject an accidental PROD assistant request *before* touching roots.
    suggestion_enabled = os.environ.get("ODYSSEY_SCHEMA_ASSISTANT_ENABLED", "0")
    if suggestion_enabled not in {"0", "1"}:
        raise ValueError("Schema assistant flag is invalid")
    if suggestion_enabled == "1" and (
        schema_enabled != "1" or os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
    ):
        raise ValueError("Schema assistant requires isolated DEV user registry")
    if schema_enabled == "0":
        return _build_runtime_from_environment_unlocked()
    if os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV":
        raise ValueError("User schema registry is restricted to DEV until its E2E adoption")
    from .user_schema_registry import UserSchemaRegistry

    vault_root = _path_env("ODYSSEY_VAULT_ROOT", "/data/odyssey/vault")
    runtime_root = _path_env("ODYSSEY_RUNTIME_ROOT", "/data/odyssey/runtime")
    pending_root = _path_env("ODYSSEY_PENDING_ROOT", "/data/odyssey/state/pending")
    state_root = _path_env("ODYSSEY_STATE_ROOT", str(pending_root.parent))
    embedding_cache = _path_env(
        "ODYSSEY_EMBEDDING_CACHE", "/data/odyssey/runtime/phase11a-benchmark/embedding-cache"
    )
    # This preflight MUST precede mkdir/chmod/lease creation: a rejected DEV
    # experiment must never create files under PROD even on invalid settings.
    protected = _USER_SCHEMA_PROTECTED_ROOT.resolve()
    if any(
        path.resolve().is_relative_to(protected)
        for path in (vault_root, runtime_root, pending_root, state_root, embedding_cache)
    ):
        raise ValueError("DEV user schema cannot access production storage")
    if state_root.is_symlink():
        raise ValueError("User schema state root must not be a symlink")
    # Provider import and construction must fail BEFORE local state is touched.
    # The public Notes API cannot enable this adapter or supply a model.
    semantic_interpreter = None
    if semantic_enabled == "1":
        from .schema_backfill_interpreter import SemanticPropertyInterpreter

        semantic_interpreter = SemanticPropertyInterpreter(
            OpenAIConversationGateway.from_environment()
        )
    # Legacy composition creates the pending root later, but the schema lease
    # needs the state parent now on a first DEV boot.
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with UserSchemaRegistry.bootstrap_lease(state_root):
        kwargs = (
            {"schema_backfill_interpreter": semantic_interpreter}
            if semantic_interpreter is not None
            else {}
        )
        if semantic_interpreter is not None:
            kwargs["schema_backfill_call_limit"] = int(raw_call_limit)
        return _build_runtime_from_environment_unlocked(**kwargs)


def _build_runtime_from_environment_unlocked(
    *,
    schema_backfill_interpreter: object | None = None,
    schema_backfill_call_limit: int | None = None,
) -> RuntimeComposition:
    """Build the production Core composition from environment-owned configuration.

    Returns:
        A persistent-process composition that reuses the local embedder and derived indexes for
        every request while refreshing time-sensitive planner context per call.

    Raises:
        ValueError: If required runtime configuration is invalid.
        OSError: If configured directories or files are unavailable.
    """
    project_root = Path(__file__).resolve().parents[1]
    vault_root = _path_env("ODYSSEY_VAULT_ROOT", "/data/odyssey/vault")
    runtime_root = _path_env("ODYSSEY_RUNTIME_ROOT", "/data/odyssey/runtime")
    pending_root = _path_env("ODYSSEY_PENDING_ROOT", "/data/odyssey/state/pending")
    state_root = _path_env("ODYSSEY_STATE_ROOT", str(pending_root.parent))
    light_source_enabled = os.environ.get("ODYSSEY_LIGHT_SOURCE_V1") == "1"
    if light_source_enabled:
        protected = Path("/data/odyssey").resolve()
        if any(
            path.resolve().is_relative_to(protected)
            for path in (vault_root, runtime_root, pending_root, state_root)
        ):
            raise ValueError("Experimental full-source route cannot access PROD storage")
    pending_root.mkdir(parents=True, exist_ok=True)
    schema_path = _path_env("ODYSSEY_SCHEMA_PATH", str(project_root / "config/note-schema.json"))
    embedding_cache = _path_env(
        "ODYSSEY_EMBEDDING_CACHE",
        "/data/odyssey/runtime/phase11a-benchmark/embedding-cache",
    )
    if light_source_enabled and embedding_cache.resolve().is_relative_to(Path("/data/odyssey")):
        raise ValueError("Experimental full-source route cannot access PROD embedding cache")
    with schema_path.open("r", encoding="utf-8") as schema_file:
        base_schema = json.load(schema_file)
    application_schema_extensions = (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION)
    schema = compose_application_schema(base_schema, application_schema_extensions)
    user_schema_registry = None
    user_schema_revision = None
    schema_activation_enabled = False
    schema_suggestion_service = None
    schema_scan_factory = None
    schema_backfill_factory = None
    backfill_flag = os.environ.get("ODYSSEY_SCHEMA_BACKFILL_ENABLED", "0")
    if backfill_flag not in {"0", "1"}:
        raise ValueError("Local schema backfill flag is invalid")
    if backfill_flag == "1" and (
        os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
        or os.environ.get("ODYSSEY_USER_SCHEMA_ENABLED") != "1"
        or os.environ.get("ODYSSEY_SCHEMA_SCAN_ENABLED") != "1"
        or os.environ.get("ODYSSEY_SCHEMA_CONFIRM_ENABLED") != "1"
    ):
        raise ValueError("Local schema backfill requires explicitly confirmed isolated DEV")
    if backfill_flag == "1" and vault_root.resolve().is_relative_to(_USER_SCHEMA_PROTECTED_ROOT):
        raise ValueError("Local schema backfill cannot target protected PROD storage")
    scan_flag = os.environ.get("ODYSSEY_SCHEMA_SCAN_ENABLED", "0")
    if scan_flag not in {"0", "1"}:
        raise ValueError("Local schema scan flag is invalid")
    if scan_flag == "1" and (
        os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
        or os.environ.get("ODYSSEY_USER_SCHEMA_ENABLED") != "1"
    ):
        raise ValueError("Local schema scan requires isolated DEV user registry")
    suggestion_flag = os.environ.get("ODYSSEY_SCHEMA_ASSISTANT_ENABLED", "0")
    if suggestion_flag not in {"0", "1"}:
        raise ValueError("Schema assistant feature flag is invalid")
    user_schema_flag = os.environ.get("ODYSSEY_USER_SCHEMA_ENABLED", "0")
    if suggestion_flag == "1" and (
        user_schema_flag != "1" or os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV"
    ):
        raise ValueError("Schema assistant requires isolated DEV user registry")
    if user_schema_flag not in {"0", "1"}:
        raise ValueError("User schema registry flag is invalid")
    if user_schema_flag == "1":
        if os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV":
            raise ValueError("User schema registry is restricted to DEV until its E2E adoption")
        from odyssey_runtime.user_schema_registry import UserSchemaRegistry

        user_schema_registry = UserSchemaRegistry(
            state_root, base_schema, application_schema_extensions
        )
        # The caller holds the exclusive bootstrap generation lease before
        # any shared indexes are read/written. Recovery also handles a process
        # failure after the browser's approval was durably accepted.
        user_schema_registry.activate_pending_at_boot()
        user_schema_revision, schema = user_schema_registry.snapshot()
        confirmation_flag = os.environ.get("ODYSSEY_SCHEMA_CONFIRM_ENABLED", "0")
        if confirmation_flag not in {"0", "1"}:
            raise ValueError("Schema confirmation flag is invalid")
        schema_activation_enabled = confirmation_flag == "1"
        if suggestion_flag == "1":
            from .schema_suggestion import SchemaSuggestionService

            schema_suggestion_service = SchemaSuggestionService(
                OpenAIConversationGateway.from_environment()
            )
    # Runtime keeps this per-boot validated snapshot. An authenticated, atomic
    # UI publication/hot-reload boundary is deliberately NOT available yet.

    repository = VaultRepository(vault_root)
    if scan_flag == "1":
        from odyssey_core.schema_retrospection_jobs import LocalSchemaScanJobs

        def schema_scan_factory(actor_id: str) -> LocalSchemaScanJobs:
            return LocalSchemaScanJobs(
                state_root=state_root, repository=repository, actor_id=actor_id
            )

    if backfill_flag == "1":
        if vault_root.resolve().is_relative_to(_USER_SCHEMA_PROTECTED_ROOT):
            raise ValueError("Local schema backfill cannot touch PROD storage")
        from odyssey_core.schema_auto_backfill import AutomaticPropertyBackfill

        from .schema_backfill_jobs import LocalBackfillJob

        deterministic_writer = AutomaticPropertyBackfill(
            repository=repository, schema=schema, history=GitHistoryRecorder(vault_root)
        )

        def schema_backfill_factory(actor_id: str) -> LocalBackfillJob:
            return LocalBackfillJob(
                state_root=state_root,
                repository=repository,
                writer=deterministic_writer,
                actor_id=actor_id,
                on_updated=lambda note_id: index_refresh_coordinator.schedule_backfill((note_id,)),
            )

    if os.environ.get("ODYSSEY_EMBEDDING_SUBPROCESS") == "1":
        if os.environ.get("ODYSSEY_DEPLOYMENT_ENV") != "DEV" or not light_source_enabled:
            raise ValueError("Isolated embedding experiment requires DEV light source")
        from odyssey_runtime.isolated_embeddings import IsolatedFastEmbedTextEmbedder

        embedder = IsolatedFastEmbedTextEmbedder(
            cache_dir=embedding_cache,
            idle_seconds=float(os.environ.get("ODYSSEY_EMBEDDING_IDLE_SECONDS", "900")),
        )
    else:
        embedder = FastEmbedTextEmbedder(cache_dir=embedding_cache, local_files_only=True)
    context_index = ContextIndex(runtime_root / "context.sqlite3")
    semantic_index = SemanticEntityIndex(runtime_root / "semantic.sqlite3")
    application_semantic_indexes = {
        extension.capability_id: SemanticEntityIndex(
            runtime_root / f"semantic-{extension.capability_id}.sqlite3"
        )
        for extension in application_schema_extensions
    }
    contextual_reasoner = _build_contextual_reasoner()
    writer = OpenAILunaWriter()
    fact_selector = OpenAILunaFactSelector()
    semantic_set_selector = OpenAILunaSemanticSetSelector()
    pending_recorder = PendingWorkRepository(pending_root)
    conversation_root_resolver = ConversationRootResolver(state_root)
    self_binding_repository = (
        SelfBindingRepository(state_root, repository, schema)
        if isinstance(repository, _VAULT_REPOSITORY_TYPE)
        else None
    )
    identity_mapping_repository = IdentityMappingRepository(state_root)
    history_recorder = GitHistoryRecorder(vault_root)
    actor = os.environ.get("ODYSSEY_ACTOR", "odyssey-runtime")
    context_limit = _positive_int_env("ODYSSEY_CONTEXT_LIMIT", 10)
    hybrid_dev_enabled = _hybrid_dev_enabled()
    hybrid_source_review_enabled = _hybrid_source_review_enabled(hybrid_dev_enabled)

    @dataclass(frozen=True)
    class _PrecomputedCorePlan:
        """Validated model output bound to one source, domain and explicit clock."""

        source: str
        clock: dict[str, str]
        domain: DomainInterpretation | None
        planner: Any

    class _PreparedPlanner:
        """Replay exactly one prior model decision through ordinary serial Core authority.

        This local wrapper does not authorize writes; execute_request remains the
        only executor, using its normal fresh identity, preflight and Git guards.
        """

        is_local_replay = True

        def __init__(
            self,
            source: str,
            result: Any,
            error: Exception | None,
            original: Any,
            duration_ms: float,
        ) -> None:
            self.source = source
            self.result = result
            self.error = error
            self.prepared_duration_ms = duration_ms
            for name in (
                "last_provider_calls",
                "last_spans",
                "last_usage",
                "model",
                "reasoning_effort",
            ):
                setattr(self, name, getattr(original, name, None))

        def plan(self, source: str) -> Any:
            """Replay only a model-validated result for its exact requested span."""
            if source != self.source:
                raise ValueError("precomputed Core plan source changed")
            if self.error is not None:
                raise self.error
            return self.result

    def prepare_core_plan(
        source: str,
        clock: dict[str, str],
        prior: Sequence[Mapping[str, str]],
        domain: DomainInterpretation | None = None,
        decorator: Callable[[Any], Any] | None = None,
    ) -> _PrecomputedCorePlan:
        """Invoke only the shared Core model planner in a worker, never repositories."""
        context = {key: clock[key] for key in ("date", "time", "timezone")}
        planner = (
            OpenAIRequestPlanner.from_environment(schema, context)
            if domain is None
            else OpenAIRequestPlanner.from_environment(
                schema, context, domain_interpretation=domain
            )
        )
        if decorator is not None:
            planner = decorator(planner)
        start = perf_counter()
        output = None
        error: Exception | None = None
        try:
            output = planner.plan(source, prior) if prior else planner.plan(source)
        except Exception as exc:
            error = exc
        duration_ms = max(0.0, (perf_counter() - start) * 1000)
        return _PrecomputedCorePlan(
            source,
            clock,
            domain,
            _PreparedPlanner(source, output, error, planner, duration_ms),
        )

    def core_execute(
        user_request: str,
        request_id: str | None = None,
        authenticated_actor: AuthenticatedActorContext | None = None,
        conversation_id: str | None = None,
        resume_plan: RequestPlan | None = None,
        clarification_choice: ClarificationChoice | None = None,
        *,
        conversation_context_override: Sequence[Mapping[str, str]] | None = None,
        domain_interpretation: DomainInterpretation | None = None,
        planner_decorator: Callable[[Any], Any] | None = None,
        write_preflight_guard: WritePreflightGuard | None = None,
        prepared_core: _PrecomputedCorePlan | None = None,
        fixed_plan: RequestPlan | None = None,
        dependent_handoff: DependentRouteHandoff | None = None,
        dependent_handoffs: tuple[DependentRouteHandoff, ...] | None = None,
        captured_request_instant: datetime | None = None,
    ) -> ApplicationResult:
        """Execute Core with optional prior context and app-specialized interpretation evidence."""
        if dependent_handoffs is not None and (
            dependent_handoff is not None
            or not isinstance(dependent_handoffs, tuple)
            or not 2 <= len(dependent_handoffs) <= 8
            or any(not isinstance(x, DependentRouteHandoff) for x in dependent_handoffs)
            or len({x.evidence.stable_note_id for x in dependent_handoffs})
            != len(dependent_handoffs)
            or len({x.mention for x in dependent_handoffs}) != 1
            or len({x.evidence.note_type for x in dependent_handoffs}) != 1
        ):
            raise ValueError("Invalid plural Core handoff")
        if prepared_core is not None:
            if (
                resume_plan is not None
                or fixed_plan is not None
                or prepared_core.source != user_request
            ):
                raise ValueError("prepared Core source or continuation mismatch")
            if prepared_core.domain != domain_interpretation:
                raise ValueError("prepared Core domain mismatch")
            if dependent_handoff is not None or dependent_handoffs is not None:
                raise ValueError("dependent route cannot reuse an independent Core plan")
            if prepared_core.clock["date"] != _current_time()["date"]:
                raise ValueError("prepared Core clock is stale")
        if captured_request_instant is not None:
            if (
                not isinstance(captured_request_instant, datetime)
                or captured_request_instant.tzinfo is None
                or captured_request_instant.utcoffset() is None
                or prepared_core is not None
            ):
                raise ValueError("Core captured request instant is invalid")
            clock = {
                "date": captured_request_instant.date().isoformat(),
                "time": captured_request_instant.time().replace(microsecond=0).isoformat(),
                "timezone": getattr(
                    captured_request_instant.tzinfo, "key", os.environ.get("TZ", "Europe/Paris")
                ),
                "timestamp": captured_request_instant.isoformat(timespec="seconds"),
            }
        else:
            clock = prepared_core.clock if prepared_core is not None else _current_time()
        planner_context = {key: clock[key] for key in ("date", "time", "timezone")}
        if dependent_handoff is not None:
            reference = dependent_handoff.evidence
            evidence = DomainEvidence(
                "canonical_reference",
                dependent_handoff.mention,
                f"{reference.note_type}:{reference.canonical_name}",
            )
            if domain_interpretation is None:
                domain_interpretation = DomainInterpretation(
                    "core", user_request, "CANONICAL_REFERENCE", (evidence,)
                )
            else:
                domain_interpretation = replace(
                    domain_interpretation,
                    evidence=(*domain_interpretation.evidence, evidence),
                )
        if dependent_handoffs is not None:
            multi_evidence = tuple(
                DomainEvidence(
                    "canonical_reference",
                    target.mention,
                    f"{target.evidence.note_type}:{target.evidence.canonical_name}",
                )
                for target in dependent_handoffs
            )
            if domain_interpretation is None:
                domain_interpretation = DomainInterpretation(
                    "core", user_request, "CANONICAL_REFERENCE", multi_evidence
                )
            else:
                domain_interpretation = replace(
                    domain_interpretation,
                    evidence=(*domain_interpretation.evidence, *multi_evidence),
                )
        capability_id = (
            domain_interpretation.capability_id if domain_interpretation is not None else None
        )
        execution_schema = planning_schema_for_capability(schema, capability_id)
        execution_semantic_index = application_semantic_indexes.get(capability_id, semantic_index)
        if fixed_plan is not None:
            if resume_plan is not None:
                raise ValueError("fixed plan cannot resume a clarification")
            if request_disposition(fixed_plan) is not RequestDisposition.READ_ONLY:
                raise ValueError("fixed plan must be proven read-only")
            planner = _FixedRequestPlanner(fixed_plan)
        elif resume_plan is not None:
            planner = _FixedRequestPlanner(resume_plan)
        elif prepared_core is not None:
            planner = prepared_core.planner
        elif domain_interpretation is None:
            planner = OpenAIRequestPlanner.from_environment(execution_schema, planner_context)
        else:
            # The app's typed domain evidence authorizes only its OWN managed
            # fields. Use the same owner-scoped schema for provider planning,
            # local plan validation and Core execution; the unprojected schema
            # incorrectly vetoed every normal Tasks status/date property.
            planner = OpenAIRequestPlanner.from_environment(
                execution_schema, planner_context, domain_interpretation=domain_interpretation
            )
        if planner_decorator is not None:
            if resume_plan is not None:
                raise ValueError("resume plan cannot use a planner decorator")
            if prepared_core is None:
                planner = planner_decorator(planner)
        if resume_plan is not None and domain_interpretation is not None:
            raise ValueError("resume plan cannot carry fresh domain interpretation")
        if domain_interpretation is not None and domain_interpretation.source_text != user_request:
            raise ValueError("domain interpretation does not match Core source")
        request_id_factory = (lambda: request_id) if request_id is not None else allocate_request_id
        if authenticated_actor is not None and not isinstance(
            authenticated_actor, AuthenticatedActorContext
        ):
            raise ValueError("authenticated actor context is invalid")
        persistence_actor = _persistence_actor(actor, authenticated_actor)
        result = execute_request(
            user_request,
            planner=planner,
            repository=repository,
            schema=execution_schema,
            context_index=context_index,
            semantic_index=execution_semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            actor=persistence_actor,
            now=clock["timestamp"],
            context_limit=context_limit,
            writer=writer,
            fact_selector=fact_selector,
            semantic_set_selector=semantic_set_selector,
            pending_recorder=pending_recorder,
            history_recorder=history_recorder,
            request_id_factory=request_id_factory,
            authenticated_actor=authenticated_actor,
            self_binding_repository=self_binding_repository,
            conversation_context=(
                conversation_context_override
                if conversation_context_override is not None
                else LocalConversationStore(
                    conversation_root_resolver.resolve(
                        authenticated_actor.stable_user_id
                        if authenticated_actor is not None
                        else actor
                    )
                ).recent_context(exclude_request_id=request_id)
                if conversation_id is not None and request_id is not None
                else ()
            ),
            clarification_choice=clarification_choice,
            write_preflight_guard=_combined_write_preflight_guard(
                write_preflight_guard,
                DependentReferenceGuard(dependent_handoff.mention, dependent_handoff.evidence)
                if dependent_handoff is not None
                else DependentReferenceSetGuard(
                    tuple(
                        DependentReferenceGuard(x.mention, x.evidence) for x in dependent_handoffs
                    )
                )
                if dependent_handoffs is not None
                else None,
            ),
            progress_callback=_emit_progress,
        )
        calls = getattr(planner, "last_provider_calls", ())
        result = _replace_planner_provider_calls(result, calls)
        if prepared_core is not None:
            # Keep model provider duration/cost evidence after the already-finished
            # parallel call; serial Core's wall clock contains only the apply step.
            duration = planner.prepared_duration_ms
            stages = tuple(
                replace(stage, duration_ms=duration, start_offset_ms=None)
                if stage.name == "planner"
                else stage
                for stage in result.operational.stages
            )
            result = replace(
                result,
                operational=replace(result.operational, stages=stages),
            )
        return result

    def refresh_indexes() -> None:
        """Rebuild both derived indexes from authoritative Markdown after a mutation."""
        runtime_root.mkdir(parents=True, exist_ok=True)
        context_index.rebuild(repository, schema, embedder)
        semantic_index.rebuild(repository, schema, embedder)
        for capability_id, index in application_semantic_indexes.items():
            index.rebuild(
                repository, planning_schema_for_capability(schema, capability_id), embedder
            )

    def refresh_affected_indexes(
        note_ids: Sequence[str], *, allow_full_rebuild: bool = True
    ) -> None:
        """Refresh changed notes; report when a strict drift check triggers rebuilding.

        The observed IDs are never logged. A rebuild preserves fail-closed safety
        for untracked external changes; telemetry must not relax that contract.
        """
        started = perf_counter()
        durations_ms: dict[str, float] = {}
        cpu_durations_ms: dict[str, float] = {}
        stage = "resolve_affected"
        outcome = "incremental"
        failure_stage: str | None = None
        failure_class: str | None = None
        expanded: tuple[str, ...] = ()
        context_embedded_notes: int | None = None

        class TimedContextEmbedder:
            """Measure ONNX inside the existing context refresh, without duplicating it."""

            model_name = embedder.model_name
            model_version = embedder.model_version
            document_count = 0

            def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
                self.document_count += len(texts)
                start_embedding = perf_counter()
                try:
                    return embedder.embed_documents(texts)
                finally:
                    durations_ms["context.embedding"] = (perf_counter() - start_embedding) * 1000

            def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
                return embedder.embed_queries(texts)

        context_embedder = TimedContextEmbedder()

        def measure(name: str, refresh: Callable[[], object]) -> object:
            nonlocal stage
            stage = name
            t0 = perf_counter()
            c0 = thread_time()
            try:
                return refresh()
            finally:
                durations_ms[name] = (perf_counter() - t0) * 1000
                cpu_durations_ms[name] = (thread_time() - c0) * 1000

        try:
            expanded = tuple(
                dict.fromkeys(
                    (
                        *note_ids,
                        *materialized_day_link_index_ids(repository, schema, tuple(note_ids)),
                    )
                )
            )
            try:
                context_embedded_notes = measure(
                    "context",
                    lambda: context_index.refresh_notes(
                        repository, schema, context_embedder, note_ids=expanded
                    ),
                )
                verified_inventory = measure(
                    "verified_inventory",
                    lambda: verified_context_source_inventory(
                        repository, schema, context_index.path
                    ),
                )
                measure(
                    "semantic",
                    lambda: semantic_index.refresh_notes(
                        repository,
                        schema,
                        embedder,
                        note_ids=expanded,
                        verified_inventory=verified_inventory,
                    ),
                )
                for capability_id, index in application_semantic_indexes.items():
                    measure(
                        f"semantic.{capability_id}",
                        lambda index=index, capability_id=capability_id: index.refresh_notes(
                            repository,
                            planning_schema_for_capability(schema, capability_id),
                            embedder,
                            note_ids=expanded,
                            verified_inventory=verified_inventory,
                        ),
                    )
            except (ContextIndexError, SemanticIndexError, ValueError) as error:
                failure_class = type(error).__name__
                failure_stage = stage
                if not allow_full_rebuild:
                    # Independent Core scopes cannot mask unknown drift.
                    raise
                outcome = "full_rebuild"
                measure("full_rebuild", refresh_indexes)
        except Exception as error:
            outcome = "failed"
            failure_class = failure_class or type(error).__name__
            failure_stage = failure_stage or stage
            raise
        finally:
            _emit_dev_index_refresh_diagnostic(
                outcome=outcome,
                note_count=len(expanded),
                duration_ms=(perf_counter() - started) * 1000,
                stages_ms=durations_ms,
                stages_cpu_ms=cpu_durations_ms,
                context_embedded_notes=context_embedded_notes,
                failure_stage=failure_stage,
                failure_class=failure_class,
            )

    index_refresh_coordinator = DerivedIndexRefreshCoordinator(refresh_affected_indexes)

    def refresh_task_lifecycle_indexes(path: str, expected_source_hash: str) -> None:
        """Incrementally refresh derived rows after a Task metadata-only lifecycle mutation."""
        context_index.refresh_existing_note(
            repository,
            schema,
            embedder,
            path=path,
            expected_source_hash=expected_source_hash,
        )
        semantic_index.refresh_existing_note(
            repository,
            schema,
            embedder,
            path=path,
            expected_source_hash=expected_source_hash,
        )
        for capability_id, index in application_semantic_indexes.items():
            index.refresh_existing_note(
                repository,
                planning_schema_for_capability(schema, capability_id),
                embedder,
                path=path,
                expected_source_hash=expected_source_hash,
            )

    def intelligent_notes(
        query: str, explicit_filters: Sequence[object]
    ) -> tuple[NotePage, OperationalEvidence]:
        """Plan one explicit Notes request and accept only a single direct RetrieveAction.

        This keeps planner interpretation singular. Clarifications, writes, delegation,
        multi-branch plans, and unimplemented graph traversal do not degrade into a lossy search.
        """
        clock = _current_time()
        planner = OpenAIRequestPlanner.from_environment(
            schema, {key: clock[key] for key in ("date", "time", "timezone")}
        )
        started = perf_counter()
        planner_started = perf_counter()
        try:
            result = planner.plan(query)
        except Exception as error:
            planner_duration_ms = max(0.0, (perf_counter() - planner_started) * 1000)
            failed_stage = OperationalStage(
                "planner",
                OperationalOutcome.FAILED,
                planner_duration_ms,
                provider_calls=getattr(planner, "last_provider_calls", ()),
                start_offset_ms=max(0.0, (planner_started - started) * 1000),
                substeps=getattr(planner, "last_spans", ()),
                error_category=type(error).__name__,
            )
            raise NotesTelemetryError(
                OperationalEvidence(
                    total_duration_ms=max(0.0, (perf_counter() - started) * 1000),
                    stages=(failed_stage,),
                ),
                bad_request=isinstance(error, NotesQueryError),
            ) from error
        planner_duration_ms = max(0.0, (perf_counter() - planner_started) * 1000)
        planner_stage = OperationalStage(
            "planner",
            OperationalOutcome.COMPLETED,
            planner_duration_ms,
            provider_calls=getattr(planner, "last_provider_calls", ()),
            start_offset_ms=max(0.0, (planner_started - started) * 1000),
            substeps=getattr(planner, "last_spans", ()),
        )
        if (
            isinstance(result, PlannerClarification)
            or not isinstance(result, RequestPlan)
            or len(result.actions) != 1
            or not isinstance(result.actions[0], RetrieveAction)
            or result.actions[0].plan.link_scope is not None
        ):
            raise NotesTelemetryError(
                OperationalEvidence(
                    total_duration_ms=max(0.0, (perf_counter() - started) * 1000),
                    stages=(planner_stage,),
                ),
                bad_request=True,
            )
        action = result.actions[0]
        filters: list[object] = [*explicit_filters, *action.plan.filters]
        if action.plan.type is not None:
            filters.append(ContextFilter("type", "eq", action.plan.type))
        query_started = perf_counter()
        try:
            page = NotesQueryService(repository, schema, context_index).query(
                mode="intelligent",
                query=action.plan.query,
                filters=_unique_note_filters(filters),
                embedder=embedder,
            )
        except Exception as error:
            failed_query = OperationalStage(
                "notes.query",
                OperationalOutcome.FAILED,
                max(0.0, (perf_counter() - query_started) * 1000),
                start_offset_ms=max(0.0, (query_started - started) * 1000),
                error_category=type(error).__name__,
            )
            raise NotesTelemetryError(
                OperationalEvidence(
                    total_duration_ms=max(0.0, (perf_counter() - started) * 1000),
                    stages=(planner_stage, failed_query),
                ),
                bad_request=isinstance(error, NotesQueryError),
            ) from error
        query_stage = OperationalStage(
            "notes.query",
            OperationalOutcome.COMPLETED,
            max(0.0, (perf_counter() - query_started) * 1000),
            start_offset_ms=max(0.0, (query_started - started) * 1000),
        )
        return page, OperationalEvidence(
            total_duration_ms=max(0.0, (perf_counter() - started) * 1000),
            stages=(planner_stage, query_stage),
        )

    if light_source_enabled:
        from odyssey_runtime.index_startup import p4_indexes_reusable

        can_reuse = p4_indexes_reusable(
            repository,
            schema,
            embedder,
            context_index,
            semantic_index,
            {
                capability_id: (index, planning_schema_for_capability(schema, capability_id))
                for capability_id, index in application_semantic_indexes.items()
            },
        )
        if not can_reuse:
            refresh_indexes()
    else:
        refresh_indexes()

    # Optional DEV experiment: WAL improves reader/writer coexistence without
    # changing the context SQL schema, canonical markdown, or PROD behavior.
    if os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV" and light_source_enabled:
        context_index.enable_concurrent_reads()

    def notes_mutation_actor(
        authenticated_actor: AuthenticatedActorContext | None,
        external_principal: ExternalPrincipal | None,
    ) -> object:
        """Apply the same trusted provenance mapping as ordinary runtime writes."""
        if external_principal is not None:
            authenticated_actor = identity_mapping_repository.resolve_existing(external_principal)
            authenticated_actor = AuthenticatedActorContext(authenticated_actor.stable_user_id)
        return _persistence_actor(actor, authenticated_actor)

    def execute_hybrid_candidate_route(
        source: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None,
        conversation_id: str | None,
    ) -> ApplicationResult:
        """Run the reviewed hybrid dispatcher for one authenticated DEV conversation.

        The ordinary v0 route never reaches this callable unless the process
        was explicitly configured for DEV hybrid evaluation.  Candidate pending
        state is rooted below the authenticated actor's conversation state, so
        an outer request ID cannot expose or resume another actor's ambiguity.
        This route intentionally has no selected-choice continuation: a stored
        F14/F27 choice remains non-executable until a general E2E continuation
        contract is approved.
        """
        if authenticated_actor is None or conversation_id is None:
            return ApplicationResult(
                request_id,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                clarification_code="HYBRID_AUTHENTICATED_CONVERSATION_REQUIRED",
            )
        try:
            from openai import OpenAI
        except ImportError as error:
            raise ValueError("Install the OpenAI SDK for DEV hybrid evaluation") from error

        clock = _current_time()
        client = OpenAI(max_retries=0)
        candidate_pending_root = (
            conversation_root_resolver.resolve(authenticated_actor.stable_user_id) / "pending"
        )
        candidate_pending_root.mkdir(mode=0o700, exist_ok=True)
        candidate_pending = CandidatePendingRepository(candidate_pending_root)

        def record_route_ambiguity(preview, options):  # type: ignore[no-untyped-def]
            """Persist only source-exact, Core-proven ambiguity for this conversation."""
            return candidate_pending.record(
                preview,
                conversation_id=conversation_id,
                created_at=clock["timestamp"],
                options=options,
                vault=repository,
                schema=schema,
            )

        return cast(
            ApplicationResult,
            execute_candidate_routed_message(
                source,
                router=OpenAIFactCandidateRouter(
                    client,
                    prompt_revision="v6" if hybrid_source_review_enabled else "v5",
                    event_routing=(
                        "events" in enabled_application_ids and hybrid_source_review_enabled
                    ),
                ),
                temporal=OpenAITemporalInterpreter(
                    client,
                    {key: clock[key] for key in ("date", "time", "timezone")},
                    max_output_tokens=1536,
                    scoped_date_time_context=True,
                ),
                core_planner_factory=OpenAILunaContextPlannerFactory(
                    client=client,
                    schema=schema,
                    clock={key: clock[key] for key in ("date", "time", "timezone")},
                ),
                core_candidate_attributor=OpenAICoreCandidateAttributor(client),
                repository=repository,
                schema=schema,
                context_index=context_index,
                semantic_index=semantic_index,
                embedder=embedder,
                contextual_reasoner=contextual_reasoner,
                actor=_persistence_actor(actor, authenticated_actor),
                now=clock["timestamp"],
                context_limit=context_limit,
                request_id_factory=lambda: request_id,
                history_recorder=history_recorder,
                route_ambiguity_recorder=record_route_ambiguity,
                # Keep Task source routed only to the registered scoped Tasks lifecycle.
                # The dispatcher has no Day/Core fallback for task candidates.
                bundle_compiler=lambda proposal: compile_hybrid_candidate_bundle(
                    proposal,
                    enable_tasks=True,
                    enable_events="events" in enabled_application_ids,
                ),
                task_route_executor=_ScopedTaskRouteExecutor(execute_scoped_tasks),
                event_route_executor=execute_events
                if "events" in enabled_application_ids
                else None,
                progress_callback=_emit_progress,
                postwrite_index_refresh=refresh_affected_indexes,
                source_boundary_reviewer=(
                    OpenAICoreSourceBoundaryReviewer(client)
                    if hybrid_source_review_enabled
                    else None
                ),
                authenticated_actor=authenticated_actor,
                self_binding_repository=self_binding_repository,
                conversation_context=LocalConversationStore(
                    conversation_root_resolver.resolve(authenticated_actor.stable_user_id)
                ).recent_context(exclude_request_id=request_id),
            ),
        )

    def execute_hybrid_proven_read(
        source: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext,
        conversation_id: str,
    ) -> ApplicationResult | None:
        """Execute only an exact-source Core plan proven to contain retrieval actions.

        Planning is read-only. A non-read, mixed, malformed, or unavailable
        plan never reaches generic Core execution here; the caller retains the
        guarded candidate route for write-capable work.
        """
        if "events" in enabled_application_ids and explicit_event_query_hint(source):
            # Legacy Core READ_ONLY preflight must not swallow an explicit
            # Event-domain query. This is only a lexical prefilter; P4 and
            # Events still require source-bound GPT evidence before reading.
            return None
        clock = _current_time()
        planner = OpenAIRequestPlanner.from_environment(
            schema, {key: clock[key] for key in ("date", "time", "timezone")}
        )
        try:
            plan = planner.plan(
                source,
                LocalConversationStore(
                    conversation_root_resolver.resolve(authenticated_actor.stable_user_id)
                ).recent_context(exclude_request_id=request_id),
            )
        except Exception:
            return None
        if isinstance(plan, PlannerClarification) or not isinstance(plan, RequestPlan):
            return None
        disposition = request_disposition(plan)
        if disposition is RequestDisposition.READ_ONLY:
            return core_execute(
                source,
                request_id,
                authenticated_actor,
                conversation_id,
                fixed_plan=plan,
            )
        if disposition is RequestDisposition.MIXED:
            return ApplicationResult(
                request_id,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                clarification_code="HYBRID_MIXED_REQUEST_REQUIRES_SEPARATE_REQUESTS",
            )
        return None

    notes_service = NotesQueryService(repository, schema, context_index)
    calendar_application = CalendarApplication(
        CalendarQueryService(repository, schema, notes_service)
    )

    enabled_application_ids = _enabled_application_ids()
    application_catalog = ApplicationRegistry.from_descriptors(
        (_TASKS_DESCRIPTOR, _EVENTS_DESCRIPTOR)
    ).catalog(enabled_ids=enabled_application_ids)
    application_router = OpenAIApplicationRouter.from_environment(application_catalog)
    direct_task_mutations = (
        TaskDirectMutationService(
            repository,
            schema,
            history_recorder,
            semantic_index=application_semantic_indexes["tasks"],
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            semantic_limit=context_limit,
        )
        if "tasks" in enabled_application_ids
        else None
    )
    work_session_service = (
        TaskWorkSessionService(repository, schema, history_recorder)
        if "tasks" in enabled_application_ids
        else None
    )

    @dataclass(frozen=True)
    class _PreparedInterpretation:
        """One request-local, read-free provider interpretation and its measured evidence."""

        clock: dict[str, str]
        value: TemporalInterpretation | TaskInterpretation | TaskScopedInterpretation | None
        stage: OperationalStage

    def prepare_temporal_interpretation(
        source_text: str,
        conversation_context: Sequence[Mapping[str, str]] = (),
        *,
        captured_clock: dict[str, str] | None = None,
    ) -> _PreparedInterpretation:
        """Interpret exact time against the SAME captured delivery instant if supplied."""
        clock = captured_clock if captured_clock is not None else _current_time()
        interpreter = OpenAITemporalInterpreter.from_environment(
            {key: clock[key] for key in ("date", "time", "timezone")}
        )
        started = perf_counter()
        try:
            temporal = interpreter.interpret(source_text, conversation_context)
        except TemporalInterpreterError as error:
            duration = max(0.0, (perf_counter() - started) * 1000)
            stage = OperationalStage(
                "temporal.interpretation",
                OperationalOutcome.FAILED,
                duration,
                model=interpreter.model,
                reasoning_effort=interpreter.reasoning_effort,
                usage=normalize_provider_usage(interpreter.last_usage),
                error_category=type(error).__name__,
            )
            return _PreparedInterpretation(clock, None, stage)
        duration = max(0.0, (perf_counter() - started) * 1000)
        calls = ()
        if interpreter.last_call:
            calls = (
                ProviderCallEvidence(
                    name="temporal.interpretation",
                    outcome=OperationalOutcome.COMPLETED,
                    duration_ms=duration,
                    model=interpreter.model,
                    reasoning_effort=interpreter.reasoning_effort,
                    usage=normalize_provider_usage(interpreter.last_usage),
                    response_id=interpreter.last_response_id,
                    provider_status=interpreter.last_provider_status,
                    attempt_count=1,
                    ordinal=1,
                ),
            )
        stage = OperationalStage(
            "temporal.interpretation",
            OperationalOutcome.COMPLETED,
            duration,
            model=interpreter.model,
            reasoning_effort=interpreter.reasoning_effort,
            usage=normalize_provider_usage(interpreter.last_usage),
            provider_calls=calls,
        )
        return _PreparedInterpretation(clock, temporal, stage)

    def prepare_task_interpretation(
        source_text: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> _PreparedInterpretation:
        """Interpret only Tasks lifecycle intent; queries and writes remain serial."""
        clock = _current_time()
        interpreter = OpenAITaskInterpreter.from_environment()
        started = perf_counter()
        try:
            task = interpreter.interpret(source_text, conversation_context)
        except TaskInterpretationError as error:
            duration = max(0.0, (perf_counter() - started) * 1000)
            return _PreparedInterpretation(
                clock,
                None,
                OperationalStage(
                    "tasks.interpretation",
                    OperationalOutcome.FAILED,
                    duration,
                    model=interpreter.model,
                    reasoning_effort=interpreter.reasoning_effort,
                    usage=normalize_provider_usage(interpreter.last_usage),
                    error_category=type(error).__name__,
                ),
            )
        duration = max(0.0, (perf_counter() - started) * 1000)
        return _PreparedInterpretation(
            clock,
            task,
            OperationalStage(
                "tasks.interpretation",
                OperationalOutcome.COMPLETED,
                duration,
                model=interpreter.model,
                reasoning_effort=interpreter.reasoning_effort,
                usage=normalize_provider_usage(interpreter.last_usage),
            ),
        )

    def prepare_scoped_task_interpretation(
        source_text: str, scoped_evidence: TaskScopedEvidence
    ) -> _PreparedInterpretation:
        """Interpret one hybrid Task route without granting its source evidence mutation authority."""
        clock = _current_time()
        interpreter = OpenAITaskInterpreter.from_environment()
        started = perf_counter()
        try:
            task = interpreter.interpret_scoped(source_text, scoped_evidence=scoped_evidence)
        except TaskInterpretationError as error:
            duration = max(0.0, (perf_counter() - started) * 1000)
            return _PreparedInterpretation(
                clock,
                None,
                OperationalStage(
                    "tasks.scoped_interpretation",
                    OperationalOutcome.FAILED,
                    duration,
                    model=interpreter.model,
                    reasoning_effort=interpreter.reasoning_effort,
                    usage=normalize_provider_usage(interpreter.last_usage),
                    error_category=type(error).__name__,
                ),
            )
        duration = max(0.0, (perf_counter() - started) * 1000)
        return _PreparedInterpretation(
            clock,
            task,
            OperationalStage(
                "tasks.scoped_interpretation",
                OperationalOutcome.COMPLETED,
                duration,
                model=interpreter.model,
                reasoning_effort=interpreter.reasoning_effort,
                usage=normalize_provider_usage(interpreter.last_usage),
            ),
        )

    def _task_flow(interpretation: TaskInterpretation) -> dict[str, object]:
        """Return bounded Task lifecycle intent, not an alternate Core plan."""
        return {
            "task": {
                "operation": interpretation.operation.value[:48],
                "reference": (interpretation.task_reference or "")[:160],
            }
        }

    def _temporal_flow(interpretation: TemporalInterpretation | None) -> dict[str, object]:
        """Project grounded human-time translations without exposing model payloads."""
        if interpretation is None:
            return {"temporal": []}
        items = []
        for mention in interpretation.mentions[:8]:
            value = mention.resolution.exact_datetime or mention.resolution.exact_date
            if value is not None:
                items.append({"source": mention.temporal_text[:120], "value": value[:80]})
        return {"temporal": items}

    def execute_temporal_core(
        source_text: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
        *,
        prepared: _PreparedInterpretation | None = None,
        prepared_core: _PrecomputedCorePlan | None = None,
        dependent_handoff: DependentRouteHandoff | None = None,
    ) -> ApplicationResult:
        """Resolve only time semantics, then return the unchanged source to ordinary Core."""
        if authenticated_actor is not None and not isinstance(
            authenticated_actor, AuthenticatedActorContext
        ):
            raise ValueError("authenticated actor context is invalid")
        _emit_progress("temporal.started")
        interpretation = prepared or prepare_temporal_interpretation(
            source_text, conversation_context
        )
        stage = interpretation.stage
        duration_ms = stage.duration_ms or 0.0
        temporal = interpretation.value
        if temporal is None:
            return ApplicationResult(
                request_id,
                ApplicationStatus.FAILED,
                (),
                (),
                planning_error="TEMPORAL_INTERPRETATION_FAILED",
                operational=OperationalEvidence(duration_ms, (stage,)),
            )
        assert isinstance(temporal, TemporalInterpretation)
        temporal_values = []
        for mention in temporal.mentions:
            value = mention.resolution.exact_datetime or mention.resolution.exact_date
            if value is not None:
                temporal_values.append(f"{mention.temporal_text}: {value}")
        _emit_progress("temporal.ready", {"values": tuple(temporal_values)})
        temporal_kinds = temporal.kinds()
        if any(kind is TemporalResolutionKind.UNSPECIFIED for kind in temporal_kinds):
            return ApplicationResult(
                request_id,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="TEMPORAL_UNRESOLVED",
                operational=OperationalEvidence(duration_ms, (stage,)),
            )
        if any(
            kind not in {TemporalResolutionKind.EXACT_DATE, TemporalResolutionKind.EXACT_DATETIME}
            for kind in temporal_kinds
        ):
            return ApplicationResult(
                request_id,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="TEMPORAL_VALUE_REQUIRES_DOMAIN_OWNER",
                operational=OperationalEvidence(duration_ms, (stage,)),
            )
        core_result = core_execute(
            source_text,
            request_id,
            authenticated_actor,
            conversation_context_override=conversation_context,
            domain_interpretation=temporal.core_domain_interpretation(),
            prepared_core=prepared_core if dependent_handoff is None else None,
            dependent_handoff=dependent_handoff,
        )
        return replace(
            core_result,
            operational=OperationalEvidence(
                (core_result.operational.total_duration_ms or 0.0) + duration_ms,
                (stage, *core_result.operational.stages),
            ),
            execution_flow={**(core_result.execution_flow or {}), **_temporal_flow(temporal)},
        )

    def execute_tasks(
        source_text: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
        *,
        prepared: _PreparedInterpretation | None = None,
        prepared_task_temporal: _PreparedInterpretation | None = None,
        prepared_core: _PrecomputedCorePlan | None = None,
        dependent_task_target: TaskDependentTarget | None = None,
        dependent_person_handoff: TaskPersonReference | None = None,
        dependent_person_set: TaskPersonReferenceSet | None = None,
        completed_work_session: Callable[[WorkSessionMutationResult], None] | None = None,
        dependent_session_evidence: CanonicalSessionEvidence | None = None,
    ) -> ApplicationResult:
        """Interpret Tasks lifecycle, consume Temporal when needed, then delegate mutation to Core."""
        interpretation = prepared or prepare_task_interpretation(source_text, conversation_context)
        clock = interpretation.clock
        task_stage = interpretation.stage
        task_duration = task_stage.duration_ms or 0.0
        task = interpretation.value
        if task is None:
            return ApplicationResult(
                request_id,
                ApplicationStatus.FAILED,
                (),
                (),
                planning_error="TASK_INTERPRETATION_FAILED",
                operational=OperationalEvidence(task_duration, (task_stage,)),
            )
        assert isinstance(task, TaskInterpretation)
        if dependent_person_handoff is not None and (
            not isinstance(dependent_person_handoff, TaskPersonReference)
            or authenticated_actor is None
            or task.operation is not TaskOperation.CREATE
            or task.source_text != source_text
            or dependent_task_target is not None
        ):
            return ApplicationResult(
                request_id,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="DEPENDENT_PERSON_PROOF_INVALID",
            )
        if dependent_person_handoff is not None:
            try:
                person_proof = dependent_person_handoff.require_current(
                    authenticated_actor.stable_user_id, source_text, repository, schema
                )
            except TaskDependentTargetError:
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="DEPENDENT_PERSON_PROOF_INVALID",
                )
        person_proofs = None
        if dependent_person_set is not None:
            if (
                not isinstance(dependent_person_set, TaskPersonReferenceSet)
                or authenticated_actor is None
                or task.operation is not TaskOperation.CREATE
                or task.source_text != source_text
                or dependent_person_handoff is not None
                or dependent_task_target is not None
            ):
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="DEPENDENT_PERSON_SET_INVALID",
                )
            try:
                person_proofs = dependent_person_set.require_current(
                    authenticated_actor.stable_user_id, source_text, repository, schema
                )
            except TaskDependentTargetError:
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="DEPENDENT_PERSON_SET_STALE",
                )
        if dependent_task_target is not None and (
            authenticated_actor is None
            or task.operation is not dependent_task_target.operation
            or task.source_text != source_text
            or task.operation
            not in {
                TaskOperation.CREATE,
                TaskOperation.START_WORK_SESSION,
                TaskOperation.STOP_WORK_SESSION,
                TaskOperation.EDIT_WORK_SESSION,
                TaskOperation.ADD_WORK_SESSION_ACTIVITY,
            }
        ):
            return ApplicationResult(
                request_id,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="DEPENDENT_TASK_SCOPE_INVALID",
            )
        stages: list[OperationalStage] = [task_stage]
        total_duration = task_duration
        if task.operation is TaskOperation.QUERY:
            assert task.query_scope is not None
            query_started = perf_counter()
            try:
                retrieval = TaskQueryService(repository, schema).query(
                    source_text, task.query_scope, now=clock["timestamp"]
                )
            except TaskQueryError as error:
                duration = max(0.0, (perf_counter() - query_started) * 1000)
                stages.append(
                    OperationalStage(
                        "tasks.query",
                        OperationalOutcome.FAILED,
                        duration,
                        error_category=type(error).__name__,
                    )
                )
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.FAILED,
                    (),
                    (),
                    planning_error="TASK_QUERY_FAILED",
                    operational=OperationalEvidence(total_duration + duration, tuple(stages)),
                )
            duration = max(0.0, (perf_counter() - query_started) * 1000)
            stages.append(OperationalStage("tasks.query", OperationalOutcome.COMPLETED, duration))
            return ApplicationResult(
                request_id,
                ApplicationStatus.COMPLETED,
                (ActionResult(0, "retrieve", ActionStatus.COMPLETED, retrieval=retrieval),),
                (),
                operational=OperationalEvidence(total_duration + duration, tuple(stages)),
                execution_flow=_task_flow(task),
            )

        temporal = None
        if task.requires_temporal():
            if dependent_task_target is not None and prepared_task_temporal is None:
                # Never call Temporal AFTER Core's predecessor already wrote.
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="DEPENDENT_TASK_TEMPORAL_NOT_PREPARED",
                    operational=OperationalEvidence(total_duration, tuple(stages)),
                )
            temporal_evidence = prepared_task_temporal or prepare_temporal_interpretation(
                source_text,
                conversation_context,
                captured_clock=clock if dependent_task_target is not None else None,
            )
            duration = temporal_evidence.stage.duration_ms or 0.0
            if (
                temporal_evidence.value is None
                or not isinstance(temporal_evidence.value, TemporalInterpretation)
                or any(
                    kind
                    not in {
                        TemporalResolutionKind.EXACT_DATE,
                        TemporalResolutionKind.EXACT_DATETIME,
                    }
                    for kind in temporal_evidence.value.kinds()
                )
            ):
                failed = replace(
                    temporal_evidence.stage,
                    outcome=OperationalOutcome.FAILED,
                    error_category=(
                        temporal_evidence.stage.error_category or "TaskRequiresExactTemporalValue"
                    ),
                )
                stages.append(failed)
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="TASK_TEMPORAL_UNRESOLVED",
                    operational=OperationalEvidence(total_duration + duration, tuple(stages)),
                )
            temporal = temporal_evidence.value
            total_duration += duration
            stages.append(temporal_evidence.stage)
        if task.operation in {
            TaskOperation.START_WORK_SESSION,
            TaskOperation.STOP_WORK_SESSION,
            TaskOperation.EDIT_WORK_SESSION,
            TaskOperation.ADD_WORK_SESSION_ACTIVITY,
        }:
            if work_session_service is None:
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.FAILED,
                    (),
                    (),
                    planning_error="WORK_SESSION_UNAVAILABLE",
                    operational=OperationalEvidence(total_duration, tuple(stages)),
                )
            resolved_task_id: str | None = None
            if dependent_task_target is not None:
                try:
                    resolved_task_id = dependent_task_target.require_current(repository, schema)
                except TaskDependentTargetError:
                    return ApplicationResult(
                        request_id,
                        ApplicationStatus.NEEDS_ATTENTION,
                        (),
                        (),
                        planning_error="DEPENDENT_TASK_TARGET_STALE",
                        operational=OperationalEvidence(total_duration, tuple(stages)),
                    )
            elif task.task_reference is not None:
                # Only the opted-in DEV runtime publishes substep timings.
                # No prompts, candidate IDs, user text, or note content are recorded.
                resolution_started = perf_counter()
                resolution_spans = (
                    SpanRecorder(resolution_started, perf_counter)
                    if os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV"
                    and os.environ.get("ODYSSEY_WORK_SESSION_RESOLUTION_TIMING_ENABLED") == "1"
                    else None
                )
                try:
                    task_schema = planning_schema_for_capability(schema, "tasks")
                    resolution = resolve_existing_entity(
                        task.task_reference,
                        source_text,
                        type=TASK_TYPE,
                        repository=repository,
                        schema=task_schema,
                        semantic_index=application_semantic_indexes.get("tasks", semantic_index),
                        embedder=embedder,
                        contextual_reasoner=contextual_reasoner,
                        semantic_limit=context_limit,
                        expand_relationship_context=True,
                        resolution_spans=resolution_spans,
                    )
                except Exception as error:
                    duration = max(0.0, (perf_counter() - resolution_started) * 1000)
                    stages.append(
                        OperationalStage(
                            "tasks.work_session_resolution",
                            OperationalOutcome.FAILED,
                            duration,
                            error_category=type(error).__name__,
                            substeps=_work_session_resolution_substeps(resolution_spans),
                        )
                    )
                    return ApplicationResult(
                        request_id,
                        ApplicationStatus.FAILED,
                        (),
                        (),
                        planning_error="WORK_SESSION_RESOLUTION_FAILED",
                        operational=OperationalEvidence(total_duration + duration, tuple(stages)),
                    )
                duration = max(0.0, (perf_counter() - resolution_started) * 1000)
                total_duration += duration
                stages.append(
                    OperationalStage(
                        "tasks.work_session_resolution",
                        OperationalOutcome.COMPLETED,
                        duration,
                        substeps=_work_session_resolution_substeps(resolution_spans),
                    )
                )
                if (
                    resolution.outcome is not ExistingEntityOutcome.RESOLVED
                    or resolution.id is None
                ):
                    code = (
                        "WORK_SESSION_TASK_AMBIGUOUS"
                        if resolution.outcome is ExistingEntityOutcome.AMBIGUOUS
                        or resolution.offers_clarification
                        else "WORK_SESSION_TASK_UNRESOLVED"
                    )
                    return ApplicationResult(
                        request_id,
                        ApplicationStatus.NEEDS_ATTENTION,
                        (),
                        (),
                        planning_error=code,
                        operational=OperationalEvidence(total_duration, tuple(stages)),
                    )
                resolved_task_id = resolution.id
            elif task.operation is not TaskOperation.ADD_WORK_SESSION_ACTIVITY:
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.FAILED,
                    (),
                    (),
                    planning_error="WORK_SESSION_UNAVAILABLE",
                    operational=OperationalEvidence(total_duration, tuple(stages)),
                )

            try:
                if task.operation is TaskOperation.ADD_WORK_SESSION_ACTIVITY:
                    session_date = compose_work_session_activity_date(task, temporal)
                    started_at = ended_at = None
                else:
                    session_date = None
                    started_at, ended_at = compose_work_session_times(
                        task, temporal, now=clock["timestamp"]
                    )
            except TaskInterpretationError:
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="WORK_SESSION_TEMPORAL_INVALID",
                    operational=OperationalEvidence(total_duration, tuple(stages)),
                )

            mutation_started = perf_counter()
            try:
                persistence_actor = _persistence_actor(actor, authenticated_actor)
                tokens = None
                if dependent_task_target is not None:
                    # E2 proof freshness is checked AGAIN immediately before
                    # the domain command; START also uses the existing CAS
                    # expected-revision and hash from the Task Notes service.
                    assert resolved_task_id is not None
                    dependent_task_target.require_current(repository, schema)
                    tokens = work_session_service.task_mutation_tokens(resolved_task_id)
                    if (
                        tokens[1]
                        != dependent_task_target.source_dependency.evidence.canonical_content_guard
                    ):
                        raise WorkSessionError("STALE_NOTE")
                if task.operation is TaskOperation.START_WORK_SESSION:
                    assert resolved_task_id is not None and started_at is not None
                    mutation = work_session_service.start(
                        task_id=resolved_task_id,
                        started_at=started_at,
                        request_id=request_id,
                        actor=persistence_actor,
                        now=clock["timestamp"],
                        expected_task_revision=tokens[0] if tokens else None,
                        expected_task_source_hash=tokens[1] if tokens else None,
                    )
                elif task.operation is TaskOperation.STOP_WORK_SESSION:
                    assert resolved_task_id is not None and ended_at is not None
                    if dependent_session_evidence is not None:
                        if (
                            dependent_task_target is None
                            or dependent_session_evidence.task_id != resolved_task_id
                        ):
                            raise WorkSessionError("SESSION_DEPENDENCY_TARGET_MISMATCH")
                        try:
                            revision, source_hash = dependent_session_evidence.require_current(
                                work_session_service
                            )
                        except ValueError as error:
                            raise WorkSessionError("SESSION_DEPENDENCY_STALE") from error
                        mutation = work_session_service.stop(
                            session_id=dependent_session_evidence.session_id,
                            ended_at=ended_at,
                            expected_revision=revision,
                            expected_source_hash=source_hash,
                            request_id=request_id,
                            actor=persistence_actor,
                            now=clock["timestamp"],
                        )
                    else:
                        mutation = work_session_service.stop_for_task(
                            task_id=resolved_task_id,
                            ended_at=ended_at,
                            request_id=request_id,
                            actor=persistence_actor,
                            now=clock["timestamp"],
                        )
                elif task.operation is TaskOperation.EDIT_WORK_SESSION:
                    assert resolved_task_id is not None
                    mutation = work_session_service.edit_for_task(
                        task_id=resolved_task_id,
                        started_at=started_at,
                        ended_at=ended_at,
                        request_id=request_id,
                        actor=persistence_actor,
                        now=clock["timestamp"],
                    )
                else:
                    assert task.activity_text is not None
                    mutation = work_session_service.add_activity_for_task(
                        task_id=resolved_task_id,
                        text=task.activity_text,
                        session_date=session_date,
                        request_id=request_id,
                        actor=persistence_actor,
                        now=clock["timestamp"],
                    )
            except TaskDependentTargetError:
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="DEPENDENT_TASK_TARGET_STALE",
                    operational=OperationalEvidence(total_duration, tuple(stages)),
                )
            except WorkSessionError as error:
                duration = max(0.0, (perf_counter() - mutation_started) * 1000)
                stages.append(
                    OperationalStage(
                        "tasks.work_session_mutation",
                        OperationalOutcome.FAILED,
                        duration,
                        error_category=error.code,
                    )
                )
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error=error.code,
                    operational=OperationalEvidence(total_duration + duration, tuple(stages)),
                )
            # This is the original, fully read-back Tasks domain result, NOT
            # AppResult. Keep it request-private and let the caller mint the
            # E2 proof. If callback crashes after physical WRITE, propagate
            # to the enclosing E3 unresolved claim rather than retrying.
            if completed_work_session is not None:
                completed_work_session(mutation)
            duration = max(0.0, (perf_counter() - mutation_started) * 1000)
            total_duration += duration
            stages.append(
                OperationalStage(
                    "tasks.work_session_mutation", OperationalOutcome.COMPLETED, duration
                )
            )
            return ApplicationResult(
                request_id,
                ApplicationStatus.COMPLETED,
                (
                    ActionResult(
                        0,
                        "write",
                        ActionStatus.COMPLETED,
                        unit_results=(
                            UnitResult(
                                0,
                                UnitStatus.SUCCEEDED,
                                operation=mutation.operation,
                                stable_note_id=mutation.session.id,
                            ),
                        ),
                    ),
                ),
                # The physical write touched the Work Session Note, NOT its
                # parent Task. Keep this canonical affected ID aligned with
                # the already returned UnitResult receipt and actual Markdown.
                (mutation.session.id,),
                history=mutation.history,
                operational=OperationalEvidence(total_duration, tuple(stages)),
                execution_flow=_task_flow(task),
            )
        if dependent_task_target is not None and task.operation is TaskOperation.CREATE:
            mutation_started = perf_counter()
            try:
                if direct_task_mutations is None:
                    raise TaskDirectMutationError("TASK_UNAVAILABLE")
                parent_id = dependent_task_target.require_current(repository, schema)
                title = dependent_task_target.require_prepared_subtask_title(source_text)
                revision, source_hash = direct_task_mutations.task_mutation_tokens(parent_id)
                if (
                    source_hash
                    != dependent_task_target.source_dependency.evidence.canonical_content_guard
                ):
                    raise TaskDependentTargetError("Dependent parent changed before subtask CAS")
                child = direct_task_mutations.create_subtask(
                    parent_note_id=parent_id,
                    title=title,
                    expected_revision=revision,
                    expected_source_hash=source_hash,
                    request_id=request_id,
                    actor=_persistence_actor(actor, authenticated_actor),
                    now=clock["timestamp"],
                )
            except TaskDependentTargetError:
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="DEPENDENT_TASK_TARGET_STALE",
                    operational=OperationalEvidence(total_duration, tuple(stages)),
                )
            except TaskDirectMutationError as error:
                if error.physical_write:
                    # An uncertain postwrite cannot safely become an E3 success receipt.
                    raise
                duration = max(0.0, (perf_counter() - mutation_started) * 1000)
                stages.append(
                    OperationalStage(
                        "tasks.subtask_mutation",
                        OperationalOutcome.FAILED,
                        duration,
                        error_category=error.code,
                    )
                )
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error=error.code,
                    operational=OperationalEvidence(total_duration + duration, tuple(stages)),
                )
            duration = max(0.0, (perf_counter() - mutation_started) * 1000)
            total_duration += duration
            stages.append(
                OperationalStage("tasks.subtask_mutation", OperationalOutcome.COMPLETED, duration)
            )
            return ApplicationResult(
                request_id,
                ApplicationStatus.COMPLETED,
                (
                    ActionResult(
                        0,
                        "write",
                        ActionStatus.COMPLETED,
                        unit_results=(
                            UnitResult(
                                0,
                                UnitStatus.SUCCEEDED,
                                operation=child.operation,
                                stable_note_id=child.note_id,
                            ),
                        ),
                    ),
                ),
                (child.note_id,),
                history=child.history,
                operational=OperationalEvidence(total_duration, tuple(stages)),
                execution_flow=_task_flow(task),
            )
        try:
            domain = compose_task_domain_interpretation(task, temporal, now=clock["timestamp"])
        except TaskInterpretationError:
            return ApplicationResult(
                request_id,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="TASK_DOMAIN_INVALID",
                operational=OperationalEvidence(total_duration, tuple(stages)),
            )
        core_result = core_execute(
            source_text,
            request_id,
            authenticated_actor,
            conversation_context_override=conversation_context,
            domain_interpretation=domain,
            planner_decorator=lambda planner: TaskCorePlanner(
                planner,
                task,
                verified_person_set=(
                    tuple((proof.mention, proof.evidence.canonical_name) for proof in person_proofs)
                    if person_proofs is not None
                    else ()
                ),
            ),
            write_preflight_guard=TaskLifecycleGuard(task.operation),
            prepared_core=prepared_core,
            dependent_handoff=(
                DependentRouteHandoff(person_proof.mention, person_proof.evidence)
                if dependent_person_handoff is not None
                else None
            ),
            dependent_handoffs=(
                tuple(
                    DependentRouteHandoff(proof.mention, proof.evidence) for proof in person_proofs
                )
                if person_proofs is not None
                else None
            ),
            captured_request_instant=(
                datetime.fromisoformat(clock["timestamp"])
                if dependent_person_handoff is not None or person_proofs is not None
                else None
            ),
        )
        if person_proofs is not None:
            # The same Core-owned postwrite guard is exercised by isolated
            # physical-corruption regressions. Never trust a Writer receipt
            # alone as evidence that every Person link persisted.
            core_result = guard_plural_task_readback(repository, schema, core_result, person_proofs)
        return replace(
            core_result,
            operational=OperationalEvidence(
                total_duration + (core_result.operational.total_duration_ms or 0.0),
                (*stages, *core_result.operational.stages),
            ),
            execution_flow={
                **(core_result.execution_flow or {}),
                **_temporal_flow(temporal),
                **_task_flow(task),
            },
        )

    def execute_scoped_tasks(
        source_text: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
        *,
        scoped_evidence: TaskScopedEvidence,
    ) -> TaskScopedExecution:
        """Run one evidence-bound hybrid Task mutation through the ordinary Task/Core lifecycle.

        Router provenance may only constrain the scoped Tasks interpreter.  The interpreter still
        chooses the Task operation, while fresh Temporal interpretation, Task lifecycle validation,
        canonical Core planning, persistence, and Git history remain their existing owners.
        """
        if scoped_evidence.source_text != source_text:
            raise ValueError("Scoped Task evidence source changed before interpretation")
        prepared = prepare_scoped_task_interpretation(source_text, scoped_evidence)
        task_duration = prepared.stage.duration_ms or 0.0
        scoped = prepared.value
        if not isinstance(scoped, TaskScopedInterpretation):
            return TaskScopedExecution(
                ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="TASK_SCOPED_INTERPRETATION_FAILED",
                    operational=OperationalEvidence(task_duration, (prepared.stage,)),
                )
            )
        task = scoped.task
        # Candidate task groups are mutation-only.  Queries and Work Sessions use their normal
        # routed entry points and cannot be smuggled through source-scoped hybrid evidence.
        if task.operation in {
            TaskOperation.QUERY,
            TaskOperation.START_WORK_SESSION,
            TaskOperation.STOP_WORK_SESSION,
            TaskOperation.EDIT_WORK_SESSION,
            TaskOperation.ADD_WORK_SESSION_ACTIVITY,
        }:
            return TaskScopedExecution(
                ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="TASK_SCOPED_OPERATION_UNSUPPORTED",
                    operational=OperationalEvidence(task_duration, (prepared.stage,)),
                )
            )

        stages = [prepared.stage]
        temporal: TemporalInterpretation | None = None
        total_duration = task_duration
        if task.requires_temporal():
            temporal_evidence = prepare_temporal_interpretation(source_text, conversation_context)
            duration = temporal_evidence.stage.duration_ms or 0.0
            if not isinstance(temporal_evidence.value, TemporalInterpretation) or any(
                kind
                not in {
                    TemporalResolutionKind.EXACT_DATE,
                    TemporalResolutionKind.EXACT_DATETIME,
                }
                for kind in temporal_evidence.value.kinds()
            ):
                failed = replace(
                    temporal_evidence.stage,
                    outcome=OperationalOutcome.FAILED,
                    error_category=(
                        temporal_evidence.stage.error_category or "TaskRequiresExactTemporalValue"
                    ),
                )
                return TaskScopedExecution(
                    ApplicationResult(
                        request_id,
                        ApplicationStatus.NEEDS_ATTENTION,
                        (),
                        (),
                        planning_error="TASK_TEMPORAL_UNRESOLVED",
                        operational=OperationalEvidence(
                            total_duration + duration, tuple((*stages, failed))
                        ),
                    )
                )
            temporal = temporal_evidence.value
            total_duration += duration
            stages.append(temporal_evidence.stage)
        try:
            domain = compose_scoped_task_domain_interpretation(
                scoped, temporal, scoped_evidence, now=prepared.clock["timestamp"]
            )
        except TaskInterpretationError:
            return TaskScopedExecution(
                ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="TASK_SCOPED_DOMAIN_INVALID",
                    operational=OperationalEvidence(total_duration, tuple(stages)),
                ),
                temporal,
            )
        core_result = core_execute(
            source_text,
            request_id,
            authenticated_actor,
            conversation_context_override=conversation_context,
            domain_interpretation=domain,
            planner_decorator=lambda planner: TaskCorePlanner(planner, task),
            write_preflight_guard=TaskLifecycleGuard(task.operation),
        )
        return TaskScopedExecution(
            replace(
                core_result,
                operational=OperationalEvidence(
                    total_duration + (core_result.operational.total_duration_ms or 0.0),
                    (*stages, *core_result.operational.stages),
                ),
                execution_flow={
                    **(core_result.execution_flow or {}),
                    **_temporal_flow(temporal),
                    **_task_flow(task),
                },
            ),
            temporal,
        )

    def execute_events(
        source_text: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
        *,
        prepared: tuple[EventCandidate, TemporalInterpretation | None] | None = None,
        captured_clock: dict[str, str] | None = None,
    ) -> ApplicationResult:
        """Run one trusted Events destination, then existing Temporal/Core/E3."""
        if authenticated_actor is None:
            return ApplicationResult(
                request_id,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="EVENT_AUTH_REQUIRED",
            )
        clock = captured_clock if captured_clock is not None else _current_time()
        started = perf_counter()
        temporal_result: TemporalInterpretation | None = None
        temporal_stage = ()
        if prepared is not None:
            candidate, temporal_result = prepared
            if (
                not isinstance(candidate, EventCandidate)
                or candidate.interpretation.source_text != source_text
                or (
                    temporal_result is not None
                    and (
                        not isinstance(temporal_result, TemporalInterpretation)
                        or temporal_result.source_text != source_text
                    )
                )
            ):
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="EVENT_PREPARED_SOURCE_UNVERIFIED",
                )
            # A previous verified E2 review already ran BEFORE any
            # independent sibling mutation; never reinterpret after WRITE.
            stage = OperationalStage("events.interpretation", OperationalOutcome.COMPLETED, 0.0)
        else:
            event_interpreter = OpenAIEventInterpreter.from_environment()
            try:
                candidate = event_interpreter.interpret(source_text)
                if candidate.interpretation.source_text != source_text:
                    raise EventInterpretationError("Events interpreter source mismatch")
            except EventInterpretationError:
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="EVENT_INTERPRETATION_REJECTED",
                )
            event_duration = max(0.0, (perf_counter() - started) * 1000)
            stage = OperationalStage(
                "events.interpretation",
                OperationalOutcome.COMPLETED,
                event_duration,
                model=event_interpreter.model,
                reasoning_effort=event_interpreter.reasoning_effort,
                usage=normalize_provider_usage(event_interpreter.last_usage),
            )
            if candidate.interpretation.operation in {
                EventOperation.CREATE,
                EventOperation.UPDATE,
                EventOperation.CANCEL,
            } or (
                candidate.interpretation.operation is EventOperation.QUERY
                and bool(candidate.interpretation.temporal_mentions)
            ):
                resolved = prepare_temporal_interpretation(
                    source_text, conversation_context, captured_clock=clock
                )
                temporal_result = (
                    resolved.value if isinstance(resolved.value, TemporalInterpretation) else None
                )
                temporal_stage = (resolved.stage,)
        result = execute_event_candidate(
            candidate=candidate,
            temporal=temporal_result,
            repository=repository,
            schema=schema,
            mutations=EventMutationService(repository, schema, history_recorder),
            request_id=request_id,
            actor=_persistence_actor(actor, authenticated_actor),
            now=clock["timestamp"],
            authenticated=True,
            query_handler=lambda candidate, temporal: event_note_snapshot(
                candidate=candidate,
                temporal=temporal,
                repository=repository,
                schema=schema,
                now=clock["timestamp"],
            ),
        )
        return replace(
            result,
            operational=OperationalEvidence(
                max(0.0, (perf_counter() - started) * 1000),
                (stage, *temporal_stage),
            ),
        )

    application_executors = bind_registered_executors(
        application_catalog,
        {"tasks": execute_tasks, "events": execute_events},
        require_enabled=True,
    )

    # In DEV workers now finish domain interpretation AND validated Core planning.
    # Only the returned execution callbacks use repositories, preflight and Git,
    # sequentially under the request's existing single-write authority.
    route_preparers: dict[str, RoutePreparer] = {}
    if os.environ.get("ODYSSEY_PARALLEL_ROUTE_PREPARATION", "0") == "1":

        def prepare_core_route(
            text: str, context: Sequence[Mapping[str, str]]
        ) -> ApplicationExecutor:
            """Compute the ordinary Core planner output without touching note state."""
            prepared = prepare_core_plan(text, _current_time(), context)

            def execute(
                source: str,
                locator: str,
                actor: AuthenticatedActorContext | None,
                prior: Sequence[Mapping[str, str]],
            ) -> ApplicationResult:
                if source != text:
                    raise ValueError("prepared Core route source changed")
                if _current_time()["date"] != prepared.clock["date"]:
                    return core_execute(source, locator, actor, conversation_context_override=prior)
                return core_execute(
                    source,
                    locator,
                    actor,
                    conversation_context_override=prior,
                    prepared_core=prepared,
                )

            return execute

        def prepare_temporal_route(
            text: str, context: Sequence[Mapping[str, str]]
        ) -> ApplicationExecutor:
            prepared = prepare_temporal_interpretation(text, context)
            core_plan = None
            temporal = prepared.value
            if isinstance(temporal, TemporalInterpretation) and all(
                kind in {TemporalResolutionKind.EXACT_DATE, TemporalResolutionKind.EXACT_DATETIME}
                for kind in temporal.kinds()
            ):
                core_plan = prepare_core_plan(
                    text,
                    prepared.clock,
                    context,
                    temporal.core_domain_interpretation(),
                )

            def execute(
                source: str,
                locator: str,
                actor: AuthenticatedActorContext | None,
                prior: Sequence[Mapping[str, str]],
            ) -> ApplicationResult:
                if source != text:
                    raise ValueError("prepared Temporal source changed")
                if _current_time()["date"] != prepared.clock["date"]:
                    # Across midnight the old interpretation is no longer authoritative.
                    return execute_temporal_core(source, locator, actor, prior)
                return execute_temporal_core(
                    source,
                    locator,
                    actor,
                    prior,
                    prepared=prepared,
                    prepared_core=core_plan,
                )

            # Expose only validated semantic date anchors to the pre-write cohort guard.
            exact = isinstance(temporal, TemporalInterpretation) and all(
                kind in {TemporalResolutionKind.EXACT_DATE, TemporalResolutionKind.EXACT_DATETIME}
                for kind in temporal.kinds()
            )
            return PreparedExecution(
                execute,
                temporal_dates=(
                    tuple(
                        (mention.resolution.exact_date or mention.resolution.exact_datetime or "")[
                            :10
                        ]
                        for mention in temporal.mentions
                    )
                    if exact
                    else ()
                ),
                temporal_resolved=bool(exact),
                temporal_stage=prepared.stage,
                temporal_evidence=(
                    tuple(
                        (
                            mention.temporal_text,
                            (
                                mention.resolution.exact_date
                                or mention.resolution.exact_datetime
                                or ""
                            )[:10],
                        )
                        for mention in temporal.mentions
                    )
                    if exact
                    else ()
                ),
            )

        def prepare_tasks_route(
            text: str, context: Sequence[Mapping[str, str]]
        ) -> ApplicationExecutor:
            prepared = prepare_task_interpretation(text, context)
            task = prepared.value
            task_temporal = None
            core_plan = None
            if isinstance(task, TaskInterpretation):
                if task.requires_temporal() and task.operation is not TaskOperation.QUERY:
                    task_temporal = prepare_temporal_interpretation(text, context)
                resolved_temporal = task_temporal.value if task_temporal is not None else None
                valid_temporal = (
                    not task.requires_temporal()
                    or isinstance(resolved_temporal, TemporalInterpretation)
                    and all(
                        kind
                        in {
                            TemporalResolutionKind.EXACT_DATE,
                            TemporalResolutionKind.EXACT_DATETIME,
                        }
                        for kind in resolved_temporal.kinds()
                    )
                )
                if (
                    task.operation
                    not in {
                        TaskOperation.QUERY,
                        TaskOperation.START_WORK_SESSION,
                        TaskOperation.STOP_WORK_SESSION,
                        TaskOperation.EDIT_WORK_SESSION,
                        TaskOperation.ADD_WORK_SESSION_ACTIVITY,
                    }
                    and valid_temporal
                ):
                    try:
                        domain = compose_task_domain_interpretation(
                            task, resolved_temporal, now=prepared.clock["timestamp"]
                        )
                    except TaskInterpretationError:
                        pass  # Ordinary serial Tasks error response remains authoritative.
                    else:
                        core_plan = prepare_core_plan(
                            text,
                            prepared.clock,
                            context,
                            domain,
                            lambda planner: TaskCorePlanner(planner, task),
                        )

            def execute(
                source: str,
                locator: str,
                actor: AuthenticatedActorContext | None,
                prior: Sequence[Mapping[str, str]],
            ) -> ApplicationResult:
                if source != text:
                    raise ValueError("prepared Tasks source changed")
                if _current_time()["date"] != prepared.clock["date"]:
                    return execute_tasks(source, locator, actor, prior)
                return execute_tasks(
                    source,
                    locator,
                    actor,
                    prior,
                    prepared=prepared,
                    prepared_task_temporal=task_temporal,
                    prepared_core=core_plan,
                )

            return execute

        route_preparers["core"] = prepare_core_route
        route_preparers["temporal"] = prepare_temporal_route
        if "tasks" in enabled_application_ids:
            route_preparers["tasks"] = prepare_tasks_route

    def _captured_dependent_clock(instant: datetime) -> dict[str, str]:
        return {
            "date": instant.date().isoformat(),
            "time": instant.time().replace(microsecond=0).isoformat(),
            "timezone": getattr(instant.tzinfo, "key", os.environ.get("TZ", "Europe/Paris")),
            "timestamp": instant.isoformat(timespec="seconds"),
        }

    def prepare_independent_event_before_any_write(
        segment: str, instant: datetime
    ) -> tuple[EventCandidate, TemporalInterpretation | None]:
        # Same provider contracts as Events-only route; no Note identity
        # or destination is selected. Only a single CREATE is currently
        # independent-app composable.
        candidate = OpenAIEventInterpreter.from_environment().interpret(segment)
        if (
            candidate.interpretation.source_text != segment
            or candidate.interpretation.operation is not EventOperation.CREATE
        ):
            raise EventInterpretationError("Independent Events scope is not one CREATE")
        clock = _captured_dependent_clock(instant)
        temporal = prepare_temporal_interpretation(segment, (), captured_clock=clock).value
        if not isinstance(temporal, TemporalInterpretation) or temporal.source_text != segment:
            raise EventInterpretationError("Independent Event temporal evidence unavailable")
        bound_occurrence(candidate, temporal)
        return candidate, temporal

    def prepare_dependent_task_before_core_write(
        source: str, instant: datetime
    ) -> tuple[TaskInterpretation, TemporalInterpretation | None]:
        # Reuse the production Task and Temporal interpreters BEFORE any
        # Core write. Semantic identity still belongs solely to Core.
        task = OpenAITaskInterpreter.from_environment().interpret(source, ())
        temporal = None
        if task.requires_temporal():
            captured = _captured_dependent_clock(instant)
            temporal = OpenAITemporalInterpreter.from_environment(
                {key: captured[key] for key in ("date", "time", "timezone")}
            ).interpret(source, ())
            if any(
                kind
                not in {TemporalResolutionKind.EXACT_DATE, TemporalResolutionKind.EXACT_DATETIME}
                for kind in temporal.kinds()
            ):
                raise TaskInterpretationError("Dependent temporal evidence not exact")
            if task.operation is TaskOperation.ADD_WORK_SESSION_ACTIVITY:
                compose_work_session_activity_date(task, temporal)
            elif task.operation in {
                TaskOperation.START_WORK_SESSION,
                TaskOperation.STOP_WORK_SESSION,
                TaskOperation.EDIT_WORK_SESSION,
            }:
                compose_work_session_times(task, temporal, now=captured["timestamp"])
        return task, temporal

    def prepare_dependent_subtask_before_core_write(
        source: str, task: TaskInterpretation, instant: datetime
    ):
        """Use the ordinary Core Task planner to prepare one child title without writing.

        The resulting plan is consumed only by the strict source-bound title
        validator.  Parent identity and the child write remain unavailable
        until the preceding Core result proves a fresh canonical Task link.
        """
        if task.operation is not TaskOperation.CREATE or task.source_text != source:
            raise TaskInterpretationError("Dependent subtask preparation requires matching CREATE")
        clock = _captured_dependent_clock(instant)
        domain = compose_task_domain_interpretation(task, None, now=clock["timestamp"])
        planner = TaskCorePlanner(
            GPT56RequestPlanner.from_environment(
                schema,
                {key: clock[key] for key in ("date", "time", "timezone")},
                domain_interpretation=domain,
            ),
            task,
        )
        plan = planner.plan(source, ())
        if not isinstance(plan, RequestPlan):
            raise TaskInterpretationError("Dependent subtask planner did not return a write plan")
        return prepare_dependent_subtask_title(source_text=source, interpretation=task, plan=plan)

    def _operation_manifest_store(identity: AuthenticatedActorContext) -> LocalDeliveryResultStore:
        return LocalDeliveryResultStore(
            conversation_root_resolver.resolve(identity.stable_user_id) / "delivery-results",
            manifest_capabilities=frozenset({"core", "tasks", *enabled_application_ids}),
        )

    def _begin_p4_operation_manifest(
        delivery: str,
        source: str,
        identity: AuthenticatedActorContext,
        groups: tuple[tuple[str, str, tuple[int, ...]], ...],
    ) -> None:
        store = _operation_manifest_store(identity)
        store.begin_operation_manifest(delivery, store.fingerprint(source, "main"), source, groups)

    def _observe_p4_operation_manifest(
        delivery: str,
        source: str,
        identity: AuthenticatedActorContext,
        ordinal: int,
        capability: str,
        outcome: ApplicationResult,
    ) -> None:
        store = _operation_manifest_store(identity)
        store.observe_operation_manifest(
            delivery,
            store.fingerprint(source, "main"),
            ordinal,
            capability,
            outcome.status.value,
            outcome.affected_stable_note_ids,
        )

    def _execute_reviewed_session_step(
        segment: str,
        locator: str,
        identity: AuthenticatedActorContext,
        task: TaskInterpretation,
        temporal: TemporalInterpretation | None,
        target: TaskDependentTarget,
        instant: datetime,
        preceding_session: CanonicalSessionEvidence | None,
    ) -> tuple[ApplicationResult, CanonicalSessionEvidence | None]:
        """Same Tasks executor; keep canonical WorkSession start receipt private."""
        if work_session_service is None or task.operation not in {
            TaskOperation.START_WORK_SESSION,
            TaskOperation.STOP_WORK_SESSION,
        }:
            raise TaskInterpretationError("Unrepresentable dependent Work Session step")
        if task.operation is TaskOperation.START_WORK_SESSION and preceding_session is not None:
            raise TaskInterpretationError("START cannot consume a prior Work Session")
        if task.operation is TaskOperation.STOP_WORK_SESSION and preceding_session is None:
            raise TaskInterpretationError("STOP requires a physically proven Work Session")
        if preceding_session is not None:
            # A stale prior-session receipt is a PREWRITE veto. A fault after
            # WorkSessionService actually persists remains an unresolved E3
            # exception; do not conflate these two phases.
            try:
                preceding_session.require_current(work_session_service)
            except CanonicalSessionEvidenceError:
                return (
                    ApplicationResult(
                        locator,
                        ApplicationStatus.NEEDS_ATTENTION,
                        (),
                        (),
                        planning_error="SESSION_DEPENDENCY_STALE",
                    ),
                    None,
                )
        proofs: list[CanonicalSessionEvidence] = []

        def _retain_start_receipt(mutation: WorkSessionMutationResult) -> None:
            if task.operation is not TaskOperation.START_WORK_SESSION or proofs:
                raise TaskInterpretationError("Unexpected Work Session receipt")
            proofs.append(
                prove_created_session(
                    result=mutation,
                    expected_task_id=target.require_current(repository, schema),
                    creator_delivery_step=locator,
                    service=work_session_service,
                )
            )

        clock = _captured_dependent_clock(instant)
        result = execute_tasks(
            segment,
            locator,
            identity,
            (),
            prepared=_PreparedInterpretation(
                clock,
                task,
                OperationalStage("tasks.interpretation", OperationalOutcome.COMPLETED, 0.0),
            ),
            prepared_task_temporal=(
                _PreparedInterpretation(
                    clock,
                    temporal,
                    OperationalStage("temporal.interpretation", OperationalOutcome.COMPLETED, 0.0),
                )
                if temporal is not None
                else None
            ),
            dependent_task_target=target,
            dependent_session_evidence=preceding_session,
            completed_work_session=(
                _retain_start_receipt
                if task.operation is TaskOperation.START_WORK_SESSION
                else None
            ),
        )
        if result.status is ApplicationStatus.COMPLETED:
            if task.operation is TaskOperation.START_WORK_SESSION:
                if len(proofs) != 1:
                    # Completed response missing physical source evidence; keep
                    # the E3 claim unresolved rather than silently progressing.
                    raise TaskInterpretationError("START receipt absent after completed write")
                return result, proofs[0]
            return result, None
        if proofs:
            raise TaskInterpretationError("Incomplete Work Session returned a START receipt")
        return result, None

    light_source_execute = None
    if light_source_enabled:
        if self_binding_repository is None:
            raise ValueError("P4 requires authenticated canonical SELF binding")
        from openai import OpenAI

        from odyssey_runtime.dev_p4_diagnostics import record_dev_p4_prewrite_gate
        from odyssey_runtime.whole_source_light import WholeSourceLightExecutor

        light_source_execute = WholeSourceLightExecutor(
            repository=repository,
            schema=schema,
            context_index=context_index,
            semantic_index=semantic_index,
            embedder=embedder,
            reasoner=contextual_reasoner,
            bindings=self_binding_repository,
            pending_recorder=pending_recorder,
            parallel_speaker_reviews=os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV",
            parallel_coverage_speaker_reviews=os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV",
            parallel_target_decisions=os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV",
            task_create_batch_enabled=os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV",
            core_anchored_coverage_enabled=(
                os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV"
                and os.environ.get("ODYSSEY_P4_SOURCE_ANCHORS_V2") == "1"
            ),
            prewrite_diagnostic=(
                record_dev_p4_prewrite_gate
                if os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV"
                else None
            ),
            refresh_affected_indexes=refresh_affected_indexes,
            refresh_between_independent_scopes=lambda ids: refresh_affected_indexes(
                ids, allow_full_rebuild=False
            ),
            operation_manifest_begin=_begin_p4_operation_manifest,
            operation_manifest_observe=_observe_p4_operation_manifest,
            task_delegate=lambda source, locator, identity: execute_tasks(
                source, locator, identity, ()
            ),
            event_delegate=(
                (lambda source, locator, identity: execute_events(source, locator, identity, ()))
                if "events" in enabled_application_ids
                else None
            ),
            client=OpenAI(max_retries=0, timeout=70),
            progress=_emit_progress,
            # For source-reviewed N independent Core/Tasks scopes, prepare
            # every Task and its Temporal meaning before the first sibling
            # Core WRITE. Execute the same prepared interpretation later via
            # the ordinary Tasks/Core/WorkSession service, without another
            # potentially divergent TaskInterpreter model call.
            independent_event_prepare=(
                prepare_independent_event_before_any_write
                if "events" in enabled_application_ids
                else None
            ),
            independent_event_delegate=(
                lambda segment, locator, identity, event, temporal, instant: (
                    execute_events(
                        segment,
                        locator,
                        identity,
                        (),
                        prepared=(event, temporal),
                        captured_clock=_captured_dependent_clock(instant),
                    )
                    if "events" in enabled_application_ids
                    else None
                )
            ),
            independent_task_prepare=(
                prepare_dependent_task_before_core_write
                if "tasks" in enabled_application_ids
                else None
            ),
            independent_task_delegate=(
                lambda segment, locator, identity, task, temporal, instant: execute_tasks(
                    segment,
                    locator,
                    identity,
                    (),
                    prepared=_PreparedInterpretation(
                        _captured_dependent_clock(instant),
                        task,
                        OperationalStage("tasks.interpretation", OperationalOutcome.COMPLETED, 0.0),
                    ),
                    prepared_task_temporal=(
                        _PreparedInterpretation(
                            _captured_dependent_clock(instant),
                            temporal,
                            OperationalStage(
                                "temporal.interpretation", OperationalOutcome.COMPLETED, 0.0
                            ),
                        )
                        if temporal is not None
                        else None
                    ),
                )
            )
            if "tasks" in enabled_application_ids
            else None,
            dependent_core_delegate=(
                lambda segment, locator, identity, instant: core_execute(
                    segment,
                    locator,
                    identity,
                    conversation_context_override=(),
                    captured_request_instant=instant,
                )
            )
            if "tasks" in enabled_application_ids
            else None,
            dependent_task_prepare=(
                prepare_dependent_task_before_core_write
                if "tasks" in enabled_application_ids
                else None
            ),
            dependent_person_create_enabled="tasks" in enabled_application_ids,
            dependent_subtask_prepare=(
                prepare_dependent_subtask_before_core_write
                if "tasks" in enabled_application_ids
                else None
            ),
            dependent_session_delegate=(
                _execute_reviewed_session_step if "tasks" in enabled_application_ids else None
            ),
            dependent_task_delegate=(
                lambda segment, locator, identity, task, temporal, target, instant: execute_tasks(
                    segment,
                    locator,
                    identity,
                    (),
                    prepared=_PreparedInterpretation(
                        _captured_dependent_clock(instant),
                        task,
                        OperationalStage("tasks.interpretation", OperationalOutcome.COMPLETED, 0.0),
                    ),
                    prepared_task_temporal=(
                        _PreparedInterpretation(
                            _captured_dependent_clock(instant),
                            temporal,
                            OperationalStage(
                                "temporal.interpretation", OperationalOutcome.COMPLETED, 0.0
                            ),
                        )
                        if temporal is not None
                        else None
                    ),
                    dependent_task_target=(
                        target if isinstance(target, TaskDependentTarget) else None
                    ),
                    dependent_person_handoff=(
                        target if isinstance(target, TaskPersonReference) else None
                    ),
                    dependent_person_set=(
                        target if isinstance(target, TaskPersonReferenceSet) else None
                    ),
                )
            )
            if "tasks" in enabled_application_ids
            else None,
        )

    return RuntimeComposition(
        core_execute=core_execute,
        refresh_indexes=refresh_indexes,
        refresh_affected_indexes=refresh_affected_indexes,
        schedule_index_refresh=index_refresh_coordinator.schedule,
        await_index_refresh=index_refresh_coordinator.wait_until_clean,
        refresh_task_lifecycle_indexes=refresh_task_lifecycle_indexes,
        application_catalog=application_catalog,
        application_router=application_router,
        application_executors=application_executors,
        temporal_executor=execute_temporal_core,
        route_preparers=route_preparers,
        identity_mapping_repository=identity_mapping_repository,
        conversation_root_resolver=conversation_root_resolver,
        notes_service=notes_service,
        calendar_application=calendar_application,
        notes_embedder=embedder,
        pending_recorder=pending_recorder,
        vault_repository=repository,
        canonical_schema=schema,
        user_schema_registry=user_schema_registry,
        user_schema_revision=user_schema_revision,
        schema_activation_enabled=schema_activation_enabled,
        schema_suggestion_service=schema_suggestion_service,
        schema_scan_factory=schema_scan_factory,
        schema_backfill_factory=schema_backfill_factory,
        schema_backfill_interpreter=schema_backfill_interpreter,
        schema_backfill_call_limit=schema_backfill_call_limit,
        clarification_classifier=OpenAILunaClarificationClassifier(),
        intelligent_notes_execute=intelligent_notes,
        direct_notes_mutations=DirectNoteMutationService(
            repository, schema, notes_service, history_recorder
        ),
        direct_task_mutations=direct_task_mutations,
        work_session_service=work_session_service,
        product_progress_store=ProductProgressStore(),
        # The canonical environment factory must wire the SAME actor-root
        # source-free checkpoints tested on standalone RuntimeComposition.
        # Without this, DEV/PROD responses silently return an empty E2 ledger
        # despite their live progress UI updating correctly.
        execution_checkpoint_store_factory=LocalExecutionCheckpointStore,
        notes_mutation_actor=notes_mutation_actor,
        hybrid_candidate_execute=(
            light_source_execute
            if light_source_enabled
            else execute_hybrid_candidate_route
            if hybrid_dev_enabled
            else None
        ),
        # Core READ_ONLY remains on the proven Core path. This is a bounded
        # additional planner call on mutating messages: measure before adoption.
        hybrid_read_execute=(
            execute_hybrid_proven_read if light_source_enabled or hybrid_dev_enabled else None
        ),
        full_source_mutation_guard=light_source_enabled,
        conversation_gateway=(
            OpenAIConversationGateway.from_environment()
            if os.environ.get("ODYSSEY_CHAT_C3_ENABLED") == "1"
            and os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV"
            else None
        ),
        # Capability set comes exclusively from this deployed factory wiring.
        # Neither the browser nor Luna can advertise new available features.
        conversation_error_guidance_enabled=(
            os.environ.get("ODYSSEY_CHAT_C4_ENABLED") == "1"
            and os.environ.get("ODYSSEY_DEPLOYMENT_ENV") == "DEV"
        ),
        conversation_error_model_advisory_enabled=_chat_c4_model_advisory_enabled(),
        conversation_graph_gateway=_c4_graph_gateway_from_environment(),
        conversation_deployed_capabilities=deployed_chat_help_capabilities(
            application_executors,
            notes_available=notes_service is not None,
            calendar_available=calendar_application is not None,
            work_sessions_available=work_session_service is not None,
        ),
    )


def _unique_note_filters(filters: Sequence[object]) -> tuple[object, ...]:
    """Preserve one canonical filter occurrence when explicit and planner criteria agree."""
    result: list[object] = []
    seen: set[tuple[object, object, str]] = set()
    for item in filters:
        if isinstance(item, ContextFilter):
            field, op, value = item.field, item.op, item.value
        elif isinstance(item, Mapping):
            field, op, value = item.get("field"), item.get("op"), item.get("value")
        else:
            result.append(item)
            continue
        try:
            key = (field, op, json.dumps(value, sort_keys=True, separators=(",", ":")))
        except (TypeError, ValueError):
            result.append(item)
            continue
        if key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)


def _notes_to_response(
    value: NoteCapabilities | NotePage | NoteDetail | BacklinkPage,
) -> dict[str, object]:
    """Serialize typed Notes evidence without exposing vault paths or derived index internals."""
    if isinstance(value, NoteCapabilities):
        return {"kind": "capabilities", "types": list(value.types), "fields": list(value.fields)}
    if isinstance(value, NotePage):
        return {
            "kind": "page",
            "mode": value.mode,
            "sort": value.sort,
            "ranking_version": value.ranking_version,
            "as_of": value.as_of,
            "applied_filters": [
                {"field": item.field, "op": item.op, "value": item.value}
                for item in value.applied_filters
            ],
            "items": [_summary_to_response(item) for item in value.items],
            "total": value.total,
            "next_cursor": value.next_cursor,
            "unavailable_ids": list(value.unavailable_ids),
            "snapshot_offset": value.snapshot_offset,
        }
    if isinstance(value, NoteDetail):
        return {
            "kind": "detail",
            "note": _summary_to_response(value.note),
            "body": value.body,
            "body_blocks": [
                {
                    "kind": block.kind,
                    **(
                        {
                            "fact_locator": block.fact_locator,
                            "deletable": True,
                        }
                        if block.deletable
                        else {}
                    ),
                    "segments": [
                        {
                            "text": segment.text,
                            **(
                                {
                                    "target_id": segment.target_id,
                                    "target_type": segment.target_type,
                                }
                                if segment.target_id is not None
                                else {}
                            ),
                        }
                        for segment in block.segments
                    ],
                }
                for block in value.body_blocks
            ],
            "links": [
                {
                    "target_id": item.target_id,
                    "target_name": item.target_name,
                    "target_type": item.target_type,
                    "label": item.label,
                    "occurrences": item.occurrences,
                }
                for item in value.links
            ],
            "mutation": {
                "revision": value.revision,
                "source_hash": value.source_hash,
            },
        }
    if isinstance(value, BacklinkPage):
        return {
            "kind": "backlinks",
            "target_id": value.target_id,
            "items": [
                {
                    "source": _summary_to_response(item.source),
                    "occurrences": item.occurrences,
                    "snippets": [
                        {
                            **(
                                {"heading": _segments_to_response(occurrence.heading)}
                                if occurrence.heading is not None
                                else {}
                            ),
                            "block": {
                                "kind": occurrence.block.kind,
                                "segments": _segments_to_response(occurrence.block.segments),
                            },
                        }
                        for occurrence in item.snippets
                    ],
                    "snippets_truncated": item.snippets_truncated,
                }
                for item in value.items
            ],
            "total": value.total,
            "next_cursor": value.next_cursor,
        }
    raise TypeError("Notes response is invalid")


def _segments_to_response(segments: Sequence[object]) -> list[dict[str, object]]:
    """Serialize Core-resolved visible text segments without exposing canonical paths."""
    return [
        {
            "text": segment.text,
            **(
                {"target_id": segment.target_id, "target_type": segment.target_type}
                if segment.target_id is not None
                else {}
            ),
        }
        for segment in segments
    ]


def _work_session_to_response(value: WorkSessionSnapshot) -> dict[str, object]:
    """Serialize one Tasks-owned session without exposing its canonical file path or name."""
    return {
        "id": value.id,
        "task_id": value.task_id,
        "started_at": value.started_at,
        "ended_at": value.ended_at,
        "activity": [
            {"id": item.id, "created_at": item.created_at, "text": item.text}
            for item in value.activity
        ],
        "mutation": {"revision": value.revision, "source_hash": value.source_hash},
    }


def _summary_to_response(value: object) -> dict[str, object]:
    """Serialize one typed Notes summary at the runtime response boundary."""
    return {
        "id": value.id,
        "name": value.name,
        "type": value.type,
        "tags": list(value.tags),
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "properties": dict(value.properties),
    }


def _persistence_actor(
    application_actor: str, authenticated_actor: AuthenticatedActorContext | None
) -> ActorInput:
    """Combine the stable application actor with optional normalized human provenance."""
    if not isinstance(application_actor, str) or not application_actor.strip():
        raise ValueError("application actor must be a non-empty string")
    return {
        "human": authenticated_actor.stable_user_id if authenticated_actor is not None else None,
        "app": application_actor,
    }


def _replace_planner_provider_calls(
    result: ApplicationResult, calls: tuple[ProviderCallEvidence, ...]
) -> ApplicationResult:
    """Replace the synthetic wrapper call with exact Luna/Sol planner-call evidence."""
    if not calls:
        return result
    stages = tuple(
        replace(stage, provider_calls=calls) if stage.name == "planner" else stage
        for stage in result.operational.stages
    )
    return cast(
        ApplicationResult, replace(result, operational=replace(result.operational, stages=stages))
    )


def _path_env(name: str, default: str) -> Path:
    """Read one non-empty filesystem path from environment configuration."""
    value = os.environ.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return Path(value).expanduser()


def _build_contextual_reasoner() -> OpenAIContextualReasoner:
    """Build the production contextual reasoner with the canonical few-shot prefix."""
    return OpenAIContextualReasoner(
        os.environ.get("ODYSSEY_CONTEXTUAL_MODEL", "gpt-5.6-luna"),
        reasoning_effort="medium",
        examples=load_contextual_calibration_examples(),
    )


def _hybrid_dev_enabled() -> bool:
    """Allow the experimental hybrid route only after an explicit DEV opt-in.

    The default is off.  A process configured as anything other than DEV
    fails at composition time instead of quietly enabling experimental model
    execution in PROD or an unidentified environment.
    """
    value = os.environ.get("ODYSSEY_HYBRID_DEV_ENABLED", "").strip()
    if value in {"", "0", "false", "False"}:
        return False
    if value not in {"1", "true", "True"}:
        raise ValueError("ODYSSEY_HYBRID_DEV_ENABLED must be 0 or 1")
    if os.environ.get("ODYSSEY_DEPLOYMENT_ENV", "").strip() != "DEV":
        raise ValueError("ODYSSEY_HYBRID_DEV_ENABLED requires ODYSSEY_DEPLOYMENT_ENV=DEV")
    return True


def _hybrid_source_review_enabled(hybrid_dev_enabled: bool) -> bool:
    """Enable v6 only inside the already-authenticated DEV hybrid seam.

    This is intentionally a second explicit switch: Router v5 remains the
    default hybrid behavior, and a stray v6 flag can never activate in PROD.
    """
    value = os.environ.get("ODYSSEY_HYBRID_SOURCE_REVIEW_ENABLED", "").strip()
    if value in {"", "0", "false", "False"}:
        return False
    if value not in {"1", "true", "True"}:
        raise ValueError("ODYSSEY_HYBRID_SOURCE_REVIEW_ENABLED must be 0 or 1")
    if not hybrid_dev_enabled or os.environ.get("ODYSSEY_DEPLOYMENT_ENV", "").strip() != "DEV":
        raise ValueError(
            "ODYSSEY_HYBRID_SOURCE_REVIEW_ENABLED requires "
            "ODYSSEY_HYBRID_DEV_ENABLED=1 and ODYSSEY_DEPLOYMENT_ENV=DEV"
        )
    return True


def _positive_int_env(name: str, default: int) -> int:
    """Read one positive integer runtime setting without exposing configuration values."""
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _current_time() -> dict[str, str]:
    """Return the explicit planner and persistence clock values for the configured timezone."""
    timezone_name = os.environ.get("TZ", "Europe/Paris")
    try:
        current = datetime.now(ZoneInfo(timezone_name))
    except (KeyError, ValueError) as error:
        raise ValueError("TZ must name a valid IANA timezone") from error
    return {
        "date": current.date().isoformat(),
        "time": current.time().replace(microsecond=0).isoformat(),
        "timezone": timezone_name,
        "timestamp": current.isoformat(timespec="seconds"),
    }
