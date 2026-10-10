"""Provider-free 23-case GPT-6 v3 Router gate with sequential cost protection."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_v2_live import run_remaining as gate
from tests.apps.test_fact_candidates import CASES, _from_design


def _sandbox(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gate, "RESULTS", tmp_path / "receipts")


def test_all_23_frozen_production_request_envelopes_are_source_only() -> None:
    assert len(gate.IDS) == 23
    assert not gate.FOCUSED_IDS.intersection(gate.IDS)
    assert set(gate.IDS) | gate.FOCUSED_IDS == set(gate.FULL_REVIEWED_IDS)
    for cid in gate.IDS:
        request = gate.checked_request(cid)
        assert request["input"][1]["content"] == next(
            case["source"] for case in CASES if case["id"] == cid
        )
        assert request["model"] == "gpt-6-luna"
        assert request["reasoning"] == {"effort": "low"}
        assert request["store"] is False
        assert request["max_output_tokens"] == 4096
        assert request["text"]["format"]["strict"] is True


def test_first_offline_run_needs_no_network_or_approval(monkeypatch, tmp_path) -> None:
    _sandbox(monkeypatch, tmp_path)
    monkeypatch.delenv(gate.AUTHORIZATION_ENV, raising=False)
    outcome = gate.run_case("F01")
    assert outcome["mode"] == "OFFLINE_REVIEW_ONLY"
    assert outcome["may_write_notes"] is False
    assert outcome["estimated_prior_usd"] == gate.OBSERVED_PRIOR_USD
    assert outcome["estimated_prior_usd"] + outcome["maximum_reserved_usd"] < 0.07
    assert not gate.RESULTS.exists()


def test_out_of_order_and_repeated_calls_fail_without_any_sdk(monkeypatch, tmp_path) -> None:
    _sandbox(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="staged order"):
        gate.run_case("F02")
    first = gate.run_case("F01")
    saved = {
        **first,
        "mode": "SYNTHETIC_ROUTER_V3_REMAINING",
        "provider_status": "completed",
        "usage": {"input_tokens": 2000, "output_tokens": 500},
    }
    gate.save_record(saved)
    with pytest.raises(ValueError, match="already called"):
        gate.run_case("F01")
    assert gate.run_case("F02")["estimated_prior_usd"] > gate.OBSERVED_PRIOR_USD


def test_only_authorized_flag_may_open_sdk_boundary(monkeypatch, tmp_path) -> None:
    _sandbox(monkeypatch, tmp_path)
    monkeypatch.delenv(gate.AUTHORIZATION_ENV, raising=False)
    called = []
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: called.append(kwargs)))
    with pytest.raises(ValueError, match="approval flag"):
        gate.run_case("F01", live=True, client=fake)
    assert not called


def test_frozen_oracle_fake_is_checked_but_does_not_authorize_core(monkeypatch, tmp_path) -> None:
    _sandbox(monkeypatch, tmp_path)
    monkeypatch.setenv(gate.AUTHORIZATION_ENV, "1")
    original = next(c for c in CASES if c["id"] == "F01")
    from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake

    fake, sent = _sdk_fake(_from_design(original))
    result = gate.run_case("F01", live=True, client=fake)
    assert len(sent) == 1
    assert result["provider_status"] == "completed"
    assert result["validation"] == "source_valid"
    assert result["candidate_count"] == len(original["expected_units"])
    assert result["core_acceptance_verified"] is False
    assert result["may_write_notes"] is False
    assert len(gate._existing_receipts()) == 0


def test_failed_sdk_attempt_is_durable_and_never_retried(monkeypatch, tmp_path) -> None:
    _sandbox(monkeypatch, tmp_path)
    monkeypatch.setenv(gate.AUTHORIZATION_ENV, "1")

    def broken(**_kwargs):
        raise RuntimeError("Synthetic provider failure")

    fake = SimpleNamespace(responses=SimpleNamespace(create=broken))
    result = gate.run_case("F01", live=True, client=fake)
    assert result["provider_status"] == "unknown"
    assert result["error_type"] == "RuntimeError"
    gate.save_record(result)
    with pytest.raises(ValueError, match="requires review"):
        gate.run_case("F02")


def test_limit_blocks_next_provider_even_after_prior_receipts(monkeypatch, tmp_path) -> None:
    _sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(gate, "OBSERVED_PRIOR_USD", 0.0699)
    with pytest.raises(ValueError, match="would be exceeded"):
        gate.preflight("F01")


def test_unreviewed_change_in_any_request_is_rejected(monkeypatch, tmp_path) -> None:
    _sandbox(monkeypatch, tmp_path)
    snapshot = json.loads(gate.PIN.read_text())
    snapshot["sha256"]["F01"] = "0" * 64
    modified = tmp_path / "wrong-pin.json"
    modified.write_text(json.dumps(snapshot))
    monkeypatch.setattr(gate, "PIN", modified)
    with pytest.raises(ValueError, match="drift"):
        gate.run_case("F01")
