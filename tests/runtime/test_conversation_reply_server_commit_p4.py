"""Real HTTP regression: the server persists the visible assistant reply before navigation.

The n8n finalizer can call /conversation/assistant-response with the rendered
user-visible response. The browser is not required to make another write.
"""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from uuid import uuid4

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.server import _handler_for


def _post(port, route, body):
    conn = HTTPConnection("127.0.0.1", port, timeout=7)
    conn.request("POST", route, json.dumps(body).encode(), {"Content-Type": "application/json"})
    response = conn.getresponse()
    status = response.status
    payload = json.loads(response.read())
    conn.close()
    return status, payload


@pytest.fixture
def isolated_http(tmp_path: Path):
    actor = AuthenticatedActorContext(str(uuid4()))
    other = AuthenticatedActorContext(str(uuid4()))
    calls = []

    def execute(_source, rid, *_):
        calls.append(rid)
        return ApplicationResult(rid, ApplicationStatus.COMPLETED, (), ())

    rt = RuntimeComposition(
        core_execute=execute,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(rt))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], rt, actor, other, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _actor(actor):
    return {"authenticated_actor": {"stable_user_id": actor.stable_user_id}}


def test_assistant_survives_navigation_without_browser_post(isolated_http):
    port, rt, actor, _other, calls = isolated_http
    status, original = _post(
        port,
        "/execute",
        {
            "request": "Hoy he conocido a Guillem.",
            "request_id": "chat-user-1",
            "conversation_id": "main",
            **_actor(actor),
        },
    )
    assert status == 200
    assert original["request_id"] == "chat-user-1"
    visible = {
        "request_id": "chat-user-1",
        "status": "completed",
        "kind": "acknowledgement",
        "message": "La información se ha guardado.",
    }
    status, confirmed = _post(
        port, "/conversation/assistant-response", {"response": visible, **_actor(actor)}
    )
    assert status == 200 and confirmed["conversation_persisted"] is True
    assert confirmed["conversation_diagnostics_preserved"] is True
    # A new browser page does only a GET equivalent, not an assistant append.
    status, reloaded = _post(port, "/conversation/main", {"operation": "main", **_actor(actor)})
    assert status == 200
    assert [(x["role"], x["text"]) for x in reloaded["turns"]] == [
        ("user", "Hoy he conocido a Guillem."),
        ("assistant", "La información se ha guardado."),
    ]
    assert calls == ["chat-user-1"]


def test_duplicate_server_delivery_is_idempotent(isolated_http):
    port, rt, actor, _other, _calls = isolated_http
    _post(
        port,
        "/execute",
        {
            "request": "Hola",
            "request_id": "chat-user-2",
            "conversation_id": "main",
            **_actor(actor),
        },
    )
    visible = {
        "request_id": "chat-user-2",
        "status": "completed",
        "kind": "acknowledgement",
        "message": "Guardado.",
    }
    for _ in range(3):
        status, payload = _post(
            port, "/conversation/assistant-response", {"response": visible, **_actor(actor)}
        )
        assert status == 200 and payload["conversation_persisted"]
    status, reloaded = _post(port, "/conversation/main", {"operation": "main", **_actor(actor)})
    assert status == 200 and len(reloaded["turns"]) == 2


def test_invalid_optional_graph_never_erases_visible_reply(isolated_http):
    port, rt, actor, _other, _calls = isolated_http
    _post(
        port,
        "/execute",
        {
            "request": "Fact",
            "request_id": "chat-user-3",
            "conversation_id": "main",
            **_actor(actor),
        },
    )
    visible = {
        "request_id": "chat-user-3",
        "status": "completed",
        "kind": "acknowledgement",
        "message": "Guardado.",
        "request_detail": {
            "request_id": "chat-user-3",
            "operational": {"stages": [{"name": "invalid", "unexpected_sensitive_field": "x"}]},
        },
    }
    status, payload = _post(
        port, "/conversation/assistant-response", {"response": visible, **_actor(actor)}
    )
    assert status == 200 and payload["conversation_persisted"] is True
    assert payload["conversation_diagnostics_preserved"] is False
    status, reloaded = _post(port, "/conversation/main", {"operation": "main", **_actor(actor)})
    assert status == 200
    assert reloaded["turns"][-1]["text"] == "Guardado."
    assert "request_detail" not in reloaded["turns"][-1]


def test_cannot_append_unsolicited_or_wrong_actor_reply(isolated_http):
    port, rt, actor, other, _calls = isolated_http
    visible = {
        "request_id": "chat-user-4",
        "status": "completed",
        "kind": "acknowledgement",
        "message": "Nunca debió guardarse.",
    }
    status, payload = _post(
        port, "/conversation/assistant-response", {"response": visible, **_actor(actor)}
    )
    assert status == 400
    _post(
        port,
        "/execute",
        {
            "request": "Fact",
            "request_id": "chat-user-4",
            "conversation_id": "main",
            **_actor(actor),
        },
    )
    status, payload = _post(
        port, "/conversation/assistant-response", {"response": visible, **_actor(other)}
    )
    assert status == 400
    status, reloaded = _post(port, "/conversation/main", {"operation": "main", **_actor(actor)})
    assert status == 200 and len(reloaded["turns"]) == 1


def test_collision_does_not_replace_a_different_visible_reply(isolated_http):
    port, rt, actor, _other, _calls = isolated_http
    _post(
        port,
        "/execute",
        {
            "request": "Fact",
            "request_id": "chat-user-5",
            "conversation_id": "main",
            **_actor(actor),
        },
    )
    good = {
        "request_id": "chat-user-5",
        "status": "completed",
        "kind": "acknowledgement",
        "message": "Guardado.",
    }
    assert (
        _post(port, "/conversation/assistant-response", {"response": good, **_actor(actor)})[0]
        == 200
    )
    bad = {**good, "message": "No sé nada."}
    assert (
        _post(port, "/conversation/assistant-response", {"response": bad, **_actor(actor)})[0]
        == 400
    )
    assert (
        _post(port, "/conversation/main", {"operation": "main", **_actor(actor)})[1]["turns"][-1][
            "text"
        ]
        == "Guardado."
    )


@pytest.mark.parametrize(
    "bad_response",
    [
        {},
        {"request_id": "bogus", "kind": "acknowledgement", "status": "completed", "message": ""},
        {"request_id": "bogus", "kind": "hack", "status": "completed", "message": "X"},
        {"request_id": "bogus", "kind": "answer", "status": "unknown", "message": "X"},
        {
            "request_id": "bogus",
            "kind": "answer",
            "status": "completed",
            "message": "X",
            "evil": "payload",
        },
    ],
)
def test_invalid_or_unauthorized_response_cannot_create_assistant_turn(isolated_http, bad_response):
    port, rt, actor, _other, _calls = isolated_http
    status, _ = _post(
        port, "/conversation/assistant-response", {"response": bad_response, **_actor(actor)}
    )
    assert status == 400


def test_replay_keeps_first_assistant_text_status_and_diagnostics(isolated_http):
    """A repeated E3 delivery must not return 200 with an empty n8n body."""
    port, _rt, actor, _other, calls = isolated_http
    _post(
        port,
        "/execute",
        {
            "request": "Create a synthetic task",
            "request_id": "e3-reply-stable-1",
            "conversation_id": "main",
            **_actor(actor),
        },
    )
    response = {
        "request_id": "e3-reply-stable-1",
        "status": "completed",
        "kind": "acknowledgement",
        "message": "Guardado.",
    }
    first_status, first = _post(
        port, "/conversation/assistant-response", {"response": response, **_actor(actor)}
    )
    assert first_status == 200 and first["conversation_persisted"] is True
    replay = {
        **response,
        "request_detail": {
            "request_id": "e3-reply-stable-1",
            "unexpected_extra": "ignored on replay",
        },
    }
    second_status, second = _post(
        port, "/conversation/assistant-response", {"response": replay, **_actor(actor)}
    )
    assert second_status == 200 and second["conversation_persisted"] is True
    assert "request_detail" not in second
    for conflict in ({**response, "message": "Otro resultado."}, {**response, "status": "failed"}):
        status, _ = _post(
            port, "/conversation/assistant-response", {"response": conflict, **_actor(actor)}
        )
        assert status == 400
    status, page = _post(port, "/conversation/main", {"operation": "main", **_actor(actor)})
    assert status == 200 and len(page["turns"]) == 2
    assert page["turns"][-1]["text"] == "Guardado."
    assert calls == ["e3-reply-stable-1"]
