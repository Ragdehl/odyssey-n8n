"""Explicit production dependency composition for the Odyssey runtime bridge."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from threading import Condition, Lock, RLock, Thread
from time import perf_counter
from typing import Any, cast
from zoneinfo import ZoneInfo

from odyssey_apps import (
    ApplicationCatalog,
    ApplicationDescriptor,
    ApplicationRegistry,
    OpenAIApplicationRouter,
)
from odyssey_apps.calendar import CalendarApplication, CalendarQueryService
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TASK_TYPE,
    OpenAITaskInterpreter,
    TaskCorePlanner,
    TaskDirectMutationError,
    TaskDirectMutationService,
    TaskInterpretationError,
    TaskLifecycleGuard,
    TaskOperation,
    TaskQueryError,
    TaskQueryService,
    TaskWorkSessionService,
    WorkSessionError,
    WorkSessionSnapshot,
    compose_task_domain_interpretation,
    compose_work_session_activity_date,
    compose_work_session_times,
)
from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    UnitResult,
    UnitStatus,
    WritePreflightGuard,
    allocate_request_id,
    execute_request,
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
from odyssey_core.domain_interpretation import DomainInterpretation
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
    OperationalStage,
    ProviderCallEvidence,
    normalize_provider_usage,
)
from odyssey_core.pending_work import PendingWorkError, PendingWorkRepository
from odyssey_core.persistence import ActorInput
from odyssey_core.reference_preflight import ReferencePreflightError, current_identity_guard
from odyssey_core.request_planning import (
    PlannerClarification,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
    validate_request_plan,
)
from odyssey_core.resolution import ExistingEntityOutcome, resolve_existing_entity
from odyssey_core.schema_types import planning_schema_for_capability
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex, SemanticIndexError
from odyssey_core.semantic_sets import OpenAILunaSemanticSetSelector
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal import calendar_day_link_dates
from odyssey_core.temporal_interpretation import (
    OpenAITemporalInterpreter,
    TemporalInterpreterError,
)
from odyssey_core.temporal_resolution import TemporalResolutionKind

from .delivery_results import LocalDeliveryResultStore
from .progress import ProductProgressStore
from .routing import (
    ApplicationExecutor,
    ApplicationRouter,
    execute_routed_request,
    is_route_execution_id,
)
from .serialization import application_result_to_response, operational_to_response


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


_VAULT_REPOSITORY_TYPE = VaultRepository

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
    """Run derived-index maintenance off the response path with a strict read barrier.

    Mutations publish only stable note IDs. A single daemon worker coalesces IDs that arrive while
    one refresh is running. Readers call :meth:`wait_until_clean` before consulting derived state;
    an unrecoverable refresh failure therefore fails closed instead of exposing stale indexes.
    """

    def __init__(self, refresh: Callable[[Sequence[str]], None]) -> None:
        self._refresh = refresh
        self._condition = Condition()
        self._pending: set[str] = set()
        self._requested_generation = 0
        self._completed_generation = 0
        self._last_error: Exception | None = None
        self._worker: Thread | None = None

    def schedule(self, note_ids: Sequence[str]) -> int:
        """Queue affected stable IDs and return the generation that now needs reconciliation."""
        bounded = tuple(dict.fromkeys(note_ids))
        if not bounded or any(not isinstance(note_id, str) or not note_id for note_id in bounded):
            raise ValueError("index refresh scheduling requires stable note IDs")
        with self._condition:
            self._pending.update(bounded)
            self._requested_generation += 1
            generation = self._requested_generation
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
        """Block until all refresh work visible at call time has completed successfully."""
        with self._condition:
            target = self._requested_generation
            while self._completed_generation < target:
                self._condition.wait()
            if self._last_error is not None:
                raise RuntimeError("derived index refresh failed") from self._last_error

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._pending:
                    self._condition.wait()
                note_ids = tuple(sorted(self._pending))
                self._pending.clear()
                generation = self._requested_generation
            error: Exception | None = None
            try:
                self._refresh(note_ids)
            except Exception as caught:  # Preserve fail-closed state for the next reader.
                error = caught
            with self._condition:
                self._completed_generation = max(self._completed_generation, generation)
                self._last_error = error
                self._condition.notify_all()


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
    identity_mapping_repository: IdentityMappingRepository | None = None
    conversation_root_resolver: ConversationRootResolver | None = None
    notes_service: NotesQueryService | None = None
    calendar_application: CalendarApplication | None = None
    notes_embedder: object | None = None
    pending_recorder: PendingWorkRepository | None = None
    vault_repository: VaultRepository | None = None
    canonical_schema: dict[str, object] | None = None
    clarification_classifier: ClarificationClassifier | None = None
    intelligent_notes_execute: (
        Callable[[str, Sequence[object]], NotePage | tuple[NotePage, OperationalEvidence]] | None
    ) = None
    direct_notes_mutations: DirectNoteMutationService | None = None
    direct_task_mutations: TaskDirectMutationService | None = None
    work_session_service: TaskWorkSessionService | None = None
    product_progress_store: ProductProgressStore | None = None
    notes_mutation_actor: (
        Callable[[AuthenticatedActorContext | None, ExternalPrincipal | None], object] | None
    ) = None
    monotonic: Callable[[], float] = perf_counter
    _execute_lock: Lock = field(default_factory=Lock, init=False, repr=False)
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
        if request_id is not None and self.product_progress_store is not None:
            self.product_progress_store.begin(actor, request_id)
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
                    return replay
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
                    return response
                clarification_store.clear()
                if decision == "CANCEL":
                    self._append_clarification_reply(
                        actor, conversation_id, request_id, user_request
                    )
                    response = self._control_response(request_id, "CANCEL")
                    if store is not None and fingerprint is not None:
                        store.save(request_id, fingerprint, response, _current_time()["timestamp"])
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
                    return self._finish_product_result(
                        result, store, fingerprint, clarification_store, force_replay=True
                    )
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
            return self._finish_product_result(result, store, fingerprint, clarification_store)

    def _execute_with_progress(
        self,
        actor: str,
        request_id: str | None,
        *args: object,
        **kwargs: object,
    ) -> ApplicationResult:
        """Run one product execution with a transient user-safe progress reporter bound to it."""
        if request_id is None or self.product_progress_store is None:
            return self.execute(*args, **kwargs)
        token = _PROGRESS_REPORTER.set(
            lambda stage, payload: self._record_progress_event(actor, request_id, stage, payload)
        )
        try:
            result = self.execute(*args, **kwargs)
            self.product_progress_store.update(actor, request_id, "finalizing", 94)
            return result
        finally:
            _PROGRESS_REPORTER.reset(token)

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
            return
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
    ) -> dict[str, object]:
        """Persist only one safely resumable decision and replay all product outcomes."""
        response = application_result_to_response(result)
        if response["product_outcome"] == "CLARIFY":
            view = self._clarification_view(result)
            response["clarification"] = view
            if clarification_store is not None:
                pending = self._pending_decision(result, view)
                if pending is not None:
                    clarification_store.replace(pending)
                elif result.clarification_code is None:
                    # A choice with no bounded safe options cannot be resumed in this v1.
                    # Keep the specific product reason so the UI can explain what was unresolved.
                    response["product_outcome"] = "CANNOT_ANSWER"
        if (
            store is not None
            and fingerprint is not None
            and (
                force_replay
                or result.affected_stable_note_ids
                or response["product_outcome"] == "CLARIFY"
            )
        ):
            store.save(result.request_id, fingerprint, response, _current_time()["timestamp"])
        return response

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
        """Execute one typed read-only Notes operation for the authenticated actor boundary.

        Actor resolution occurs even though current local-first Notes storage is root-bound. This
        preserves the existing outer isolation contract and prevents a route from bypassing it.
        """
        self._resolve_actor(authenticated_actor, external_principal)
        if self.notes_service is None:
            raise ValueError("Notes service is unavailable")
        if (
            operation in {"query", "backlinks", "intelligent"}
            and self.await_index_refresh is not None
        ):
            self.await_index_refresh()
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
            return {
                "kind": "mutation",
                "operation": result.operation,
                "note_id": result.task_id,
                "history": {"status": result.history.status.value},
                "work_sessions": [
                    _work_session_to_response(item)
                    for item in self.work_session_service.list_for_task(result.task_id)
                ],
            }
        if operation in {"delete_fact", "delete_note", "task_status", "task_subtask_create"}:
            if self.direct_notes_mutations is None or self.notes_mutation_actor is None:
                raise ValueError("Notes mutation service is unavailable")
            if self.await_index_refresh is not None:
                self.await_index_refresh()
            request_id = payload.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("Notes mutation request ID is invalid")
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
                if self.schedule_index_refresh is not None:
                    self.schedule_index_refresh((result.note_id,))
                elif operation == "task_status" and self.refresh_task_lifecycle_indexes is not None:
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
            return response
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


def build_runtime_from_environment() -> RuntimeComposition:
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
    pending_root.mkdir(parents=True, exist_ok=True)
    schema_path = _path_env("ODYSSEY_SCHEMA_PATH", str(project_root / "config/note-schema.json"))
    embedding_cache = _path_env(
        "ODYSSEY_EMBEDDING_CACHE",
        "/data/odyssey/runtime/phase11a-benchmark/embedding-cache",
    )
    with schema_path.open("r", encoding="utf-8") as schema_file:
        base_schema = json.load(schema_file)
    application_schema_extensions = (TASK_SCHEMA_EXTENSION,)
    schema = compose_application_schema(base_schema, application_schema_extensions)

    repository = VaultRepository(vault_root)
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
    ) -> ApplicationResult:
        """Execute Core with optional prior context and app-specialized interpretation evidence."""
        clock = _current_time()
        planner_context = {key: clock[key] for key in ("date", "time", "timezone")}
        capability_id = (
            domain_interpretation.capability_id if domain_interpretation is not None else None
        )
        execution_schema = planning_schema_for_capability(schema, capability_id)
        execution_semantic_index = application_semantic_indexes.get(capability_id, semantic_index)
        if resume_plan is not None:
            planner = _FixedRequestPlanner(resume_plan)
        elif domain_interpretation is None:
            planner = OpenAIRequestPlanner.from_environment(schema, planner_context)
        else:
            planner = OpenAIRequestPlanner.from_environment(
                schema, planner_context, domain_interpretation=domain_interpretation
            )
        if planner_decorator is not None:
            if resume_plan is not None:
                raise ValueError("resume plan cannot use a planner decorator")
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
            write_preflight_guard=write_preflight_guard,
            progress_callback=_emit_progress,
        )
        calls = getattr(planner, "last_provider_calls", ())
        return _replace_planner_provider_calls(result, calls)

    def refresh_indexes() -> None:
        """Rebuild both derived indexes from authoritative Markdown after a mutation."""
        runtime_root.mkdir(parents=True, exist_ok=True)
        context_index.rebuild(repository, schema, embedder)
        semantic_index.rebuild(repository, schema, embedder)
        for capability_id, index in application_semantic_indexes.items():
            index.rebuild(
                repository, planning_schema_for_capability(schema, capability_id), embedder
            )

    def refresh_affected_indexes(note_ids: Sequence[str]) -> None:
        """Incrementally reconcile exactly the notes changed by one serialized mutation.

        Incremental refresh verifies unrelated rows before changing derived state. Any contract
        mismatch, unrelated drift, or unsupported edge case falls back to the established atomic
        full rebuild so correctness remains the authority over latency.
        """
        try:
            context_index.refresh_notes(repository, schema, embedder, note_ids=note_ids)
            semantic_index.refresh_notes(repository, schema, embedder, note_ids=note_ids)
            for capability_id, index in application_semantic_indexes.items():
                index.refresh_notes(
                    repository,
                    planning_schema_for_capability(schema, capability_id),
                    embedder,
                    note_ids=note_ids,
                )
        except (ContextIndexError, SemanticIndexError, ValueError):
            refresh_indexes()

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

    refresh_indexes()

    def notes_mutation_actor(
        authenticated_actor: AuthenticatedActorContext | None,
        external_principal: ExternalPrincipal | None,
    ) -> object:
        """Apply the same trusted provenance mapping as ordinary runtime writes."""
        if external_principal is not None:
            authenticated_actor = identity_mapping_repository.resolve_existing(external_principal)
            authenticated_actor = AuthenticatedActorContext(authenticated_actor.stable_user_id)
        return _persistence_actor(actor, authenticated_actor)

    notes_service = NotesQueryService(repository, schema, context_index)
    calendar_application = CalendarApplication(
        CalendarQueryService(repository, schema, notes_service)
    )

    enabled_application_ids = _enabled_application_ids()
    application_catalog = ApplicationRegistry.from_descriptors((_TASKS_DESCRIPTOR,)).catalog(
        enabled_ids=enabled_application_ids
    )
    application_router = OpenAIApplicationRouter.from_environment(application_catalog)
    application_executors: dict[str, ApplicationExecutor] = {}
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

    def execute_temporal_core(
        source_text: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
    ) -> ApplicationResult:
        """Resolve only time semantics, then return the unchanged source to ordinary Core."""
        if authenticated_actor is not None and not isinstance(
            authenticated_actor, AuthenticatedActorContext
        ):
            raise ValueError("authenticated actor context is invalid")
        clock = _current_time()
        interpreter = OpenAITemporalInterpreter.from_environment(
            {key: clock[key] for key in ("date", "time", "timezone")}
        )
        _emit_progress("temporal.started")
        started = perf_counter()
        try:
            temporal = interpreter.interpret(source_text, conversation_context)
        except TemporalInterpreterError as error:
            duration_ms = max(0.0, (perf_counter() - started) * 1000)
            stage = OperationalStage(
                "temporal.interpretation",
                OperationalOutcome.FAILED,
                duration_ms,
                model=interpreter.model,
                reasoning_effort=interpreter.reasoning_effort,
                usage=normalize_provider_usage(interpreter.last_usage),
                error_category=type(error).__name__,
            )
            return ApplicationResult(
                request_id,
                ApplicationStatus.FAILED,
                (),
                (),
                planning_error="TEMPORAL_INTERPRETATION_FAILED",
                operational=OperationalEvidence(duration_ms, (stage,)),
            )
        duration_ms = max(0.0, (perf_counter() - started) * 1000)
        provider_calls: tuple[ProviderCallEvidence, ...] = ()
        if interpreter.last_call:
            provider_calls = (
                ProviderCallEvidence(
                    name="temporal.interpretation",
                    outcome=OperationalOutcome.COMPLETED,
                    duration_ms=duration_ms,
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
            duration_ms,
            model=interpreter.model,
            reasoning_effort=interpreter.reasoning_effort,
            usage=normalize_provider_usage(interpreter.last_usage),
            provider_calls=provider_calls,
        )
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
        )
        return replace(
            core_result,
            operational=OperationalEvidence(
                (core_result.operational.total_duration_ms or 0.0) + duration_ms,
                (stage, *core_result.operational.stages),
            ),
        )

    def execute_tasks(
        source_text: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
    ) -> ApplicationResult:
        """Interpret Tasks lifecycle, consume Temporal when needed, then delegate mutation to Core."""
        clock = _current_time()
        task_interpreter = OpenAITaskInterpreter.from_environment()
        task_started = perf_counter()
        try:
            task = task_interpreter.interpret(source_text, conversation_context)
        except TaskInterpretationError as error:
            duration = max(0.0, (perf_counter() - task_started) * 1000)
            stage = OperationalStage(
                "tasks.interpretation",
                OperationalOutcome.FAILED,
                duration,
                model=task_interpreter.model,
                reasoning_effort=task_interpreter.reasoning_effort,
                usage=normalize_provider_usage(task_interpreter.last_usage),
                error_category=type(error).__name__,
            )
            return ApplicationResult(
                request_id,
                ApplicationStatus.FAILED,
                (),
                (),
                planning_error="TASK_INTERPRETATION_FAILED",
                operational=OperationalEvidence(duration, (stage,)),
            )
        task_duration = max(0.0, (perf_counter() - task_started) * 1000)
        task_stage = OperationalStage(
            "tasks.interpretation",
            OperationalOutcome.COMPLETED,
            task_duration,
            model=task_interpreter.model,
            reasoning_effort=task_interpreter.reasoning_effort,
            usage=normalize_provider_usage(task_interpreter.last_usage),
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
            )

        temporal = None
        if task.requires_temporal():
            temporal_interpreter = OpenAITemporalInterpreter.from_environment(
                {key: clock[key] for key in ("date", "time", "timezone")}
            )
            temporal_started = perf_counter()
            try:
                temporal = temporal_interpreter.interpret(source_text, conversation_context)
                if any(
                    kind
                    not in {
                        TemporalResolutionKind.EXACT_DATE,
                        TemporalResolutionKind.EXACT_DATETIME,
                    }
                    for kind in temporal.kinds()
                ):
                    raise TemporalInterpreterError("Tasks requires exact temporal values")
            except TemporalInterpreterError as error:
                duration = max(0.0, (perf_counter() - temporal_started) * 1000)
                stages.append(
                    OperationalStage(
                        "temporal.interpretation",
                        OperationalOutcome.FAILED,
                        duration,
                        model=temporal_interpreter.model,
                        reasoning_effort=temporal_interpreter.reasoning_effort,
                        usage=normalize_provider_usage(temporal_interpreter.last_usage),
                        error_category=type(error).__name__,
                    )
                )
                return ApplicationResult(
                    request_id,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="TASK_TEMPORAL_UNRESOLVED",
                    operational=OperationalEvidence(total_duration + duration, tuple(stages)),
                )
            duration = max(0.0, (perf_counter() - temporal_started) * 1000)
            total_duration += duration
            stages.append(
                OperationalStage(
                    "temporal.interpretation",
                    OperationalOutcome.COMPLETED,
                    duration,
                    model=temporal_interpreter.model,
                    reasoning_effort=temporal_interpreter.reasoning_effort,
                    usage=normalize_provider_usage(temporal_interpreter.last_usage),
                )
            )
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
            if task.task_reference is not None:
                resolution_started = perf_counter()
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
                    )
                except Exception as error:
                    duration = max(0.0, (perf_counter() - resolution_started) * 1000)
                    stages.append(
                        OperationalStage(
                            "tasks.work_session_resolution",
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
                if task.operation is TaskOperation.START_WORK_SESSION:
                    assert resolved_task_id is not None and started_at is not None
                    mutation = work_session_service.start(
                        task_id=resolved_task_id,
                        started_at=started_at,
                        request_id=request_id,
                        actor=persistence_actor,
                        now=clock["timestamp"],
                    )
                elif task.operation is TaskOperation.STOP_WORK_SESSION:
                    assert resolved_task_id is not None and ended_at is not None
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
                (mutation.task_id,),
                history=mutation.history,
                operational=OperationalEvidence(total_duration, tuple(stages)),
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
            planner_decorator=lambda planner: TaskCorePlanner(planner, task),
            write_preflight_guard=TaskLifecycleGuard(task.operation),
        )
        return replace(
            core_result,
            operational=OperationalEvidence(
                total_duration + (core_result.operational.total_duration_ms or 0.0),
                (*stages, *core_result.operational.stages),
            ),
        )

    if "tasks" in enabled_application_ids:
        application_executors["tasks"] = execute_tasks

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
        identity_mapping_repository=identity_mapping_repository,
        conversation_root_resolver=conversation_root_resolver,
        notes_service=notes_service,
        calendar_application=calendar_application,
        notes_embedder=embedder,
        pending_recorder=pending_recorder,
        vault_repository=repository,
        canonical_schema=schema,
        clarification_classifier=OpenAILunaClarificationClassifier(),
        intelligent_notes_execute=intelligent_notes,
        direct_notes_mutations=DirectNoteMutationService(
            repository, schema, notes_service, history_recorder
        ),
        direct_task_mutations=direct_task_mutations,
        work_session_service=work_session_service,
        product_progress_store=ProductProgressStore(),
        notes_mutation_actor=notes_mutation_actor,
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
