"""Runtime Notes boundary integration for Tasks-owned Work Sessions."""

from __future__ import annotations

import json
from pathlib import Path

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION, TaskWorkSessionService
from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.storage import VaultRepository
from odyssey_runtime.composition import RuntimeComposition

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
            repository, SCHEMA, None, id_allocator=lambda: "session-runtime"
        ),
        notes_mutation_actor=lambda *_args: "runtime-test",
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
    assert refreshes == ["refresh", "refresh", "refresh"]

    fresh_detail = runtime.notes("detail", {"note_id": "task-odyssey"})
    assert fresh_detail["work_sessions"] == edited["work_sessions"]
