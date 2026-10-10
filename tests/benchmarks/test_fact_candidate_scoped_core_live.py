"""Off-network reviewed single-fact GPT-5.6 gates and cumulative spending checks."""

from __future__ import annotations

import json

import pytest

from benchmarks.fact_candidate_core_live import run_scoped_live as scope
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import _raw_semantic_plan


def test_all_scoped_requests_are_reviewed_and_not_whole_source() -> None:
    for case_id, unit_id in scope.STAGES:
        unit, domain, request, spec = scope._reviewed(case_id, unit_id)
        assert unit.scoped_request() == request
        assert spec["input"][1]["content"] == request
        assert "Mañana" not in request
        assert "cine" not in request
        assert spec["model"] == "gpt-5.6-luna"
        assert spec["reasoning"] == {"effort": "low"}
        assert spec["store"] is False
        assert spec["max_output_tokens"] == 2048
        assert spec["text"]["format"]["strict"] is True
        assert len(domain.temporal_references()) == 1


def test_dry_run_first_unit_is_bounded_without_credentials(monkeypatch):
    monkeypatch.delenv(scope.RUN_ENV, raising=False)
    result = scope.run("F14", "candidate-1", live=False)
    assert result["mode"] == "OFFLINE_DRY_RUN"
    assert result["max_calls"] == 1
    assert result["may_authorize_writes"] is False
    assert 0.02 < result["reservation_usd"] < 0.04
    assert result["previous_estimated_usd"] + result["reservation_usd"] < 0.07


def test_second_stage_refuses_unobserved_previous_call(monkeypatch, tmp_path):
    monkeypatch.setattr(scope, "RESULTS", tmp_path)
    # Baseline receipt paths are absent in this isolated result dir:
    # the budget checker must stop BEFORE provider access.
    with pytest.raises((FileNotFoundError, ValueError)):
        scope.run("F27", "candidate-1", live=True, client=object())


def test_missing_approval_flag_blocks_even_fake_provider(monkeypatch):
    monkeypatch.delenv(scope.RUN_ENV, raising=False)
    fake, calls = _sdk_fake(_raw_semantic_plan())
    with pytest.raises(ValueError, match="explicit approval"):
        scope.run("F14", "candidate-1", live=True, client=fake)
    assert not calls


def test_reviewed_request_drift_prevents_provider_access(monkeypatch, tmp_path):
    copied = json.loads(scope.PIN.read_text(encoding="utf-8"))
    copied["sha256"]["F14/candidate-1"] = "0" * 64
    other = tmp_path / "pin.json"
    other.write_text(json.dumps(copied), encoding="utf-8")
    monkeypatch.setattr(scope, "PIN", other)
    with pytest.raises(ValueError, match="reviewed immutable"):
        scope.run("F14", "candidate-1", live=True, client=object())


def test_scoped_fake_plan_is_one_call_with_no_write_authority(monkeypatch):
    monkeypatch.setenv(scope.RUN_ENV, "1")
    fake, calls = _sdk_fake(_raw_semantic_plan())
    result = scope.run("F14", "candidate-1", live=True, client=fake)
    assert len(calls) == 1
    assert result["outcome"] == "PLAN"
    assert result["validation"] == "locally_valid"
    assert result["may_authorize_writes"] is False
