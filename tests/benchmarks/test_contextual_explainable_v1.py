"""Provider-free guards for the frozen explainable contextual live gate."""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest

from benchmarks.contextual_explainable_v1 import run_live as runner


def test_gate_is_frozen_bounded_and_costed() -> None:
    """Pin the case mix, no-retry policy, and conservative maximum cost."""
    cases = runner.load_cases()
    ceiling, input_tokens = runner.conservative_cost_ceiling(cases)
    assert [case["expected"]["outcome"] for case in cases] == [
        "RESOLVED",
        "AMBIGUOUS",
        "UNRESOLVED",
        "AMBIGUOUS",
        "AMBIGUOUS",
        "RESOLVED",
    ]
    assert cases[3]["request"]["entity_type"] == "canonical_fact"
    assert (
        hashlib.sha256(runner.CASES_PATH.read_bytes()).hexdigest()
        == "ca1e3bfbbf1fe4cffcf31f8e5eacbf4361db4980073e3910fd59dbd1c525384b"
    )
    assert input_tokens > 0
    assert ceiling == Decimal("0.01875900")
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert runner.GATE_CONSUMED is True
    assert runner.MAX_PROVIDER_CALLS == 6


def test_default_gate_refuses_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Neither the confirmation flag nor credentials alone can authorize provider spend."""
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "result.jsonl")
    monkeypatch.setattr(
        runner,
        "OpenAIContextualReasoner",
        lambda *_args, **_kwargs: pytest.fail("provider constructed"),
    )
    with pytest.raises(SystemExit, match="permanently consumed"):
        runner.main(["--confirm-live-provider-calls"])


def test_consumed_gate_refuses_even_when_budget_is_monkeypatched(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A consumed gate cannot be revived by restoring its former cost ceiling."""
    output = tmp_path / "result.jsonl"
    ceiling, _ = runner.conservative_cost_ceiling(runner.load_cases())
    monkeypatch.setattr(runner, "MAX_COST_USD", ceiling)
    monkeypatch.setattr(runner, "OUTPUT_PATH", output)
    monkeypatch.setattr(
        runner,
        "OpenAIContextualReasoner",
        lambda *_args, **_kwargs: pytest.fail("provider constructed"),
    )
    with pytest.raises(SystemExit, match="permanently consumed"):
        runner.main(["--confirm-live-provider-calls"])
