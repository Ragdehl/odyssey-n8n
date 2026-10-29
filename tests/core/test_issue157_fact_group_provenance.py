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


def test_one_verified_group_does_not_invent_links_in_elliptical_day_fact():
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
                "participants": ["Nora", "Ivo"] if text == CHILDREN else [],
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
                "reviewed_text": (
                    "{{ref:0}} y {{ref:1}} visitaron el jardín." if text == CHILDREN else text
                ),
                "date": "2026-10-29",
                "reference_names": ["Nora", "Ivo"] if text == CHILDREN else [],
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
    assert result.reviewed_facts[0].reference_names == ("Nora", "Ivo")
    assert result.reviewed_facts[1].reference_names == ()


def test_singular_ellipsis_never_inherits_entire_prior_collective():
    first = "Mis hijos y mi pareja salieron."
    second = "Ella cocinó."
    source = first + " " + second
    proposed = {
        "entities": [],
        "unresolved": [],
        "facts": [
            {
                "meaning": statement,
                "kind": "record",
                "subject": "family",
                "date": "2026-10-29",
                "daypart": None,
                "participants": list(ALL_PEOPLE),
                "source_evidence": statement,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
            for statement in (first, second)
        ],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": index,
                "source_quote": statement,
                "kind": "record",
                "reviewed_text": "{{ref:0}} {{ref:1}} {{ref:2}} participaron.",
                "date": "2026-10-29",
                "reference_names": list(ALL_PEOPLE),
                "supported": True,
            }
            for index, statement in enumerate((first, second))
        ],
    }
    with pytest.raises(
        WholeMessageCoverageError,
        match="Verified group member unsupported by this atomic source fact",
    ):
        validate_whole_message_coverage(
            source,
            proposed,
            review,
            ["core", "temporal"],
            verified_relationship_members=ALL_PEOPLE,
            verified_relationship_groups=(
                ("Mis hijos", ("Nora", "Ivo")),
                ("mi pareja", ("Vera",)),
            ),
        )


@pytest.mark.parametrize("core_anchored", [False, True])
def test_broad_review_quote_cannot_launder_other_fact_group(core_anchored):
    """Only planner-anchored atomic evidence may authorize a SELF link."""
    proposed, reviewed = _review(ALL_PEOPLE, ("Vera",))
    if core_anchored:
        for fact in proposed["facts"]:
            fact.update(
                source_evidence_fragments=[],
                source_evidence_context=None,
                source_evidence_fragment_contexts=[],
            )
        for claim in reviewed["facts"]:
            del claim["source_quote"]
    else:
        # The reviewer can enlarge a quote to the entire original message,
        # but that does not make its other relationship part of THIS fact.
        reviewed["facts"][0]["source_quote"] = SOURCE
    with pytest.raises(
        WholeMessageCoverageError,
        match="Verified group member unsupported by this atomic source fact",
    ):
        validate_whole_message_coverage(
            SOURCE,
            proposed,
            reviewed,
            ["core", "temporal"],
            verified_relationship_members=ALL_PEOPLE,
            verified_relationship_groups=GROUPS,
            core_anchored_evidence=core_anchored,
        )
