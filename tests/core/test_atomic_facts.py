"""Focused deterministic coverage for Phase 17D atomic fact markup."""

import pytest

from odyssey_core.atomic_facts import (
    AtomicFactError,
    append_atomic_facts,
    find_unique_atomic_fact,
    parse_atomic_facts,
    remove_atomic_fact,
    render_atomic_facts,
)
from odyssey_core.fact_selection import FactCandidate


def test_atomic_facts_render_parse_and_note_scoped_identity() -> None:
    """Preserve ordered locators while deriving global identity from the containing note."""
    body = append_atomic_facts(
        "Legacy prose.",
        ("Works at Thales.", "Has two children."),
        "R1",
        (4, 5),
        "2026-08-29T10:00:00+02:00",
    )
    facts = parse_atomic_facts(body)
    assert [fact.text for fact in facts] == ["Works at Thales.", "Has two children."]
    assert facts[0].global_identity("marta") == ("marta", "R1", 4)
    assert "## Added 2026-08-29" in body and "Legacy prose." in body


def test_malformed_odyssey_marker_fails_closed() -> None:
    """Reject malformed owned markers without treating arbitrary comments as facts."""
    with pytest.raises(AtomicFactError):
        parse_atomic_facts("- fact\n  <!-- odyssey:fact request=R1 -->")
    assert parse_atomic_facts("<!-- user comment -->") == ()


@pytest.mark.parametrize(
    "fact",
    ["line one\nline two", "line one\rline two", "human <!-- odyssey:fact text"],
)
def test_renderer_rejects_noncanonical_fact_text(fact: str) -> None:
    """Keep canonical fact text single-line and outside Odyssey's reserved marker namespace."""
    with pytest.raises(AtomicFactError):
        render_atomic_facts((fact,), "R1", (0,), "2026-08-29")


def test_exact_marked_fact_removal_leaves_neighbors_untouched() -> None:
    """Remove a complete marker block only after unique exact normalized targeting."""
    body = append_atomic_facts(
        "Legacy prose.", ("Works at Airbus.", "Has two children."), "R1", (0, 1), "2026-08-29"
    )
    target = find_unique_atomic_fact(body, " Works   at Airbus. ")
    assert target is not None
    result = remove_atomic_fact(body, target)
    assert (
        "Works at Airbus." not in result
        and "Has two children." in result
        and "Legacy prose." in result
    )


def test_locator_is_note_scoped_for_global_identity() -> None:
    """Use the same request/ordinal locator in distinct containing notes without collision."""
    fact = parse_atomic_facts(
        append_atomic_facts("", ("Works at Airbus.",), "R1", (0,), "2026-08-29")
    )[0]
    assert fact.locator == "R1:0"
    assert fact.global_identity("marta") != fact.global_identity("ada")
    assert FactCandidate(fact.locator, fact.text).text == "Works at Airbus."
