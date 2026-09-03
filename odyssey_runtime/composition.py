"""Explicit production dependency composition for the Odyssey runtime bridge."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from odyssey_core.application import ApplicationResult, execute_request
from odyssey_core.context import ContextIndex
from odyssey_core.contextual import OpenAIContextualReasoner
from odyssey_core.fact_selection import OpenAILunaFactSelector
from odyssey_core.git_history import GitHistoryRecorder
from odyssey_core.materialization import OpenAILunaWriter
from odyssey_core.pending_work import PendingWorkRepository
from odyssey_core.request_planning import OpenAIRequestPlanner
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex
from odyssey_core.storage import VaultRepository


@dataclass(slots=True)
class RuntimeComposition:
    """Own one long-lived assembly of providers, repositories, indexes, and Core execution."""

    core_execute: Callable[[str], ApplicationResult]
    refresh_indexes: Callable[[], None]

    def execute(self, user_request: str) -> ApplicationResult:
        """Execute one request and refresh derived indexes after affected mutations.

        Args:
            user_request: Raw request accepted by the Core application boundary.

        Returns:
            The typed Core ApplicationResult after any required derived-index refresh.
        """
        result = self.core_execute(user_request)
        if result.affected_stable_note_ids:
            self.refresh_indexes()
        return result


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
    contextual_reasoner = OpenAIContextualReasoner(
        os.environ.get("ODYSSEY_CONTEXTUAL_MODEL", "gpt-5.6-sol"),
        reasoning_effort="medium",
    )
    writer = OpenAILunaWriter()
    fact_selector = OpenAILunaFactSelector()
    pending_recorder = PendingWorkRepository(pending_root)
    history_recorder = GitHistoryRecorder(vault_root)
    actor = os.environ.get("ODYSSEY_ACTOR", "odyssey-runtime")
    context_limit = _positive_int_env("ODYSSEY_CONTEXT_LIMIT", 10)

    def core_execute(user_request: str) -> ApplicationResult:
        """Execute one request with fresh planner and persistence clock context."""
        clock = _current_time()
        planner_context = {key: clock[key] for key in ("date", "time", "timezone")}
        planner = OpenAIRequestPlanner.from_environment(schema, planner_context)
        return execute_request(
            user_request,
            planner=planner,
            repository=repository,
            schema=schema,
            context_index=context_index,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            actor=actor,
            now=clock["timestamp"],
            context_limit=context_limit,
            writer=writer,
            fact_selector=fact_selector,
            pending_recorder=pending_recorder,
            history_recorder=history_recorder,
        )

    def refresh_indexes() -> None:
        """Rebuild both derived indexes from authoritative Markdown after a mutation."""
        runtime_root.mkdir(parents=True, exist_ok=True)
        context_index.rebuild(repository, schema, embedder)
        semantic_index.rebuild(repository, schema, embedder)

    refresh_indexes()
    return RuntimeComposition(core_execute=core_execute, refresh_indexes=refresh_indexes)


def _path_env(name: str, default: str) -> Path:
    """Read one non-empty filesystem path from environment configuration."""
    value = os.environ.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return Path(value).expanduser()


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
