"""No-provider tests for bounded clarification choices."""

from __future__ import annotations

from pathlib import Path

import pytest

from odyssey_core.clarification import (
    ClarificationOption,
    LocalClarificationStore,
    PendingClarification,
    match_clarification_reply,
    resolve_clarification_reply,
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


class _Classifier:
    """Supply one deterministic candidate without contacting a provider."""

    def __init__(self, decision: str) -> None:
        self.decision = decision
        self.calls = 0

    def classify(
        self, reply: str, original_request: str, options: tuple[ClarificationOption, ...]
    ) -> str:
        """Record classifier invocation for precedence assertions."""
        assert original_request == "original request"
        assert options == OPTIONS
        self.calls += 1
        return self.decision


def test_reply_precedence_and_bounded_control_outcomes() -> None:
    """Deterministic choices and explicit cancel precede any optional classifier."""
    classifier = _Classifier("NEW_REQUEST")
    assert resolve_clarification_reply("2", OPTIONS, classifier, "original request") == "note-b"
    assert (
        resolve_clarification_reply("Marta in Lyon", OPTIONS, classifier, "original request")
        == "note-a"
    )
    assert (
        resolve_clarification_reply("cancel", OPTIONS, classifier, "original request") == "CANCEL"
    )
    assert (
        resolve_clarification_reply("Cancel it", OPTIONS, classifier, "original request")
        == "CANCEL"
    )
    assert classifier.calls == 0
    assert (
        resolve_clarification_reply("What about tomorrow?", OPTIONS, classifier, "original request")
        == "NEW_REQUEST"
    )
    assert classifier.calls == 1
    classifier.decision = "fabricated-note"
    assert (
        resolve_clarification_reply("maybe", OPTIONS, classifier, "original request")
        == "UNRESOLVED"
    )


def test_one_durable_pending_decision_per_conversation_without_ttl(tmp_path: Path) -> None:
    """State survives a new store instance and is isolated by conversation identity."""
    first = LocalClarificationStore(tmp_path, "main")
    pending = PendingClarification(
        "original request", "request-1", "pending-1", OPTIONS, ("a" * 64, "b" * 64)
    )
    with first.locked():
        first.replace(pending)
    assert LocalClarificationStore(tmp_path, "main").read() == pending
    assert LocalClarificationStore(tmp_path, "new-conversation").read() is None
    first.clear()
    assert first.read() is None


def test_invalid_pending_guard_is_not_persisted(tmp_path: Path) -> None:
    """Malformed revision guards cannot create durable clarification authority."""
    store = LocalClarificationStore(tmp_path, "main")
    with pytest.raises(ValueError):
        store.replace(
            PendingClarification(
                "original request", "request-1", "pending-1", OPTIONS, ("not-a-digest",)
            )
        )
    assert store.read() is None
