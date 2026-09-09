"""Deterministic tests for the bounded contextual Luna replacement gate."""

from __future__ import annotations

import pytest

from benchmarks.run_contextual_luna_mini_gate import SELECTED_CASE_IDS, select_cases, summarize


def _row(
    case_id: str,
    outcome: str,
    identity: str | None,
    *,
    correct: bool = True,
    false_resolved: bool = False,
    schema_valid: bool = True,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "outcome": outcome,
        "id": identity,
        "correct": correct,
        "false_resolved": false_resolved,
        "schema_valid": schema_valid,
        "input_tokens": 10,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 2,
        "reasoning_tokens": 1,
    }


def test_selected_gate_is_frozen_and_contains_historical_a19() -> None:
    """The mini-gate stays bounded and cannot silently omit the historical Luna failure."""
    assert len(SELECTED_CASE_IDS) == 8
    assert "A19" in SELECTED_CASE_IDS
    cases = [{"id": case_id} for case_id in reversed(SELECTED_CASE_IDS)]
    assert [case["id"] for case in select_cases(cases)] == list(SELECTED_CASE_IDS)


def test_select_cases_fails_closed_when_one_sentinel_is_missing() -> None:
    """A partial local fixture must not produce a misleading live quality result."""
    with pytest.raises(ValueError, match="missing"):
        select_cases([{"id": case_id} for case_id in SELECTED_CASE_IDS if case_id != "A19"])


def test_summary_passes_only_exact_safe_eight_case_result() -> None:
    """Passing requires all labels plus the explicit A19 ambiguous regression result."""
    rows = [
        _row("A02", "RESOLVED", "xavi-pujol"),
        _row("A09", "RESOLVED", "delta"),
        _row("A11", "RESOLVED", "carrefour-balma"),
        _row("A19", "AMBIGUOUS", None),
        _row("A22", "AMBIGUOUS", None),
        _row("A28", "AMBIGUOUS", None),
        _row("A31", "UNRESOLVED", None),
        _row("A34", "UNRESOLVED", None),
    ]

    result = summarize(rows)

    assert result["pass"] is True
    assert result["correct"] == 8
    assert result["clear_false_resolved"] == 0
    assert result["a19_safe"] is True


def test_summary_rejects_historical_a19_false_resolution() -> None:
    """Resolving the generic work project to Atlas remains an immediate safety failure."""
    rows = [
        _row("A02", "RESOLVED", "xavi-pujol"),
        _row("A09", "RESOLVED", "delta"),
        _row("A11", "RESOLVED", "carrefour-balma"),
        _row("A19", "RESOLVED", "atlas", correct=False, false_resolved=True),
        _row("A22", "AMBIGUOUS", None),
        _row("A28", "AMBIGUOUS", None),
        _row("A31", "UNRESOLVED", None),
        _row("A34", "UNRESOLVED", None),
    ]

    result = summarize(rows)

    assert result["pass"] is False
    assert result["clear_false_resolved"] == 1
    assert result["a19_safe"] is False
