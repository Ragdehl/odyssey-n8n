"""Opt-in C4 second AI semantic reviewer for WRITE uncertainty, without text rules."""

from __future__ import annotations

import json

import pytest

from odyssey_runtime.composition import _chat_c4_semantic_review_enabled
from odyssey_runtime.conversation_error import diagnose_trusted_execution_graph
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from odyssey_runtime.execution_ledger import project_execution_ledger
from odyssey_runtime.serialization import application_result_to_response
from tests.runtime.test_c4_graph_diagnosis import AI_REPLY, SOURCE, rejected
from tests.runtime.test_conversation_gateway import FakeClient


def _diagnose(responses, *, reviewed=True, proposal=None):
    typed = rejected()
    fake = FakeClient([proposal or AI_REPLY, *responses])
    result = diagnose_trusted_execution_graph(
        typed,
        application_result_to_response(typed),
        project_execution_ledger(typed),
        OpenAIConversationGateway(fake),
        original_message=SOURCE,
        semantic_review=reviewed,
    )
    return result, fake.responses.calls


def test_semantic_reviewer_cannot_override_legacy_write_text_boundary():
    proposal = {
        **AI_REPLY,
        "explanation": "La etapa de escritura falló y no se confirmó el resultado físico de la operación.",
        "next_step": "INSPECT_RESULT",
        "user_question": "",
    }
    legacy, before = _diagnose([], reviewed=False, proposal=proposal)
    assert legacy is None and len(before) == 1  # historical false rejection
    vetted, calls = _diagnose([{"verdict": "SUPPORTED", "reason": "GROUNDED"}], proposal=proposal)
    assert vetted is not None
    assert vetted["verified_stage_only"] is True
    assert "explanation" not in vetted and "user_question" not in vetted
    assert len(calls) == 2
    assert calls[1]["text"]["format"]["strict"] is True
    assert calls[1]["text"]["format"]["name"] == "odyssey_execution_diagnosis_semantic_review"
    assert calls[1]["store"] is False
    content = json.loads(calls[1]["input"][1]["content"])
    assert content["proposed"] == proposal
    assert content["observed"]["write_evidence"] == "UNKNOWN"
    assert "request_id" not in calls[1]["input"][1]["content"]


@pytest.mark.parametrize(
    "review_response",
    [
        {"verdict": "UNSUPPORTED", "reason": "WRITE_CLAIM_UNVERIFIED"},
        {"verdict": "SUPPORTED", "reason": "WRITE_CLAIM_UNVERIFIED"},
        {"verdict": "UNSUPPORTED", "reason": "GROUNDED"},
        {"verdict": "SURE", "reason": "GROUNDED"},
        {"verdict": "SUPPORTED", "reason": "GROUNDED", "retry_authorized": True},
        RuntimeError("verifier transport error"),
    ],
)
def test_review_failure_never_releases_model_text(review_response):
    proposal = {**AI_REPLY, "explanation": "He guardado el archivo sin cambios, puedes repetir."}
    reviewed, calls = _diagnose([review_response], proposal=proposal)
    assert reviewed is None
    assert len(calls) == 2


def test_false_positive_second_review_never_releases_unverified_physical_claim():
    proposed = {
        **AI_REPLY,
        "explanation": "He creado tus notas y la información ya está guardada.",
        "next_step": "INSPECT_RESULT",
        "user_question": "",
    }
    value, calls = _diagnose([{"verdict": "SUPPORTED", "reason": "GROUNDED"}], proposal=proposed)
    assert value is not None
    assert value["verified_stage_only"] is True
    assert set(value) == {
        "status",
        "reason_code",
        "write_evidence",
        "evidence_stage",
        "route_index",
        "next_step",
        "verified_stage_only",
    }
    assert len(calls) == 2


def test_stage_mismatch_rejected_before_second_model_call():
    proposed = {**AI_REPLY, "evidence_stage": "core.identity_resolution"}
    result, calls = _diagnose([{"verdict": "SUPPORTED", "reason": "GROUNDED"}], proposal=proposed)
    assert result is None and len(calls) == 1


def test_semantic_verification_requires_separate_dev_flag(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_CHAT_C4_ENABLED", "1")
    monkeypatch.setenv("ODYSSEY_CHAT_C4_GRAPH_ENABLED", "1")
    monkeypatch.delenv("ODYSSEY_CHAT_C4_SEMANTIC_REVIEW_ENABLED", raising=False)
    assert not _chat_c4_semantic_review_enabled()
    monkeypatch.setenv("ODYSSEY_CHAT_C4_SEMANTIC_REVIEW_ENABLED", "1")
    assert _chat_c4_semantic_review_enabled()
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "PROD")
    assert not _chat_c4_semantic_review_enabled()
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_CHAT_C4_GRAPH_ENABLED", "0")
    assert not _chat_c4_semantic_review_enabled()


def test_verified_second_ai_pass_controls_real_prewrite_retry_and_e3_replay(tmp_path):
    from odyssey_core.notes import parse_note
    from tests.runtime.test_c4_safe_prewrite_recovery import RETRY_ADVICE, _bad_route
    from tests.runtime.test_issue157_family_day_recollection import DAY, _family, _model_responses
    from tests.runtime.test_issue157_family_day_recollection import SOURCE as FAMILY_SOURCE
    from tests.runtime.test_whole_source_light_product_p4 import RecordedClient

    repo, actor, source_executor, runtime = _family(tmp_path)
    source_executor.client = RecordedClient([_bad_route(), *_model_responses()])
    primary_and_review = FakeClient([RETRY_ADVICE, {"verdict": "SUPPORTED", "reason": "GROUNDED"}])
    runtime.conversation_graph_gateway = OpenAIConversationGateway(primary_and_review)
    runtime.conversation_graph_semantic_review_enabled = True
    runtime.conversation_prewrite_recovery_enabled = True
    result = runtime.execute_product(FAMILY_SOURCE, "semantic-reviewed-recovery", "main", actor)
    assert result["status"] == "completed"
    assert [call["text"]["format"]["name"] for call in primary_and_review.responses.calls] == [
        "odyssey_execution_graph_diagnosis",
        "odyssey_execution_diagnosis_semantic_review",
    ]
    note = parse_note(repo.read_text(f"calendar/days/{DAY}.md"))
    assert note.content.count("odyssey:fact request=semantic-reviewed-recovery-") == 2
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    replay = runtime.execute_product(FAMILY_SOURCE, "semantic-reviewed-recovery", "main", actor)
    assert replay["delivery_replayed"] is True
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    assert len(primary_and_review.responses.calls) == 2


def test_rejected_second_ai_pass_blocks_retry_and_preserves_original_failure(tmp_path):
    from tests.runtime.test_c4_safe_prewrite_recovery import RETRY_ADVICE, _bad_route
    from tests.runtime.test_issue157_family_day_recollection import SOURCE as FAMILY_SOURCE
    from tests.runtime.test_issue157_family_day_recollection import _family
    from tests.runtime.test_whole_source_light_product_p4 import RecordedClient

    repo, actor, source_executor, runtime = _family(tmp_path)
    source_executor.client = RecordedClient([_bad_route()])
    primary_and_review = FakeClient(
        [RETRY_ADVICE, {"verdict": "UNSUPPORTED", "reason": "MISLEADING_ACTION"}]
    )
    runtime.conversation_graph_gateway = OpenAIConversationGateway(primary_and_review)
    runtime.conversation_graph_semantic_review_enabled = True
    runtime.conversation_prewrite_recovery_enabled = True
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(FAMILY_SOURCE, "semantic-denied-recovery", "main", actor)
    assert result["status"] == "needs_attention"
    assert "error_diagnosis" not in result
    assert len(primary_and_review.responses.calls) == 2
    assert len(source_executor.client.calls) == 1
    replay = runtime.execute_product(FAMILY_SOURCE, "semantic-denied-recovery", "main", actor)
    assert replay["delivery_replayed"] is True
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}
