"""Regression tests for persistent-runtime time and execution-safety boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.conversations import ConversationRepository
from odyssey_core.git_history import GitHistoryResult
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_runtime import composition
from odyssey_runtime import server as runtime_server
from odyssey_runtime.composition import (
    RuntimeComposition,
    _current_time,
    _path_env,
    _positive_int_env,
)


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
    request_ids: list[str] = []

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
        request_ids.append(kwargs["request_id_factory"]())
        return _result()

    monkeypatch.setattr(composition, "execute_request", fake_execute_request)

    runtime = composition.build_runtime_from_environment()
    runtime.execute("¿Qué pasa hoy?", "delivery-1")
    runtime.execute("¿Qué pasa hoy?", "delivery-2")

    assert [context["date"] for context in planner_contexts] == ["2026-09-02", "2026-09-03"]
    assert persistence_times == ["2026-09-02T23:59:59+02:00", "2026-09-03T00:00:01+02:00"]
    assert request_ids == ["delivery-1", "delivery-2"]


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
    runtime = RuntimeComposition(
        core_execute=lambda request, request_id: _result(), refresh_indexes=lambda: None
    )

    runtime_server.serve(runtime, host="127.0.0.1", port=18765)

    assert calls == [("127.0.0.1", 18765)]


def test_runtime_configuration_helpers_fail_closed_and_read_timezone(
    monkeypatch, tmp_path: Path
) -> None:
    """Runtime configuration rejects empty/invalid values and exposes explicit clock context."""
    monkeypatch.setenv("TEST_PATH", "   ")
    with pytest.raises(ValueError, match="must not be empty"):
        _path_env("TEST_PATH", str(tmp_path))

    monkeypatch.setenv("TEST_INT", "not-an-int")
    with pytest.raises(ValueError, match="must be a positive integer"):
        _positive_int_env("TEST_INT", "4")
    monkeypatch.setenv("TEST_INT", "0")
    with pytest.raises(ValueError, match="must be a positive integer"):
        _positive_int_env("TEST_INT", "4")

    monkeypatch.setenv("TZ", "Europe/Paris")
    current = _current_time()
    assert set(current) == {"date", "time", "timezone", "timestamp"}
    assert current["timezone"] == "Europe/Paris"

    monkeypatch.setenv("TZ", "Not/AZone")
    with pytest.raises(ValueError, match="valid IANA timezone"):
        _current_time()


def test_runtime_conversation_helpers_preserve_actor_scope_and_context(tmp_path: Path) -> None:
    """Runtime conversation projections stay actor-scoped and use durable Core state."""
    repository = ConversationRepository(tmp_path / "state")
    runtime = RuntimeComposition(
        core_execute=lambda *args: _result(),
        refresh_indexes=lambda: None,
        conversation_repository=repository,
    )
    actor = AuthenticatedActorContext("user-a")

    created = runtime.create_conversation(authenticated_actor=actor)
    conversation_id = str(created["conversation_id"])
    runtime.append_conversation_turn(
        conversation_id,
        "req-1",
        "user",
        "Hablamos de Marta",
        authenticated_actor=actor,
    )
    runtime.append_conversation_turn(
        conversation_id,
        "req-1",
        "assistant",
        "Marta vive en Lyon",
        status="completed",
        authenticated_actor=actor,
    )

    listed = runtime.list_conversations(authenticated_actor=actor)
    loaded = runtime.load_conversation(conversation_id, authenticated_actor=actor)
    context = runtime.conversation_context(conversation_id, authenticated_actor=actor)

    assert listed[0]["conversation_id"] == conversation_id
    assert listed[0]["turn_count"] == 2
    assert loaded["conversation_id"] == conversation_id
    assert "actor_id" not in loaded
    assert context == [
        {"role": "user", "text": "Hablamos de Marta"},
        {"role": "assistant", "text": "Marta vive en Lyon"},
    ]
    assert runtime.list_conversations(authenticated_actor=AuthenticatedActorContext("user-b")) == []


def test_runtime_execute_persists_user_turn_and_forwards_conversation_identity(tmp_path: Path) -> None:
    """Conversation execution persists the visible user turn before forwarding to Core."""
    repository = ConversationRepository(tmp_path / "state")
    repository.create("user-a", now="2026-09-16T10:00:00Z", conversation_id="conv-1")
    calls: list[tuple[object, ...]] = []

    def execute(*args):
        calls.append(args)
        return _result()

    runtime = RuntimeComposition(
        core_execute=execute,
        refresh_indexes=lambda: None,
        conversation_repository=repository,
    )
    actor = AuthenticatedActorContext("user-a")

    runtime.execute(
        "¿Dónde vive?",
        request_id="req-1",
        conversation_id="conv-1",
        authenticated_actor=actor,
    )

    assert calls == [("¿Dónde vive?", "req-1", actor, "conv-1")]
    loaded = repository.load("user-a", "conv-1")
    assert [(turn["request_id"], turn["role"], turn["text"]) for turn in loaded["turns"]] == [
        ("req-1", "user", "¿Dónde vive?")
    ]


def test_runtime_conversation_dependencies_fail_closed(tmp_path: Path) -> None:
    """Missing conversation and identity dependencies are explicit failures."""
    actor = AuthenticatedActorContext("user-a")
    runtime = RuntimeComposition(core_execute=lambda *args: _result(), refresh_indexes=lambda: None)

    with pytest.raises(ValueError, match="conversation repository is unavailable"):
        runtime.create_conversation(authenticated_actor=actor)
    with pytest.raises(ValueError, match="conversation repository is unavailable"):
        runtime.execute("hola", conversation_id="conv-1", authenticated_actor=actor)

    repository = ConversationRepository(tmp_path / "state")
    runtime = RuntimeComposition(
        core_execute=lambda *args: _result(),
        refresh_indexes=lambda: None,
        conversation_repository=repository,
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        runtime.create_conversation(authenticated_actor=actor, external_principal=object())
    with pytest.raises(ValueError, match="external principal mapping is unavailable"):
        runtime.create_conversation(external_principal=object())
    with pytest.raises(ValueError, match="mutually exclusive"):
        runtime.execute(
            "hola",
            authenticated_actor=actor,
            external_principal=object(),
        )


def test_runtime_resolves_external_principal_before_conversation_access(tmp_path: Path) -> None:
    """External principals resolve to the stable internal actor before state access."""
    repository = ConversationRepository(tmp_path / "state")

    class MappingRepository:
        def resolve_existing(self, principal):
            assert principal is marker
            return AuthenticatedActorContext("mapped-user")

    marker = object()
    runtime = RuntimeComposition(
        core_execute=lambda *args: _result(),
        refresh_indexes=lambda: None,
        identity_mapping_repository=MappingRepository(),
        conversation_repository=repository,
    )

    created = runtime.create_conversation(external_principal=marker)
    conversation_id = str(created["conversation_id"])
    assert repository.load("mapped-user", conversation_id)["conversation_id"] == conversation_id
