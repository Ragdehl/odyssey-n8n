"""Durable gate for full-source multi-App deliveries with crash between writes and receipt.

Unlike the old chat result store, pending claims block re-execution when the
remote service may have physically created a Task before failing to respond.
"""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.delivery_results import DeliveryResultError
from odyssey_runtime.server import _handler_for


def _runtime(root, operation):
    return RuntimeComposition(
        core_execute=lambda *_: (_ for _ in ()).throw(AssertionError("legacy path forbidden")),
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(root),
        hybrid_candidate_execute=operation,
        full_source_mutation_guard=True,
    )


def _result(request_id):
    return ApplicationResult(request_id, ApplicationStatus.COMPLETED, (), ("task-1",))


def test_guard_requires_complete_authenticated_outer_delivery(tmp_path):
    called = []
    runtime = _runtime(tmp_path, lambda *args: called.append(args) or _result(args[1]))
    with pytest.raises(ValueError, match="isolated delivery"):
        runtime.execute_product("Hoy tengo que escribir.")
    assert called == []


def test_successful_multi_app_response_is_replayable_after_restart(tmp_path):
    actor = AuthenticatedActorContext(str(uuid4()))
    calls = []
    runtime = _runtime(tmp_path, lambda _source, rid, *_: calls.append(rid) or _result(rid))
    first = runtime.execute_product("Record and task", "same-outer", "main", actor)
    assert first["status"] == "completed" and first["affected_stable_note_ids"] == ["task-1"]
    root = ConversationRootResolver(tmp_path).resolve(actor.stable_user_id) / "delivery-results"
    assert not any(root.glob("*.claim"))
    restarted = _runtime(tmp_path, lambda *_: (_ for _ in ()).throw(AssertionError("must replay")))
    second = restarted.execute_product("Record and task", "same-outer", "main", actor)
    assert second["delivery_replayed"] is True
    assert calls == ["same-outer"]


def test_uncertain_crash_after_physical_task_create_blocks_repeat(tmp_path):
    actor = AuthenticatedActorContext(str(uuid4()))
    effects = tmp_path / "write-effects.txt"

    def crash_after_write(_source, _id, *_):
        with effects.open("a", encoding="utf-8") as f:
            f.write("created-task\n")
        raise RuntimeError("crash after durable Task CREATE")

    initial = _runtime(tmp_path, crash_after_write)
    with pytest.raises(RuntimeError, match="crash"):
        initial.execute_product("Call Maite tomorrow", "fault-1", "main", actor)
    assert effects.read_text() == "created-task\n"
    restarted = _runtime(tmp_path, crash_after_write)
    with pytest.raises(DeliveryResultError, match="unresolved prior attempt"):
        restarted.execute_product("Call Maite tomorrow", "fault-1", "main", actor)
    assert effects.read_text() == "created-task\n"
    root = ConversationRootResolver(tmp_path).resolve(actor.stable_user_id) / "delivery-results"
    assert len(list(root.glob("*.claim"))) == 1


def test_same_claim_id_cannot_switch_source_after_uncertain_write(tmp_path):
    actor = AuthenticatedActorContext(str(uuid4()))

    def crash(*_):
        raise RuntimeError("uncertain write")

    runtime = _runtime(tmp_path, crash)
    with pytest.raises(RuntimeError):
        runtime.execute_product("Create a task", "fault-2", "main", actor)
    with pytest.raises(DeliveryResultError):
        runtime.execute_product("Create a different task", "fault-2", "main", actor)


def test_actual_http_fail_closed_after_uncertain_multi_app_write(tmp_path):
    actor = AuthenticatedActorContext(str(uuid4()))
    effects = []

    def crash(_source, _request, *_):
        effects.append("created-task")
        raise RuntimeError("after task commit")

    runtime = _runtime(tmp_path, crash)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post():
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        connection.request(
            "POST",
            "/execute",
            json.dumps(
                {
                    "request": "Call Maite tomorrow",
                    "request_id": "http-fault",
                    "conversation_id": "main",
                    "authenticated_actor": {"stable_user_id": actor.stable_user_id},
                }
            ).encode(),
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        status = response.status
        connection.close()
        return status, body

    try:
        first, first_payload = post()
        second, second_payload = post()
        assert first == 500 and first_payload["error"] == "runtime failure"
        assert second == 409 and second_payload["error"] == "delivery result conflict"
        assert effects == ["created-task"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
