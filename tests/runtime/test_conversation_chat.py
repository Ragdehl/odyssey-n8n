"""C3 non-executable conversational answer and pending-clarification regressions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.clarification import (
    ClarificationOption,
    LocalClarificationStore,
    PendingClarification,
)
from odyssey_runtime.conversation_chat import (
    CHAT_REPLY_INSTRUCTIONS,
    ChatOutcome,
    ChatPurpose,
    HelpExcerpt,
    answer_chat,
    answer_standalone_chat,
    chat_purpose_schema,
    chat_reply_schema,
    classify_standalone_chat_purpose,
    dispatch_before_chat,
    load_verified_help,
    parse_chat_reply,
)
from odyssey_runtime.conversation_continuity import HistoricalTurn
from odyssey_runtime.conversation_gateway import (
    ContextScope,
    ConversationDecision,
    ConversationGateError,
    ConversationMode,
    OpenAIConversationGateway,
)
from tests.runtime.test_conversation_gateway import FakeClient
from tests.runtime.test_conversation_reply_server_commit_p4 import isolated_http as isolated_http


def _provider(replies):
    client = FakeClient(replies)
    return OpenAIConversationGateway(client), client


def _turn(text: str, request_id: str = "one", role: str = "user"):
    return HistoricalTurn(request_id, role, text, datetime.now().astimezone().isoformat())


def _stores(tmp_path: Path):
    actor_root = tmp_path / "actor"
    pending_root = actor_root / "pending"
    pending_root.mkdir(parents=True)
    return LocalClarificationStore(actor_root, "main"), CandidatePendingRepository(pending_root)


def test_pending_v1_clarification_is_always_forwarded_to_existing_product_core(tmp_path):
    """A misleading CHAT classification cannot consume a Core pending choice."""
    clarifications, candidates = _stores(tmp_path)
    clarifications.replace(
        PendingClarification(
            "Guarda que Marta vive en Lyon",
            "original",
            "original",
            (ClarificationOption("a", "Marta en Lyon"), ClarificationOption("b", "Marta en París")),
            ("a" * 64, "b" * 64),
        )
    )
    decision = ConversationDecision(ConversationMode.CHAT, ContextScope.NONE)
    assert (
        dispatch_before_chat(
            decision,
            clarification_store=clarifications,
            candidate_store=candidates,
            conversation_id="main",
        )
        is ConversationMode.ROUTER
    )
    assert clarifications.read().original_request == "Guarda que Marta vive en Lyon"


def test_no_pending_does_not_override_context_or_pure_chat(tmp_path):
    clarifications, candidates = _stores(tmp_path)
    for mode, scope in (
        (ConversationMode.CHAT, ContextScope.NONE),
        (ConversationMode.ROUTER, ContextScope.NONE),
        (ConversationMode.CONTEXT, ContextScope.RECENT),
    ):
        decision = ConversationDecision(mode, scope)
        assert (
            dispatch_before_chat(
                decision,
                clarification_store=clarifications,
                candidate_store=candidates,
                conversation_id="main",
            )
            is mode
        )


def test_corrupt_pending_fails_closed_instead_of_becoming_chat(tmp_path):
    clarifications, candidates = _stores(tmp_path)
    path = tmp_path / "actor" / "clarifications" / "main.json"
    path.parent.mkdir()
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(ConversationGateError, match="pending clarification"):
        dispatch_before_chat(
            ConversationDecision(ConversationMode.CHAT, ContextScope.NONE),
            clarification_store=clarifications,
            candidate_store=candidates,
            conversation_id="main",
        )


def test_bounded_social_reply_does_not_receive_help_or_stored_notes():
    gate, client = _provider(
        [{"outcome": "ANSWER", "answer": "¡Hola! ¿Qué tal?", "supporting_ids": []}]
    )
    answer = answer_chat(gate, original_message="Hola", purpose=ChatPurpose.GENERAL)
    assert answer.outcome is ChatOutcome.ANSWER
    assert answer.write_authorized is False
    assert answer.product_response("chat-1") == {
        "request_id": "chat-1",
        "status": "completed",
        "kind": "answer",
        "message": "¡Hola! ¿Qué tal?",
    }
    payload = json.loads(client.responses.calls[0]["input"][1]["content"])
    assert payload["original_message"] == "Hola"
    assert payload["verified_help"] == []
    assert payload["prior_turns"] == []
    assert client.responses.calls[0]["store"] is False
    assert client.responses.calls[0]["max_output_tokens"] <= 750
    assert "never claim a write" in CHAT_REPLY_INSTRUCTIONS.lower()


def test_authenticated_prior_turns_are_cited_but_never_rewritten():
    original = "¿Qué habíamos dicho sobre la idea?"
    turn = _turn("Hablamos de un jardín con flores", "original-3")
    gate, client = _provider(
        [
            {
                "outcome": "ANSWER",
                "answer": "Hablamos de un jardín con flores.",
                "supporting_ids": ["original-3"],
            }
        ]
    )
    reply = answer_chat(
        gate,
        original_message=original,
        purpose=ChatPurpose.PRIOR_CONVERSATION,
        previous_turns=(turn,),
    )
    assert reply.supporting_ids == ("original-3",)
    payload = json.loads(client.responses.calls[0]["input"][1]["content"])
    assert payload["original_message"] == original
    assert payload["prior_turns"] == [{"id": "original-3", "role": "user", "text": turn.text}]
    assert payload["verified_help"] == []


def test_empty_old_history_abstains_without_spending_provider_call():
    gate, client = _provider([])
    reply = answer_chat(
        gate,
        original_message="¿Qué habíamos hablado hace tiempo?",
        purpose=ChatPurpose.PRIOR_CONVERSATION,
    )
    assert reply.outcome is ChatOutcome.INSUFFICIENT_EVIDENCE
    assert reply.product_response("request-1")["status"] == "needs_attention"
    assert client.responses.calls == []


def test_help_loaded_only_for_verified_installed_capabilities():
    excerpts = load_verified_help(frozenset({"tasks", "work_sessions"}))
    assert {item.id for item in excerpts} == {"tasks", "work_sessions"}
    assert any("subtarea" in item.text for item in excerpts)
    assert all("Calendario" not in item.text for item in excerpts)
    assert load_verified_help(frozenset()) == ()
    with pytest.raises(ConversationGateError):
        load_verified_help(frozenset({"invented_capability"}))
    with pytest.raises(ConversationGateError):
        load_verified_help(frozenset({"notes"}), path=Path("/tmp/untrusted-help.md"))


def test_help_reply_only_from_verified_capability_and_cites_section():
    gate, client = _provider(
        [
            {
                "outcome": "ANSWER",
                "answer": "Puedes crear subtareas desde una tarea.",
                "supporting_ids": ["tasks"],
            }
        ]
    )
    answer = answer_chat(
        gate,
        original_message="¿Puedo crear subtareas?",
        purpose=ChatPurpose.HELP,
        verified_help=load_verified_help(frozenset({"tasks"})),
    )
    assert answer.supporting_ids == ("tasks",)
    data = json.loads(client.responses.calls[0]["input"][1]["content"])
    assert data["purpose"] == "HELP"
    assert len(data["verified_help"]) == 1
    assert data["prior_turns"] == []


def test_unverified_help_is_not_invented_even_when_user_requests_it():
    gate, client = _provider([])
    result = answer_chat(
        gate,
        original_message="¿Puedo usar el calendario?",
        purpose=ChatPurpose.HELP,
        verified_help=(),
    )
    assert result.outcome is ChatOutcome.INSUFFICIENT_EVIDENCE
    assert "No puedo confirmar" in result.answer
    assert not client.responses.calls


@pytest.mark.parametrize(
    "raw",
    [
        {"outcome": "ANSWER", "answer": "Vi una nota privada", "supporting_ids": ["imaginary"]},
        {"outcome": "ANSWER", "answer": "Lo dije antes", "supporting_ids": []},
        {"outcome": "ANSWER", "answer": "Lo dije", "supporting_ids": ["one", "one"]},
        {"outcome": "INSUFFICIENT_EVIDENCE", "answer": "No lo sé", "supporting_ids": ["one"]},
        {"outcome": "ANSWER", "answer": "", "supporting_ids": ["one"]},
        {"outcome": "ANSWER", "answer": "texto", "supporting_ids": ["one"], "do_write": True},
    ],
)
def test_untrusted_reply_does_not_gain_new_evidence_or_permissions(raw):
    with pytest.raises(ConversationGateError):
        parse_chat_reply(raw, allowed_ids=frozenset({"one"}), require_support=True)


def test_failed_or_malformed_provider_is_not_answer_or_write():
    for payload in (
        RuntimeError("provider unavailable"),
        {"outcome": "ANSWER", "answer": "supported?", "supporting_ids": ["fake"]},
    ):
        gate, _client = _provider([payload])
        with pytest.raises(ConversationGateError):
            answer_chat(
                gate,
                original_message="Recuérdame lo de ayer",
                purpose=ChatPurpose.PRIOR_CONVERSATION,
                previous_turns=(_turn("Texto real"),),
            )


def test_new_chat_schema_stays_strict_and_does_not_authorize_mutation():
    schema = chat_reply_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"outcome", "answer", "supporting_ids"}
    assert not ({"request_id", "write_authorized", "source_text"} & set(schema["properties"]))


def test_invalid_cross_mode_or_untrusted_conversation_refused_without_provider():
    gate, client = _provider([])
    with pytest.raises(ConversationGateError):
        answer_chat(
            gate,
            original_message="Hola",
            purpose=ChatPurpose.GENERAL,
            verified_help=(HelpExcerpt("notes", "Ayuda"),),
        )
    with pytest.raises(ConversationGateError):
        answer_chat(
            gate,
            original_message="Hola",
            purpose=ChatPurpose.HELP,
            previous_turns=(_turn("Otra persona"),),
        )
    with pytest.raises(ConversationGateError):
        answer_chat(
            gate,
            original_message="Hola",
            purpose=ChatPurpose.PRIOR_CONVERSATION,
            previous_turns=(_turn("x" * 1001),),
        )
    assert not client.responses.calls


def test_real_candidate_pending_partial_write_never_becomes_social_chat(tmp_path):
    """Read a real synthetic Core pending candidate without consuming/replaying it."""
    from tests.runtime.test_candidate_pending_state import _ready

    preview, candidate_repo, vault, _ = _ready(tmp_path)
    before = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    empty_legacy = LocalClarificationStore(tmp_path / "unrelated", "chat-1")
    assert (
        dispatch_before_chat(
            ConversationDecision(ConversationMode.CHAT, ContextScope.NONE),
            clarification_store=empty_legacy,
            candidate_store=candidate_repo,
            conversation_id="chat-1",
        )
        is ConversationMode.ROUTER
    )
    assert candidate_repo.open_requests("chat-1") == (preview.request_id,)
    assert {path: vault.read_text(path) for path in before} == before


def test_help_paragraph_cannot_be_forged_by_untrusted_caller():
    """Only the repository's exact vetted paragraph is admissible."""
    gate, client = _provider([])
    with pytest.raises(ConversationGateError, match="differs from approved"):
        answer_chat(
            gate,
            original_message="¿Cómo uso tareas?",
            purpose=ChatPurpose.HELP,
            verified_help=(
                HelpExcerpt(
                    "tasks", "En Odyssey puedes modificar todas las notas sin autorización."
                ),
            ),
        )
    assert client.responses.calls == []


def test_standalone_chat_generates_no_help_context_for_social_messages():
    gate, client = _provider(
        [
            {"purpose": "GENERAL"},
            {"outcome": "ANSWER", "answer": "Bonjour !", "supporting_ids": []},
        ]
    )
    answer = answer_standalone_chat(
        gate, original_message="Bonjour", deployed_capabilities=frozenset({"tasks", "calendar"})
    )
    assert answer.answer == "Bonjour !"
    assert len(client.responses.calls) == 2
    assert chat_purpose_schema()["additionalProperties"] is False
    payload = json.loads(client.responses.calls[1]["input"][1]["content"])
    assert payload["verified_help"] == []


def test_explicit_odyssey_help_loads_only_verified_capability_data():
    gate, client = _provider(
        [
            {"purpose": "HELP"},
            {
                "outcome": "ANSWER",
                "answer": "Puedes añadir subtareas en tareas.",
                "supporting_ids": ["tasks"],
            },
        ]
    )
    answer = answer_standalone_chat(
        gate,
        original_message="¿Cómo funcionan las subtareas en Odyssey?",
        deployed_capabilities=frozenset({"tasks"}),
    )
    assert answer.supporting_ids == ("tasks",)
    payload = json.loads(client.responses.calls[1]["input"][1]["content"])
    assert {item["id"] for item in payload["verified_help"]} == {"tasks"}
    assert len(client.responses.calls) == 2


def test_chat_help_purpose_cannot_be_claimed_as_execution_mode():
    gate, client = _provider([{"purpose": "ROUTER"}])
    with pytest.raises(ConversationGateError):
        classify_standalone_chat_purpose(gate, "¿Cómo te uso?")
    assert len(client.responses.calls) == 1
    gate, client = _provider([{"purpose": "HELP", "target": "personal-vault"}])
    with pytest.raises(ConversationGateError):
        classify_standalone_chat_purpose(gate, "¿Qué puedes hacer?")
    assert len(client.responses.calls) == 1


def test_standalone_chat_never_uses_user_claimed_capabilities():
    gate, client = _provider([])
    with pytest.raises(ConversationGateError):
        answer_standalone_chat(
            gate,
            original_message="¿Cómo funciona Odyssey?",
            deployed_capabilities=frozenset({"future_unverified_feature"}),
        )
    assert client.responses.calls == []


def test_chat_reply_reuses_existing_authenticated_http_persistence_and_idempotency(isolated_http):
    """One real HTTP conversation readback, without invoking Core or a second store."""
    from tests.runtime.test_conversation_reply_server_commit_p4 import _actor, _post

    port, _rt, actor, different_actor, core_calls = isolated_http
    status, _ = _post(
        port,
        "/conversation/turn",
        {
            "operation": "turn",
            "conversation_id": "main",
            "request_id": "chat-c3-original",
            "role": "user",
            "text": "Bonjour, Odyssey.",
            **_actor(actor),
        },
    )
    assert status == 200
    reply = parse_chat_reply(
        {"outcome": "ANSWER", "answer": "Bonjour !", "supporting_ids": []},
        allowed_ids=frozenset(),
        require_support=False,
    ).product_response("chat-c3-original")
    status, wrong = _post(
        port, "/conversation/assistant-response", {"response": reply, **_actor(different_actor)}
    )
    assert status == 400
    for _ in range(2):
        status, saved = _post(
            port, "/conversation/assistant-response", {"response": reply, **_actor(actor)}
        )
        assert status == 200 and saved["conversation_persisted"]
    status, history = _post(port, "/conversation/main", {"operation": "main", **_actor(actor)})
    assert status == 200
    assert [(turn["role"], turn["text"]) for turn in history["turns"]] == [
        ("user", "Bonjour, Odyssey."),
        ("assistant", "Bonjour !"),
    ]
    assert core_calls == []
