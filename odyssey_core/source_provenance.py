"""Immutable, type-independent literal provenance over a user's original message.

This component knows nothing about Tasks, NoteSchema, calendar, identity, or
Markdown.  It proves only exact text occurrence and offsets. Semantic meaning,
cardinality, scope, permission and write authority belong elsewhere in Core.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass


class SourceEvidenceError(ValueError):
    """An untrusted evidence proposal has no unique unchanged-source anchor."""


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    """Exact character offsets into the immutable source, never a model ID."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class AnchoredEvidence:
    """One primary occurrence plus zero or more shared contextual occurrences."""

    primary: SourceAnchor
    supporting: tuple[SourceAnchor, ...]

    @property
    def all_spans(self) -> tuple[tuple[int, int], ...]:
        return tuple((part.start, part.end) for part in (self.primary, *self.supporting))


def anchor_literal_evidence(
    original: str, primary: str, supporting: Sequence[str] = ()
) -> AnchoredEvidence:
    """Proof of exact provenance; no assumptions about number/kind of facts.

    Source spans can be shared by arbitrarily many facts; separate facts can
    cite different or overlapping spans. An ambiguous occurrence fails closed
    rather than selecting the first match. Semantic coverage is independent.
    """
    if not isinstance(original, str) or not original.strip():
        raise SourceEvidenceError("Invalid original source")
    if (
        not isinstance(primary, str)
        or not primary.strip()
        or not isinstance(supporting, (list, tuple))
        or len(supporting) > 16
    ):
        raise SourceEvidenceError("Invalid original-source evidence shape")

    def locate(literal: str) -> SourceAnchor:
        if not isinstance(literal, str) or not literal.strip():
            raise SourceEvidenceError("Missing original source evidence")
        matches = list(re.finditer(re.escape(literal), original))
        if len(matches) != 1:
            raise SourceEvidenceError("Source evidence ambiguous or absent")
        start, end = matches[0].span()
        return SourceAnchor(start, end)

    main = locate(primary)
    seen = {main}
    siblings = []
    for literal in supporting:
        span = locate(literal)
        if span not in seen:
            siblings.append(span)
            seen.add(span)
    return AnchoredEvidence(main, tuple(siblings))
