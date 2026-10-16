"""Runtime Notes boundary integration for Tasks-owned Work Sessions."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from time import sleep

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskDirectMutationService,
    TaskWorkSessionService,
)
from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.delivery_results import DeliveryResultError, LocalDeliveryResultStore

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
SCHEMA = compose_application_schema(BASE, (TASK_SCHEMA_EXTENSION,))


class Embedder:
    model_name = "work-session-runtime-tests"
    model_version = "1"

    def embed_documents(self, texts):
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts):
        return [[1.0, 0.5] for _ in texts]


class NoReasoner:
    def resolve(self, request):
        return {"outcome": "UNRESOLVED", "id": None, "ambiguous_ids": []}, {"output_tokens": 0}


def test_runtime_task_detail_start_stop_and_edit_share_one_domain_service(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="odyssey.md",
        entity_id="task-odyssey",
        metadata={"name": "Trabajar en Odyssey", "type": "task", "status": "pending"},
        content="- Trabajar en Odyssey.\n",
        actor="fixture",
        now="2026-10-05T17:00:00+02:00",
    )
    context = ContextIndex(tmp_path / "context.sqlite3")
    context.rebuild(repository, SCHEMA, Embedder())
    refreshes: list[str] = []
    runtime = RuntimeComposition(
        core_execute=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Core called")),
        refresh_indexes=lambda: refreshes.append("refresh"),
        notes_service=NotesQueryService(repository, SCHEMA, context),
        work_session_service=TaskWorkSessionService(
            repository,
            SCHEMA,
            None,
            id_allocator=lambda: "session-runtime",
            activity_id_allocator=lambda: "activity-runtime",
        ),
        notes_mutation_actor=lambda *_args: "runtime-test",
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
    )

    detail = runtime.notes("detail", {"note_id": "task-odyssey"})
    assert detail["work_sessions"] == []
    assert set(detail["mutation"]) == {"revision", "source_hash"}

    started = runtime.notes(
        "work_session_start",
        {
            "note_id": "task-odyssey",
            "expected_revision": detail["mutation"]["revision"],
            "expected_source_hash": detail["mutation"]["source_hash"],
            "request_id": "runtime-start",
        },
    )
    assert started["operation"] == "work_session_started"
    assert len(started["work_sessions"]) == 1
    active = started["work_sessions"][0]
    assert active["id"] == "session-runtime"
    assert active["task_id"] == "task-odyssey"
    assert active["ended_at"] is None
    assert "path" not in active and "name" not in active

    # The same direct UI delivery is an actor-root durable replay: no second
    # session, persistence call, or derived-index work is permitted.
    assert (
        runtime.notes(
            "work_session_start",
            {
                "note_id": "task-odyssey",
                "expected_revision": detail["mutation"]["revision"],
                "expected_source_hash": detail["mutation"]["source_hash"],
                "request_id": "runtime-start",
            },
        )
        == started
    )
    assert len(repository.list_markdown_paths()) == 2

    stopped = runtime.notes(
        "work_session_stop",
        {
            "session_id": active["id"],
            "expected_revision": active["mutation"]["revision"],
            "expected_source_hash": active["mutation"]["source_hash"],
            "request_id": "runtime-stop",
        },
    )
    closed = stopped["work_sessions"][0]
    assert stopped["operation"] == "work_session_stopped"
    assert closed["ended_at"] is not None

    edited = runtime.notes(
        "work_session_edit",
        {
            "session_id": closed["id"],
            "started_at": "2026-10-05T17:30:00+02:00",
            "ended_at": "2026-10-05T18:15:00+02:00",
            "expected_revision": closed["mutation"]["revision"],
            "expected_source_hash": closed["mutation"]["source_hash"],
            "request_id": "runtime-edit",
        },
    )
    corrected = edited["work_sessions"][0]
    assert edited["operation"] == "work_session_edited"
    assert corrected["started_at"] == "2026-10-05T17:30:00+02:00"
    assert corrected["ended_at"] == "2026-10-05T18:15:00+02:00"
    assert refreshes == []

    activity = runtime.notes(
        "work_session_activity_add",
        {
            "session_id": corrected["id"],
            "text": "Corregido el calendario.",
            "expected_revision": corrected["mutation"]["revision"],
            "expected_source_hash": corrected["mutation"]["source_hash"],
            "request_id": "runtime-activity",
        },
    )
    logged = activity["work_sessions"][0]
    assert activity["operation"] == "work_session_activity_added"
    assert logged["activity"][0]["id"] == "activity-runtime"
    assert logged["activity"][0]["text"] == "Corregido el calendario."
    assert refreshes == []

    fresh_detail = runtime.notes("detail", {"note_id": "task-odyssey"})
    assert fresh_detail["work_sessions"] == activity["work_sessions"]

    deleted = runtime.notes(
        "work_session_delete",
        {
            "session_id": logged["id"],
            "expected_revision": logged["mutation"]["revision"],
            "expected_source_hash": logged["mutation"]["source_hash"],
            "request_id": "runtime-delete-session",
        },
    )
    assert deleted["operation"] == "work_session_deleted"
    assert deleted["note_id"] == "task-odyssey"
    assert deleted["work_sessions"] == []


def test_runtime_same_delivery_parallel_start_is_a_single_mutation(tmp_path: Path) -> None:
    """The replay check and writer must be one critical section, not two."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="task.md",
        entity_id="task-parallel",
        metadata={"name": "Trabajo", "type": "task", "status": "pending"},
        content="- Trabajo.\n",
        actor="fixture",
        now="2026-10-05T17:00:00+02:00",
    )
    context = ContextIndex(tmp_path / "context.sqlite3")
    context.rebuild(repository, SCHEMA, Embedder())

    class SlowWorkSessionService(TaskWorkSessionService):
        calls = 0

        def start(self, **kwargs):
            self.calls += 1
            sleep(0.08)  # Makes a check-outside-the-lock implementation race.
            return super().start(**kwargs)

    sessions = SlowWorkSessionService(
        repository, SCHEMA, None, id_allocator=lambda: "session-parallel"
    )
    runtime = RuntimeComposition(
        core_execute=lambda *args, **kwargs: None,
        refresh_indexes=lambda: None,
        notes_service=NotesQueryService(repository, SCHEMA, context),
        work_session_service=sessions,
        notes_mutation_actor=lambda *_args: "test",
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
    )
    detail = runtime.notes("detail", {"note_id": "task-parallel"})
    payload = {
        "note_id": "task-parallel",
        "expected_revision": detail["mutation"]["revision"],
        "expected_source_hash": detail["mutation"]["source_hash"],
        "request_id": "same-parallel-delivery",
    }
    barrier = Barrier(3)

    def deliver():
        barrier.wait()
        return runtime.notes("work_session_start", dict(payload))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(deliver)
        second = pool.submit(deliver)
        barrier.wait()
        assert first.result() == second.result()
    assert sessions.calls == 1
    assert len(repository.list_markdown_paths()) == 2
    with pytest.raises(ValueError, match="replay is unavailable"):
        runtime.notes("work_session_start", {**payload, "note_id": "different-task"})
    assert sessions.calls == 1


def test_unpersisted_result_blocks_blind_retry_of_known_physical_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="task.md",
        entity_id="task-receipt",
        metadata={"name": "Reconciliar", "type": "task", "status": "pending"},
        content="- Reconciliar.\n",
        actor="fixture",
        now="2026-10-05T17:00:00+02:00",
    )
    context = ContextIndex(tmp_path / "context.sqlite3")
    context.rebuild(repository, SCHEMA, Embedder())

    class RecordingSessions(TaskWorkSessionService):
        calls = 0

        def start(self, **kwargs):
            self.calls += 1
            return super().start(**kwargs)

    sessions = RecordingSessions(
        repository, SCHEMA, None, id_allocator=lambda: "session-unpersisted"
    )
    runtime = RuntimeComposition(
        core_execute=lambda *args, **kwargs: None,
        refresh_indexes=lambda: None,
        notes_service=NotesQueryService(repository, SCHEMA, context),
        work_session_service=sessions,
        notes_mutation_actor=lambda *_args: "test",
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
    )
    detail = runtime.notes("detail", {"note_id": "task-receipt"})
    payload = {
        "note_id": "task-receipt",
        "expected_revision": detail["mutation"]["revision"],
        "expected_source_hash": detail["mutation"]["source_hash"],
        "request_id": "uncertain-receipt",
    }
    original_save = LocalDeliveryResultStore.save

    def fail_after_write(self, *args, **kwargs):
        raise DeliveryResultError("simulated interrupted receipt storage")

    monkeypatch.setattr(LocalDeliveryResultStore, "save", fail_after_write)
    partial = runtime.notes("work_session_start", payload)
    assert partial["operation"] == "work_session_started"
    assert partial["partial"]["physical_write"] is True
    assert sessions.calls == 1
    assert len(repository.list_markdown_paths()) == 2

    monkeypatch.setattr(LocalDeliveryResultStore, "save", original_save)
    with pytest.raises(ValueError, match="unresolved previous attempt"):
        runtime.notes("work_session_start", payload)
    assert sessions.calls == 1
    assert len(repository.list_markdown_paths()) == 2


def test_runtime_subtask_create_is_a_typed_notes_mutation(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="parent.md",
        entity_id="parent",
        metadata={"name": "Padre", "type": "task", "status": "pending"},
        content="- Padre.\n",
        actor="fixture",
        now="2026-10-05T17:00:00+02:00",
    )
    embedder = Embedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    context.rebuild(repository, SCHEMA, embedder)
    semantic.rebuild(repository, SCHEMA, embedder)
    refreshes: list[str] = []
    runtime = RuntimeComposition(
        core_execute=lambda *args, **kwargs: None,
        refresh_indexes=lambda: refreshes.append("refresh"),
        notes_service=NotesQueryService(repository, SCHEMA, context),
        direct_notes_mutations=object(),
        direct_task_mutations=TaskDirectMutationService(
            repository,
            SCHEMA,
            None,
            semantic_index=semantic,
            embedder=embedder,
            contextual_reasoner=NoReasoner(),
            semantic_limit=5,
        ),
        notes_mutation_actor=lambda *_args: "runtime-test",
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
    )
    parent = runtime.notes("detail", {"note_id": "parent"})
    result = runtime.notes(
        "task_subtask_create",
        {
            "parent_note_id": "parent",
            "title": "Hija",
            "expected_revision": parent["mutation"]["revision"],
            "expected_source_hash": parent["mutation"]["source_hash"],
            "request_id": "subtask-create",
        },
    )
    assert result["operation"] == "task_subtask_created"
    assert result["child"] == {"id": result["note_id"], "name": "Hija", "status": "pending"}
    assert refreshes == ["refresh"]
    created_tasks = []
    for path in repository.list_markdown_paths():
        if path == "parent.md":
            continue
        note = parse_note(repository.read_text(path))
        if note.metadata.get("type") == "task":
            created_tasks.append(note)
    assert len(created_tasks) == 1
    child_note = created_tasks[0]
    assert child_note.metadata["status"] == "pending"
    assert child_note.content.count("Tarea superior:") == 1
    assert "[[parent|Padre]]" in child_note.content
    assert (
        runtime.notes(
            "task_subtask_create",
            {
                "parent_note_id": "parent",
                "title": "Hija",
                "expected_revision": parent["mutation"]["revision"],
                "expected_source_hash": parent["mutation"]["source_hash"],
                "request_id": "subtask-create",
            },
        )
        == result
    )
    assert refreshes == ["refresh"]
