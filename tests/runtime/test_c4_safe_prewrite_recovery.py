"""AI may ask Router to REINTERPRET once, only with positive prewrite proof.

All canonical writes, actor isolation and physical replay use the real E3
application; source/diagnostic provider responses are bounded recordings.
"""

from __future__ import annotations

import json

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.notes import parse_note
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from tests.runtime.test_conversation_gateway import FakeClient
from tests.runtime.test_issue157_family_day_recollection import (
    DAY,
    PEOPLE,
    SOURCE,
    _family,
    _model_responses,
)
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient

RETRY_ADVICE = {
    "evidence_stage": "application.source_processing",
    "route_index": None,
    "explanation": "El enrutamiento original no pudo justificar una ruta completa para todos los hechos.",
    "next_step": "REVIEW_SAFE_RETRY",
    "user_question": "",
}


def _bad_route():
    return {
        "capabilities": ["events", "core", "temporal"],
        "self_relation_span": None,
        "self_relation_spans": ["mis hijos", "mi pareja"],
        "interpretation": "joint",
        "reason": "shared_subject",
        "app_scopes": [],
    }


def test_one_c4_advised_retry_reuses_original_id_and_real_core_day_writer(tmp_path):
    repo, actor, source_executor, runtime = _family(tmp_path)
    from odyssey_runtime.execution_checkpoints import LocalExecutionCheckpointStore

    runtime.execution_checkpoint_store_factory = LocalExecutionCheckpointStore
    responses = [_bad_route(), *_model_responses()]
    source_executor.client = RecordedClient(responses)
    model = FakeClient([RETRY_ADVICE])
    runtime.conversation_graph_gateway = OpenAIConversationGateway(model)
    runtime.conversation_prewrite_recovery_enabled = True

    first = runtime.execute_product(SOURCE, "recover-prewrite-day", "main", actor)
    assert first["status"] == "completed", first
    assert source_executor.client.calls.count("odyssey_light_capability_route_events_v1") == 2
    assert len(model.responses.calls) == 1
    evidence = json.loads(model.responses.calls[0]["input"][1]["content"])
    assert evidence["prewrite_recovery_proven"] is True
    assert evidence["entry_intent"] == "ROUTED_PERSONAL_INFORMATION_OR_OPERATION"
    assert "error_diagnosis" not in first  # final status success, not a prior failure
    graph_events = first["execution_ledger"]["events"]
    assert sum(e["stage"] == "diagnostic.prewrite_reinterpretation" for e in graph_events) == 1
    day = parse_note(repo.read_text(f"calendar/days/{DAY}.md"))
    assert day.content.count("odyssey:fact request=recover-prewrite-day-") == 2
    assert all(f"[[{name}" in day.content for name in PEOPLE)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    replay = runtime.execute_product(SOURCE, "recover-prewrite-day", "main", actor)
    assert replay["delivery_replayed"] is True
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    assert len(model.responses.calls) == 1
    assert len(source_executor.client.calls) == 6


def test_prewrite_proof_is_not_inferred_from_empty_result_after_event_delegate(tmp_path):
    repo, actor, source_executor, runtime = _family(tmp_path)
    route = {
        "capabilities": ["events", "temporal"],
        "interpretation": "joint",
        "reason": "single",
        "app_scopes": [],
        "self_relation_span": None,
        "self_relation_spans": [],
    }
    service_calls = []

    def event_delegate(source, delivery, identity):
        service_calls.append((source, delivery, identity.stable_user_id))
        # A domain delegate may have attempted a write and returned no
        # affected IDs; that absence must NEVER authorize reinterpretation.
        return ApplicationResult(
            delivery,
            ApplicationStatus.NEEDS_ATTENTION,
            (),
            (),
            clarification_code="FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED",
            prewrite_recovery_proven=True,  # forged by a delegated callback
        )

    source_executor.event_delegate = event_delegate
    source_executor.client = RecordedClient([route])
    model = FakeClient([RETRY_ADVICE])
    runtime.conversation_graph_gateway = OpenAIConversationGateway(model)
    runtime.conversation_prewrite_recovery_enabled = True
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    first = runtime.execute_product("Mañana tengo una cita.", "not-safe-after-event", "main", actor)
    assert first["status"] == "needs_attention"
    assert len(service_calls) == 1
    assert source_executor.client.calls == ["odyssey_light_capability_route_events_v1"]
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    assert runtime.execute_product("Mañana tengo una cita.", "not-safe-after-event", "main", actor)[
        "delivery_replayed"
    ]
    assert len(service_calls) == 1


@pytest.mark.parametrize(
    "ai_output",
    [
        {**RETRY_ADVICE, "next_step": "ASK_USER", "user_question": "¿Puedes aclararlo?"},
        {**RETRY_ADVICE, "evidence_stage": "core.identity_resolution"},
        {**RETRY_ADVICE, "explanation": "No hay notas nuevas, repite el pedido."},
    ],
)
def test_invalid_or_no_retry_advice_preserves_original_refusal(tmp_path, ai_output):
    repo, actor, source_executor, runtime = _family(tmp_path)
    source_executor.client = RecordedClient([_bad_route()])
    model = FakeClient([ai_output])
    runtime.conversation_graph_gateway = OpenAIConversationGateway(model)
    runtime.conversation_prewrite_recovery_enabled = True
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(SOURCE, "no-retry-prewrite", "main", actor)
    assert result["status"] == "needs_attention"
    assert len(source_executor.client.calls) == 1
    assert len(model.responses.calls) == 1  # diagnosis memoized, no duplicate C4
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_recovery_disabled_never_calls_extra_router_or_graph_model(tmp_path):
    repo, actor, source_executor, runtime = _family(tmp_path)
    source_executor.client = RecordedClient([_bad_route()])
    model = FakeClient([RETRY_ADVICE])
    runtime.conversation_graph_gateway = OpenAIConversationGateway(model)
    runtime.conversation_prewrite_recovery_enabled = False
    result = runtime.execute_product(SOURCE, "disabled-recovery", "main", actor)
    assert result["status"] == "needs_attention"
    assert len(source_executor.client.calls) == 1
    assert len(model.responses.calls) == 1  # C4 description only


def test_c4_provider_crash_during_optional_retry_preserves_original_durable_refusal(tmp_path):
    repo, actor, source_executor, runtime = _family(tmp_path)
    source_executor.client = RecordedClient([_bad_route()])
    # A provider-specific runtime exception must not strand the delivery claim.
    model = FakeClient([RuntimeError("simulated provider crash")])
    runtime.conversation_graph_gateway = OpenAIConversationGateway(model)
    runtime.conversation_prewrite_recovery_enabled = True
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    response = runtime.execute_product(SOURCE, "c4-provider-crash-prewrite", "main", actor)
    assert response["status"] == "needs_attention"
    assert len(model.responses.calls) == 1
    assert len(source_executor.client.calls) == 1
    replay = runtime.execute_product(SOURCE, "c4-provider-crash-prewrite", "main", actor)
    assert replay["delivery_replayed"] is True
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    assert len(model.responses.calls) == 1


def test_repeated_router_refusal_has_hard_cap_one_reinterpretation(tmp_path):
    repo, actor, source_executor, runtime = _family(tmp_path)
    source_executor.client = RecordedClient([_bad_route(), _bad_route()])
    model = FakeClient([RETRY_ADVICE, RETRY_ADVICE])
    runtime.conversation_graph_gateway = OpenAIConversationGateway(model)
    runtime.conversation_prewrite_recovery_enabled = True
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(SOURCE, "bounded-repeat-source", "main", actor)
    assert result["status"] == "needs_attention"
    assert len(source_executor.client.calls) == 2
    assert len(model.responses.calls) == 2  # first retry decision, then last-failure explanation
    replay = runtime.execute_product(SOURCE, "bounded-repeat-source", "main", actor)
    assert replay["delivery_replayed"] is True
    assert len(source_executor.client.calls) == 2
    assert len(model.responses.calls) == 2
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_env_guard_wont_auto_activate_recovery_when_c4_is_enabled(monkeypatch):
    from odyssey_runtime.composition import _chat_c4_prewrite_recovery_enabled

    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_CHAT_C4_ENABLED", "1")
    monkeypatch.setenv("ODYSSEY_CHAT_C4_GRAPH_ENABLED", "1")
    monkeypatch.delenv("ODYSSEY_CHAT_C4_RECOVERY_ENABLED", raising=False)
    assert not _chat_c4_prewrite_recovery_enabled()
    monkeypatch.setenv("ODYSSEY_CHAT_C4_RECOVERY_ENABLED", "1")
    assert _chat_c4_prewrite_recovery_enabled()
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")
    assert not _chat_c4_prewrite_recovery_enabled()
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_CHAT_C4_GRAPH_ENABLED", "0")
    assert not _chat_c4_prewrite_recovery_enabled()
