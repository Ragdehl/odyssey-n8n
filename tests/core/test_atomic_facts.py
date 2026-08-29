"""Focused deterministic coverage for Phase 17D atomic fact markup."""

import pytest

from odyssey_core.atomic_facts import (
    AtomicFactError,
    append_atomic_facts,
    find_unique_atomic_fact,
    parse_atomic_facts,
    remove_atomic_fact,
)


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
