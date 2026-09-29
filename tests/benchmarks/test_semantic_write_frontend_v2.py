"""Offline guards for the unexecuted semantic-write-frontend-v2 live gate."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.semantic_write_frontend_v2 import run_live as runner

ROOT = Path(__file__).resolve().parents[2]


def test_gate_reuses_the_same_hash_pinned_ten_plus_three_cases() -> None:
    """Keep the successor gate fixed to the consumed v1 case and oracle surface."""
    cases, context = runner.load_gate_cases()
    assert len(cases) == 13
    assert [case["lineage"] for case in cases].count("frozen_swr") == 10
    assert [case["lineage"] for case in cases].count("frontend_sentinel") == 3
    assert context == {"date": "2026-09-28", "time": "20:30", "timezone": "Europe/Paris"}
    assert [case["id"] for case in cases[-3:]] == [
        "SWF-READ-01",
        "SWF-DELEGATE-01",
        "SWF-MIXED-ORDER-01",
    ]


def test_gate_cost_ceiling_is_offline_luna_only_and_unauthorized() -> None:
    """Freeze the successor call count, input bound, ceiling, and fresh evidence path."""
    cases, context = runner.load_gate_cases()
    schema = json.loads(runner.SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, input_bound = runner.conservative_cost_ceiling(cases, context, schema)
    assert len(cases) == 13
    assert cost == Decimal("0.162357")
    assert input_bound == 50_157
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert runner.OUTPUT_PATH == (
        ROOT / "benchmarks/.live-results/semantic-write-frontend-v2-luna-gate.jsonl"
    )
    assert not runner.OUTPUT_PATH.exists()


def test_gate_refuses_before_provider_construction_at_zero_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep the v2 cost lock ahead of credentials, artifact creation, and provider construction."""
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "must-not-exist.jsonl")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without authorization"),
    )
    with pytest.raises(SystemExit, match=r"exceeds \$0.00 authorization"):
        runner.main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()


def test_gate_requires_confirmation_before_any_hypothetical_authorized_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep explicit command confirmation independent from any later reviewed budget."""
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without confirmation"),
    )
    with pytest.raises(SystemExit, match="without --confirm-live-provider-calls"):
        runner.main([])
