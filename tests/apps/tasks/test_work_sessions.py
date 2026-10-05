"""Deterministic canonical Work Session lifecycle owned by Tasks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskWorkSessionService,
    WorkSessionError,
)
from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
SCHEMA = compose_application_schema(BASE, (TASK_SCHEMA_EXTENSION,))


class Embedder:
    model_name = "work-session-tests"
    model_version = "1"

    def embed_documents(self, texts):
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts):
        return [[1.0, 0.5] for _ in texts]


def _build(tmp_path: Path):
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
        now="2026-10-05T16:00:00+02:00",
    )
    create_entity(
        repository,
        SCHEMA,
        path="taxes.md",
        entity_id="task-taxes",
        metadata={"name": "Preparar impuestos", "type": "task", "status": "pending"},
        content="- Preparar impuestos.\n",
        actor="fixture",
        now="2026-10-05T16:00:00+02:00",
    )
    ids = iter(("session-one", "session-two", "session-three"))
    service = TaskWorkSessionService(repository, SCHEMA, None, id_allocator=lambda: next(ids))
    return repository, service


def _task_tokens(repository: VaultRepository, path: str = "odyssey.md") -> tuple[int, str]:
    raw = repository.read_text(path)
    return parse_note(raw).metadata["revision"], hashlib.sha256(raw.encode()).hexdigest()


def test_start_stop_and_edit_work_session_preserve_task_lifecycle(tmp_path: Path) -> None:
    repository, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repository)
    started = service.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="start-session",
        actor="test",
        now="2026-10-05T18:00:00+02:00",
    )
    assert started.operation == "work_session_started"
    assert started.session.ended_at is None
    task = parse_note(repository.read_text("odyssey.md"))
    assert task.metadata["status"] == "pending"
    assert task.metadata["revision"] == revision

    stopped = service.stop(
        session_id=started.session.id,
        ended_at="2026-10-05T19:15:00+02:00",
        expected_revision=started.session.revision,
        expected_source_hash=started.session.source_hash,
        request_id="stop-session",
        actor="test",
        now="2026-10-05T19:15:00+02:00",
    )
    assert stopped.operation == "work_session_stopped"
    assert stopped.session.ended_at == "2026-10-05T19:15:00+02:00"

    edited = service.edit(
        session_id=stopped.session.id,
        started_at="2026-10-05T17:45:00+02:00",
        ended_at="2026-10-05T19:00:00+02:00",
        expected_revision=stopped.session.revision,
        expected_source_hash=stopped.session.source_hash,
        request_id="edit-session",
        actor="test",
        now="2026-10-05T19:20:00+02:00",
    )
    assert edited.operation == "work_session_edited"
    assert edited.session.started_at == "2026-10-05T17:45:00+02:00"
    assert edited.session.ended_at == "2026-10-05T19:00:00+02:00"
    session_note = parse_note(repository.read_text(edited.path))
    validate_note(session_note, SCHEMA)
    assert session_note.metadata["task_id"] == "task-odyssey"
    assert session_note.content == ""


def test_only_one_active_session_is_allowed_globally(tmp_path: Path) -> None:
    repository, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repository)
    service.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="start-one",
        actor="test",
        now="2026-10-05T18:00:00+02:00",
    )
    tax_revision, tax_hash = _task_tokens(repository, "taxes.md")
    with pytest.raises(WorkSessionError, match="WORK_SESSION_ALREADY_ACTIVE") as exc:
        service.start(
            task_id="task-taxes",
            started_at="2026-10-05T18:10:00+02:00",
            expected_task_revision=tax_revision,
            expected_task_source_hash=tax_hash,
            request_id="start-two",
            actor="test",
            now="2026-10-05T18:10:00+02:00",
        )
    assert exc.value.active_task_id == "task-odyssey"


def test_stale_session_and_invalid_interval_fail_closed(tmp_path: Path) -> None:
    repository, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repository)
    started = service.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="start",
        actor="test",
        now="2026-10-05T18:00:00+02:00",
    )
    with pytest.raises(WorkSessionError, match="STALE_NOTE"):
        service.stop(
            session_id=started.session.id,
            ended_at="2026-10-05T18:10:00+02:00",
            expected_revision=started.session.revision + 1,
            expected_source_hash=started.session.source_hash,
            request_id="stale",
            actor="test",
            now="2026-10-05T18:10:00+02:00",
        )
    with pytest.raises(WorkSessionError, match="WORK_SESSION_END_BEFORE_START"):
        service.stop(
            session_id=started.session.id,
            ended_at="2026-10-05T17:59:00+02:00",
            expected_revision=started.session.revision,
            expected_source_hash=started.session.source_hash,
            request_id="invalid",
            actor="test",
            now="2026-10-05T18:10:00+02:00",
        )


def test_work_sessions_are_hidden_from_normal_notes_feed(tmp_path: Path) -> None:
    repository, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repository)
    service.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="start",
        actor="test",
        now="2026-10-05T18:00:00+02:00",
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    context = ContextIndex(runtime / "context.sqlite3")
    context.rebuild(repository, SCHEMA, Embedder())
    notes = NotesQueryService(repository, SCHEMA, context)
    page = notes.query(mode="feed", sort="updated_desc")
    assert {item.type for item in page.items} == {"task"}
    assert {item.id for item in page.items} == {"task-odyssey", "task-taxes"}
