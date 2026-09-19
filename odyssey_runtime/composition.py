"""Explicit production dependency composition for the Odyssey runtime bridge."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import cast
from zoneinfo import ZoneInfo

from odyssey_core.application import ApplicationResult, allocate_request_id, execute_request
from odyssey_core.context import ContextIndex
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
from odyssey_core.observability import (
    OperationalOutcome,
    OperationalStage,
    ProviderCallEvidence,
)
from odyssey_core.pending_work import PendingWorkRepository
from odyssey_core.persistence import ActorInput
from odyssey_core.request_planning import PlannerClarification, RequestPlan, RetrieveAction
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex
from odyssey_core.storage import VaultRepository

_VAULT_REPOSITORY_TYPE = VaultRepository

# Preserve the existing runtime composition injection seam while changing its production target.
# Runtime tests and downstream composition overrides can keep patching this symbol; it now points to
# the validated Luna-first planner rather than the former Sol-only planner.
OpenAIRequestPlanner = LunaFirstRequestPlanner


@dataclass(slots=True)
class RuntimeComposition:
    """Own one long-lived assembly of providers, repositories, indexes, and Core execution."""

    core_execute: Callable[..., ApplicationResult]
    refresh_indexes: Callable[[], None]
    identity_mapping_repository: IdentityMappingRepository | None = None
    conversation_root_resolver: ConversationRootResolver | None = None
    notes_service: NotesQueryService | None = None
    notes_embedder: object | None = None
    intelligent_notes_execute: Callable[[str, Sequence[object]], NotePage] | None = None
    monotonic: Callable[[], float] = perf_counter

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
            return _notes_to_response(
                self.intelligent_notes_execute(payload["query"], payload.get("filters", ()))
            )
        raise ValueError("Notes operation is unsupported")

    def execute(
        self,
        user_request: str,
        request_id: str | None = None,
        conversation_id: str | None = None,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
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
            self._conversation_store(resolved_actor).append_turn(
                request_id=request_id,
                role="user",
                text=user_request,
                created_at=_current_time()["timestamp"],
            )
        started = self.monotonic()
        if conversation_id is None:
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
        stages = list(result.operational.stages)
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
                    )
                )
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
            stages.append(
                OperationalStage(
                    "index_refresh",
                    OperationalOutcome.COMPLETED,
                    max(0.0, (self.monotonic() - refresh_started) * 1000),
                )
            )
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
        return self._conversation_store(actor).load_main_page()

    def append_conversation_turn(
        self,
        conversation_id: str,
        request_id: str,
        role: str,
        text: str,
        status: str | None = None,
        request_detail: dict[str, object] | None = None,
        authenticated_actor: AuthenticatedActorContext | None = None,
        external_principal: ExternalPrincipal | None = None,
    ) -> dict[str, object]:
        """Persist one visible turn idempotently for the trusted actor."""
        actor = self._resolve_actor(authenticated_actor, external_principal)
        if conversation_id != MAIN_CONVERSATION_ID:
            raise ValueError("only the main conversation is available")
        return self._conversation_store(actor).append_turn(
            request_id=request_id,
            role=role,
            text=text,
            created_at=_current_time()["timestamp"],
            status=status,
            request_detail=request_detail,
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
    ) -> ApplicationResult:
        """Execute one request with fresh Luna-first planning and persistence clock context."""
        clock = _current_time()
        planner_context = {key: clock[key] for key in ("date", "time", "timezone")}
        planner = OpenAIRequestPlanner.from_environment(schema, planner_context)
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
        )
        calls = getattr(planner, "last_provider_calls", ())
        return _replace_planner_provider_calls(result, calls)

    def refresh_indexes() -> None:
        """Rebuild both derived indexes from authoritative Markdown after a mutation."""
        runtime_root.mkdir(parents=True, exist_ok=True)
        context_index.rebuild(repository, schema, embedder)
        semantic_index.rebuild(repository, schema, embedder)

    def intelligent_notes(query: str, explicit_filters: Sequence[object]) -> NotePage:
        """Plan one explicit Notes request and accept only a single direct RetrieveAction.

        This keeps planner interpretation singular. Clarifications, writes, delegation,
        multi-branch plans, and unimplemented graph traversal do not degrade into a lossy search.
        """
        clock = _current_time()
        planner = OpenAIRequestPlanner.from_environment(
            schema, {key: clock[key] for key in ("date", "time", "timezone")}
        )
        result = planner.plan(query)
        if (
            isinstance(result, PlannerClarification)
            or not isinstance(result, RequestPlan)
            or len(result.actions) != 1
            or not isinstance(result.actions[0], RetrieveAction)
            or result.actions[0].plan.link_scope is not None
        ):
            raise NotesQueryError("Intelligent Notes request needs clarification")
        action = result.actions[0]
        return NotesQueryService(repository, schema, context_index).query(
            mode="intelligent",
            query=action.plan.query,
            filters=[*explicit_filters, *action.plan.filters],
            embedder=embedder,
        )

    refresh_indexes()
    return RuntimeComposition(
        core_execute=core_execute,
        refresh_indexes=refresh_indexes,
        identity_mapping_repository=identity_mapping_repository,
        conversation_root_resolver=conversation_root_resolver,
        notes_service=NotesQueryService(repository, schema, context_index),
        notes_embedder=embedder,
        intelligent_notes_execute=intelligent_notes,
    )


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
        }
    if isinstance(value, NoteDetail):
        return {
            "kind": "detail",
            "note": _summary_to_response(value.note),
            "body": value.body,
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
                    "context": item.context,
                }
                for item in value.items
            ],
            "total": value.total,
            "next_cursor": value.next_cursor,
        }
    raise TypeError("Notes response is invalid")


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
