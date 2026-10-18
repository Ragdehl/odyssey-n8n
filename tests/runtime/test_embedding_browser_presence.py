"""No browser interaction may block on ONNX initialization or leave dangling sessions."""

from __future__ import annotations

import json
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.isolated_embeddings import IsolatedFastEmbedTextEmbedder
from odyssey_runtime.server import _handler_for


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setattr("odyssey_runtime.isolated_embeddings.version", lambda _: "0.7.3")
    model = IsolatedFastEmbedTextEmbedder(
        cache_dir=tmp_path,
        worker_module="tests.runtime.mock_embedding_worker",
        idle_seconds=0.35,
        request_timeout_seconds=3,
    )
    composed = RuntimeComposition(
        core_execute=lambda _source, rid, *_: ApplicationResult(
            rid, ApplicationStatus.COMPLETED, (), ()
        ),
        refresh_indexes=lambda: None,
        notes_embedder=model,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(composed))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield composed, model, server.server_address[1], AuthenticatedActorContext(str(uuid4()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        model.close()


def post(port, body):
    conn = HTTPConnection("127.0.0.1", port, timeout=3)
    conn.request(
        "POST",
        "/conversation/presence",
        json.dumps(body).encode(),
        {"Content-Type": "application/json"},
    )
    response = conn.getresponse()
    outcome = response.status, json.loads(response.read())
    conn.close()
    return outcome


def test_authenticated_browser_entry_starts_background_worker(runtime):
    _composed, model, port, actor = runtime
    body = {
        "operation": "presence",
        "session_id": "tab-one",
        "state": "active",
        "authenticated_actor": {"stable_user_id": actor.stable_user_id},
    }
    started = time.monotonic()
    assert post(port, body) == (200, {"ok": True})
    assert time.monotonic() - started < 0.5
    deadline = time.monotonic() + 2
    while (model._worker is None or model._warm_pending) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert model._worker is not None and model._worker.poll() is None
    pid = model._worker.pid
    # Heartbeats prevent idle shutdown even without a semantic query.
    time.sleep(0.55)
    assert post(port, {**body, "state": "heartbeat"}) == (200, {"ok": True})
    assert model._worker is not None and model._worker.pid == pid
    assert post(port, {**body, "state": "inactive"}) == (200, {"ok": True})
    deadline = time.monotonic() + 2
    while model._worker is not None and time.monotonic() < deadline:
        time.sleep(0.03)
    assert model._worker is None


def test_multiple_tabs_keep_worker_until_the_last_tab_leaves(runtime):
    _composed, model, port, actor = runtime
    base = {
        "operation": "presence",
        "state": "active",
        "authenticated_actor": {"stable_user_id": actor.stable_user_id},
    }
    assert post(port, {**base, "session_id": "tab-1"})[0] == 200
    assert post(port, {**base, "session_id": "tab-2"})[0] == 200
    assert post(port, {**base, "session_id": "tab-1", "state": "inactive"})[0] == 200
    assert len(model._sessions) == 1
    assert post(port, {**base, "session_id": "tab-2", "state": "inactive"})[0] == 200
    assert len(model._sessions) == 0


def test_presence_rejects_bad_actor_request_and_prod(runtime, monkeypatch):
    _composed, model, port, actor = runtime
    base = {"operation": "presence", "session_id": "tab-1", "state": "active"}
    assert post(port, base)[0] == 400
    assert (
        post(
            port,
            {
                **base,
                "state": "unknown",
                "authenticated_actor": {"stable_user_id": actor.stable_user_id},
            },
        )[0]
        == 400
    )
    assert (
        post(
            port,
            {
                **base,
                "unexpected": True,
                "authenticated_actor": {"stable_user_id": actor.stable_user_id},
            },
        )[0]
        == 400
    )
    assert model._worker is None
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")
    assert (
        post(port, {**base, "authenticated_actor": {"stable_user_id": actor.stable_user_id}})[0]
        == 400
    )
    assert model._worker is None


def test_abandoned_tab_expires_before_idle_grace_starts(runtime):
    _composed, model, port, actor = runtime
    assert (
        post(
            port,
            {
                "operation": "presence",
                "session_id": "dead-tab",
                "state": "active",
                "authenticated_actor": {"stable_user_id": actor.stable_user_id},
            },
        )[0]
        == 200
    )
    with model._lock:
        model._sessions[(actor.stable_user_id, "dead-tab")] = time.monotonic() - 151
    deadline = time.monotonic() + 2
    while model._sessions and time.monotonic() < deadline:
        time.sleep(0.04)
    assert not model._sessions
    assert model._worker is not None  # idle grace starts after tab expiration
