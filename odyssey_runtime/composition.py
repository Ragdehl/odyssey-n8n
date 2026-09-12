"""Explicit production dependency composition for the Odyssey runtime bridge."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
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
from odyssey_core.cost_aware_planning import LunaFirstRequestPlanner
from odyssey_core.fact_selection import OpenAILunaFactSelector
from odyssey_core.git_history import GitHistoryRecorder
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.materialization import OpenAILunaWriter
from odyssey_core.observability import (
    OperationalOutcome,
    OperationalStage,
    ProviderCallEvidence,
)
from odyssey_core.pending_work import PendingWorkRepository
from odyssey_core.persistence import ActorInput
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex
from odyssey_core.storage import VaultRepository

# Preserve the existing runtime composition injection seam while changing its production target.
# Runtime tests and downstream composition overrides can keep patching this symbol; it now points to
# the validated Luna-first planner rather than the former Sol-only planner.
OpenAIRequestPlanner = LunaFirstRequestPlanner


@dataclass(slots=True)
class RuntimeComposition:
    """Own one long-lived assembly of providers, repositories, indexes, and Core execution."""

    core_execute: Callable[..., ApplicationResult]
    refresh_indexes: Callable[[], None]
    monotonic: Callable[[], float] = perf_counter

    def execute(
        self,
        user_request: str,
        request_id: str | None = None,
        authenticated_actor: AuthenticatedActorContext | None = None,
    ) -> ApplicationResult:
        """Execute one request and refresh derived indexes after affected mutations.

        Args:
            user_request: Raw request accepted by the Core application boundary.
            request_id: Optional identity supplied by the delivery boundary and reused by retries.

        Returns:
            The typed Core ApplicationResult after any required derived-index refresh.
        """
        started = self.monotonic()
        if authenticated_actor is None:
            result = self.core_execute(user_request, request_id)
        else:
            result = self.core_execute(user_request, request_id, authenticated_actor)
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
    history_recorder = GitHistoryRecorder(vault_root)
    actor = os.environ.get("ODYSSEY_ACTOR", "odyssey-runtime")
    context_limit = _positive_int_env("ODYSSEY_CONTEXT_LIMIT", 10)

    def core_execute(
        user_request: str,
        request_id: str | None = None,
        authenticated_actor: AuthenticatedActorContext | None = None,
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
        )
        calls = getattr(planner, "last_provider_calls", ())
        return _replace_planner_provider_calls(result, calls)

    def refresh_indexes() -> None:
        """Rebuild both derived indexes from authoritative Markdown after a mutation."""
        runtime_root.mkdir(parents=True, exist_ok=True)
        context_index.rebuild(repository, schema, embedder)
        semantic_index.rebuild(repository, schema, embedder)

    refresh_indexes()
    return RuntimeComposition(core_execute=core_execute, refresh_indexes=refresh_indexes)


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
