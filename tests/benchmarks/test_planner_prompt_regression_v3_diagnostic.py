from __future__ import annotations

import pytest

from benchmarks.planner_prompt_regression_v3_diagnostic import run_live


def test_diagnostic_is_exactly_two_blocking_cases() -> None:
    cases, _context = run_live._selected_cases()
    assert [case["id"] for case in cases] == list(run_live.CASE_IDS)
    assert run_live.CASE_IDS == (
        "SWR10-relational-target-two-bounded-references",
        "SWF-MIXED-ORDER-01",
    )


def test_diagnostic_preflight_refuses_reuse_after_contract_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The consumed diagnostic authorization cannot be reused for the new Core contract."""
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match="contract changed"):
        run_live._preflight()


def test_retained_diagnostic_evidence_is_complete_and_distinct() -> None:
    import json

    files = sorted(run_live.RESULTS_DIR.glob("*.json"))
    assert [path.name for path in files] == [
        "8a63bf8730ae__SWF-MIXED-ORDER-01.json",
        "8a63bf8730ae__SWR10-relational-target-two-bounded-references.json",
        "8a63bf8730ae__summary.json",
    ]
    rows = {
        data["case_id"]: data
        for path in files
        if "case_id" in (data := json.loads(path.read_text(encoding="utf-8")))
    }
    assert rows["SWF-MIXED-ORDER-01"]["passed"] is True
    swr10 = rows["SWR10-relational-target-two-bounded-references"]
    assert swr10["passed"] is False
    assert swr10["findings"] == ["both_references_bounded_to_event"]
    summary = json.loads((run_live.RESULTS_DIR / "8a63bf8730ae__summary.json").read_text())
    assert summary["provider_attempts"] == summary["completed_provider_responses"] == 2
    assert summary["automatic_retries"] == 0
    assert summary["estimated_standard_cost_usd"] == "0.0051432"
