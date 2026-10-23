"""Contract and safety regressions for the non-executing conversation gateway."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from odyssey_apps.router import ROUTER_MODEL
from odyssey_core.local_conversations import LocalConversationStore
from odyssey_runtime.conversation_gateway import (
    CHAT_GATE_MAX_INPUT_CHARS,
    CLASSIFY_INSTRUCTIONS,
    ERROR_INSTRUCTIONS,
    ContextScope,
    ConversationDecision,
    ConversationGateError,
    ConversationMode,
    ConversationState,
    ErrorAdvice,
    GuidanceKind,
    OpenAIConversationGateway,
    RecoveryHint,
    VerifiedFailure,
    decision_schema,
    error_advice_schema,
    parse_decision,
    parse_error_advice,
    read_recent_continuity,
)


class FakeResponses:
    """Record provider args and return SDK-shaped, injected strict output."""

    def __init__(self, replies: list[object]) -> None:
        """Preserve a finite provider trace for each exercised model mode."""
        self.replies = replies
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        """Return the next response without using a billable model."""
        self.calls.append(kwargs)
        output = self.replies.pop(0)
        if isinstance(output, Exception):
            raise output
        return SimpleNamespace(status="completed", output_text=json.dumps(output))


class FakeClient:
    """Expose the same Responses attribute used by Router."""

    def __init__(self, replies: list[object]):
        """Initialize fixed fake payloads."""
        self.responses = FakeResponses(replies)


@pytest.mark.parametrize(
    ("raw", "mode", "scope"),
    [
        ({"mode": "ROUTER", "context_scope": "NONE"}, ConversationMode.ROUTER, ContextScope.NONE),
        ({"mode": "CHAT", "context_scope": "NONE"}, ConversationMode.CHAT, ContextScope.NONE),
        (
            {"mode": "CONTEXT", "context_scope": "RECENT"},
            ConversationMode.CONTEXT,
            ContextScope.RECENT,
        ),
        (
            {"mode": "CONTEXT", "context_scope": "HISTORY"},
            ConversationMode.CONTEXT,
            ContextScope.HISTORY,
        ),
    ],
)
def test_closed_preflight_decision_contract(raw, mode, scope):
    """Only a post-execution trusted result may activate error guidance."""
    assert parse_decision(raw) == ConversationDecision(mode, scope)


@pytest.mark.parametrize(
    "raw",
    [
        {"mode": "ERROR", "context_scope": "NONE"},
        {"mode": "ROUTER", "context_scope": "RECENT"},
        {"mode": "CONTEXT", "context_scope": "NONE"},
        {"mode": "CHAT", "context_scope": "HISTORY"},
        {"mode": "ROUTER", "context_scope": "NONE", "source_text": "invented"},
        {"mode": "ROUTER"},
        {"mode": "OTHER", "context_scope": "NONE"},
        {"mode": 1, "context_scope": "NONE"},
    ],
)
def test_invalid_preflight_is_not_executable(raw):
    """Reject injected fields, unauthorized modes and contradictory evidence."""
    with pytest.raises(ConversationGateError):
        parse_decision(raw)


def test_decision_model_call_reuses_router_luna_and_does_not_rewrite_message():
    """Classify only original source and compact conversational state."""
    model = FakeClient([{"mode": "CONTEXT", "context_scope": "RECENT"}])
    gateway = OpenAIConversationGateway(model)
    state = ConversationState(
        active_topic="Encuentro con Bruno",
        pending_clarification=False,
        last_status="completed",
    )
    original = "Luego también hemos ido a tomar algo."
    decision = gateway.classify(original, state)
    assert decision.mode is ConversationMode.CONTEXT
    call = model.responses.calls[0]
    assert len(model.responses.calls) == 1
    assert call["model"] == ROUTER_MODEL
    assert call["reasoning"] == {"effort": "low"}
    assert call["store"] is False
    assert call["max_output_tokens"] <= 320
    source = json.loads(call["input"][1]["content"])
    assert source["original_message"] == original
    assert source["active_topic_hint"] == "Encuentro con Bruno"
    assert list(source) == [
        "original_message",
        "active_topic_hint",
        "pending_clarification",
        "last_status",
    ]
    assert "Router" not in source
    assert "never resolve note identities" in CLASSIFY_INSTRUCTIONS


def test_model_error_advice_uses_verified_receipt_and_cannot_retry():
    """Error guidance is read-only; model never selects a target or executes."""
    model = FakeClient([{"guidance_kind": "SPECIFY_IDENTITY", "hint": "ASK_USER"}])
    gateway = OpenAIConversationGateway(model)
    receipt = VerifiedFailure(
        "safe123", "needs_attention", "WORK_SESSION_TASK_AMBIGUOUS", written_count=0
    )
    advice = gateway.explain_error(receipt)
    assert advice.hint is RecoveryHint.ASK_USER
    assert advice.retry_authorized is False
    assert "no tiene escrituras confirmadas" in advice.user_message(receipt)
    call = model.responses.calls[0]
    assert call["model"] == ROUTER_MODEL
    assert call["max_output_tokens"] <= 550
    assert "no automatic retries" in ERROR_INSTRUCTIONS
    evidence = json.loads(call["input"][1]["content"])
    assert evidence == {
        "status": "needs_attention",
        "reason_code": "WORK_SESSION_TASK_AMBIGUOUS",
        "write_evidence": "ZERO_CONFIRMED",
    }
    assert "request_id" not in evidence


def test_unknown_write_evidence_never_defaults_to_zero():
    """Missing write proof must not be silently interpreted as no mutation."""
    with pytest.raises(TypeError):
        VerifiedFailure("safe123", "partial", "OPERATIONAL_FAILURE")
    unknown = VerifiedFailure("safe123", "partial", "OPERATIONAL_FAILURE", None)
    advice = ErrorAdvice(GuidanceKind.UNKNOWN, RecoveryHint.EXPLAIN)
    assert "No puedo confirmar" in advice.user_message(unknown)
    client = FakeClient([{"guidance_kind": "UNKNOWN", "hint": "EXPLAIN"}])
    gate = OpenAIConversationGateway(client)
    assert gate.explain_error(unknown).guidance_kind is GuidanceKind.UNKNOWN
    evidence = json.loads(client.responses.calls[0]["input"][1]["content"])
    assert evidence["write_evidence"] == "UNKNOWN"


def test_model_cannot_inject_false_status_or_free_text_into_error():
    """LLM output never supplies the words used to describe canonical writes."""
    with pytest.raises(ConversationGateError):
        parse_error_advice(
            {
                "guidance_kind": "UNKNOWN",
                "hint": "ASK_USER",
                "guidance": "Nada se ha guardado, repite ya la operación",
            }
        )
    with pytest.raises(ConversationGateError):
        parse_error_advice(
            {
                "guidance_kind": "Nada se ha guardado",
                "hint": "ASK_USER",
            }
        )


def test_partial_write_is_never_reported_as_certain_empty():
    """Model guidance cannot override independently verified mutation count."""
    advice = ErrorAdvice(GuidanceKind.CLARIFY_REQUEST, RecoveryHint.EXPLAIN)
    receipt = VerifiedFailure("req1", "partial", "OPERATIONAL_FAILURE", written_count=2)
    assert advice.user_message(receipt).startswith("Odyssey ha guardado parte")


@pytest.mark.parametrize(
    "invalid",
    [
        {"guidance_kind": "SPECIFY_IDENTITY", "hint": "ASK_USER", "auto_retry": True},
        {"guidance_kind": "", "hint": "EXPLAIN"},
        {"guidance_kind": "UNKNOWN", "hint": "RETRY_NOW"},
        {"guidance_kind": "UNKNOWN"},
    ],
)
def test_untrusted_repair_commands_never_enter_execution(invalid):
    """Even REVIEW_RETRY is only a hint, never a new routed request."""
    with pytest.raises(ConversationGateError):
        parse_error_advice(invalid)
    assert (
        parse_error_advice({"guidance_kind": "UNKNOWN", "hint": "REVIEW_RETRY"}).retry_authorized
        is False
    )


@pytest.mark.parametrize(
    "receipt",
    [
        ("x", "completed", "ANY", 0),
        ("x", "failed", "ERROR", -1),
        ("x", "failed", "ERROR", True),
        ("", "failed", "ERROR", 0),
        ("x", "failed", "", 0),
    ],
)
def test_verified_failure_requires_trusted_and_bounded_state(receipt):
    """Never render post-execution advice for success or malformed evidence."""
    with pytest.raises(ConversationGateError):
        VerifiedFailure(*receipt)


def test_providers_fail_closed_on_transport_incomplete_and_malformed():
    """No routing or advice may be inferred from model transport failures."""
    failures = [RuntimeError("provider down"), ["not a dict"], {"unknown": 1}]
    for value in failures:
        gateway = OpenAIConversationGateway(FakeClient([value]))
        with pytest.raises(ConversationGateError):
            gateway.classify("Guárdalo.", ConversationState())


def test_bounded_inputs_and_statuses():
    """Prompt size and stale continuity state are constrained before provider."""
    gateway = OpenAIConversationGateway(FakeClient([]))
    with pytest.raises(ConversationGateError):
        gateway.classify("x" * (CHAT_GATE_MAX_INPUT_CHARS + 1), ConversationState())
    with pytest.raises(ConversationGateError):
        ConversationState(active_topic="x" * 121)
    with pytest.raises(ConversationGateError):
        ConversationState(last_status="unexpected")
    with pytest.raises(ConversationGateError):
        gateway.explain_error("failed")


def test_only_strict_schema_fields_and_no_error_entry_route():
    """Validate the same strict provider policy used by the existing Router."""
    schema = decision_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["mode"]["enum"] == ["ROUTER", "CHAT", "CONTEXT"]
    assert set(schema["required"]) == {"mode", "context_scope"}
    assert error_advice_schema()["additionalProperties"] is False
    assert "retry_authorized" not in error_advice_schema()["properties"]


def test_context_mode_reuses_actor_rooted_recent_messages_without_current_request(tmp_path):
    """Use existing local transcript bounds, not an untrusted LLM-written summary."""
    old = "2026-10-23T09:00:00+02:00"
    store = LocalConversationStore(tmp_path / "actor-a")
    store.load_or_create_main(now=old)
    store.append_turn(
        request_id="previous1",
        role="user",
        text="Hoy he visto a Bruno, al que le encanta la guitarra.",
        created_at=old,
    )
    store.append_turn(
        request_id="previous1",
        role="assistant",
        text="La información se ha guardado.",
        created_at=old,
        status="completed",
    )
    store.append_turn(
        request_id="current2",
        role="user",
        text="Luego hemos ido a tomar algo.",
        created_at=old,
    )
    decision = ConversationDecision(ConversationMode.CONTEXT, ContextScope.RECENT)
    history = read_recent_continuity(decision, store, request_id="current2")
    assert [turn["role"] for turn in history] == ["user", "assistant"]
    assert history[0]["text"].startswith("Hoy he visto a Bruno")
    assert all("Luego hemos ido" not in turn["text"] for turn in history)
    # A caller supplied with the wrong actor's authenticated root obtains no
    # transcript; this gateway cannot escape that root or select identities.
    other = LocalConversationStore(tmp_path / "actor-b")
    other.load_or_create_main(now=old)
    assert read_recent_continuity(decision, other, request_id="current2") == ()


def test_history_retrieval_not_silently_implemented_or_guessed(tmp_path):
    """Thirty-day/week/month recall needs a separate scoped evidence contract."""
    store = LocalConversationStore(tmp_path / "actor-a")
    old = "2026-10-23T09:00:00+02:00"
    store.load_or_create_main(now=old)
    with pytest.raises(ConversationGateError, match="Historical context"):
        read_recent_continuity(
            ConversationDecision(ConversationMode.CONTEXT, ContextScope.HISTORY),
            store,
            request_id="current2",
        )
    with pytest.raises(ConversationGateError, match="validated CONTEXT"):
        read_recent_continuity(
            ConversationDecision(ConversationMode.ROUTER, ContextScope.NONE),
            store,
            request_id="current2",
        )
