from __future__ import annotations

from decimal import Decimal

import pytest

from benchmarks.planner_prompt_regression_v3_diagnostic import run_live


def test_diagnostic_is_exactly_two_blocking_cases() -> None:
    cases, _context = run_live._selected_cases()
    assert [case["id"] for case in cases] == list(run_live.CASE_IDS)
    assert run_live.CASE_IDS == (
        "SWR10-relational-target-two-bounded-references",
        "SWF-MIXED-ORDER-01",
    )


def test_diagnostic_budget_is_bounded() -> None:
    budget = run_live.budget_snapshot()
    assert budget["calls"] == run_live.MAX_CALLS == 2
    assert budget["conservative_usd_upper"] == Decimal("0.0259248")
    assert budget["conservative_usd_upper"] <= run_live.AUTHORIZED_CEILING_USD == Decimal("0.026")


def test_diagnostic_has_zero_authority_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()
