"""Offline guards for the consumed semantic-write-frontend-v3 live gate."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.semantic_write_frontend_v3 import run_live as runner

ROOT = Path(__file__).resolve().parents[2]


def test_gate_reuses_the_same_hash_pinned_ten_plus_three_cases() -> None:
    cases, context = runner.load_gate_cases()
    assert len(cases) == 13
    assert [case["lineage"] for case in cases].count("frozen_swr") == 10
    assert [case["lineage"] for case in cases].count("frontend_sentinel") == 3
    assert context == {"date": "2026-09-28", "time": "20:30", "timezone": "Europe/Paris"}


def test_gate_is_consumed_with_recorded_immutable_evidence() -> None:
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert runner.GATE_CONSUMED is True
    manifest = json.loads(runner.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["provider_calls_made"] == 4
    assert manifest["result"] == "failed_swr04"
    assert (
        manifest["artifact_sha256"]
        == "ff1c88f2cb29613009f943f73cba61cbcb2a00b613acca75207070771d93f8fc"
    )
    assert manifest["max_cost_usd"] == "0.00"
    if runner.OUTPUT_PATH.exists():
        assert (
            hashlib.sha256(runner.OUTPUT_PATH.read_bytes()).hexdigest()
            == manifest["artifact_sha256"]
        )
        rows = [json.loads(line) for line in runner.OUTPUT_PATH.read_text().splitlines()]
        assert len(rows) == 4
        assert [row["passed"] for row in rows] == [True, True, True, False]
        assert rows[-1]["case_id"] == "SWR04-target-and-described-reference"
        assert rows[-1]["result"] == {"outcome": "ESCALATE"}


def test_consumed_gate_refuses_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "must-not-exist.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed for consumed gate"),
    )
    with pytest.raises(SystemExit, match="permanently consumed"):
        runner.main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()
