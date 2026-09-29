"""Offline guards for the consumed semantic-write-frontend-v1 live gate."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.semantic_write_frontend_v1 import run_live as runner

ROOT = Path(__file__).resolve().parents[2]


def test_gate_reuses_hash_pinned_swr_cases_and_only_three_new_sentinels() -> None:
    """Keep the new lineage small while reusing the immutable active SWR registry by hash."""
    cases, context = runner.load_gate_cases()
    assert len(cases) == 13
    assert [case["lineage"] for case in cases].count("frozen_swr") == 10
    assert [case["lineage"] for case in cases].count("frontend_sentinel") == 3
    assert context == {"date": "2026-09-28", "time": "20:30", "timezone": "Europe/Paris"}
    assert [case["expect_action_kinds"] for case in cases[-3:]] == [
        ["retrieve"],
        ["delegate"],
        ["retrieve", "write", "delegate"],
    ]


def test_gate_is_consumed_with_recorded_immutable_evidence() -> None:
    """Freeze consumed v1 metadata and verify the local ignored artifact when available."""
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert runner.GATE_CONSUMED is True
    assert runner.OUTPUT_PATH == (
        ROOT / "benchmarks/.live-results/semantic-write-frontend-v1-luna-gate.jsonl"
    )
    manifest = json.loads(runner.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["provider_calls_made"] == 1
    assert manifest["consumed_artifact"] == (
        "benchmarks/.live-results/semantic-write-frontend-v1-luna-gate.jsonl"
    )
    assert manifest["artifact_sha256"] == (
        "4431ba7ca547aa3c82070d20f4c391b2113cb4ce8b9754d88e0ddefb1018ebfa"
    )
    assert manifest["result"] == "failed_swr01"
    assert manifest["max_cost_usd"] == "0.00"

    # The live artifact is intentionally ignored and therefore absent in a clean CI checkout.
    # When present locally, verify that it is still the exact retained evidence.
    if runner.OUTPUT_PATH.exists():
        assert (
            hashlib.sha256(runner.OUTPUT_PATH.read_bytes()).hexdigest()
            == (manifest["artifact_sha256"])
        )
        rows = [json.loads(line) for line in runner.OUTPUT_PATH.read_text().splitlines()]
        assert len(rows) == 1
        row = rows[0]
        assert row["case_id"] == "SWR01-self-coworkers"
        assert row["passed"] is False
        assert row["provider_status"] == "completed"
        assert row["usage"] == {
            "input_tokens": 9073,
            "output_tokens": 125,
            "cached_input_tokens": 0,
            "reasoning_tokens": 0,
        }


def test_consumed_gate_refuses_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Make v1 non-reusable even if callers alter its budget or artifact path."""
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "must-not-exist.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without authorization"),
    )
    with pytest.raises(SystemExit, match="permanently consumed"):
        runner.main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()
