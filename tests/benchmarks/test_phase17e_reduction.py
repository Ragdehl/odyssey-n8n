"""Deterministic tests for the Phase 17E reduction harness boundary."""

from types import SimpleNamespace

import pytest

from benchmarks.phase17e_retrieval.reduction import (
    REASONING_EFFORTS,
    select_cases,
    selector_schema,
    validate_selection,
)
from benchmarks.phase17e_retrieval.run_answer_path import (
    aggregate_rows,
    answer_schema,
    evaluate_answer,
    validate_answer,
)


def test_answer_contract_and_oracle() -> None:
    """Answer validation and local oracle remain closed and deterministic."""
    assert answer_schema()["additionalProperties"] is False
    answer = validate_answer({"answer": "Trabaja en Thales."})
    assert evaluate_answer(answer, ("Trabaja en Thales.",))


def test_answer_aggregates_split_selector_branches() -> None:
    """Answer-path summaries keep SELECT and ESCALATE measurements separate."""
    row = {
        "decision": "SELECT",
        "oracle_correct": True,
        "sol_input_tokens": 10,
        "sol_output_tokens": 2,
        "sol_reasoning_tokens": 0,
        "evidence_fact_count": 1,
        "evidence_text_tokens": 4,
    }
    summary = aggregate_rows([row, {**row, "decision": "ESCALATE", "oracle_correct": False}])
    assert summary["select"]["case_count"] == 1
    assert summary["escalate"]["correct"] == 0
    assert summary["overall"]["case_count"] == 2


def test_case_filter_preserves_frozen_order() -> None:
    """Repeated case selection returns requested cases in corpus order."""
    cases = tuple(SimpleNamespace(id=value) for value in ("q1", "scale-100", "q2"))
    assert [case.id for case in select_cases(cases, ("q2", "q1"))] == ["q1", "q2"]


def test_case_filter_defaults_to_full_suite() -> None:
    """No case arguments preserve the complete benchmark suite."""
    cases = tuple(SimpleNamespace(id=value) for value in ("q1", "q2"))
    assert select_cases(cases, None) == cases


def test_case_filter_rejects_unknown_id() -> None:
    """A typo cannot silently produce an empty or partial live run."""
    with pytest.raises(ValueError, match="unknown benchmark case ids"):
        select_cases((SimpleNamespace(id="q1"),), ("missing",))


def test_reasoning_efforts_are_staged() -> None:
    """The CLI exposes the staged benchmark configurations without production changes."""
    assert REASONING_EFFORTS == ("none", "low", "medium", "high")


def test_selector_schema_is_closed() -> None:
    """The model contract permits only the decision and supplied locator list."""
    assert selector_schema()["additionalProperties"] is False


def test_selection_rejects_unknown_locator() -> None:
    """Unknown model-selected locators fail closed."""
    with pytest.raises(ValueError, match="unknown locator"):
        validate_selection({"decision": "SELECT", "locators": ["missing"]}, {"known"})
