"""Guards for the authorized GPT-6 Luna model-only semantic WRITE comparison."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

import odyssey_core.experimental_luna_planning as luna_planning
from benchmarks.semantic_write_frontend_gpt6_luna_v1 import run_live as runner

ROOT = Path(__file__).resolve().parents[2]


def test_gate_is_model_only_and_bounded() -> None:
    cases, context = runner.load_gate_cases()
    schema = json.loads(runner.SCHEMA_PATH.read_text())
    cost, bound = runner.conservative_cost_ceiling(cases, context, schema)
    assert len(cases) == 13
    assert runner.MODEL == "gpt-6-luna"
    assert runner.REASONING_EFFORT == "low"
    assert runner.MAX_COST_USD == Decimal("0.0809432")
    assert cost == Decimal("0.0809432")
    assert bound == 52_024
    assert not runner.OUTPUT_PATH.exists()
    manifest = json.loads(runner.MANIFEST_PATH.read_text())
    v8 = json.loads((ROOT / "benchmarks/semantic_write_frontend_v8/manifest.json").read_text())
    assert manifest["sha256"] == v8["sha256"]
    assert manifest["evaluator_sha256"] == v8["evaluator_sha256"]
    actual = hashlib.sha256(
        (ROOT / "benchmarks/semantic_write_resolution_v1/evaluate.py").read_bytes()
    ).hexdigest()
    assert manifest["evaluator_sha256"] == actual
    assert luna_planning.LUNA_EXPERIMENT_MODEL == "gpt-5.6-luna"


def test_gate_refuses_if_budget_is_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("0.00"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "x.jsonl")
    monkeypatch.setattr(runner, "_build_planner", lambda *_a: pytest.fail("provider constructed"))
    with pytest.raises(SystemExit, match=r"exceeds \$0.0000000 authorization"):
        runner.main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()
