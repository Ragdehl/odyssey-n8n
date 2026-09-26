"""Explicit production dependency composition for the Odyssey runtime bridge."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from threading import Lock, RLock
from time import perf_counter
from typing import cast
from zoneinfo import ZoneInfo

from odyssey_core.application import ApplicationResult, allocate_request_id, execute_request
from odyssey_core.clarification import (
    ClarificationChoice,
    ClarificationClassifier,
    ClarificationOption,
    LocalClarificationStore,
    OpenAILunaClarificationClassifier,
    PendingClarification,
    resolve_clarification_reply,
)
from odyssey_core.context import ContextFilter, ContextIndex
from odyssey_core.contextual import OpenAIContextualReasoner
from odyssey_core.contextual_calibration import load_contextual_calibration_examples
from odyssey_core.conversations import MAIN_CONVERSATION_ID
from odyssey_core.cost_aware_planning import LunaFirstRequestPlanner
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
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex
from odyssey_core.semantic_sets import OpenAILunaSemanticSetSelector
from odyssey_core.storage import VaultRepository

from .delivery_results import LocalDeliveryResultStore
from .serialization import application_result_to_response, operational_to_response

_VAULT_REPOSITORY_TYPE = VaultRepository

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


@dataclass(slots=True)
class RuntimeComposition:
    """Own one long-lived assembly of providers, repositories, indexes, and Core execution."""

    core_execute: Callable[..., ApplicationResult]
    refresh_indexes: Callable[[], None]
    identity_mapping_repository: IdentityMappingRepository | None = None
    conversation_root_resolver: ConversationRootResolver | None = None
    notes_service: NotesQueryService | None = None
    notes_embedder: object | None = None
    pending_recorder: PendingWorkRepository | None = None
    vault_repository: VaultRepository | None = None
    canonical_schema: dict[str, object] | None = None
    clarification_classifier: ClarificationClassifier | None = None
    intelligent_notes_execute: (
        Callable[[str, Sequence[object]], NotePage | tuple[NotePage, OperationalEvidence]] | None
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
                    choice = ClarificationChoice(decision, pending.evidence_guards[option_index])
                    result = self.execute(
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
            result = self.execute(
                user_request,
                request_id,
                conversation_id,
                AuthenticatedActorContext(actor)
                if authenticated_actor is not None or external_principal is not None
                else None,
                None,
            )
            return self._finish_product_result(result, store, fingerprint, clarification_store)

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
                    response["product_outcome"] = "CANNOT_ANSWER"
                    response["product_reason"] = "INCOMPLETE_EVIDENCE"
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
            or result.affected_stable_note_ids
            or len(result.action_results) != 1
            or not isinstance(view["options"], list)
            or not 1 < len(view["options"]) <= 4
        ):
            return None
        try:
            record = self.pending_recorder.read(result.pending_work.record_id)
            incomplete = record["incomplete_actions"]
            if len(incomplete) != 1:
                return None
            action = incomplete[0]["planned_action"]
            execution = incomplete[0]["execution_result"]
            if action["kind"] == "write":
                if (
                    len(action["units"]) != 1
                    or len(execution["unit_results"]) != 1
                    or execution["unit_results"][0]["reason"] != "ambiguous_existing_target"
                ):
                    return None
                candidates = execution["unit_results"][0]["candidates"]
            elif action["kind"] == "retrieve":
                if (
                    action["result_shape"] != "single"
                    or action["plan"]["entity"] is None
                    or execution["reason"] != "ambiguous_existing_target"
                ):
                    return None
                candidates = execution["candidate_note_ids"]
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
            return PendingClarification(
                record["user_request"],
                result.request_id,
                result.pending_work.record_id,
                options,
                tuple(guards),
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
            safe = (
                len(action.get("units", ())) == 1
                and len(evidence.get("unit_results", ())) == 1
                and evidence["unit_results"][0].get("reason") == "ambiguous_existing_target"
                and tuple(evidence["unit_results"][0].get("candidates", ())) == candidate_ids
            )
        elif action.get("kind") == "retrieve":
            safe = (
                action.get("result_shape") == "single"
                and action.get("plan", {}).get("entity") is not None
                and evidence.get("reason") == "ambiguous_existing_target"
                and tuple(evidence.get("candidate_note_ids", ())) == candidate_ids
            )
        else:
            safe = False
        if evidence.get("status") != "deferred" or not safe:
            raise ValueError("pending continuation is not one supported decision")
        plan = validate_request_plan(
            {"actions": [action], "limitations": record["planner_limitations"]},
            self.canonical_schema,
        )
        if len(plan.actions) != 1 or not isinstance(plan.actions[0], WriteAction | RetrieveAction):
            raise ValueError("pending continuation is unsupported")
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
                "options": [{"id": item.id, "label": item.label} for item in pending.options],
            },
            "actions": [],
            "affected_stable_note_ids": [],
            "operational": {"total_duration_ms": 0.0, "stages": []},
        }

    def _clarification_view(self, result: ApplicationResult) -> dict[str, object]:
        """Project only current, bounded, actor-local option labels for one unresolved decision."""
        candidates = next(
            (
                action.candidate_note_ids or (unit.candidates if unit is not None else ())
                for action in result.action_results
                for unit in action.unit_results or (None,)
                if action.reason == "ambiguous_existing_target"
                or unit is not None
                and unit.reason == "ambiguous_existing_target"
            ),
            (),
        )
        options: list[dict[str, str]] = []
        if self.notes_service is not None and 1 < len(candidates) <= 4:
            try:
                for note_id in candidates:
                    note = self.notes_service.detail(note_id).note
                    options.append({"id": note.id, "label": note.name})
            except (NotesQueryError, ValueError):
                options = []
        if len({option["label"].casefold() for option in options}) != len(options):
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
            return _notes_to_response(self.notes_service.detail(payload["note_id"]))
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
        started = self.monotonic()
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
            replace(
                stage,
                start_offset_ms=(
                    stage.start_offset_ms + core_offset_ms
                    if stage.start_offset_ms is not None
                    else None
                ),
            )
            for stage in result.operational.stages
        ]
        if result.affected_stable_note_ids:
            refresh_started = self.monotonic()
            try:
                self.refresh_indexes()
            except Exception as error:
                stages.append(
                    OperationalStage(
                        "index_refresh",
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
                    "index_refresh",
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
        schema = json.load(schema_file)

    repository = VaultRepository(vault_root)
    embedder = FastEmbedTextEmbedder(cache_dir=embedding_cache, local_files_only=True)
    context_index = ContextIndex(runtime_root / "context.sqlite3")
    semantic_index = SemanticEntityIndex(runtime_root / "semantic.sqlite3")
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
    ) -> ApplicationResult:
        """Execute one request with fresh Luna-first planning and persistence clock context."""
        clock = _current_time()
        planner_context = {key: clock[key] for key in ("date", "time", "timezone")}
        planner = (
            _FixedRequestPlanner(resume_plan)
            if resume_plan is not None
            else OpenAIRequestPlanner.from_environment(schema, planner_context)
        )
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
            schema=schema,
            context_index=context_index,
            semantic_index=semantic_index,
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
                LocalConversationStore(
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
        )
        calls = getattr(planner, "last_provider_calls", ())
        return _replace_planner_provider_calls(result, calls)

    def refresh_indexes() -> None:
        """Rebuild both derived indexes from authoritative Markdown after a mutation."""
        runtime_root.mkdir(parents=True, exist_ok=True)
        context_index.rebuild(repository, schema, embedder)
        semantic_index.rebuild(repository, schema, embedder)

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
    return RuntimeComposition(
        core_execute=core_execute,
        refresh_indexes=refresh_indexes,
        identity_mapping_repository=identity_mapping_repository,
        conversation_root_resolver=conversation_root_resolver,
        notes_service=NotesQueryService(repository, schema, context_index),
        notes_embedder=embedder,
        pending_recorder=pending_recorder,
        vault_repository=repository,
        canonical_schema=schema,
        clarification_classifier=OpenAILunaClarificationClassifier(),
        intelligent_notes_execute=intelligent_notes,
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
