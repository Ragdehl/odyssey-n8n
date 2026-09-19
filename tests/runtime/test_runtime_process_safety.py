"""Regression tests for persistent-runtime time and execution-safety boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.context import ContextFilter
from odyssey_core.conversations import MAIN_CONVERSATION_ID
from odyssey_core.git_history import GitHistoryResult
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver, LocalConversationStore
from odyssey_core.note_queries import NotePage, NoteSummary
from odyssey_core.request_planning import SelectionCriteria
from odyssey_runtime import composition
from odyssey_runtime import server as runtime_server
from odyssey_runtime.composition import (
    RuntimeComposition,
    _current_time,
    _path_env,
    _positive_int_env,
)

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
MAPPED_USER = "33333333-3333-4333-8333-333333333333"


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


def test_runtime_builds_note_set_snapshot_from_the_canonical_notes_service() -> None:
    """A validated note-set request uses Notes ordering and does not need an answerer seam."""
    selection = SelectionCriteria(
        entity=None,
        query="personas en Toulouse",
        type="person",
        filters=(ContextFilter("tags", "contains", "people"),),
        link_scope=None,
    )
    source = ApplicationResult(
        request_id="notes-request",
        status=ApplicationStatus.COMPLETED,
        action_results=(),
        affected_stable_note_ids=(),
        presentation_intent="note_set",
        note_set_selection=selection,
    )
    calls: list[dict[str, object]] = []

    class Notes:
        def query(self, **kwargs):
            calls.append(kwargs)
            return NotePage(
                mode="intelligent",
                sort="relevance",
                ranking_version="ui2-feed-v1",
                as_of="2026-09-19T10:00:00+00:00",
                applied_filters=(),
                items=(
                    NoteSummary(
                        "a", "Ada", "person", (), "2026-01-01T00:00:00Z", "2026-09-01T00:00:00Z", {}
                    ),
                    NoteSummary(
                        "b",
                        "Beto",
                        "person",
                        (),
                        "2026-01-01T00:00:00Z",
                        "2026-09-02T00:00:00Z",
                        {},
                    ),
                ),
                total=2,
                next_cursor=None,
            )

    runtime = RuntimeComposition(
        core_execute=lambda *args: source,
        refresh_indexes=lambda: None,
        notes_service=Notes(),
        notes_embedder=object(),
    )
    result = runtime.execute("Muéstrame las personas de Toulouse", "notes-request")

    assert result.note_result_snapshot is not None
    assert result.note_result_snapshot["note_ids"] == ["a", "b"]
    assert result.note_result_snapshot["filters"] == [
        {"field": "tags", "op": "contains", "value": "people"},
        {"field": "type", "op": "eq", "value": "person"},
    ]
    assert len(calls) == 1
    assert calls[0]["mode"] == "intelligent"


def test_runtime_answer_intent_does_not_execute_an_extra_notes_query() -> None:
    """Normal Chat answers retain their existing request path without Notes side effects."""
    calls: list[object] = []

    class Notes:
        def query(self, **kwargs):
            calls.append(kwargs)
            raise AssertionError("answer intent must not query Notes")

    runtime = RuntimeComposition(
        core_execute=lambda *args: _result(),
        refresh_indexes=lambda: None,
        notes_service=Notes(),
        notes_embedder=object(),
    )
    assert runtime.execute("¿Dónde trabaja Marta?", "answer-request").note_result_snapshot is None
    assert calls == []


def test_runtime_answer_and_note_set_attaches_membership_without_altering_answer_evidence() -> None:
    """An answer-plus-set request retains its normal Core result while adding a Notes snapshot."""
    selection = SelectionCriteria(None, "Airbus", None, (), None)
    source = ApplicationResult(
        request_id="answer-and-set",
        status=ApplicationStatus.COMPLETED,
        action_results=(),
        affected_stable_note_ids=(),
        presentation_intent="answer_and_note_set",
        note_set_selection=selection,
    )

    class Notes:
        def query(self, **kwargs):
            return NotePage(
                "intelligent",
                "relevance",
                "ui2-feed-v1",
                "2026-09-19T10:00:00+00:00",
                (),
                (
                    NoteSummary(
                        "airbus",
                        "Airbus",
                        "project",
                        (),
                        "2026-01-01T00:00:00Z",
                        "2026-09-01T00:00:00Z",
                        {},
                    ),
                ),
                1,
                None,
            )

    result = RuntimeComposition(
        core_execute=lambda *args: source,
        refresh_indexes=lambda: None,
        notes_service=Notes(),
        notes_embedder=object(),
    ).execute("Explica Airbus y muestra las notas", "answer-and-set")

    assert result is not source
    assert result.presentation_intent == "answer_and_note_set"
    assert result.note_result_snapshot is not None
    assert result.note_result_snapshot["note_ids"] == ["airbus"]


def test_runtime_server_rejects_invalid_port() -> None:
    """Transport configuration fails before attempting a socket bind."""
    with pytest.raises(ValueError, match="between 1 and 65535"):
        runtime_server.serve(object(), port=0)


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


def test_runtime_main_conversation_is_actor_scoped_and_has_recent_context(tmp_path: Path) -> None:
    """The product main conversation is durable, actor-scoped, and safely windowed."""
    resolver = ConversationRootResolver(tmp_path / "state")
    runtime = RuntimeComposition(
        core_execute=lambda *args: _result(),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
    )
    actor = AuthenticatedActorContext(USER_A)

    created = runtime.main_conversation(authenticated_actor=actor)
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

    loaded = runtime.load_conversation(conversation_id, authenticated_actor=actor)
    context = runtime.recent_conversation_context(conversation_id, authenticated_actor=actor)

    assert conversation_id == MAIN_CONVERSATION_ID
    assert loaded["conversation_id"] == conversation_id
    assert "actor_id" not in loaded
    assert context == [
        {"role": "user", "text": "Hablamos de Marta"},
        {"role": "assistant", "text": "Marta vive en Lyon"},
    ]
    other = AuthenticatedActorContext(USER_B)
    assert runtime.main_conversation(authenticated_actor=other)["turns"] == []


def test_runtime_execute_forwards_conversation(tmp_path: Path) -> None:
    """Conversation execution persists the visible user turn before forwarding to Core."""
    resolver = ConversationRootResolver(tmp_path / "state")
    calls: list[tuple[object, ...]] = []

    def execute(*args):
        calls.append(args)
        return _result()

    runtime = RuntimeComposition(
        core_execute=execute,
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
    )
    actor = AuthenticatedActorContext(USER_A)

    runtime.execute(
        "¿Dónde vive?",
        request_id="req-1",
        conversation_id=MAIN_CONVERSATION_ID,
        authenticated_actor=actor,
    )

    assert calls == [("¿Dónde vive?", "req-1", actor, MAIN_CONVERSATION_ID)]
    loaded = LocalConversationStore(resolver.resolve(USER_A)).load_main_page()
    turns = [(turn["request_id"], turn["role"], turn["text"]) for turn in loaded["turns"]]
    assert turns == [("req-1", "user", "¿Dónde vive?")]


def test_runtime_conversation_dependencies_fail_closed(tmp_path: Path) -> None:
    """Missing conversation and identity dependencies are explicit failures."""
    actor = AuthenticatedActorContext(USER_A)
    runtime = RuntimeComposition(
        core_execute=lambda *args: _result(),
        refresh_indexes=lambda: None,
    )

    with pytest.raises(ValueError, match="conversation root resolver is unavailable"):
        runtime.execute(
            "hola",
            conversation_id="conv-1",
            authenticated_actor=actor,
        )

    resolver = ConversationRootResolver(tmp_path / "state")
    runtime = RuntimeComposition(
        core_execute=lambda *args: _result(),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        runtime.execute(
            "hola",
            authenticated_actor=actor,
            external_principal=object(),
        )
    with pytest.raises(ValueError, match="external principal mapping"):
        runtime.execute("hola", external_principal=object())
    with pytest.raises(ValueError, match="conversation root resolver"):
        RuntimeComposition(
            core_execute=lambda *args: _result(), refresh_indexes=lambda: None
        ).main_conversation()


def test_runtime_external_principal_maps_actor(tmp_path: Path) -> None:
    """External principals resolve to the stable internal actor before state access."""
    resolver = ConversationRootResolver(tmp_path / "state")
    marker = object()

    class MappingRepository:
        def resolve_existing(self, principal):
            assert principal is marker
            return AuthenticatedActorContext(MAPPED_USER)

    runtime = RuntimeComposition(
        core_execute=lambda *args: _result(),
        refresh_indexes=lambda: None,
        identity_mapping_repository=MappingRepository(),
        conversation_root_resolver=resolver,
    )

    loaded = runtime.main_conversation(external_principal=marker)
    assert loaded["conversation_id"] == MAIN_CONVERSATION_ID
    assert LocalConversationStore(resolver.resolve(MAPPED_USER)).load_main_page()["turns"] == []


def test_runtime_rejects_non_main_conversation_operations(tmp_path: Path) -> None:
    """The root-bound UI-0 boundary exposes no arbitrary chat tenancy operations."""
    runtime = RuntimeComposition(
        core_execute=lambda *args: _result(),
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
    )
    with pytest.raises(ValueError, match="only the main conversation"):
        runtime.load_conversation("other", authenticated_actor=AuthenticatedActorContext(USER_A))
    with pytest.raises(ValueError, match="only the main conversation"):
        runtime.append_conversation_turn(
            "other", "req-1", "user", "text", authenticated_actor=AuthenticatedActorContext(USER_A)
        )
    with pytest.raises(ValueError, match="only the main conversation"):
        runtime.recent_conversation_context(
            "other", authenticated_actor=AuthenticatedActorContext(USER_A)
        )
    with pytest.raises(ValueError, match="only the main conversation"):
        runtime.create_conversation(authenticated_actor=AuthenticatedActorContext(USER_A))
    with pytest.raises(ValueError, match="unavailable"):
        runtime.list_conversations(authenticated_actor=AuthenticatedActorContext(USER_A))
    with pytest.raises(ValueError, match="mutually exclusive"):
        runtime.main_conversation(
            authenticated_actor=AuthenticatedActorContext(USER_A), external_principal=object()
        )
    with pytest.raises(ValueError, match="external principal mapping"):
        runtime.main_conversation(external_principal=object())


def test_runtime_rejects_non_main_execute_and_forwards_anonymous_main(tmp_path: Path) -> None:
    """Execution uses the default hosted actor only for the one supported main conversation."""
    calls: list[tuple[object, ...]] = []

    def execute(*args):
        calls.append(args)
        return _result()

    runtime = RuntimeComposition(
        core_execute=execute,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
    )
    with pytest.raises(ValueError, match="only the main conversation"):
        runtime.execute("text", conversation_id="other")
    runtime.execute("text", conversation_id=MAIN_CONVERSATION_ID)
    assert calls[0][0] == "text"
    assert isinstance(calls[0][1], str)
    assert calls[0][2:] == (None, MAIN_CONVERSATION_ID)
