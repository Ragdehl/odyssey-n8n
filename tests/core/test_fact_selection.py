"""Provider-free validation for bounded atomic-fact locator selection."""

import pytest

from odyssey_core.fact_selection import FactCandidate, FactSelectionError, validate_fact_selection


def test_selector_accepts_only_supplied_match_locator() -> None:
    """Allow a match only when it selects exactly one offered locator."""
    candidates = (FactCandidate("R1:0", "Works at Airbus."),)
    assert (
        validate_fact_selection({"outcome": "MATCH", "locator": "R1:0"}, candidates).locator
        == "R1:0"
    )
    with pytest.raises(FactSelectionError, match="unknown"):
        validate_fact_selection({"outcome": "MATCH", "locator": "invented"}, candidates)


@pytest.mark.parametrize("outcome", ["NO_MATCH", "AMBIGUOUS"])
def test_non_match_selector_outcomes_cannot_smuggle_a_locator(outcome: str) -> None:
    """Keep no-match and ambiguity fail-closed and locator-free."""
    assert validate_fact_selection({"outcome": outcome, "locator": None}, ()).outcome == outcome
    with pytest.raises(FactSelectionError):
        validate_fact_selection({"outcome": outcome, "locator": "R1:0"}, ())
