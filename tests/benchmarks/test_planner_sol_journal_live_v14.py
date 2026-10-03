"""Provider-free guards for the focused Sol Journal fallback gate v14."""

from __future__ import annotations

import json

import pytest

from benchmarks.planner_sol_journal_live_v14 import run_live


def test_v14_retained_evidence_is_historical_and_complete() -> None:
    artifacts = list(run_live.RESULTS_DIR.glob("*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact["version"] == 14
    assert artifact["model"] == "gpt-5.6-sol"
    assert artifact["reasoning_effort"] == "low"
    assert artifact["provider_attempts"] == artifact["completed_provider_responses"] == 1
    assert artifact["automatic_retries"] == 0
    assert artifact["passed"] is True
    assert float(artifact["estimated_standard_cost_usd"]) < float(run_live.AUTHORIZED_CEILING_USD)


def test_v14_historical_contract_is_not_current_and_cannot_rerun(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = run_live._schema()
    assert run_live._contract_hashes(schema) != (
        run_live.PROMPT_SHA256,
        run_live.PROVIDER_SCHEMA_SHA256,
    )
    monkeypatch.setenv(run_live.AUTH_ENV, "1")
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match="candidate contract changed"):
        run_live._preflight()


def test_v14_requires_filter_property_and_fact() -> None:
    good = {
        "target_type": "journal_entry",
        "filters": [("entry_date", "eq", "2026-10-03")],
        "properties": [("entry_date", "set", "2026-10-03")],
        "facts": ["Hoy he tenido un día muy tranquilo."],
    }
    assert run_live._matches(good)
    assert not run_live._matches({**good, "properties": []})
