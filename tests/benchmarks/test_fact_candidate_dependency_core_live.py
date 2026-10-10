"""Frozen F23/F26 GPT-5.6 Core experiment, no authority to write notes."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_core_live import run_dependency_core as gate


@pytest.mark.parametrize("case_id,unit_id", gate.STAGES)
def test_frozen_real_core_planner_inputs_are_per_unit(case_id, unit_id):
    task, request, domain, spec = gate.reviewed(case_id, unit_id)
    assert task.candidate_id == unit_id
    assert task.selected_quote in request
    assert spec["input"][1]["content"] == request
    assert spec["model"] == "gpt-5.6-luna"
    assert spec["reasoning"] == {"effort": "low"}
    assert spec["store"] is False
    assert spec["max_output_tokens"] == 2048
    assert spec["text"]["format"]["strict"] is True
    assert not task.may_authorize_writes
    if unit_id == "candidate-2":
        assert task.prior_context_quote in request
        assert "exclusivamente" in request
    else:
        assert "exclusivamente" not in request
    assert (domain is not None) == (case_id == "F26")


def test_first_live_call_needs_explicit_flag_before_sdk(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RESULTS", tmp_path)
    monkeypatch.delenv(gate.FLAG, raising=False)
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: 123))
    assert gate.run("F23", "candidate-1")["mode"] == "OFFLINE_DRY_RUN"
    with pytest.raises(ValueError, match="flag"):
        gate.run("F23", "candidate-1", live=True, client=fake)


def test_out_of_order_and_duplicate_model_stage_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="next approved"):
        gate.run("F26", "candidate-1")
    (tmp_path / "F23--candidate-1.json").write_text(
        json.dumps(
            {
                "case": "F23",
                "unit": "candidate-1",
                "mode": "LIVE_DEPENDENCY_CORE_PLAN_ONLY",
                "provider_status": "completed",
                "usage": {"input_tokens": 9500, "output_tokens": 300},
                "outcome": "PLAN",
                "validation": "locally_valid",
            }
        )
    )
    with pytest.raises(ValueError, match="Already tested"):
        gate.run("F23", "candidate-1")
    next_stage = gate.run("F23", "candidate-2")
    assert next_stage["previous_estimated_usd"] > gate.PRIOR_SPEND_USD


def test_refusal_receipt_prevents_any_subsequent_core_call(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RESULTS", tmp_path)
    (tmp_path / "F23--candidate-1.json").write_text(
        json.dumps(
            {
                "case": "F23",
                "unit": "candidate-1",
                "mode": "LIVE_DEPENDENCY_CORE_PLAN_ONLY",
                "provider_status": "completed",
                "usage": {"input_tokens": 9500, "output_tokens": 300},
                "outcome": "ESCALATE",
                "validation": "locally_valid",
            }
        )
    )
    with pytest.raises(ValueError, match="incomplete provider receipt"):
        gate.run("F23", "candidate-2")


def test_request_hash_cannot_be_modified_to_authorize_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RESULTS", tmp_path / "receipts")
    freeze = json.loads(gate.PIN.read_text())
    freeze["sha256"]["F23/candidate-1"] = "0" * 64
    altered = tmp_path / "reviewed.json"
    altered.write_text(json.dumps(freeze))
    monkeypatch.setattr(gate, "PIN", altered)
    with pytest.raises(ValueError, match="not reviewed"):
        gate.preflight("F23", "candidate-1")


def test_cumulative_budget_never_allows_a_full_unreserved_call(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RESULTS", tmp_path / "receipts")
    monkeypatch.setattr(gate, "PRIOR_SPEND_USD", 0.065)
    with pytest.raises(ValueError, match="authorized cumulative ceiling"):
        gate.preflight("F23", "candidate-1")
