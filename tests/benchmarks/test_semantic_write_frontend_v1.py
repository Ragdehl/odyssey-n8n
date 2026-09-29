"""Offline guards for the unexecuted semantic-write-frontend-v1 live gate."""

from __future__ import annotations

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


def test_gate_cost_ceiling_is_offline_luna_only_and_unauthorized() -> None:
    """Record the future maximum call count and conservative no-cache ceiling at $0 authority."""
    cases, context = runner.load_gate_cases()
    schema = json.loads(runner.SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, input_bound = runner.conservative_cost_ceiling(cases, context, schema)
    assert len(cases) == 13
    assert cost == Decimal("0.1594554")
    assert input_bound == 49_041
    assert runner.MAX_COST_USD == Decimal("0.1594554")
    assert runner.OUTPUT_PATH == (
        ROOT / "benchmarks/.live-results/semantic-write-frontend-v1-luna-gate.jsonl"
    )
    assert not runner.OUTPUT_PATH.exists()


def test_gate_refuses_before_provider_construction_when_budget_is_insufficient(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep the cost cap fail-closed even though this exact gate is now authorized."""
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("0.00"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "must-not-exist.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without authorization"),
    )
    with pytest.raises(SystemExit, match=r"exceeds \$0.00 authorization"):
        runner.main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()


def test_gate_requires_confirmation_even_after_hypothetical_future_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep command confirmation independent from a future reviewed cost authorization."""
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without confirmation"),
    )
    with pytest.raises(SystemExit, match="without --confirm-live-provider-calls"):
        runner.main([])
