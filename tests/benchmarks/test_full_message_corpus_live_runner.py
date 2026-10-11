"""The 27-message real-provider corpus runner cannot silently bill or mutate Notes."""

from __future__ import annotations

import pytest

from benchmarks.fact_candidate_core_live import run_full_message_corpus_live as gate
from tests.apps.test_fact_candidates import CASES


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_every_case_is_registered_and_offline_by_default(case, tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "RESULTS", tmp_path / "no_existing_receipts")
    result = gate.run(case["id"])
    assert result["mode"] == "offline"
    assert result["source"] == case["source"]
    assert result["model_calls"] == 0
    assert result["written_notes"] == 0
    assert result["remaining_approved_usd"] > 0
    assert result["source_fixture"].endswith("full_message_corpus_v1/manifest.json")


def test_bounded_gate_refuses_to_start_incomplete_paid_case(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RESULTS", tmp_path / "receipts")
    monkeypatch.setattr(gate, "PREVIOUS_ESTIMATED_SPEND_USD", 0.056766)
    monkeypatch.setattr(gate, "MAX_SPEND_USD", 0.07)
    with pytest.raises(ValueError, match="Insufficient approved headroom"):
        gate.run("F11", live=True)
    assert not gate.RESULTS.exists()


def test_existing_unknown_cost_receipt_blocks_any_new_spending(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RESULTS", tmp_path / "receipts")
    gate.RESULTS.mkdir()
    (gate.RESULTS / "F11.json").write_text(
        '{"case":"F11","status":"armed","reserved_or_estimated_usd":null}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="uncertain cost"):
        gate.run("F12")


def test_existing_valid_receipt_is_charged_before_new_attempt(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RESULTS", tmp_path / "receipts")
    gate.RESULTS.mkdir()
    (gate.RESULTS / "F11.json").write_text(
        '{"case":"F11","outcome":"stopped_before_completion","reserved_or_estimated_usd":0.0003639}',
        encoding="utf-8",
    )
    info = gate.run("F12")
    assert info["already_consumed_estimated_usd"] == round(
        gate.PREVIOUS_ESTIMATED_SPEND_USD + 0.0003639, 8
    )
