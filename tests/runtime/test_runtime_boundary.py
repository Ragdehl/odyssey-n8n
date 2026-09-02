"""Deterministic tests for the n8n-facing Odyssey runtime boundary."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace

from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    PendingWorkStatus,
    UnitResult,
    UnitStatus,
)
from odyssey_core.bulk_update import BulkUpdateFailure, BulkUpdateResult
from odyssey_core.context import ContextItem, ContextPackage
from odyssey_core.git_history import GitHistoryResult
from odyssey_runtime import __main__ as runtime_main
from odyssey_runtime import composition
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


def test_application_result_serialization_maps_action_evidence() -> None:
    """Serialization preserves bounded retrieval, unit, bulk, and delegation evidence."""
    item = ContextItem(
        id="note-1",
        path="notes/note-1.md",
        primary_name="Note 1",
        type="concept",
        tags=("tag",),
        metadata={"name": "Note 1"},
        content="safe content",
        similarity=0.9,
    )
    action = ActionResult(
        action_index=0,
        kind="retrieve",
        status=ActionStatus.COMPLETED,
        retrieval=ContextPackage(query="find note", items=(item,)),
        unit_results=(
            UnitResult(
                unit_index=1,
                status=UnitStatus.DEFERRED,
                operation="update",
                stable_note_id="note-1",
                reason="needs review",
                candidates=("note-1",),
                dependencies=(),
            ),
        ),
        bulk_result=BulkUpdateResult(
            requested_cardinality="all",
            selected_note_ids=("note-1",),
            succeeded=(),
            failed=(BulkUpdateFailure("note-2", "error", "not writable"),),
            status="partial",
        ),
        delegated_request="follow-up",
    )
    response = application_result_to_response(
        ApplicationResult(
            request_id="request-rich",
            status=ApplicationStatus.PARTIAL,
            action_results=(action,),
            affected_stable_note_ids=(),
        )
    )

    assert response["actions"][0]["retrieval"]["items"][0]["id"] == "note-1"
    assert response["actions"][0]["units"][0]["dependencies"] == []
    assert response["actions"][0]["bulk"]["failed"] == [
        {"stable_note_id": "note-2", "reason": "not writable"}
    ]
    assert response["actions"][0]["delegated_request"] == "follow-up"


def test_application_result_serialization_rejects_non_result() -> None:
    """The adapter rejects an incorrectly wired Core executor safely."""
    try:
        application_result_to_response(SimpleNamespace())
    except TypeError as error:
        assert str(error) == "runtime executor must return ApplicationResult"
    else:
        raise AssertionError("expected TypeError")


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


def test_http_boundary_supports_health_and_rejects_unknown_paths() -> None:
    """Only the documented health and execute paths are exposed."""
    server = _test_server(
        RuntimeComposition(core_execute=lambda request: _result(), refresh_indexes=lambda: None)
    )
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", "/healthz")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["ok"] is True

        connection.request("GET", "/unknown")
        response = connection.getresponse()
        assert response.status == 404
        assert json.loads(response.read()) == {"error": "not found"}

        connection.request("POST", "/unknown", body="{}")
        response = connection.getresponse()
        assert response.status == 404
        assert json.loads(response.read()) == {"error": "not found"}
    finally:
        server.shutdown()
        server.server_close()


def test_http_boundary_returns_safe_500_for_core_failure() -> None:
    """Unexpected Core failures become a generic response without exception details."""
    server = _test_server(
        RuntimeComposition(
            core_execute=lambda request: (_ for _ in ()).throw(RuntimeError("secret detail")),
            refresh_indexes=lambda: None,
        )
    )
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("POST", "/execute", body=json.dumps({"request": "hello"}))
        response = connection.getresponse()
        assert response.status == 500
        assert json.loads(response.read()) == {"error": "runtime failure"}
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


def test_runtime_composition_builds_from_environment(monkeypatch, tmp_path: Path) -> None:
    """The composition root wires environment paths into the existing production boundaries."""
    schema_path = tmp_path / "schema.json"
    schema_path.write_text('{"fields": {}}', encoding="utf-8")
    pending = tmp_path / "pending"
    runtime_root = tmp_path / "runtime"
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("ODYSSEY_SCHEMA_PATH", str(schema_path))
    monkeypatch.setenv("ODYSSEY_PENDING_ROOT", str(pending))
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("ODYSSEY_VAULT_ROOT", str(vault_root))
    monkeypatch.setenv("ODYSSEY_EMBEDDING_CACHE", str(tmp_path / "embeddings"))
    monkeypatch.setenv("ODYSSEY_CONTEXT_LIMIT", "4")
    monkeypatch.setenv("ODYSSEY_ACTOR", "test-runtime")

    class FakeIndex:
        def __init__(self, path):
            self.path = path
            self.rebuild_calls = 0

        def rebuild(self, repository, schema, embedder):
            self.rebuild_calls += 1

    class FakePlanner:
        @classmethod
        def from_environment(cls, schema, context):
            return cls()

    monkeypatch.setattr(composition, "VaultRepository", lambda root: ("repository", root))
    monkeypatch.setattr(composition, "FastEmbedTextEmbedder", lambda **kwargs: kwargs)
    monkeypatch.setattr(composition, "ContextIndex", FakeIndex)
    monkeypatch.setattr(composition, "SemanticEntityIndex", FakeIndex)
    monkeypatch.setattr(composition, "OpenAIRequestPlanner", FakePlanner)
    monkeypatch.setattr(composition, "OpenAIContextualReasoner", lambda *args, **kwargs: args)
    monkeypatch.setattr(composition, "OpenAILunaWriter", lambda: "writer")
    monkeypatch.setattr(composition, "OpenAILunaFactSelector", lambda: "selector")
    monkeypatch.setattr(composition, "PendingWorkRepository", lambda root: ("pending", root))
    monkeypatch.setattr(composition, "GitHistoryRecorder", lambda root: ("history", root))
    monkeypatch.setattr(
        composition,
        "_current_time",
        lambda: {
            "date": "2026-09-02",
            "time": "12:00:00",
            "timezone": "Europe/Paris",
            "timestamp": "2026-09-02T12:00:00+02:00",
        },
    )
    monkeypatch.setattr(composition, "execute_request", lambda request, **kwargs: _result())

    runtime = composition.build_runtime_from_environment()
    assert pending.is_dir()
    assert runtime.execute("hello").request_id == "request-test"


def test_runtime_entrypoint_passes_environment_transport_settings(monkeypatch) -> None:
    """The process entrypoint passes explicit host and port settings to the adapter."""
    calls: list[tuple[str, int]] = []
    runtime = object()
    monkeypatch.setenv("ODYSSEY_RUNTIME_HOST", "172.18.0.1")
    monkeypatch.setenv("ODYSSEY_RUNTIME_PORT", "18765")
    monkeypatch.setattr(runtime_main, "build_runtime_from_environment", lambda: runtime)
    monkeypatch.setattr(
        runtime_main, "serve", lambda received, host, port: calls.append((host, port))
    )

    runtime_main.main()

    assert calls == [("172.18.0.1", 18765)]


def _test_server(runtime: RuntimeComposition):
    """Start one local-only HTTP server using the production request handler."""
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
