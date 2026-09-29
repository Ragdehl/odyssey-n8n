"""Offline guards for semantic-write-frontend-v8."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.semantic_write_frontend_v8 import run_live as runner

ROOT = Path(__file__).resolve().parents[2]


def test_gate_shape_cost_and_oracle_pin() -> None:
    cases, context = runner.load_gate_cases()
    schema = json.loads(runner.SCHEMA_PATH.read_text())
    cost, bound = runner.conservative_cost_ceiling(cases, context, schema)
    assert len(cases) == 13
    assert cost == Decimal("0.1668914")
    assert bound == 51_901
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert not runner.OUTPUT_PATH.exists()
    manifest = json.loads(runner.MANIFEST_PATH.read_text())
    actual = hashlib.sha256(
        (ROOT / "benchmarks/semantic_write_resolution_v1/evaluate.py").read_bytes()
    ).hexdigest()
    assert manifest["evaluator_sha256"] == actual


def test_gate_refuses_without_authority(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "x.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_a, **_k: pytest.fail("provider constructed"),
    )
    with pytest.raises(SystemExit, match=r"exceeds \$0.0000000 authorization"):
        runner.main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()
