"""Provider-free price/pin, source-scoped request and fail-close reviews."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_core_live import run_dependent_live as gate


def test_immutable_actual_core_contract_is_separately_scoped():
    assert gate.STAGES == (
        ("F23", "candidate-1"),
        ("F23", "candidate-2"),
        ("F26", "candidate-1"),
        ("F26", "candidate-2"),
    )
    for case, uid in gate.STAGES:
        unit, task, domain, wire = gate.reviewed(case, uid)
        assert unit.candidate_id == uid
        assert not unit.is_semantically_authorized
        assert wire["input"][1]["content"] == task
        assert wire["reasoning"] == {"effort": "low"}
        assert wire["model"] == "gpt-5.6-luna"
        assert wire["max_output_tokens"] == 2048
        assert wire["store"] is False
        assert wire["text"]["format"]["strict"] is True
        assert ("CONTEXTO ANTERIOR" in task) == (uid == "candidate-2")
        assert ("SEGMENTO ACTUAL" in task) == (uid == "candidate-2")
        assert (domain is not None) == (case == "F26")
        if domain is not None:
            assert len(domain.temporal_references()) == 1


def test_offline_first_stage_reserves_without_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RECEIPTS", tmp_path / "only-test")
    monkeypatch.delenv(gate.FLAG, raising=False)
    result = gate.run("F23", "candidate-1")
    assert result["mode"] == "OFFLINE_DRY_RUN"
    assert result["max_calls"] == 1
    assert not result["may_write_notes"]
    assert not result["semantically_authorized"]
    assert result["previous_estimated_usd"] == 0.0339488
    assert 0.03 < result["maximum_reserved_usd"] < 0.035
    assert sum((result["previous_estimated_usd"], result["maximum_reserved_usd"])) < 0.07


def test_out_of_order_stage_is_rejected_before_provider_call(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RECEIPTS", tmp_path)
    with pytest.raises(ValueError, match="Out-of-order"):
        gate.run("F23", "candidate-2", live=True, client=object())


def test_live_flag_is_required_even_with_injected_sdk(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RECEIPTS", tmp_path)
    monkeypatch.delenv(gate.FLAG, raising=False)
    calls = []
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **req: calls.append(req)))
    with pytest.raises(ValueError, match="approved live gate"):
        gate.run("F23", "candidate-1", live=True, client=fake)
    assert calls == []


def test_modifying_any_core_prompt_byte_refuses_authority(monkeypatch, tmp_path):
    orig = json.loads(gate.FREEZE.read_text())
    orig["sha256"]["F23/candidate-1"] = "0" * 64
    changed = tmp_path / "wrong.json"
    changed.write_text(json.dumps(orig))
    monkeypatch.setattr(gate, "FREEZE", changed)
    with pytest.raises(ValueError, match="Unreviewed"):
        gate.preflight("F23", "candidate-1")


def test_expensive_call_has_no_cost_authority(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RECEIPTS", tmp_path)
    monkeypatch.setattr(gate, "PREVIOUS_FOCUSED_USD", 0.05)
    with pytest.raises(ValueError, match="limit"):
        gate.preflight("F23", "candidate-1")


def test_provider_error_does_not_trigger_retries(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RECEIPTS", tmp_path)
    monkeypatch.setenv(gate.FLAG, "1")
    attempts = []

    def failed(**kwargs):
        attempts.append(kwargs)
        raise RuntimeError("Simulated provider error")

    fake = SimpleNamespace(responses=SimpleNamespace(create=failed))
    result = gate.run("F23", "candidate-1", live=True, client=fake)
    assert len(attempts) == 1
    assert result["validation"] == "provider_or_compiler_error"
    assert result["error_type"] == "RuntimeError"
    assert not result["may_write_notes"]
    with pytest.raises(ValueError, match="no retries"):
        gate.run("F23", "candidate-1", live=True, client=fake)
    assert len(attempts) == 1
