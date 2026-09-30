"""Provider-free checks for the prepared production-planner regression gate."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from benchmarks.planner_prompt_regression_v1 import run_live as runner


def test_gate_is_frozen_small_complete_and_bounded_to_production_model() -> None:
    cases, context = runner.load_gate_cases()
    schema = json.loads(runner.SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, costs, bound = runner.total_conservative_cost_ceiling(cases, context, schema)
    assert len(cases) == 16
    assert [case["id"] for case in cases[-3:]] == [
        "PPR14-unknown-self-member-write",
        "PPR15-unknown-self-member-after-related-turn",
        "PPR16-unknown-self-project-member-write",
    ]
    assert runner.PRODUCTION_MODEL == "gpt-5.6-luna"
    assert runner.REASONING_EFFORT == "low"
    assert runner.MAX_TOTAL_COST_USD == Decimal("0.00")
    assert set(costs) == {runner.PRODUCTION_MODEL}
    assert cost == costs[runner.PRODUCTION_MODEL]
    assert cost > runner.MAX_TOTAL_COST_USD
    assert bound > 0
    runner.verify_candidate_contract(schema, context)


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


def test_matrix_acceptance_allows_only_reviewed_safe_degradations() -> None:
    reviewed = [
        {"case_id": "SWR07-qualified-event-member", "passed": False},
        {"case_id": "SWR08-relational-target-described-reference", "passed": False},
        {"case_id": "PPR16-unknown-self-project-member-write", "passed": False},
        {"case_id": "PPR14-unknown-self-member-write", "passed": True},
    ]
    assert runner._matrix_acceptable(reviewed) is True
    assert (
        runner._matrix_acceptable(
            reviewed
            + [{"case_id": "SWR10-relational-target-two-bounded-references", "passed": False}]
        )
        is False
    )


def test_only_production_matrix_runs(monkeypatch, tmp_path) -> None:
    """The final prompt gate evaluates only the currently deployed planner model."""
    calls = []
    monkeypatch.setattr(runner, "MAX_TOTAL_COST_USD", Decimal("999"))
    monkeypatch.setattr(runner, "GPT56_OUTPUT_PATH", tmp_path / "gpt56.jsonl")
    monkeypatch.setattr(runner, "verify_candidate_contract", lambda *_args: None)
    monkeypatch.setattr(
        runner,
        "_run_model",
        lambda model, *_args: calls.append(model) or [{"case_id": "PPR14", "passed": True}],
    )
    assert runner.main(["--confirm-live-provider-calls"]) == 0
    assert calls == [runner.PRODUCTION_MODEL]
