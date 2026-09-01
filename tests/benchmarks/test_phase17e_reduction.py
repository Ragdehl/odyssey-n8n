"""Deterministic tests for the Phase 17E reduction harness boundary."""

from types import SimpleNamespace

import pytest

from benchmarks.phase17e_retrieval.reduction import (
    REASONING_EFFORTS,
    select_cases,
    selector_schema,
    validate_selection,
)


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


def test_reasoning_efforts_are_cheap_then_low() -> None:
    """The CLI exposes only the staged reasoning configurations."""
    assert REASONING_EFFORTS == ("none", "low")


def test_selector_schema_is_closed() -> None:
    """The model contract permits only the decision and supplied locator list."""
    assert selector_schema()["additionalProperties"] is False


def test_selection_rejects_unknown_locator() -> None:
    """Unknown model-selected locators fail closed."""
    with pytest.raises(ValueError, match="unknown locator"):
        validate_selection({"decision": "SELECT", "locators": ["missing"]}, {"known"})
