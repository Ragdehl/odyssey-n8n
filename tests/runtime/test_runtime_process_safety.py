"""Regression tests for persistent-runtime time and execution-safety boundaries."""

from __future__ import annotations

from pathlib import Path

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.git_history import GitHistoryResult
from odyssey_runtime import composition
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime import server as runtime_server


def _result() -> ApplicationResult:
    """Return a completed non-mutating result for runtime wiring tests."""
    return ApplicationResult(
        request_id="request-runtime-safety",
        status=ApplicationStatus.COMPLETED,
        action_results=(),
        affected_stable_note_ids=(),
        history=GitHistoryResult.disabled(),
    )


def test_persistent_runtime_refreshes_planner_clock_for_each_request(
    monkeypatch, tmp_path: Path
) -> None:
    """Relative-date planning must not keep the process-start timestamp forever."""
    schema_path = tmp_path / "schema.json"
    schema_path.write_text('{"fields": {}}', encoding="utf-8")
    monkeypatch.setenv("ODYSSEY_SCHEMA_PATH", str(schema_path))
    monkeypatch.setenv("ODYSSEY_PENDING_ROOT", str(tmp_path / "pending"))
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("ODYSSEY_VAULT_ROOT", str(tmp_path / "vault"))
    monkeypatch.setenv("ODYSSEY_EMBEDDING_CACHE", str(tmp_path / "embeddings"))

    class FakeIndex:
        """Provide a no-op rebuildable index."""

        def __init__(self, path):
            self.path = path

        def rebuild(self, repository, schema, embedder):
            return None

    planner_contexts: list[dict[str, str]] = []

    class FakePlanner:
        """Record the current-context snapshot used for each request."""

        @classmethod
        def from_environment(cls, schema, context):
            planner_contexts.append(dict(context))
            return cls()

    clocks = iter(
        [
            {
                "date": "2026-09-02",
                "time": "23:59:59",
                "timezone": "Europe/Paris",
                "timestamp": "2026-09-02T23:59:59+02:00",
            },
            {
                "date": "2026-09-03",
                "time": "00:00:01",
                "timezone": "Europe/Paris",
                "timestamp": "2026-09-03T00:00:01+02:00",
            },
        ]
    )
    persistence_times: list[str] = []

    monkeypatch.setattr(composition, "VaultRepository", lambda root: ("repository", root))
    monkeypatch.setattr(composition, "FastEmbedTextEmbedder", lambda **kwargs: kwargs)
    monkeypatch.setattr(composition, "ContextIndex", FakeIndex)
    monkeypatch.setattr(composition, "SemanticEntityIndex", FakeIndex)
    monkeypatch.setattr(composition, "OpenAIRequestPlanner", FakePlanner)
    monkeypatch.setattr(composition, "OpenAIContextualReasoner", lambda *args, **kwargs: "reasoner")
    monkeypatch.setattr(composition, "OpenAILunaWriter", lambda: "writer")
    monkeypatch.setattr(composition, "OpenAILunaFactSelector", lambda: "selector")
    monkeypatch.setattr(composition, "PendingWorkRepository", lambda root: ("pending", root))
    monkeypatch.setattr(composition, "GitHistoryRecorder", lambda root: ("history", root))
    monkeypatch.setattr(composition, "_current_time", lambda: next(clocks))

    def fake_execute_request(request, **kwargs):
        persistence_times.append(kwargs["now"])
        return _result()

    monkeypatch.setattr(composition, "execute_request", fake_execute_request)

    runtime = composition.build_runtime_from_environment()
    runtime.execute("¿Qué pasa hoy?")
    runtime.execute("¿Qué pasa hoy?")

    assert [context["date"] for context in planner_contexts] == ["2026-09-02", "2026-09-03"]
    assert persistence_times == ["2026-09-02T23:59:59+02:00", "2026-09-03T00:00:01+02:00"]


def test_runtime_server_uses_serial_http_execution(monkeypatch) -> None:
    """The initial adapter must not introduce concurrent Core execution implicitly."""
    calls: list[tuple[str, int]] = []

    class FakeHTTPServer:
        """Record the production server choice without opening a socket."""

        def __init__(self, address, handler):
            calls.append(address)
            self.handler = handler

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def serve_forever(self):
            return None

    monkeypatch.setattr(runtime_server, "HTTPServer", FakeHTTPServer)
    runtime = RuntimeComposition(core_execute=lambda request: _result(), refresh_indexes=lambda: None)

    runtime_server.serve(runtime, host="127.0.0.1", port=18765)

    assert calls == [("127.0.0.1", 18765)]
