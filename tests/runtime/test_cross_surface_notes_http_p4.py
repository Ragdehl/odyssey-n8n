"""Real isolated HTTP /notes lifecycle: parent → subtask → Work Session → Task.

Does not pretend to exercise an authenticated browser or n8n, and never loads
DEV or PROD vault. The real HTTP adapter + RuntimeComposition + Core Markdown
and direct Tasks/Work Sessions are used (no stub HTTP responses or model).
"""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import odyssey_runtime.composition as composition
from odyssey_core.identity_boundary import OdysseyUser
from odyssey_core.notes import parse_note, validate_note
from odyssey_runtime.server import _handler_for
from tests.apps.tasks.test_work_session_runtime import SCHEMA
from tests.runtime.test_cross_surface_task_session_contract_p4 import (
    CLOCK_START,
    CLOCK_STOP,
    _build,
    _mutation,
)


def test_real_http_notes_subtask_session_activity_and_task_status(tmp_path: Path, monkeypatch):
    repository, runtime, _service = _build(tmp_path / "isolated-http", with_direct=True)
    now = [CLOCK_START]
    monkeypatch.setattr(composition, "_current_time", lambda: {"timestamp": now[0]})
    actor = OdysseyUser.new()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(operation: str, **payload):
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        body = {
            "operation": operation,
            **payload,
            "authenticated_actor": {"stable_user_id": actor.stable_user_id},
        }
        connection.request(
            "POST", "/notes", body=json.dumps(body), headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        status = response.status
        value = json.loads(response.read())
        connection.close()
        return status, value

    try:
        status, parent = post("detail", note_id="task-parent")
        assert status == 200
        payload = {
            "parent_note_id": "task-parent",
            "title": "Validar HTTP completo",
            **_mutation(parent),
            "request_id": "http-child",
        }
        status, created = post("task_subtask_create", **payload)
        assert status == 200 and created["operation"] == "task_subtask_created"
        status, duplicate = post("task_subtask_create", **payload)
        assert status == 200 and duplicate == created
        child_id = created["note_id"]
        status, detail = post("detail", note_id=child_id)
        assert status == 200
        # One actor-scoped request ID must NEVER be reusable for a different
        # mutation surface, or a previous Task CREATE receipt could conceal
        # a missing Work Session. This is a cross-operation E3 collision.
        collision = {"note_id": child_id, **_mutation(detail), "request_id": "http-child"}
        collision_status, collision_body = post("work_session_start", **collision)
        assert collision_status == 400 and collision_body == {"error": "invalid notes request"}
        assert all(
            parse_note(repository.read_text(path)).metadata.get("type") != "work_session"
            for path in repository.list_markdown_paths()
        )
        start = {"note_id": child_id, **_mutation(detail), "request_id": "http-start"}
        status, started = post("work_session_start", **start)
        assert status == 200 and len(started["work_sessions"]) == 1
        assert post("work_session_start", **start) == (200, started)
        session = started["work_sessions"][0]

        add = {
            "session_id": session["id"],
            "text": "Probadas entradas y salidas.",
            **_mutation(session),
            "request_id": "http-activity-add",
        }
        status, added = post("work_session_activity_add", **add)
        assert status == 200
        activity_id = added["work_sessions"][0]["activity"][0]["id"]
        assert post("work_session_activity_add", **add) == (200, added)

        current = added["work_sessions"][0]
        activity_edit = {
            "session_id": current["id"],
            "activity_id": activity_id,
            "text": "Probadas rutas HTTP y replay.",
            **_mutation(current),
            "request_id": "http-activity-edit",
        }
        status, edited = post("work_session_activity_edit", **activity_edit)
        assert status == 200
        assert edited["work_sessions"][0]["activity"][0]["text"].endswith("replay.")
        now[0] = CLOCK_STOP
        current = edited["work_sessions"][0]
        stop = {
            "session_id": current["id"],
            **_mutation(current),
            "request_id": "http-session-stop",
        }
        status, stopped = post("work_session_stop", **stop)
        assert status == 200
        assert stopped["work_sessions"][0]["ended_at"] == CLOCK_STOP
        assert post("work_session_stop", **stop) == (200, stopped)

        current = stopped["work_sessions"][0]
        bad = {
            "session_id": current["id"],
            "started_at": CLOCK_STOP,
            "ended_at": CLOCK_START,
            **_mutation(current),
            "request_id": "invalid-order",
        }
        status, rejected = post("work_session_edit", **bad)
        assert status == 409 and "error" in rejected
        current = stopped["work_sessions"][0]
        delete_activity = {
            "session_id": current["id"],
            "activity_id": activity_id,
            **_mutation(current),
            "request_id": "http-activity-delete",
        }
        status, emptied = post("work_session_activity_delete", **delete_activity)
        assert status == 200
        assert emptied["work_sessions"][0]["activity"] == []

        status, detail = post("detail", note_id=child_id)
        assert status == 200
        done = {
            "note_id": child_id,
            "completed": True,
            **_mutation(detail),
            "request_id": "http-task-complete",
        }
        status, completed = post("task_status", **done)
        assert status == 200 and completed["status"] == "completed"
        assert post("task_status", **done) == (200, completed)
        status, latest = post("detail", note_id=child_id)
        assert status == 200
        status, refused = post(
            "work_session_start",
            note_id=child_id,
            **_mutation(latest),
            request_id="new-closed-session",
        )
        assert status == 409 and refused["error"] == "WORK_SESSION_TASK_CLOSED"
        status, malformed = post(
            "work_session_start", note_id=child_id, request_id="malformed-no-concurrency-tokens"
        )
        assert status == 400 and "error" in malformed

        task_notes = []
        session_notes = []
        for path in repository.list_markdown_paths():
            note = parse_note(repository.read_text(path))
            validate_note(note, SCHEMA)
            if note.metadata.get("type") == "task":
                task_notes.append(note)
            if note.metadata.get("type") == "work_session":
                session_notes.append(note)
        assert len(task_notes) == 2 and len(session_notes) == 1
        assert session_notes[0].metadata["task_id"] == child_id
        assert session_notes[0].metadata["ended_at"] == CLOCK_STOP
        assert session_notes[0].content == ""
        assert any(
            item.metadata["name"] == "Validar HTTP completo"
            and item.metadata["status"] == "completed"
            and "[[parent|Desarrollar Odyssey]]" in item.content
            for item in task_notes
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
