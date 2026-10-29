"""C4 model interprets observed E2 evidence rather than deterministic guesses."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.observability import OperationalEvidence, OperationalOutcome, OperationalStage
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.conversation_error import diagnose_trusted_execution_graph
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway, graph_diagnosis_schema
from odyssey_runtime.execution_ledger import project_execution_ledger
from odyssey_runtime.serialization import application_result_to_response
from tests.runtime.test_conversation_gateway import FakeClient

SOURCE = "Ayer mis hijos y mi pareja visitaron el jardín; después fuimos al museo."
REASON = "FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED"
AI_REPLY = {
    "evidence_stage": "candidate.source_boundary_review",
    "route_index": None,
    "explanation": "La revisión de cobertura del texto no pudo comprobar la separación de los recuerdos.",
    "next_step": "ASK_USER",
    "user_question": "¿Puedes confirmar si fueron dos visitas diferentes?",
}


def rejected(request_id="synthetic-c4-graph"):
    return ApplicationResult(
        request_id=request_id,
        status=ApplicationStatus.NEEDS_ATTENTION,
        action_results=(),
        affected_stable_note_ids=(),
        clarification_code=REASON,
        operational=OperationalEvidence(
            12,
            (
                OperationalStage("application.router", OperationalOutcome.COMPLETED, 3),
                OperationalStage(
                    "candidate.source_boundary_review",
                    OperationalOutcome.FAILED,
                    9,
                    error_category="COVERAGE_UNVERIFIED",
                ),
            ),
        ),
    )


def test_graph_ai_reuses_existing_c4_gateway_with_stages_and_original_message():
    typed = rejected()
    fake = FakeClient([AI_REPLY.copy()])
    diagnosis = diagnose_trusted_execution_graph(
        typed,
        application_result_to_response(typed),
        project_execution_ledger(typed),
        OpenAIConversationGateway(fake),
        original_message=SOURCE,
    )
    assert diagnosis is not None
    assert diagnosis["evidence_stage"] == "candidate.source_boundary_review"
    assert diagnosis["next_step"] == "ASK_USER"
    assert diagnosis["write_evidence"] == "UNKNOWN"
    assert "retry_authorized" not in diagnosis
    call = fake.responses.calls[0]
    assert call["text"]["format"]["strict"] is True
    assert call["text"]["format"]["schema"] == graph_diagnosis_schema()
    evidence = json.loads(call["input"][1]["content"])
    assert evidence["original_message"] == SOURCE
    assert [st["name"] for st in evidence["stages"]] == [
        "application.router",
        "candidate.source_boundary_review",
    ]
    assert evidence["stages"][1]["error_category"] == "COVERAGE_UNVERIFIED"
    assert evidence["write_evidence"] == "UNKNOWN"
    assert evidence["entry_route"] == "PRODUCT_ROUTER"
    assert evidence["prewrite_recovery_proven"] is False
    assert evidence["specific_provider_failures"] == []
    assert "request_id" not in call["input"][1]["content"]


@pytest.mark.parametrize(
    "alteration",
    [
        {"evidence_stage": "core.identity_resolution"},  # did not run
        {"explanation": "No he guardado nada. Puedes volver a pedirlo."},
        {"explanation": "No se modificó ningún archivo, puedes repetirlo."},
        {"explanation": "No hay notas nuevas. Repite la solicitud."},
        {"explanation": "No hubo cambios físicos en la bóveda."},
        {"evidence_stage": "application.router"},
        {"next_step": "AUTO_RETRY"},
        {"user_question": ""},
        {"free_write_command": "CREATE"},
    ],
)
def test_ai_must_not_invent_stages_safety_evidence_or_commands(alteration):
    typed = rejected()
    fake = FakeClient([{**AI_REPLY, **alteration}])
    result = diagnose_trusted_execution_graph(
        typed,
        application_result_to_response(typed),
        project_execution_ledger(typed),
        OpenAIConversationGateway(fake),
        original_message=SOURCE,
    )
    assert result is None


def test_graph_ai_runs_for_clarify_before_core_with_actor_replay_and_zero_new_writes(tmp_path):
    actor = AuthenticatedActorContext(str(uuid4()))
    fake = FakeClient([AI_REPLY.copy()])
    calls = []

    def hybrid(source, request_id, authenticated, conversation_id):
        calls.append((source, request_id, authenticated.stable_user_id, conversation_id))
        return rejected(request_id)

    runtime = RuntimeComposition(
        core_execute=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("Unexpected Core")),
        hybrid_candidate_execute=hybrid,
        full_source_mutation_guard=True,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "actor-owned"),
        conversation_error_guidance_enabled=True,
        conversation_graph_gateway=OpenAIConversationGateway(fake),
    )
    first = runtime.execute_product(SOURCE, "graph-c4-one", "main", actor)
    assert first["status"] == "needs_attention"
    assert first["product_outcome"] == "CLARIFY"
    assert "error_guidance" not in first  # old C4 skipped CLARIFY; AI now diagnoses it
    assert first["error_diagnosis"]["evidence_stage"] == AI_REPLY["evidence_stage"]
    assert first["affected_stable_note_ids"] == []
    assert first["actions"] == []
    again = runtime.execute_product(SOURCE, "graph-c4-one", "main", actor)
    assert again["delivery_replayed"] is True
    assert {key: value for key, value in again.items() if key != "delivery_replayed"} == first
    assert len(calls) == len(fake.responses.calls) == 1


def test_graph_ai_failure_preserves_existing_core_result_and_never_retries(tmp_path):
    actor = AuthenticatedActorContext(str(uuid4()))
    fake = FakeClient([RuntimeError("provider offline")])
    calls = []

    def hybrid(source, request_id, authenticated, conversation_id):
        calls.append(request_id)
        return rejected(request_id)

    runtime = RuntimeComposition(
        core_execute=lambda *_a, **_kw: None,
        hybrid_candidate_execute=hybrid,
        full_source_mutation_guard=True,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "isolated"),
        conversation_graph_gateway=OpenAIConversationGateway(fake),
    )
    first = runtime.execute_product(SOURCE, "model-down", "main", actor)
    assert first["product_outcome"] == "CLARIFY"
    assert "error_diagnosis" not in first
    assert runtime.execute_product(SOURCE, "model-down", "main", actor)["delivery_replayed"]
    assert calls == ["model-down"]
    assert len(fake.responses.calls) == 1


def test_real_source_prewrite_provider_failure_reports_failed_graph_stage_without_core_identity(
    tmp_path,
):
    """The actual P4 source path, not a hand-authored graph, must expose its failed AI stage."""
    from openai import OpenAIError

    from tests.runtime.test_whole_source_light_product_p4 import (
        RecordedClient,
        _actual_snapshot,
        _fixture,
    )

    source, router, _planner, _review = _actual_snapshot("maya_simple")
    repo, actor, executor, runtime = _fixture(tmp_path)

    class PlannerDown(RecordedClient):
        def create(self, **kwargs):
            if kwargs["text"]["format"]["name"] == "odyssey_light_shared_semantic_plan_v1":
                raise OpenAIError("synthetic provider interruption")
            return super().create(**kwargs)

    executor.client = PlannerDown([router])
    gateway = FakeClient(
        [
            {
                "evidence_stage": "provider.gpt-5.6-luna.odyssey_light_shared_semantic_plan_v1",
                "route_index": None,
                "explanation": "La llamada al planificador falló antes de la interpretación Core.",
                "next_step": "CHECK_SYSTEM",
                "user_question": "",
            }
        ]
    )
    runtime.conversation_graph_gateway = OpenAIConversationGateway(gateway)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    actual = runtime.execute_product(source, "real-router-prewrite", "main", actor)
    assert actual["status"] == "needs_attention"
    assert actual["clarification_code"] == "FULL_SOURCE_PROVIDER_OR_CONTEXT_UNAVAILABLE"
    assert actual["error_diagnosis"]["evidence_stage"].startswith("provider.")
    assert actual["error_diagnosis"]["next_step"] == "CHECK_SYSTEM"
    sent = json.loads(gateway.responses.calls[0]["input"][1]["content"])
    assert sent["entry_route"] == "PRODUCT_ROUTER"
    assert sent["prewrite_recovery_proven"] is True
    assert len(sent["specific_provider_failures"]) == 1
    provider = sent["specific_provider_failures"][0]
    assert provider["name"].startswith("provider.")
    assert any(
        stage["name"] == provider["name"] and stage["outcome"] == "failed"
        for stage in sent["stages"]
    )
    stages = actual["execution_ledger"]["stages"]
    assert stages[0]["name"] == "application.source_processing"
    assert stages[0]["outcome"] == "failed"
    assert stages[0]["error_category"] == "FULL_SOURCE_PROVIDER_OR_CONTEXT_UNAVAILABLE"
    assert any(s["name"].startswith("provider.") and s["outcome"] == "failed" for s in stages)
    assert all("core.identity" not in s["name"] for s in stages)
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
    assert runtime.execute_product(source, "real-router-prewrite", "main", actor)[
        "delivery_replayed"
    ]
    assert len(gateway.responses.calls) == 1


def test_c4_graph_gateway_is_independent_from_chat_and_gracefully_handles_missing_provider(
    monkeypatch,
):
    from odyssey_runtime.composition import _c4_graph_gateway_from_environment
    from odyssey_runtime.conversation_gateway import ConversationGateError

    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_CHAT_C4_ENABLED", "1")
    monkeypatch.delenv("ODYSSEY_CHAT_C4_GRAPH_ENABLED", raising=False)
    assert _c4_graph_gateway_from_environment() is None
    monkeypatch.setenv("ODYSSEY_CHAT_C4_GRAPH_ENABLED", "1")
    monkeypatch.delenv("ODYSSEY_CHAT_C3_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert _c4_graph_gateway_from_environment() is None

    gateway = OpenAIConversationGateway(FakeClient([]))
    monkeypatch.setattr(
        OpenAIConversationGateway, "from_environment", classmethod(lambda cls, **kwargs: gateway)
    )
    assert _c4_graph_gateway_from_environment() is gateway
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")
    assert _c4_graph_gateway_from_environment() is None
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_CHAT_C4_GRAPH_ENABLED", "0")
    assert _c4_graph_gateway_from_environment() is None
    monkeypatch.setenv("ODYSSEY_CHAT_C4_GRAPH_ENABLED", "1")
    monkeypatch.setenv("ODYSSEY_CHAT_C4_ENABLED", "0")
    assert _c4_graph_gateway_from_environment() is None
    monkeypatch.setenv("ODYSSEY_CHAT_C4_ENABLED", "1")
    monkeypatch.setattr(
        OpenAIConversationGateway,
        "from_environment",
        classmethod(lambda cls, **kwargs: (_ for _ in ()).throw(ConversationGateError("offline"))),
    )
    assert _c4_graph_gateway_from_environment() is None


def test_graph_ai_rejects_mismatched_route_owner_and_marks_source_truncation():
    typed = rejected()
    source = SOURCE + " y otro hecho posiblemente omitido" * 100
    route_ledger = project_execution_ledger(typed)
    route_ledger["routes"] = [
        {"route_index": 0, "capability": "core", "status": "completed", "depends_on": None},
        {"route_index": 1, "capability": "tasks", "status": "failed", "depends_on": None},
    ]
    route_ledger["stages"] = [
        {**route_ledger["stages"][1], "route_index": 0, "outcome": "completed"},
        {**route_ledger["stages"][1], "route_index": 1, "outcome": "failed"},
    ]
    bad = FakeClient([{**AI_REPLY, "route_index": 0}])
    denied = diagnose_trusted_execution_graph(
        typed,
        application_result_to_response(typed),
        route_ledger,
        OpenAIConversationGateway(bad),
        original_message=source,
    )
    assert denied is None
    good = FakeClient([{**AI_REPLY, "route_index": 1}])
    accepted = diagnose_trusted_execution_graph(
        typed,
        application_result_to_response(typed),
        route_ledger,
        OpenAIConversationGateway(good),
        original_message=source,
    )
    assert accepted is not None and accepted["route_index"] == 1
    observed = json.loads(good.responses.calls[0]["input"][1]["content"])
    assert observed["source_truncated"] is True
    assert observed["original_message"] == source[:2048]
    assert [stage["route_index"] for stage in observed["stages"]] == [0, 1]
    assert observed["routes"][1]["capability"] == "tasks"


def test_parent_source_failure_rejected_only_if_a_real_failed_child_exists():
    typed = rejected()
    ledger = project_execution_ledger(typed)
    parent = {
        "name": "application.source_processing",
        "outcome": "failed",
        "route_index": None,
        "parent_stage": None,
        "error_category": "FULL_SOURCE_PROVIDER_OR_CONTEXT_UNAVAILABLE",
    }
    child = {
        "name": "provider.plan",
        "outcome": "failed",
        "route_index": None,
        "parent_stage": parent["name"],
        "error_category": "OpenAIError",
    }
    ledger["stages"] = [parent, child]
    parent_reply = {**AI_REPLY, "evidence_stage": parent["name"]}
    assert (
        diagnose_trusted_execution_graph(
            typed,
            application_result_to_response(typed),
            ledger,
            OpenAIConversationGateway(FakeClient([parent_reply])),
            original_message=SOURCE,
        )
        is None
    )
    child_reply = {**AI_REPLY, "evidence_stage": child["name"]}
    actual = diagnose_trusted_execution_graph(
        typed,
        application_result_to_response(typed),
        ledger,
        OpenAIConversationGateway(FakeClient([child_reply])),
        original_message=SOURCE,
    )
    assert actual is not None and actual["evidence_stage"] == child["name"]
    ledger["stages"][1]["outcome"] = "completed"
    assert (
        diagnose_trusted_execution_graph(
            typed,
            application_result_to_response(typed),
            ledger,
            OpenAIConversationGateway(FakeClient([parent_reply])),
            original_message=SOURCE,
        )
        is not None
    )


def test_provider_child_after_thirty_two_stages_cannot_be_lost_or_ignored():
    typed = rejected()
    parent = {
        "name": "application.source_processing",
        "outcome": "failed",
        "route_index": None,
        "parent_stage": None,
        "error_category": "SOURCE_FAILURE",
    }
    child = {
        "name": "provider.review",
        "outcome": "failed",
        "route_index": None,
        "parent_stage": parent["name"],
        "error_category": "PROVIDER_FAILURE",
    }
    completed = [
        {
            "name": f"context.stage_{i}",
            "outcome": "completed",
            "route_index": None,
            "parent_stage": None,
        }
        for i in range(31)
    ]
    ledger = project_execution_ledger(typed)
    ledger["stages"] = [parent, *completed, child]
    parent_reply = {**AI_REPLY, "evidence_stage": parent["name"]}
    model_bad = FakeClient([parent_reply])
    assert (
        diagnose_trusted_execution_graph(
            typed,
            application_result_to_response(typed),
            ledger,
            OpenAIConversationGateway(model_bad),
            original_message=SOURCE,
        )
        is None
    )
    sent = json.loads(model_bad.responses.calls[0]["input"][1]["content"])
    assert len(sent["stages"]) == 32
    assert parent["name"] in {st["name"] for st in sent["stages"]}
    assert child["name"] in {st["name"] for st in sent["stages"]}
    assert sent["specific_provider_failures"] == [{"name": child["name"], "route_index": None}]
    model_good = FakeClient([{**AI_REPLY, "evidence_stage": child["name"]}])
    accepted = diagnose_trusted_execution_graph(
        typed,
        application_result_to_response(typed),
        ledger,
        OpenAIConversationGateway(model_good),
        original_message=SOURCE,
    )
    assert accepted is not None and accepted["evidence_stage"] == child["name"]
    overflow = {
        **ledger,
        "stages": [
            {
                "name": f"provider.failed_{i}",
                "outcome": "failed",
                "route_index": None,
                "parent_stage": None,
            }
            for i in range(33)
        ],
    }
    no_call = FakeClient([])
    assert (
        diagnose_trusted_execution_graph(
            typed,
            application_result_to_response(typed),
            overflow,
            OpenAIConversationGateway(no_call),
            original_message=SOURCE,
        )
        is None
    )
    assert not no_call.responses.calls
