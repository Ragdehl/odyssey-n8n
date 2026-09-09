"""Deterministic routing tests for the Phase 20.2F Luna-first production planner."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from odyssey_core import cost_aware_planning
from odyssey_core.cost_aware_planning import LunaFirstRequestPlanner
from odyssey_core.experimental_luna_planning import PlannerEscalation
from odyssey_core.request_planning import (
    PlannerClarification,
    RequestPlan,
    RequestPlanningError,
)


@dataclass
class _FakePlanner:
    """Return or raise one configured result while exposing bounded provider metadata."""

    result: object | None = None
    error: Exception | None = None
    model: str = "fake-model"
    reasoning_effort: str = "low"
    calls: int = 0
    last_usage: dict[str, int] | None = None
    last_attempt_count: int = 1
    last_response_id: str | None = "resp-test"
    last_provider_status: str | None = "completed"

    def plan(self, request: str):
        """Record the call and return/raise the frozen behavior."""
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def _planner(luna: _FakePlanner, sol: _FakePlanner) -> LunaFirstRequestPlanner:
    return LunaFirstRequestPlanner(luna, sol)


def test_safe_luna_plan_skips_sol() -> None:
    """A validated Luna PLAN is the production result without a Sol call."""
    luna = _FakePlanner(RequestPlan(actions=(), limitations=()), model="gpt-5.6-luna")
    sol = _FakePlanner(RequestPlan(actions=(), limitations=()), model="gpt-5.6-sol")

    result = _planner(luna, sol).plan("What do I know about Odyssey?")

    assert isinstance(result, RequestPlan)
    assert luna.calls == 1
    assert sol.calls == 0


def test_luna_clarification_skips_sol() -> None:
    """A Luna clarification goes directly to the user rather than spending a Sol call."""
    luna = _FakePlanner(PlannerClarification("UNRECOGNIZED_REQUEST"), model="gpt-5.6-luna")
    sol = _FakePlanner(RequestPlan(actions=(), limitations=()), model="gpt-5.6-sol")

    result = _planner(luna, sol).plan("...???...")

    assert result == PlannerClarification("UNRECOGNIZED_REQUEST")
    assert sol.calls == 0


def test_luna_escalation_becomes_user_clarification_without_sol() -> None:
    """Missing authority remains non-executing and does not invite Sol guessing."""
    luna = _FakePlanner(PlannerEscalation(), model="gpt-5.6-luna")
    sol = _FakePlanner(RequestPlan(actions=(), limitations=()), model="gpt-5.6-sol")

    result = _planner(luna, sol).plan(
        "Rewrite whichever family notes seem outdated without asking which facts are true."
    )

    assert result == PlannerClarification("UNRECOGNIZED_REQUEST")
    assert sol.calls == 0


def test_fail_closed_luna_result_falls_back_once_to_sol() -> None:
    """A bounded Luna validation failure receives exactly one established Sol attempt."""
    luna = _FakePlanner(
        error=RequestPlanningError("malformed structured result"),
        model="gpt-5.6-luna",
        last_usage={"input_tokens": 11, "output_tokens": 2},
    )
    sol_result = RequestPlan(actions=(), limitations=())
    sol = _FakePlanner(
        sol_result,
        model="gpt-5.6-sol",
        last_usage={"input_tokens": 13, "output_tokens": 3},
    )
    planner = _planner(luna, sol)

    result = planner.plan("Remember that Marta works at Thales.")

    assert result is sol_result
    assert luna.calls == 1
    assert sol.calls == 1
    assert planner.last_attempt_count == 2
    assert [call.name for call in planner.last_provider_calls] == [
        "planner.luna",
        "planner.sol_fallback",
    ]
    assert planner.last_provider_calls[0].usage == {
        "input_tokens": 11,
        "output_tokens": 2,
    }
    assert planner.last_provider_calls[1].usage == {
        "input_tokens": 13,
        "output_tokens": 3,
    }


def test_generic_luna_provider_error_does_not_double_call_same_provider() -> None:
    """Network/provider exceptions propagate instead of triggering a Sol retry."""
    luna = _FakePlanner(error=RuntimeError("provider unavailable"), model="gpt-5.6-luna")
    sol = _FakePlanner(RequestPlan(actions=(), limitations=()), model="gpt-5.6-sol")
    planner = _planner(luna, sol)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        planner.plan("What do I know about Marta?")

    assert luna.calls == 1
    assert sol.calls == 0
    assert len(planner.last_provider_calls) == 1
    assert planner.last_provider_calls[0].error_category == "RuntimeError"


def test_sol_failure_after_luna_fail_closed_is_not_retried() -> None:
    """The fallback chain remains bounded to one Luna and one Sol attempt."""
    luna = _FakePlanner(error=RequestPlanningError("invalid Luna result"), model="gpt-5.6-luna")
    sol = _FakePlanner(error=RequestPlanningError("invalid Sol result"), model="gpt-5.6-sol")
    planner = _planner(luna, sol)

    with pytest.raises(RequestPlanningError, match="invalid Sol result"):
        planner.plan("Remember something safely representable.")

    assert luna.calls == 1
    assert sol.calls == 1
    assert planner.last_attempt_count == 2
    assert planner.last_provider_calls[-1].error_category == "RequestPlanningError"


def test_empty_request_makes_no_provider_call() -> None:
    """Local input validation happens before either model is invoked."""
    luna = _FakePlanner(RequestPlan(actions=(), limitations=()), model="gpt-5.6-luna")
    sol = _FakePlanner(RequestPlan(actions=(), limitations=()), model="gpt-5.6-sol")
    planner = _planner(luna, sol)

    with pytest.raises(RequestPlanningError, match="non-empty"):
        planner.plan("   ")

    assert luna.calls == 0
    assert sol.calls == 0


def test_from_environment_builds_both_provider_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production construction wires one Luna first pass and one Sol fallback."""
    luna = object()
    sol = object()
    monkeypatch.setattr(
        cost_aware_planning.OpenAILunaExperimentalPlanner,
        "from_environment",
        classmethod(lambda cls, schema, context: luna),
    )
    monkeypatch.setattr(
        cost_aware_planning.OpenAIRequestPlanner,
        "from_environment",
        classmethod(lambda cls, schema, context: sol),
    )

    planner = LunaFirstRequestPlanner.from_environment({}, {"timezone": "Europe/Paris"})

    assert planner._luna is luna
    assert planner._sol is sol


def test_unsupported_luna_result_fails_closed_without_sol() -> None:
    """A validated boundary must not let an unknown Luna result through."""
    luna = _FakePlanner(object())
    sol = _FakePlanner(RequestPlan(actions=(), limitations=()))

    with pytest.raises(TypeError, match="unsupported planner result"):
        _planner(luna, sol).plan("What do I know about Odyssey?")

    assert luna.calls == 1
    assert sol.calls == 0


def test_unsupported_sol_fallback_result_fails_closed() -> None:
    """A fallback result outside the production contract remains rejected."""
    luna = _FakePlanner(error=RequestPlanningError("invalid Luna result"))
    sol = _FakePlanner(object())

    with pytest.raises(TypeError, match="unsupported planner result"):
        _planner(luna, sol).plan("What do I know about Odyssey?")

    assert luna.calls == 1
    assert sol.calls == 1
