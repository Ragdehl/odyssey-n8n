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


def test_live_execution_ledger_does_not_erase_canonical_flow_from_history(isolated_http):
    """Transport-only ledger stays ephemeral; validated stages/graph survive reload."""
    port, rt, actor, _other, _calls = isolated_http
    _post(
        port,
        "/execute",
        {
            "request": "He organizado el escritorio.",
            "request_id": "chat-ledger-1",
            "conversation_id": "main",
            **_actor(actor),
        },
    )
    detail = {
        "request_id": "chat-ledger-1",
        "operational": {
            "stages": [
                {
                    "name": "application.router",
                    "outcome": "completed",
                    "duration_ms": 8,
                    "stage_view": {"version": 1, "label": "Router", "icon": "router"},
                }
            ]
        },
        "execution_ledger": {"version": 1, "events": [], "transport_only": True},
        "flow": {
            "version": 1,
            "input": "He organizado el escritorio.",
            "parallel_preparation": False,
            "routes": [
                {
                    "capability": "core",
                    "text": "He organizado el escritorio.",
                    "stage_count": 0,
                    "status": "completed",
                    "temporal": [],
                    "plan": [],
                    "entities": [],
                    "writes": [],
                }
            ],
        },
    }
    response = {
        "request_id": "chat-ledger-1",
        "status": "completed",
        "kind": "acknowledgement",
        "message": "Guardado.",
        "request_detail": detail,
    }
    status, saved = _post(
        port, "/conversation/assistant-response", {"response": response, **_actor(actor)}
    )
    assert status == 200, saved
    assert saved["conversation_diagnostics_preserved"] is True
    status, history = _post(port, "/conversation/main", {"operation": "main", **_actor(actor)})
    assert status == 200
    retained = history["turns"][-1]["request_detail"]
    assert "execution_ledger" not in retained
    assert retained["flow"] == detail["flow"]
    assert retained["operational"]["stages"][0]["stage_view"]["label"] == "Router"


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


def test_rendered_graph_and_model_timing_survive_actual_server_history_and_replay(isolated_http):
    """Real n8n stage_view used to trigger text-only fallback on EVERY live turn."""
    port, _runtime, actor, _other, calls = isolated_http
    request_id = "p4-dev-real-stage-view-reload"
    status, _ = _post(
        port,
        "/execute",
        {
            "request": "Ayer compré un cuaderno y hoy regué una planta.",
            "request_id": request_id,
            "conversation_id": "main",
            **_actor(actor),
        },
    )
    assert status == 200
    detail = {
        "request_id": request_id,
        "operational": {
            "total_duration_ms": 52460.0,
            "stages": [
                {
                    "name": "application.source_processing",
                    "outcome": "completed",
                    "duration_ms": 52000.0,
                    "provider_calls": [],
                    "stage_view": {"version": 1, "label": "Analizar mensaje", "icon": "router"},
                    "substeps": [
                        {
                            "name": "provider.gpt-6-luna.odyssey_light_capability_route_v1",
                            "outcome": "completed",
                            "start_offset_ms": 0.0,
                            "duration_ms": 12460.0,
                            "error_category": None,
                        }
                    ],
                },
                {
                    "name": "application.router",
                    "outcome": "completed",
                    "duration_ms": 12460.0,
                    "provider_calls": [],
                    "stage_view": {"version": 1, "label": "Router", "icon": "router"},
                },
                {
                    "name": "planner",
                    "outcome": "completed",
                    "duration_ms": 0.1,
                    "provider_calls": [],
                    "route_index": 0,
                    "stage_view": {"version": 1, "label": "Planner", "icon": "planner"},
                },
                {
                    "name": "action.write",
                    "outcome": "completed",
                    "duration_ms": 240.0,
                    "provider_calls": [],
                    "route_index": 0,
                    "stage_view": {"version": 1, "label": "Escribir", "icon": "core"},
                },
            ],
        },
        "flow": {
            "version": 1,
            "input": "Ayer compré un cuaderno y hoy regué una planta.",
            "parallel_preparation": False,
            "routes": [
                {
                    "capability": "core",
                    "text": "Ayer compré un cuaderno y hoy regué una planta.",
                    "stage_count": 2,
                    "status": "completed",
                    "temporal": [],
                }
            ],
        },
        "changes": {
            "affected_stable_note_ids": ["date:2026-10-16", "date:2026-10-17"],
            "units": [],
        },
    }
    response = {
        "request_id": request_id,
        "status": "completed",
        "kind": "acknowledgement",
        "message": "La información se ha guardado.",
        "request_detail": detail,
    }
    status, first = _post(
        port, "/conversation/assistant-response", {"response": response, **_actor(actor)}
    )
    assert status == 200 and first["conversation_diagnostics_preserved"] is True
    status, history = _post(port, "/conversation/main", {"operation": "main", **_actor(actor)})
    assert status == 200
    assistant = next(turn for turn in history["turns"] if turn["role"] == "assistant")
    assert assistant["request_detail"] == detail
    assert assistant["request_detail"]["flow"]["routes"][0]["capability"] == "core"
    assert (
        assistant["request_detail"]["operational"]["stages"][0]["substeps"][0]["duration_ms"]
        == 12460.0
    )
    status, replay = _post(
        port,
        "/conversation/assistant-response",
        {
            "response": {**response, "request_detail": {"some_new_timing": 0}},
            **_actor(actor),
        },
    )
    assert status == 200 and replay["request_detail"] == detail
    assert calls == [request_id]
