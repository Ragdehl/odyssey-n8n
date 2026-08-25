"""Offline checks for the focused Phase 16.5A planner-contract benchmark."""

from __future__ import annotations

from benchmarks.phase16_5_reference_occurrence.run_benchmark import load_cases


def test_reference_occurrence_benchmark_is_small_and_contract_focused() -> None:
    """Keep the live evidence at ten synthetic Sol/low cases with no model fallback."""
    cases = load_cases()
    assert len(cases) == 10
    assert len({case["id"] for case in cases}) == 10
    assert {case["expected"].get("reference_count") for case in cases} >= {0, 1, 2}
