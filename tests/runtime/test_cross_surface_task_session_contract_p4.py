"""Canonical same-service parity for chat-owned and UI-owned Work Session operations.

The chat *interpretation/HTTP* is NOT mocked as covered here: these tests start
at its proven Tasks domain-service call boundary. That semantic routing remains
a separate live end-to-end gate. All effects use real Core Markdown/E3 in
isolated vaults and confirm that direct UI and task-owned calls cannot diverge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import odyssey_runtime.composition as composition
from odyssey_apps.tasks import TaskDirectMutationService, TaskWorkSessionService
from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_runtime.composition import RuntimeComposition
from tests.apps.tasks.test_work_session_runtime import SCHEMA, Embedder, NoReasoner

CLOCK_START = "2026-10-05T18:00:00+02:00"
CLOCK_STOP = "2026-10-05T19:00:00+02:00"
CLOCK_EDIT_START = "2026-10-05T17:45:00+02:00"
CLOCK_EDIT_STOP = "2026-10-05T18:45:00+02:00"


def _build(tmp_path: Path, *, with_direct: bool = False):
    tmp_path.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="parent.md",
        entity_id="task-parent",
        metadata={"name": "Desarrollar Odyssey", "type": "task", "status": "pending"},
        content="- Desarrollar Odyssey.\n",
        actor="fixture",
        now="2026-10-05T17:00:00+02:00",
    )
    embedder = Embedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    context.rebuild(repository, SCHEMA, embedder)
    semantic.rebuild(repository, SCHEMA, embedder)
    sessions = TaskWorkSessionService(
        repository,
        SCHEMA,
        None,
        id_allocator=lambda: "session-shared",
        activity_id_allocator=lambda: "activity-shared",
    )
    direct = TaskDirectMutationService(
        repository,
        SCHEMA,
        None,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=NoReasoner(),
        semantic_limit=5,
    )

    def refresh():
        context.rebuild(repository, SCHEMA, embedder)
        semantic.rebuild(repository, SCHEMA, embedder)

    runtime = RuntimeComposition(
        core_execute=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("UI mutation must not invoke an LLM/Core planner")
        ),
        refresh_indexes=refresh,
        notes_service=NotesQueryService(repository, SCHEMA, context),
        direct_notes_mutations=object() if with_direct else None,
        direct_task_mutations=direct if with_direct else None,
        work_session_service=sessions,
        notes_mutation_actor=lambda *_args: "runtime-test",
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
    )
    return repository, runtime, sessions


def _mutation(value: dict):
    return {
        "expected_revision": value["mutation"]["revision"],
        "expected_source_hash": value["mutation"]["source_hash"],
    }


def _session_note(repository: VaultRepository):
    matches = [
        parse_note(repository.read_text(p))
        for p in repository.list_markdown_paths()
        if parse_note(repository.read_text(p)).metadata.get("type") == "work_session"
    ]
    assert len(matches) == 1
    validate_note(matches[0], SCHEMA)
    return matches[0]


def _assert_canonical_equal(left: VaultRepository, right: VaultRepository):
    one, two = _session_note(left), _session_note(right)
    for field in ["id", "type", "task_id", "started_at", "ended_at", "deleted", "revision"]:
        assert one.metadata.get(field) == two.metadata.get(field), field
    assert one.content == two.content
    assert parse_note(left.read_text("parent.md")).metadata["status"] == "pending"
    assert parse_note(right.read_text("parent.md")).metadata["status"] == "pending"


def test_ui_and_chat_domain_entry_use_identical_canonical_work_session_service(
    tmp_path, monkeypatch
):
    ui_repo, ui, _ = _build(tmp_path / "ui")
    chat_repo, _, chat_service = _build(tmp_path / "chat")
    # Chat's verified post-interpretation service entry and UI's Notes entry
    # receive identical timestamps/actors and must produce equivalent Markdown.
    now = [CLOCK_START]
    monkeypatch.setattr(composition, "_current_time", lambda: {"timestamp": now[0]})
    task = ui.notes("detail", {"note_id": "task-parent"})
    source = {"note_id": "task-parent", **_mutation(task), "request_id": "shared-start"}
    started = ui.notes("work_session_start", source)
    assert ui.notes("work_session_start", source) == started  # replay has zero effects
    chat_service.start(
        task_id="task-parent",
        started_at=CLOCK_START,
        request_id="shared-start",
        actor="runtime-test",
        now=CLOCK_START,
    )
    _assert_canonical_equal(ui_repo, chat_repo)

    ui_session = started["work_sessions"][0]
    activity = {
        "session_id": ui_session["id"],
        "text": "Probadas tres rutas.",
        **_mutation(ui_session),
        "request_id": "shared-activity",
    }
    added = ui.notes("work_session_activity_add", activity)
    assert ui.notes("work_session_activity_add", activity) == added
    chat_service.add_activity_for_task(
        task_id="task-parent",
        text="Probadas tres rutas.",
        session_date=None,
        request_id="shared-activity",
        actor="runtime-test",
        now=CLOCK_START,
    )
    _assert_canonical_equal(ui_repo, chat_repo)

    now[0] = CLOCK_STOP
    ui_session = added["work_sessions"][0]
    stop = {"session_id": ui_session["id"], **_mutation(ui_session), "request_id": "shared-stop"}
    stopped = ui.notes("work_session_stop", stop)
    assert ui.notes("work_session_stop", stop) == stopped
    chat_service.stop_for_task(
        task_id="task-parent",
        ended_at=CLOCK_STOP,
        request_id="shared-stop",
        actor="runtime-test",
        now=CLOCK_STOP,
    )
    _assert_canonical_equal(ui_repo, chat_repo)

    ui_session = stopped["work_sessions"][0]
    correction = {
        "session_id": ui_session["id"],
        "started_at": CLOCK_EDIT_START,
        "ended_at": CLOCK_EDIT_STOP,
        **_mutation(ui_session),
        "request_id": "shared-edit",
    }
    edited = ui.notes("work_session_edit", correction)
    assert ui.notes("work_session_edit", correction) == edited
    chat_service.edit_for_task(
        task_id="task-parent",
        started_at=CLOCK_EDIT_START,
        ended_at=CLOCK_EDIT_STOP,
        request_id="shared-edit",
        actor="runtime-test",
        now=CLOCK_STOP,
    )
    _assert_canonical_equal(ui_repo, chat_repo)
    assert _session_note(ui_repo).metadata["revision"] == 4

    # A stale UI write cannot override the chat-domain shared state.
    with pytest.raises(ValueError, match="STALE_NOTE"):
        ui.notes("work_session_edit", {**correction, "request_id": "stale-different"})
    _assert_canonical_equal(ui_repo, chat_repo)


@pytest.mark.parametrize(
    "title",
    [
        "Revisar las pruebas",
        "Organizar el proyecto",
        "Corregir enlaces",
        "Enviar factura 2026",
        "Documentar API",
        "Verificar índices",
        "Actualizar notas",
        "Preparar informe",
        "Evaluar rendimiento",
        "Probar varios idiomas",
        "Comprobar el calendario",
        "Revisar mañana",
    ],
)
def test_parent_subtask_session_checkbox_chain_is_one_canonical_vault(tmp_path, monkeypatch, title):
    repository, ui, _ = _build(tmp_path / "chain", with_direct=True)
    now = [CLOCK_START]
    monkeypatch.setattr(composition, "_current_time", lambda: {"timestamp": now[0]})
    parent = ui.notes("detail", {"note_id": "task-parent"})
    create = {
        "parent_note_id": "task-parent",
        "title": title,
        **_mutation(parent),
        "request_id": "chain-child",
    }
    child = ui.notes("task_subtask_create", create)
    assert ui.notes("task_subtask_create", create) == child
    child_id = child["note_id"]
    child_detail = ui.notes("detail", {"note_id": child_id})
    child_path = next(
        p
        for p in repository.list_markdown_paths()
        if parse_note(repository.read_text(p)).metadata["id"] == child_id
    )
    child_note = parse_note(repository.read_text(child_path))
    assert child_note.metadata["type"] == "task"
    assert child_note.content.count("Tarea superior:") == 1
    assert "[[parent|Desarrollar Odyssey]]" in child_note.content

    start = {"note_id": child_id, **_mutation(child_detail), "request_id": "chain-start"}
    started = ui.notes("work_session_start", start)
    assert ui.notes("work_session_start", start) == started
    session = started["work_sessions"][0]
    assert session["task_id"] == child_id
    assert parse_note(repository.read_text(child_path)).metadata["status"] == "pending"
    now[0] = CLOCK_STOP
    stop = {"session_id": session["id"], **_mutation(session), "request_id": "chain-stop"}
    stopped = ui.notes("work_session_stop", stop)
    assert ui.notes("work_session_stop", stop) == stopped
    child_detail = ui.notes("detail", {"note_id": child_id})
    complete = {
        "note_id": child_id,
        "completed": True,
        **_mutation(child_detail),
        "request_id": "chain-complete",
    }
    finished = ui.notes("task_status", complete)
    assert ui.notes("task_status", complete) == finished
    assert finished["status"] == "completed"
    child_note = parse_note(repository.read_text(child_path))
    assert child_note.metadata["status"] == "completed"
    assert parse_note(repository.read_text("parent.md")).metadata["status"] == "pending"
    assert _session_note(repository).metadata["task_id"] == child_id
    # A completed Task may not be activated again even with fresh tokens.
    with pytest.raises(ValueError, match="WORK_SESSION_TASK_CLOSED"):
        ui.notes(
            "work_session_start",
            {
                "note_id": child_id,
                **_mutation(ui.notes("detail", {"note_id": child_id})),
                "request_id": "chain-forbidden-start",
            },
        )
