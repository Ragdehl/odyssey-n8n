"""Provider-free guards for the focused Sol Journal fallback gate v14."""

from __future__ import annotations

import pytest

from benchmarks.planner_sol_journal_live_v14 import run_live


def test_v14_pins_current_sol_contract_and_budget() -> None:
    schema = run_live._schema()
    assert run_live._contract_hashes(schema) == (
        run_live.PROMPT_SHA256,
        run_live.PROVIDER_SCHEMA_SHA256,
    )
    budget = run_live.budget_snapshot()
    assert budget["calls"] == run_live.MAX_CALLS == 1
    assert budget["standard_usd_upper"] < run_live.AUTHORIZED_CEILING_USD


def test_v14_requires_filter_property_and_fact() -> None:
    good = {
        "target_type": "journal_entry",
        "filters": [("entry_date", "eq", "2026-10-03")],
        "properties": [("entry_date", "set", "2026-10-03")],
        "facts": ["Hoy he tenido un día muy tranquilo."],
    }
    assert run_live._matches(good)
    assert not run_live._matches({**good, "properties": []})


def test_v14_has_zero_provider_authority_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()
