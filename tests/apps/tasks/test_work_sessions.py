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
    activity_ids = iter(("activity-one", "activity-two", "activity-three"))
    service = TaskWorkSessionService(
        repository,
        SCHEMA,
        None,
        id_allocator=lambda: next(ids),
        activity_id_allocator=lambda: next(activity_ids),
    )
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


def test_activity_can_be_added_edited_and_deleted_before_or_after_session_close(
    tmp_path: Path,
) -> None:
    repository, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repository)
    started = service.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="start-activity",
        actor="test",
        now="2026-10-05T18:00:00+02:00",
    )
    added = service.add_activity(
        session_id=started.session.id,
        text="  Corregido   el selector de notas. ",
        expected_revision=started.session.revision,
        expected_source_hash=started.session.source_hash,
        request_id="activity-add",
        actor="test",
        now="2026-10-05T18:14:00+02:00",
    )
    assert added.operation == "work_session_activity_added"
    assert [(item.id, item.created_at, item.text) for item in added.session.activity] == [
        ("activity-one", "2026-10-05T18:14:00+02:00", "Corregido el selector de notas.")
    ]
    raw = repository.read_text(added.path)
    assert "## Actividad" in raw
    assert "Corregido el selector de notas." in raw
    assert "odyssey-work-session-entry:activity-one:2026-10-05T18:14:00+02:00" in raw

    stopped = service.stop(
        session_id=added.session.id,
        ended_at="2026-10-05T19:00:00+02:00",
        expected_revision=added.session.revision,
        expected_source_hash=added.session.source_hash,
        request_id="activity-stop",
        actor="test",
        now="2026-10-05T19:00:00+02:00",
    )
    edited = service.edit_activity(
        session_id=stopped.session.id,
        activity_id="activity-one",
        text="Corregido el selector y añadidos tests.",
        expected_revision=stopped.session.revision,
        expected_source_hash=stopped.session.source_hash,
        request_id="activity-edit",
        actor="test",
        now="2026-10-05T19:05:00+02:00",
    )
    assert edited.session.activity[0].created_at == "2026-10-05T18:14:00+02:00"
    assert edited.session.activity[0].text == "Corregido el selector y añadidos tests."

    deleted = service.delete_activity(
        session_id=edited.session.id,
        activity_id="activity-one",
        expected_revision=edited.session.revision,
        expected_source_hash=edited.session.source_hash,
        request_id="activity-delete",
        actor="test",
        now="2026-10-05T19:10:00+02:00",
    )
    assert deleted.operation == "work_session_activity_deleted"
    assert deleted.session.activity == ()
    assert parse_note(repository.read_text(deleted.path)).content == ""


def test_activity_can_target_unique_active_or_date_scoped_session(tmp_path: Path) -> None:
    repository, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repository)
    started = service.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="start-current",
        actor="test",
        now="2026-10-05T18:00:00+02:00",
    )
    current = service.add_activity_for_task(
        task_id=None,
        text="He terminado los tests.",
        session_date=None,
        request_id="activity-current",
        actor="test",
        now="2026-10-05T18:20:00+02:00",
    )
    assert current.session.id == started.session.id
    assert current.session.activity[0].text == "He terminado los tests."
    stopped = service.stop(
        session_id=current.session.id,
        ended_at="2026-10-05T19:00:00+02:00",
        expected_revision=current.session.revision,
        expected_source_hash=current.session.source_hash,
        request_id="stop-current",
        actor="test",
        now="2026-10-05T19:00:00+02:00",
    )
    dated = service.add_activity_for_task(
        task_id="task-odyssey",
        text="Revisado el calendario.",
        session_date="2026-10-05",
        request_id="activity-dated",
        actor="test",
        now="2026-10-05T19:10:00+02:00",
    )
    assert dated.session.id == stopped.session.id
    assert [item.text for item in dated.session.activity] == [
        "He terminado los tests.",
        "Revisado el calendario.",
    ]


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


def test_work_session_can_be_deleted_with_current_stale_state_tokens(tmp_path: Path) -> None:
    repository, service = _build(tmp_path)
    revision, source_hash = _task_tokens(repository)
    started = service.start(
        task_id="task-odyssey",
        started_at="2026-10-05T18:00:00+02:00",
        expected_task_revision=revision,
        expected_task_source_hash=source_hash,
        request_id="delete-start",
        actor="test",
        now="2026-10-05T18:00:00+02:00",
    )
    deleted = service.delete(
        session_id=started.session.id,
        expected_revision=started.session.revision,
        expected_source_hash=started.session.source_hash,
        request_id="delete-session",
        actor="test",
        now="2026-10-05T18:05:00+02:00",
    )
    assert deleted.operation == "work_session_deleted"
    assert deleted.task_id == "task-odyssey"
    assert service.list_for_task("task-odyssey") == ()
    retired = parse_note(repository.read_text(deleted.path))
    assert retired.metadata["deleted"] is True
    assert retired.metadata["revision"] == started.session.revision + 1

    with pytest.raises(WorkSessionError, match="STALE_NOTE"):
        service.delete(
            session_id=started.session.id,
            expected_revision=started.session.revision,
            expected_source_hash=started.session.source_hash,
            request_id="delete-session-again",
            actor="test",
            now="2026-10-05T18:06:00+02:00",
        )
