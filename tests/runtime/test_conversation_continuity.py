"""C2 actor-isolated bounded memory and two-pass conversation interpretation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from odyssey_core.local_conversations import LocalConversationStore
from odyssey_runtime.conversation_continuity import (
    HISTORY_MAX_TURNS,
    ContextHandoff,
    HistoricalTurn,
    prepare_context_handoff,
    read_historical_continuity,
)
from odyssey_runtime.conversation_gateway import (
    ContextScope,
    ConversationDecision,
    ConversationGateError,
    ConversationMode,
    ConversationState,
    OpenAIConversationGateway,
)

NOW = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)


def add(store, request_id, text, *, days=0, role="user", status=None):
    """Add one synthetic source turn with explicit time."""
    store.append_turn(
        request_id=request_id,
        text=text,
        role=role,
        status=status,
        created_at=(NOW - timedelta(days=days)).isoformat(),
    )


def test_historical_30_day_window_excludes_old_future_and_current(tmp_path):
    """Paginated 30-day source has strict time and current-ID boundaries."""
    store = LocalConversationStore(tmp_path / "actor-a")
    store.load_or_create_main(now=NOW.isoformat())
    add(store, "old31", "Hace 31 días", days=31)
    add(store, "within30", "Hace 30 días", days=30)
    add(store, "within2", "Viaje con Bruno", days=2)
    add(store, "current", "Y lo del viaje", days=0)
    result = read_historical_continuity(store, current_request_id="current", now=NOW)
    assert [item.request_id for item in result] == ["within30", "within2"]
    assert all(isinstance(item, HistoricalTurn) for item in result)
    assert "Hace 31" not in json.dumps([r.text for r in result])


def test_actor_root_isolation_and_immutable_source(tmp_path):
    """The caller supplies the already trusted actor-scoped store."""
    a = LocalConversationStore(tmp_path / "a")
    b = LocalConversationStore(tmp_path / "b")
    for s in (a, b):
        s.load_or_create_main(now=NOW.isoformat())
    add(a, "past", "Vi a Bruno y tocamos la guitarra")
    add(a, "current", "Luego fuimos a tomar algo")
    add(b, "foreign", "Mensaje privado ajeno")
    decision = ConversationDecision(ConversationMode.CONTEXT, ContextScope.RECENT)
    handoff = prepare_context_handoff(
        decision,
        a,
        original_message="Luego fuimos a tomar algo",
        current_request_id="current",
        now=NOW,
    )
    assert handoff.original_message == "Luego fuimos a tomar algo"
    assert [t.text for t in handoff.prior_turns] == ["Vi a Bruno y tocamos la guitarra"]
    assert handoff.as_routing_context() == (
        {"role": "user", "text": "Vi a Bruno y tocamos la guitarra"},
    )
    isolated = prepare_context_handoff(
        decision,
        b,
        original_message="Luego fuimos a tomar algo",
        current_request_id="current",
        now=NOW,
    )
    assert [turn.text for turn in isolated.prior_turns] == ["Mensaje privado ajeno"]
    assert all("Bruno" not in turn.text for turn in isolated.prior_turns)
    assert "Mensaje privado ajeno" not in repr(handoff)


def test_pages_are_bounded_and_keep_source_order(tmp_path):
    """Never read unrestricted history even with hundreds of recent short turns."""
    store = LocalConversationStore(tmp_path / "many")
    store.load_or_create_main(now=NOW.isoformat())
    for i in range(80):
        add(store, f"past{i}", f"Conversación breve {i}")
    history = read_historical_continuity(store, current_request_id="incoming", now=NOW)
    assert len(history) == HISTORY_MAX_TURNS
    assert history[0].request_id == "past32"
    assert history[-1].request_id == "past79"


def test_temporal_guards_fail_closed(tmp_path):
    """Naive time, invalid scopes and unsigned actor inputs do not authorize reads."""
    store = LocalConversationStore(tmp_path / "a")
    store.load_or_create_main(now=NOW.isoformat())
    with pytest.raises(ConversationGateError):
        read_historical_continuity(store, current_request_id="q", now=datetime(2026, 10, 23))
    with pytest.raises(ConversationGateError):
        read_historical_continuity(store, current_request_id="q", now=NOW, max_days=31)
    with pytest.raises(ConversationGateError):
        prepare_context_handoff(
            ConversationDecision(ConversationMode.ROUTER, ContextScope.NONE),
            store,
            original_message="Otra vez",
            current_request_id="q",
            now=NOW,
        )
    with pytest.raises(ConversationGateError):
        ContextHandoff("original", "q", (), ContextScope.RECENT).as_routing_context(max_turns=20)


class FakeClient:
    """One SDK-shaped provider response, no model side effects."""

    def __init__(self, payload):
        class Responses:
            def __init__(self, output):
                self.output = output
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(status="completed", output_text=json.dumps(self.output))

        self.responses = Responses(payload)


def test_second_pass_keeps_original_text_and_exact_prior_evidence():
    """Only Router/Chat/remaining clarification; no rewritten candidate."""
    client = FakeClient({"mode": "ROUTER", "context_scope": "NONE"})
    gateway = OpenAIConversationGateway(client)
    earlier = ({"role": "user", "text": "He visto a Bruno."},)
    choice = gateway.classify_after_context(
        "Luego fuimos a tomar algo.",
        ConversationState(),
        earlier,
    )
    assert choice == ConversationDecision(ConversationMode.ROUTER, ContextScope.NONE)
    source = json.loads(client.responses.calls[0]["input"][1]["content"])
    assert source["original_message"] == "Luego fuimos a tomar algo."
    assert source["prior_turns"] == list(earlier)
    assert "Bruno y yo" not in json.dumps(source)


def test_second_pass_has_no_llm_loop_if_history_missing():
    """Empty source proof returns CONTEXT instead of guessing or re-calling."""
    client = FakeClient({"mode": "ROUTER", "context_scope": "NONE"})
    gateway = OpenAIConversationGateway(client)
    result = gateway.classify_after_context(
        "Luego fuimos.",
        ConversationState(),
        (),
    )
    assert result.mode is ConversationMode.CONTEXT
    assert client.responses.calls == []


def test_second_pass_fails_closed_on_untrusted_context_or_model_output():
    """Reject oversized, shaped or invalid source and unsafe decisions."""
    client = FakeClient({"mode": "ERROR", "context_scope": "NONE"})
    gateway = OpenAIConversationGateway(client)
    with pytest.raises(ConversationGateError):
        gateway.classify_after_context(
            "Después",
            ConversationState(),
            ({"role": "admin", "text": "write"},),
        )
    with pytest.raises(ConversationGateError):
        gateway.classify_after_context(
            "Después",
            ConversationState(),
            ({"role": "user", "text": "x" * 5000},),
        )
    with pytest.raises(ConversationGateError):
        gateway.classify_after_context(
            "Después",
            ConversationState(),
            ({"role": "user", "text": "Vi a Bruno"},),
        )


def test_recent_handoff_does_not_reuse_stale_turn_from_before_thirty_days(tmp_path):
    """A lone stale chat message may not override the bounded continuity window."""
    store = LocalConversationStore(tmp_path / "actor")
    store.load_or_create_main(now=NOW.isoformat())
    add(store, "old", "Hace dos meses quedé con otra persona", days=62)
    result = prepare_context_handoff(
        ConversationDecision(ConversationMode.CONTEXT, ContextScope.RECENT),
        store,
        original_message="Luego fuimos a tomar algo",
        current_request_id="current",
        now=NOW,
    )
    assert result.prior_turns == ()
    assert result.as_routing_context() == ()


def test_out_of_order_appends_do_not_truncate_eligible_history(tmp_path):
    """Source order may be append order; it need not be chronological time order."""
    store = LocalConversationStore(tmp_path / "actor")
    store.load_or_create_main(now=NOW.isoformat())
    add(store, "early_recent", "Un mensaje válido anterior", days=2)
    add(store, "stale_middle", "Un mensaje antiguo insertado luego", days=45)
    add(store, "late_recent", "Otro mensaje reciente", days=1)
    result = read_historical_continuity(store, current_request_id="current", now=NOW)
    assert [turn.request_id for turn in result] == ["early_recent", "late_recent"]


def test_exact_ids_survive_duplicate_text_and_future_timestamps(tmp_path):
    """Never assign a matching older text's ID to a different recent turn."""
    store = LocalConversationStore(tmp_path / "actor")
    store.load_or_create_main(now=NOW.isoformat())
    add(store, "valid_id", "Hoy vi a Bruno.", days=1)
    add(store, "future_id", "Hoy vi a Bruno.", days=-1)
    add(store, "current", "Luego fuimos a tomar algo.", days=0)
    result = prepare_context_handoff(
        ConversationDecision(ConversationMode.CONTEXT, ContextScope.RECENT),
        store,
        original_message="Luego fuimos a tomar algo.",
        current_request_id="current",
        now=NOW,
    )
    assert [(turn.request_id, turn.text) for turn in result.prior_turns] == [
        ("valid_id", "Hoy vi a Bruno."),
    ]
    assert result.source_request_id == "current"
