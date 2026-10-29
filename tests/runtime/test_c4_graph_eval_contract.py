"""No paid calls: C4 model evaluation runs the real gateway contract and stage validator."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from odyssey_runtime.conversation_gateway import (
    GRAPH_DIAGNOSIS_INSTRUCTIONS,
    OpenAIConversationGateway,
)
from scripts.evaluate_c4_graph import CASES, dry_run, evaluate_live, evidence_for
from tests.runtime.test_conversation_gateway import FakeClient


def test_eval_matrix_is_comprehensive_bounded_real_e2_schema():
    report = dry_run()
    assert report["model_calls"] == 0
    assert len(CASES) == report["case_count"] == 14
    assert len({case.name for case in CASES}) == len(CASES)
    assert any(case.write_ids for case in CASES)
    assert any(case.routes for case in CASES)
    assert any(len(case.source) > 2048 for case in CASES)
    for index, case in enumerate(CASES):
        typed, product, ledger = evidence_for(case, f"c4-check-{index}")
        assert product["product_outcome"] in {"CLARIFY", "CANNOT_ANSWER"}
        assert typed.request_id == ledger["request_id"]
        assert [s["name"] for s in ledger["stages"]] == [s[0] for s in case.stages]
        assert (case.expected_stage, case.expected_route) in {
            (stage["name"], stage["route_index"])
            for stage in ledger["stages"]
            if stage["outcome"] == "failed"
        }


def test_live_eval_requires_explicit_full_budget_even_with_sdk_mocked(monkeypatch):
    monkeypatch.delenv("ODYSSEY_C4_LIVE_EVAL_AUTHORIZED", raising=False)
    gateway_calls = []
    monkeypatch.setattr(
        OpenAIConversationGateway,
        "from_environment",
        classmethod(lambda cls, **kw: gateway_calls.append(kw)),
    )
    for max_calls in (0, 1, 13, 14, 20):
        with pytest.raises(ValueError, match="exact 14-call budget"):
            evaluate_live(max_calls=max_calls)
    monkeypatch.setenv("ODYSSEY_C4_LIVE_EVAL_AUTHORIZED", "1")
    for max_calls in (0, 1, 13, 15, 20):
        with pytest.raises(ValueError, match="exact 14-call budget"):
            evaluate_live(max_calls=max_calls)
    assert gateway_calls == []  # No provider constructed or called.


def test_authorized_eval_with_recorded_provider_only_uses_real_schema(monkeypatch):
    replies = [
        {
            "evidence_stage": case.expected_stage,
            "route_index": case.expected_route,
            "explanation": "La etapa observada falló durante la interpretación y requiere revisión.",
            "next_step": case.accepted_steps[0],
            "user_question": "¿Puedes aclarar el dato pendiente?"
            if case.accepted_steps[0] == "ASK_USER"
            else "",
        }
        for case in CASES
    ]
    recorded = FakeClient(replies)
    monkeypatch.setenv("ODYSSEY_C4_LIVE_EVAL_AUTHORIZED", "1")
    monkeypatch.setattr(
        OpenAIConversationGateway,
        "from_environment",
        classmethod(lambda cls, **kw: OpenAIConversationGateway(recorded)),
    )
    result = evaluate_live(max_calls=14)
    assert result["executed_calls"] == 14
    assert result["stage_correct"] == 14
    assert result["step_acceptable"] == 14
    assert len(recorded.responses.calls) == 14
    assert result["usage_missing"] == 14
    assert result["reported_input_tokens"] == 0
    assert result["semantic_acceptance"] == "PENDING_INDEPENDENT_REVIEW"
    assert all(row["human_semantic_review_pending"] for row in result["cases"])
    assert all(call["text"]["format"]["strict"] for call in recorded.responses.calls)
    assert all(call["store"] is False for call in recorded.responses.calls)
    assert all(call["max_output_tokens"] == 880 for call in recorded.responses.calls)


def test_cli_defaults_to_zero_cost_and_refuses_live_without_approval(tmp_path, monkeypatch):
    monkeypatch.delenv("ODYSSEY_C4_LIVE_EVAL_AUTHORIZED", raising=False)
    cmd = [sys.executable, "-m", "scripts.evaluate_c4_graph"]
    safe = subprocess.run(cmd, capture_output=True, text=True, check=True)
    report = json.loads(safe.stdout)
    assert report["model_calls"] == 0
    refused = subprocess.run(
        cmd + ["--mode", "live", "--max-calls", "14"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode == 2
    assert "C4_EVAL_REJECTED" in refused.stderr
    assert "model_calls" not in refused.stdout


def test_graph_diagnosis_perf_probe_runs_actual_c4_with_delayed_fake():
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.odyssey_chat_c4_perf_gate", "--graph-diagnosis"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    result = json.loads(completed.stdout)
    assert result["pass"] is True
    assert result["graph_diagnosis_enabled"] is True
    assert result["C4_advisory_calls"] == result["calls"] == 7
    assert result["notes_written"] == 0
    assert result["real_provider"] is False
    assert result["replay_core_extra_calls"] == 0


def test_live_evaluation_resumes_after_three_calls_and_never_repeats_cases(tmp_path, monkeypatch):
    replies = [
        {
            "evidence_stage": case.expected_stage,
            "route_index": case.expected_route,
            "explanation": "La etapa observada falló durante la interpretación y requiere revisión.",
            "next_step": case.accepted_steps[0],
            "user_question": "¿Puedes aclarar el dato pendiente?"
            if case.accepted_steps[0] == "ASK_USER"
            else "",
        }
        for case in CASES
    ]
    monkeypatch.setenv("ODYSSEY_C4_LIVE_EVAL_AUTHORIZED", "1")
    first_provider = FakeClient(replies)
    monkeypatch.setattr(
        OpenAIConversationGateway,
        "from_environment",
        classmethod(lambda cls, **kw: OpenAIConversationGateway(first_provider)),
    )
    complete = evaluate_live(max_calls=14)
    prior = {
        **complete,
        "executed_calls": 3,
        "cases": complete["cases"][:3],
        "reported_input_tokens": 0,
        "reported_output_tokens": 0,
        "usage_missing": 3,
    }
    prior_path = tmp_path / "prior.json"
    prior_path.write_text(json.dumps(prior), encoding="utf-8")
    last_provider = FakeClient(replies[3:])
    monkeypatch.setattr(
        OpenAIConversationGateway,
        "from_environment",
        classmethod(lambda cls, **kw: OpenAIConversationGateway(last_provider)),
    )
    checkpoint = tmp_path / "resume.json"
    report = evaluate_live(
        max_calls=14,
        resume_report=prior_path,
        continue_after_rejection=True,
        checkpoint_path=checkpoint,
    )
    assert report["executed_calls"] == 14
    assert report["remaining_call_budget"] == 0
    assert [r["case"] for r in report["cases"]] == [case.name for case in CASES]
    assert len(last_provider.responses.calls) == 11
    assert json.loads(checkpoint.read_text())["executed_calls"] == 14
    tampered = {**prior, "prompt_sha256": "altered"}
    prior_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="Resume report does not match"):
        evaluate_live(max_calls=14, resume_report=prior_path, continue_after_rejection=True)
    assert len(last_provider.responses.calls) == 11


def test_c4_prompt_preserves_graph_provenance_and_journal_intent_without_names():
    prompt = GRAPH_DIAGNOSIS_INSTRUCTIONS
    for concept in (
        "entry_intent",
        "Day journal",
        "prewrite_recovery_proven",
        "specific_provider_failures",
        "interpretation stage",
        "identity resolution",
    ):
        assert concept in prompt
    assert "Manu" not in prompt
    assert "Manon" not in prompt
