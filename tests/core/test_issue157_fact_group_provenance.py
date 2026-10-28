"""Fail closed when one verified SELF group is attributed to another fact."""

from __future__ import annotations

import pytest

from odyssey_core.whole_message_coverage import (
    WholeMessageCoverageError,
    validate_whole_message_coverage,
)

CHILDREN = "Hoy mis hijos visitaron el jardín."
PARTNER = "Mi pareja visitó el museo."
SOURCE = CHILDREN + " " + PARTNER
GROUPS = (("mis hijos", ("Nora", "Ivo")), ("Mi pareja", ("Vera",)))
ALL_PEOPLE = ("Nora", "Ivo", "Vera")


def _review(names_a, names_b):
    facts = []
    reviews = []
    for statement, names in ((CHILDREN, names_a), (PARTNER, names_b)):
        facts.append(
            {
                "kind": "record",
                "subject": "family",
                "meaning": statement,
                "date": "2026-10-29",
                "daypart": None,
                "participants": list(names),
                "source_evidence": statement,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
        )
        references = " ".join("{{ref:" + str(i) + "}}" for i in range(len(names)))
        reviews.append(
            {
                "ordinal": len(reviews),
                "source_quote": statement,
                "kind": "record",
                "reviewed_text": references + " visitó un lugar.",
                "date": "2026-10-29",
                "reference_names": list(names),
                "supported": True,
            }
        )
    return (
        {"entities": [], "facts": facts, "unresolved": []},
        {"approved": True, "complete": True, "reason": None, "facts": reviews},
    )


def _validate(first, second):
    proposed, reviewed = _review(first, second)
    return validate_whole_message_coverage(
        SOURCE,
        proposed,
        reviewed,
        ["core", "temporal"],
        verified_relationship_members=ALL_PEOPLE,
        verified_relationship_groups=GROUPS,
    )


def test_two_independent_groups_remain_bound_to_their_own_facts():
    approved = _validate(("Nora", "Ivo"), ("Vera",))
    assert [row.reference_names for row in approved.reviewed_facts] == [
        ("Nora", "Ivo"),
        ("Vera",),
    ]


@pytest.mark.parametrize(
    "first,second",
    [
        (ALL_PEOPLE, ("Vera",)),
        (("Nora", "Ivo"), ALL_PEOPLE),
        (("Vera",), ("Nora", "Ivo")),
    ],
)
def test_verified_in_self_does_not_authorize_wrong_fact(first, second):
    with pytest.raises(
        WholeMessageCoverageError,
        match="Verified group member unsupported by this atomic source fact",
    ):
        _validate(first, second)


def test_later_ellipsis_cannot_inherit_a_set_from_two_different_fact_sources():
    second = "Después visitamos otra tienda."
    original = CHILDREN + " " + PARTNER + " " + second
    proposed = {
        "entities": [],
        "unresolved": [],
        "facts": [
            {
                "kind": "record",
                "subject": "family",
                "meaning": line,
                "date": "2026-10-29",
                "daypart": None,
                "participants": list(ALL_PEOPLE),
                "source_evidence": line,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
            for line in (CHILDREN, PARTNER, second)
        ],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": i,
                "source_quote": line,
                "kind": "record",
                "reviewed_text": "{{ref:0}} {{ref:1}} {{ref:2}} fuimos.",
                "date": "2026-10-29",
                "reference_names": list(ALL_PEOPLE),
                "supported": True,
            }
            for i, line in enumerate((CHILDREN, PARTNER, second))
        ],
    }
    with pytest.raises(WholeMessageCoverageError):
        validate_whole_message_coverage(
            original,
            proposed,
            review,
            ["core", "temporal"],
            verified_relationship_members=ALL_PEOPLE,
            verified_relationship_groups=GROUPS,
        )


def test_one_verified_group_carries_to_subsequent_elliptical_same_day_fact():
    continuation = "Después visitamos el museo."
    source = CHILDREN + " " + continuation
    statements = (CHILDREN, continuation)
    proposed = {
        "entities": [],
        "unresolved": [],
        "facts": [
            {
                "kind": "record",
                "subject": "family",
                "meaning": text,
                "date": "2026-10-29",
                "daypart": None,
                "participants": ["Nora", "Ivo"],
                "source_evidence": text,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
            for text in statements
        ],
    }
    reviewed = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": i,
                "source_quote": text,
                "kind": "record",
                "reviewed_text": "{{ref:0}} y {{ref:1}} visitaron un lugar.",
                "date": "2026-10-29",
                "reference_names": ["Nora", "Ivo"],
                "supported": True,
            }
            for i, text in enumerate(statements)
        ],
    }
    result = validate_whole_message_coverage(
        source,
        proposed,
        reviewed,
        ["core", "temporal"],
        verified_relationship_members=("Nora", "Ivo"),
        verified_relationship_groups=(("mis hijos", ("Nora", "Ivo")),),
    )
    assert len(result.reviewed_facts) == 2
