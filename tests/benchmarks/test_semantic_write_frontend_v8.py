"""Offline guards for semantic-write-frontend-v8."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.semantic_write_frontend_v8 import run_live as runner

ROOT = Path(__file__).resolve().parents[2]


def test_consumed_gate_shape_and_oracle_pin() -> None:
    """Check immutable v8 evidence without recomputing its historical budget from today's prompt."""
    cases, _context = runner.load_gate_cases()
    assert len(cases) == 13
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert runner.GATE_CONSUMED is True
    manifest = json.loads(runner.MANIFEST_PATH.read_text())
    actual = hashlib.sha256(
        (ROOT / "benchmarks/semantic_write_resolution_v1/evaluate.py").read_bytes()
    ).hexdigest()
    assert manifest["evaluator_sha256"] == actual
    assert manifest["provider_calls_made"] == 13
    assert manifest["result"] == "12_passed_1_failed_swr07"
    assert (
        manifest["artifact_sha256"]
        == "49e3598e4f8fb8131bfd0122501160cf113ca4da952112207e7573fa2b98be61"
    )
    if runner.OUTPUT_PATH.exists():
        assert (
            hashlib.sha256(runner.OUTPUT_PATH.read_bytes()).hexdigest()
            == manifest["artifact_sha256"]
        )
    assert manifest["failure_policy"] == "collect_all_case_results"
    assert manifest["logical_cases"] == 13
    assert manifest["max_provider_calls"] == 13
    assert manifest["retries"] == 0
    assert manifest["sol_calls"] == 0


def test_consumed_gate_refuses_before_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "x.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_a, **_k: pytest.fail("provider constructed"),
    )
    with pytest.raises(SystemExit, match="permanently consumed"):
        runner.main(["--confirm-live-provider-calls"])


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
