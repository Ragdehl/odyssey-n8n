"""P4 chat routing and UI use ONE concrete Work Session domain service.

Only Router and scope auditor responses are frozen; canonical Markdown, E3
receipt, chat task delegate and UI mutation are all real and actor-isolated.
"""

from __future__ import annotations

from uuid import uuid4

from odyssey_apps.tasks import TaskWorkSessionService
from odyssey_core import create_entity
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from tests.runtime.test_whole_source_light_product_p4 import SCHEMA, RecordedClient, _fixture

CLOCK = "2026-10-16T18:00:00+02:00"


def test_taskonly_chat_then_actual_ui_activity_and_stop_same_canonical_session(
    tmp_path, monkeypatch
):
    repo, actor, executor, runtime = _fixture(tmp_path)
    task_id = "task-same-source"
    create_entity(
        repo,
        SCHEMA,
        path="task.md",
        entity_id=task_id,
        metadata={"name": "Preparar informe de prueba", "type": "task", "status": "pending"},
        content="- Preparar informe de prueba.\n",
        actor="fixture",
        now=CLOCK,
    )
    executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    domain = TaskWorkSessionService(
        repo,
        SCHEMA,
        None,
        id_allocator=lambda: "session-" + str(uuid4()),
        activity_id_allocator=lambda: "activity-" + str(uuid4()),
    )
    calls = []

    def chat_delegate(source, delivery, identity):
        assert source == "Empieza a trabajar en Preparar informe de prueba."
        assert identity.stable_user_id == actor.stable_user_id
        effect = domain.start(
            task_id=task_id,
            started_at=CLOCK,
            request_id=delivery,
            actor=identity.stable_user_id,
            now=CLOCK,
        )
        calls.append(effect.session.id)
        return ApplicationResult(delivery, ApplicationStatus.COMPLETED, (), (effect.session.id,))

    executor.task_delegate = chat_delegate
    source = "Empieza a trabajar en Preparar informe de prueba."
    executor.client = RecordedClient(
        [
            {
                "capabilities": ["tasks"],
                "reason": "single",
                "interpretation": "joint",
                "app_scopes": [],
                "self_relation_span": None,
            },
            {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": source},
        ]
    )
    runtime.notes_service = NotesQueryService(repo, SCHEMA, executor.context_index)
    runtime.work_session_service = domain
    runtime.vault_repository = repo
    runtime.canonical_schema = SCHEMA
    runtime.notes_mutation_actor = lambda *_args: actor.stable_user_id
    chat = runtime.execute_product(source, "chat-work-session-1", "main", actor)
    assert chat["status"] == "completed"
    assert len(calls) == 1
    assert runtime.execute_product(source, "chat-work-session-1", "main", actor)[
        "delivery_replayed"
    ]
    assert len(calls) == 1

    details = runtime.notes("detail", {"note_id": task_id}, actor)
    assert len(details["work_sessions"]) == 1
    item = details["work_sessions"][0]
    added = runtime.notes(
        "work_session_activity_add",
        {
            "session_id": item["id"],
            "text": "Comprobadas tareas y API.",
            "request_id": "ui-activity-1",
            "expected_revision": item["mutation"]["revision"],
            "expected_source_hash": item["mutation"]["source_hash"],
        },
        actor,
    )
    assert len(added["work_sessions"]) == 1
    activity = added["work_sessions"][0]
    assert len(activity["activity"]) == 1
    assert (
        runtime.notes(
            "work_session_activity_add",
            {
                "session_id": item["id"],
                "text": "Comprobadas tareas y API.",
                "request_id": "ui-activity-1",
                "expected_revision": item["mutation"]["revision"],
                "expected_source_hash": item["mutation"]["source_hash"],
            },
            actor,
        )
        == added
    )
    stopped = runtime.notes(
        "work_session_stop",
        {
            "session_id": activity["id"],
            "request_id": "ui-stop-1",
            "expected_revision": activity["mutation"]["revision"],
            "expected_source_hash": activity["mutation"]["source_hash"],
        },
        actor,
    )
    assert stopped["work_sessions"][0]["ended_at"] is not None
    sessions = [
        parse_note(repo.read_text(path))
        for path in repo.list_markdown_paths()
        if parse_note(repo.read_text(path)).metadata["type"] == "work_session"
    ]
    assert len(sessions) == 1
    assert "Comprobadas tareas y API." in sessions[0].content
