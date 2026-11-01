"""Historical Core pilot safety: stale source refusal and isolated mechanics.

Old per-candidate requests were retired in favor of whole-source Core. Their
recorded contract must NOT be reapproved by changing frozen prompt hashes.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_core_live import run_dependent_live as gate


def test_archived_core_scopes_stay_non_authoritative_and_are_now_stale():
    assert gate.STAGES == (
        ("F23", "candidate-1"),
        ("F23", "candidate-2"),
        ("F26", "candidate-1"),
        ("F26", "candidate-2"),
    )
    for case, uid in gate.STAGES:
        unit, task, domain, wire = gate._request(case, uid)
        with pytest.raises(ValueError, match="Unreviewed dependent Core request"):
            gate.reviewed(case, uid)
        assert unit.candidate_id == uid
        assert not unit.is_semantically_authorized
        assert wire["input"][1]["content"] == task
        assert wire["reasoning"] == {"effort": "low"}
        assert wire["model"] == "gpt-5.6-luna"
        assert wire["max_output_tokens"] == (1280 if case == "F26" else 2048)
        assert wire["store"] is False
        assert wire["text"]["format"]["strict"] is True
        assert ("CONTEXTO ANTERIOR" in task) == (uid == "candidate-2")
        assert ("SEGMENTO ACTUAL" in task) == (uid == "candidate-2")
        assert (domain is not None) == (case == "F26")
        if domain is not None:
            assert len(domain.temporal_references()) == 1


def test_archived_offline_stage_refuses_changed_prompt_without_credentials(monkeypatch, tmp_path):
    """Even a dry run must not mistake stale source for a reviewed request."""
    monkeypatch.setattr(gate, "RECEIPTS", tmp_path / "only-test")
    monkeypatch.delenv(gate.FLAG, raising=False)
    with pytest.raises(ValueError, match="Unreviewed dependent Core request"):
        gate.run("F23", "candidate-1")
    assert not gate.RECEIPTS.exists()


def test_out_of_order_stage_is_rejected_before_provider_call(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RECEIPTS", tmp_path)
    # Test the existing order guard directly; its unrelated archived prompt
    # would (correctly) refuse the attempt even earlier in run().
    with pytest.raises(ValueError, match="Out-of-order"):
        gate._prior(("F23", "candidate-2"))


def test_live_flag_is_required_even_with_injected_sdk(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RECEIPTS", tmp_path)
    monkeypatch.delenv(gate.FLAG, raising=False)
    # Isolate the legacy flag boundary after the stale-source check. This
    # monkeypatch is local to a fake-provider test, NEVER live authorization.
    monkeypatch.setattr(gate, "reviewed", gate._request)
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
    monkeypatch.setattr(gate, "PREVIOUS_FOCUSED_USD", 0.06)
    # Only isolate the historical cost envelope, do not reapprove the prompt.
    monkeypatch.setattr(gate, "reviewed", gate._request)
    with pytest.raises(ValueError, match="limit"):
        gate.preflight("F23", "candidate-1")


def test_provider_error_does_not_trigger_retries(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RECEIPTS", tmp_path)
    monkeypatch.setenv(gate.FLAG, "1")
    # Exercise the old no-retry mechanism with a synthetic failing SDK only;
    # the real reviewed() above still refuses current source before the SDK.
    monkeypatch.setattr(gate, "reviewed", gate._request)
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
