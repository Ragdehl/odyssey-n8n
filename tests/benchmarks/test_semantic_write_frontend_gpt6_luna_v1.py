"""Guards for the consumed GPT-6 Luna model-only semantic WRITE comparison."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

import odyssey_core.experimental_luna_planning as luna_planning
from benchmarks.semantic_write_frontend_gpt6_luna_v1 import run_live as runner

ROOT = Path(__file__).resolve().parents[2]


def test_gate_is_consumed_with_complete_matrix() -> None:
    assert runner.MODEL == "gpt-6-luna"
    assert runner.REASONING_EFFORT == "low"
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert runner.GATE_CONSUMED is True
    manifest = json.loads(runner.MANIFEST_PATH.read_text())
    assert manifest["provider_calls_made"] == 13
    assert manifest["result"] == "11_of_13_passed"
    assert (
        manifest["artifact_sha256"]
        == "896e73337a9a1ffbf2984b8db18c214d7dea03e8f705ad181b6950554a941628"
    )
    assert manifest["comparison_conclusion"] == "retain_gpt-5.6-luna_for_planner"
    assert luna_planning.LUNA_EXPERIMENT_MODEL == "gpt-5.6-luna"
    if runner.OUTPUT_PATH.exists():
        rows = [json.loads(line) for line in runner.OUTPUT_PATH.read_text().splitlines()]
        assert len(rows) == 13
        assert sum(row["passed"] for row in rows) == 11
        assert (
            hashlib.sha256(runner.OUTPUT_PATH.read_bytes()).hexdigest()
            == manifest["artifact_sha256"]
        )


def test_consumed_gate_refuses_before_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "x.jsonl")
    monkeypatch.setattr(runner, "_build_planner", lambda *_a: pytest.fail("provider constructed"))
    with pytest.raises(SystemExit, match="permanently consumed"):
        runner.main(["--confirm-live-provider-calls"])
