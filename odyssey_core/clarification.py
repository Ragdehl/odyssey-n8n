"""Bounded choice interpretation for an already grounded clarification decision."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClarificationOption:
    """Carry one Core-supplied opaque identity and its user-safe displayed label."""

    id: str
    label: str


def match_clarification_reply(reply: str, options: tuple[ClarificationOption, ...]) -> str | None:
    """Choose only a numeric or exact unique displayed option; otherwise stay unresolved.

    Args:
        reply: The next user message, never treated as canonical identity authority.
        options: The complete bounded options previously supplied by Core.

    Returns:
        The selected supplied opaque ID, or ``None`` when no unique decision is proven.

    Raises:
        ValueError: If the purported option set is malformed or has duplicate identities.
    """
    if not isinstance(reply, str) or not isinstance(options, tuple) or not 1 < len(options) <= 4:
        raise ValueError("Clarification reply or option set is invalid")
    if any(
        not isinstance(option, ClarificationOption)
        or not isinstance(option.id, str)
        or not option.id
        or not isinstance(option.label, str)
        or not option.label.strip()
        or len(option.label) > 160
        for option in options
    ) or len({option.id for option in options}) != len(options):
        raise ValueError("Clarification options are invalid")
    normalized = reply.strip()
    if normalized.isascii() and normalized.isdecimal():
        index = int(normalized)
        return options[index - 1].id if 1 <= index <= len(options) else None
    matches = [option.id for option in options if option.label.casefold() == normalized.casefold()]
    return matches[0] if len(matches) == 1 else None


def validate_bounded_classifier_choice(
    proposed_id: str | None, options: tuple[ClarificationOption, ...]
) -> str | None:
    """Constrain any optional language-model classifier to one supplied option or unresolved."""
    if proposed_id is None:
        return None
    return proposed_id if proposed_id in {option.id for option in options} else None
