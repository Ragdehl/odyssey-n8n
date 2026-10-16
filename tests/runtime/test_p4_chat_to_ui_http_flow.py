"""Real localhost HTTP P4 chat → E3 → Tasks service → Notes UI mutation bridge.

The real web browser and n8n node engine are still NOT part of this test. The
model's Router/scope responses alone are frozen; HTTP, actor, receipt, Task
Writer, canonical Markdown and UI API all execute without stubs.
"""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

from odyssey_apps.tasks import TaskWorkSessionService
from odyssey_core import create_entity
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from odyssey_runtime.server import _handler_for
from tests.runtime.test_whole_source_light_product_p4 import SCHEMA, RecordedClient, _fixture

CLOCK = "2026-10-16T17:00:00+02:00"
SOURCE = "Empieza una sesión de trabajo en la tarea Preparar informe Atlas."


def test_real_http_chat_session_can_be_seen_modified_and_closed_from_ui_api(tmp_path):
    repo, actor, executor, runtime = _fixture(tmp_path)
    create_entity(
        repo,
        SCHEMA,
        path="task.md",
        entity_id="task-atlas",
        metadata={"name": "Preparar informe Atlas", "type": "task", "status": "pending"},
        content="- Preparar informe Atlas.\n",
        actor="fixture",
        now=CLOCK,
    )
    executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    sessions = TaskWorkSessionService(
        repo,
        SCHEMA,
        None,
        id_allocator=lambda: "http-e2e-session",
        activity_id_allocator=lambda: "http-e2e-activity",
    )
    executor.task_delegate = lambda source, request_id, who: ApplicationResult(
        request_id,
        ApplicationStatus.COMPLETED,
        (),
        (
            sessions.start(
                task_id="task-atlas",
                started_at=CLOCK,
                request_id=request_id,
                actor=who.stable_user_id,
                now=CLOCK,
            ).session.id,
        ),
    )
    executor.client = RecordedClient(
        [
            {
                "capabilities": ["tasks"],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
                "self_relation_span": None,
            },
            {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": SOURCE},
        ]
    )
    runtime.notes_service = NotesQueryService(repo, SCHEMA, executor.context_index)
    runtime.work_session_service = sessions
    runtime.vault_repository = repo
    runtime.canonical_schema = SCHEMA
    runtime.notes_mutation_actor = lambda *_: actor.stable_user_id
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(endpoint, payload):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        body = {**payload, "authenticated_actor": {"stable_user_id": actor.stable_user_id}}
        connection.request("POST", endpoint, json.dumps(body), {"Content-Type": "application/json"})
        response = connection.getresponse()
        status, content = response.status, json.loads(response.read())
        connection.close()
        return status, content

    try:
        chat_payload = {"request": SOURCE, "request_id": "p4-chat-ui-1", "conversation_id": "main"}
        status, initial = post("/execute", chat_payload)
        assert status == 200 and initial["status"] == "completed"
        status, repeated = post("/execute", chat_payload)
        assert status == 200 and repeated["delivery_replayed"] is True
        status, task = post("/notes", {"operation": "detail", "note_id": "task-atlas"})
        assert status == 200 and len(task["work_sessions"]) == 1
        session = task["work_sessions"][0]
        payload = {
            "operation": "work_session_activity_add",
            "session_id": session["id"],
            "text": "Verificado el chat y la interfaz.",
            "request_id": "p4-ui-activity",
            "expected_revision": session["mutation"]["revision"],
            "expected_source_hash": session["mutation"]["source_hash"],
        }
        status, activity = post("/notes", payload)
        assert status == 200 and len(activity["work_sessions"][0]["activity"]) == 1
        assert post("/notes", payload) == (200, activity)
        latest = activity["work_sessions"][0]
        status, stopped = post(
            "/notes",
            {
                "operation": "work_session_stop",
                "session_id": latest["id"],
                "request_id": "p4-ui-stop",
                "expected_revision": latest["mutation"]["revision"],
                "expected_source_hash": latest["mutation"]["source_hash"],
            },
        )
        assert status == 200 and stopped["work_sessions"][0]["ended_at"] is not None
        canonical_sessions = [
            parse_note(repo.read_text(path))
            for path in repo.list_markdown_paths()
            if parse_note(repo.read_text(path)).metadata["type"] == "work_session"
        ]
        assert len(canonical_sessions) == 1
        assert "Verificado el chat y la interfaz." in canonical_sessions[0].content
        assert (
            len(
                [
                    p
                    for p in repo.list_markdown_paths()
                    if parse_note(repo.read_text(p)).metadata["type"] == "task"
                ]
            )
            == 1
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
