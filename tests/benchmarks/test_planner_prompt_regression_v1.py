"""Provider-free checks for the prepared GPT-6-first planner regression gate."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from benchmarks.planner_prompt_regression_v1 import run_live as runner


def test_gate_is_frozen_small_complete_and_zero_authority() -> None:
    cases, context = runner.load_gate_cases()
    schema = json.loads(runner.SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, bound = runner.conservative_cost_ceiling(cases, context, schema)
    assert len(cases) == 16
    assert [case["id"] for case in cases[-3:]] == [
        "PPR14-unknown-self-member-write",
        "PPR15-unknown-self-member-after-related-turn",
        "PPR16-unknown-self-project-member-write",
    ]
    assert runner.MODEL == "gpt-6-luna"
    assert runner.REASONING_EFFORT == "low"
    assert runner.MAX_COST_USD == Decimal("0.00")
    assert cost > 0
    assert bound > 0


def test_zero_authority_refuses_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not be constructed")

    monkeypatch.setattr(runner, "_build_planner", forbidden)
    with pytest.raises(SystemExit, match="zero authority"):
        runner.main(["--confirm-live-provider-calls"])
    assert called is False


def test_additional_oracle_requires_relational_one_member_without_preselection() -> None:
    cases, _context = runner.load_gate_cases()
    case = cases[-1]
    # Provider-free shape check: the extra oracle must reject an escalation/non-plan.
    passed, findings = runner._clarification_entry_passed(object(), case)
    assert passed is False
    assert findings == ["expected_single_request_plan"]
