"""Deterministic tests for the n8n-facing Odyssey runtime boundary."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

from odyssey_core.application import (
    ApplicationResult,
    ApplicationStatus,
    PendingWorkStatus,
)
from odyssey_core.git_history import GitHistoryResult
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.serialization import application_result_to_response
from odyssey_runtime.server import _handler_for


def _result() -> ApplicationResult:
    """Return minimal typed application evidence for boundary tests."""
    return ApplicationResult(
        request_id="request-test",
        status=ApplicationStatus.COMPLETED,
        action_results=(),
        affected_stable_note_ids=("note-test",),
        pending_work=PendingWorkStatus(),
        history=GitHistoryResult.disabled(),
    )


def test_application_result_serialization_exposes_only_public_evidence() -> None:
    """Serialization keeps stable evidence and omits provider/internal fields."""
    response = application_result_to_response(_result())

    assert response == {
        "request_id": "request-test",
        "status": "completed",
        "planning_error": None,
        "affected_stable_note_ids": ["note-test"],
        "actions": [],
        "pending_work": {"required": False, "persisted": False, "record_id": None, "error": None},
        "history": {"status": "DISABLED", "commit_sha": None, "reason": None},
    }
    assert "reasoning" not in json.dumps(response)
    assert "prompt" not in json.dumps(response)


def test_http_boundary_rejects_invalid_input_without_calling_core() -> None:
    """Malformed payloads return a stable 400 response and never reach Core."""
    calls: list[str] = []
    runtime = RuntimeComposition(core_execute=calls.append, refresh_indexes=lambda: None)
    server = _test_server(runtime)
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("POST", "/execute", body=json.dumps({"request": ""}))
        response = connection.getresponse()
        assert response.status == 400
        assert json.loads(response.read()) == {"error": "invalid request"}
        assert calls == []
    finally:
        server.shutdown()
        server.server_close()


def test_http_boundary_returns_serialized_application_result() -> None:
    """A valid request invokes Core once and returns its public ApplicationResult mapping."""
    calls: list[str] = []

    def execute(request: str) -> ApplicationResult:
        """Record the request and return deterministic application evidence."""
        calls.append(request)
        return _result()

    server = _test_server(RuntimeComposition(core_execute=execute, refresh_indexes=lambda: None))
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "POST",
            "/execute",
            body=json.dumps({"request": "remember this"}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["request_id"] == "request-test"
        assert calls == ["remember this"]
    finally:
        server.shutdown()
        server.server_close()


def test_runtime_refreshes_indexes_after_core_reports_a_mutation() -> None:
    """A successful mutation refreshes derived indexes exactly once."""
    refreshed: list[bool] = []
    runtime = RuntimeComposition(
        core_execute=lambda request: _result(),
        refresh_indexes=lambda: refreshed.append(True),
    )

    assert runtime.execute("remember this").request_id == "request-test"
    assert refreshed == [True]


def _test_server(runtime: RuntimeComposition):
    """Start one local-only HTTP server using the production request handler."""
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
