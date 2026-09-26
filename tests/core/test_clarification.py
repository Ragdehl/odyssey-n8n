"""No-provider tests for bounded clarification choices."""

from __future__ import annotations

import pytest

from odyssey_core.clarification import (
    ClarificationOption,
    match_clarification_reply,
    validate_bounded_classifier_choice,
)

OPTIONS = (
    ClarificationOption("note-a", "Marta in Lyon"),
    ClarificationOption("note-b", "Marta in Madrid"),
)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [("1", "note-a"), (" 2 ", "note-b"), ("marta in lyon", "note-a"), ("3", None), ("Marta", None)],
)
def test_only_numeric_or_exact_unique_label_selects_option(
    reply: str, expected: str | None
) -> None:
    """Free text and unknown numbers cannot invent a target."""
    assert match_clarification_reply(reply, OPTIONS) == expected


def test_duplicate_labels_remain_unresolved_and_ids_must_be_unique() -> None:
    """Displayed labels cannot silently identify one of two same-named Notes."""
    same_label = (ClarificationOption("note-a", "Marta"), ClarificationOption("note-b", "Marta"))
    assert match_clarification_reply("Marta", same_label) is None
    assert match_clarification_reply("2", same_label) == "note-b"
    with pytest.raises(ValueError):
        match_clarification_reply("1", (OPTIONS[0], OPTIONS[0]))


def test_optional_classifier_cannot_invent_an_identity() -> None:
    """An optional language-model classification has no canonical authority."""
    assert validate_bounded_classifier_choice("note-b", OPTIONS) == "note-b"
    assert validate_bounded_classifier_choice("fabricated", OPTIONS) is None
    assert validate_bounded_classifier_choice(None, OPTIONS) is None
