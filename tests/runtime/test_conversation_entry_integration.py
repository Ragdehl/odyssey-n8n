"""C1–C3 integration: real runtime delivery, replay, pending choices and isolation.

No provider, network credentials or production vault. Calls follow the same
execute_product/assistant-response contracts as the existing n8n workflow.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from odyssey_runtime.delivery_results import DeliveryResultError
from tests.runtime.test_conversation_gateway import FakeClient


def _runtime(tmp_path, replies):
    calls = []

    def core_execute(source, request_id, *_args, **_kwargs):
        calls.append((source, request_id))
        return ApplicationResult(request_id, ApplicationStatus.COMPLETED, (), ())

    client = FakeClient(replies)
    runtime = RuntimeComposition(
        core_execute=core_execute,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "synthetic-state"),
        conversation_gateway=OpenAIConversationGateway(client),
        conversation_deployed_capabilities=frozenset({"tasks", "notes"}),
    )
    return runtime, calls, client


def _actor():
    return AuthenticatedActorContext(str(uuid4()))


def _turns(runtime, actor):
    return runtime.main_conversation(actor)["turns"]


def test_chat_general_is_nonwriting_durable_and_replayed(tmp_path):
    runtime, writes, client = _runtime(
        tmp_path,
        [
            {"mode": "CHAT", "context_scope": "NONE"},
            {"purpose": "GENERAL"},
            {"outcome": "ANSWER", "answer": "¡Hola! 😊", "supporting_ids": []},
        ],
    )
    actor = _actor()
    payload = runtime.execute_product("Hola", "c3-social", "main", actor)
    assert payload["product_outcome"] == "ANSWER"
    assert payload["conversation_reply"]["message"] == "¡Hola! 😊"
    assert payload["actions"] == [] and payload["affected_stable_note_ids"] == []
    assert writes == [] and len(client.responses.calls) == 3
    assert [(t["role"], t["text"]) for t in _turns(runtime, actor)] == [("user", "Hola")]
    response = {"request_id": "c3-social", **payload["conversation_reply"]}
    runtime.persist_product_assistant_response(response, actor)
    runtime.persist_product_assistant_response(response, actor)
    repeat = runtime.execute_product("Hola", "c3-social", "main", actor)
    assert repeat["delivery_replayed"] is True
    assert len(client.responses.calls) == 3 and writes == []
    assert [(t["role"], t["text"]) for t in _turns(runtime, actor)] == [
        ("user", "Hola"),
        ("assistant", "¡Hola! 😊"),
    ]


def test_explicit_save_or_mixed_request_keeps_original_core_route(tmp_path):
    for source in (
        "Hoy he visto a Bruno, guárdalo.",
        "Compré una bicicleta ayer. ¿Cómo puedo usar mis tareas?",
    ):
        runtime, writes, client = _runtime(
            tmp_path / str(len(source)), [{"mode": "ROUTER", "context_scope": "NONE"}]
        )
        result = runtime.execute_product(source, "save-one", "main", _actor())
        assert result["product_outcome"] == "ANSWER"
        assert writes == [(source, "save-one")]
        assert "conversation_reply" not in result
        assert len(client.responses.calls) == 1


def test_help_requires_verified_deployed_capability_and_no_core(tmp_path):
    runtime, writes, client = _runtime(
        tmp_path,
        [
            {"mode": "CHAT", "context_scope": "NONE"},
            {"purpose": "HELP"},
            {
                "outcome": "ANSWER",
                "answer": "Puedes añadir subtareas.",
                "supporting_ids": ["tasks"],
            },
        ],
    )
    result = runtime.execute_product("¿Cómo creo subtareas?", "help-one", "main", _actor())
    assert result["conversation_reply"]["message"] == "Puedes añadir subtareas."
    assert writes == []
    assert len(client.responses.calls) == 3


def test_unavailable_provider_never_turns_into_a_write(tmp_path):
    runtime, writes, _client = _runtime(tmp_path, [RuntimeError("temporary failure")])
    actor = _actor()
    outcome = runtime.execute_product("Guarda que he salido", "no-retry", "main", actor)
    assert outcome["product_outcome"] == "CANNOT_ANSWER"
    assert outcome["conversation_reply"]["status"] == "needs_attention"
    assert writes == []
    assert _turns(runtime, actor)[0]["text"] == "Guarda que he salido"
    assert runtime.execute_product("Guarda que he salido", "no-retry", "main", actor)[
        "delivery_replayed"
    ]


def test_context_chat_preserves_prior_sources_and_does_not_core_write(tmp_path):
    runtime, writes, client = _runtime(
        tmp_path,
        [
            {"mode": "CONTEXT", "context_scope": "RECENT"},
            {"intent": "CHAT"},
            {"outcome": "ANSWER", "answer": "Hablamos de un jardín.", "supporting_ids": ["old-id"]},
        ],
    )
    actor = _actor()
    runtime.append_conversation_turn(
        "main", "old-id", "user", "Hablamos de un jardín.", authenticated_actor=actor
    )
    result = runtime.execute_product("¿Qué hablamos antes?", "recall-id", "main", actor)
    assert result["conversation_reply"]["message"] == "Hablamos de un jardín."
    assert writes == []
    assert len(client.responses.calls) == 3
    assert _turns(runtime, actor)[-1]["text"] == "¿Qué hablamos antes?"


def test_context_clarify_does_not_guess_referents_or_write(tmp_path):
    runtime, writes, client = _runtime(
        tmp_path,
        [
            {"mode": "CONTEXT", "context_scope": "RECENT"},
            {"intent": "CLARIFY"},
        ],
    )
    actor = _actor()
    outcome = runtime.execute_product("Y ellos también", "ambig", "main", actor)
    assert outcome["conversation_reply"]["kind"] == "clarification"
    assert writes == [] and len(client.responses.calls) == 2


def test_second_actor_does_not_read_first_actor_history(tmp_path):
    runtime, writes, client = _runtime(
        tmp_path,
        [
            {"mode": "CONTEXT", "context_scope": "RECENT"},
            {"intent": "CHAT"},
            {"outcome": "INSUFFICIENT_EVIDENCE", "answer": "No consta.", "supporting_ids": []},
        ],
    )
    first, other = _actor(), _actor()
    runtime.append_conversation_turn(
        "main", "private", "user", "El gato se llama Sol", authenticated_actor=first
    )
    outcome = runtime.execute_product("¿Qué dije?", "other-1", "main", other)
    assert outcome["conversation_reply"]["status"] == "needs_attention"
    import json

    for call in client.responses.calls:
        assert "El gato se llama Sol" not in json.dumps(call, ensure_ascii=False)
    assert writes == []


def test_disabled_gateway_is_exact_legacy_path(tmp_path):
    runtime, writes, client = _runtime(tmp_path, [])
    runtime.conversation_gateway = None
    result = runtime.execute_product("Hola", "legacy-1", "main", _actor())
    assert "conversation_reply" not in result
    assert writes == [("Hola", "legacy-1")]
    assert client.responses.calls == []


def test_pending_core_clarification_is_handled_before_any_chat_model(tmp_path):
    """A reply to an active Core question must never be treated as small talk."""
    from tests.runtime.test_clarification_continuation import _pending_runtime

    touched = []

    def core(_source, rid, *_args, **kwargs):
        touched.append((rid, kwargs))
        return ApplicationResult(rid, ApplicationStatus.COMPLETED, (), ())

    runtime, pending = _pending_runtime(tmp_path, core)
    model = FakeClient([])
    runtime.conversation_gateway = OpenAIConversationGateway(model)
    actor = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")
    result = runtime.execute_product("2", "c3-pending-choice", "main", actor)
    assert result["product_outcome"] == "ANSWER"
    assert pending.read() is None
    assert len(touched) == 1
    assert model.responses.calls == []


def test_same_id_cannot_be_rebound_to_other_source_after_chat(tmp_path):
    runtime, writes, client = _runtime(
        tmp_path,
        [
            {"mode": "CHAT", "context_scope": "NONE"},
            {"purpose": "GENERAL"},
            {"outcome": "ANSWER", "answer": "Hola", "supporting_ids": []},
        ],
    )
    actor = _actor()
    runtime.execute_product("Buenas", "same-id", "main", actor)
    with pytest.raises(DeliveryResultError):
        runtime.execute_product("Guardar algo diferente", "same-id", "main", actor)
    assert len(client.responses.calls) == 3 and writes == []
