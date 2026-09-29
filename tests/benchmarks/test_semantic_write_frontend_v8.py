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
    assert cost == Decimal("0.1672112")
    assert bound == 52_024
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert not runner.OUTPUT_PATH.exists()
    manifest = json.loads(runner.MANIFEST_PATH.read_text())
    actual = hashlib.sha256(
        (ROOT / "benchmarks/semantic_write_resolution_v1/evaluate.py").read_bytes()
    ).hexdigest()
    assert manifest["evaluator_sha256"] == actual
    assert manifest["failure_policy"] == "collect_all_case_results"
    assert manifest["logical_cases"] == 13
    assert manifest["max_provider_calls"] == 13
    assert manifest["retries"] == 0
    assert manifest["sol_calls"] == 0


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


def test_gate_collects_all_cases_after_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    cases, _ = runner.load_gate_cases()
    seen: list[str] = []

    def fake_single_case_runner(_planner, one_case, _evidence):
        assert len(one_case) == 1
        case_id = one_case[0]["id"]
        seen.append(case_id)
        return [{"case_id": case_id, "passed": case_id != cases[1]["id"]}]

    monkeypatch.setattr(runner, "run_cases", fake_single_case_runner)
    rows = runner.run_all_cases(object(), cases, object())
    assert len(rows) == 13
    assert seen == [case["id"] for case in cases]
    assert rows[1]["passed"] is False
    assert rows[-1]["case_id"] == cases[-1]["id"]
