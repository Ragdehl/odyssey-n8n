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
    original: str,
    primary: str,
    supporting: Sequence[str] = (),
    *,
    primary_context: str | None = None,
    supporting_contexts: Sequence[str | None] | None = None,
) -> AnchoredEvidence:
    """Proof of exact provenance; no assumptions about number/kind of facts.

    Source spans can be shared by arbitrarily many facts; separate facts can
    cite different or overlapping spans. An ambiguous occurrence fails closed
    rather than selecting the first match. For repeated literal text, a unique
    ORIGINAL-source containing scope can identify one precise occurrence.
    Context itself has no semantic authority. Semantic coverage is independent.
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

    if supporting_contexts is None:
        supporting_contexts = (None,) * len(supporting)
    if (
        not isinstance(supporting_contexts, (list, tuple))
        or len(supporting_contexts) != len(supporting)
        or (primary_context is not None and not isinstance(primary_context, str))
        or any(
            context is not None and not isinstance(context, str) for context in supporting_contexts
        )
    ):
        raise SourceEvidenceError("Invalid source occurrence contexts")

    def locate(literal: str, context: str | None) -> SourceAnchor:
        if not isinstance(literal, str) or not literal.strip():
            raise SourceEvidenceError("Missing original source evidence")
        if context is None:
            matches = list(re.finditer(re.escape(literal), original))
            if len(matches) != 1:
                raise SourceEvidenceError("Source evidence ambiguous or absent")
            start, end = matches[0].span()
        else:
            if not context.strip():
                raise SourceEvidenceError("Missing disambiguating original source context")
            original_matches = list(re.finditer(re.escape(context), original))
            contained = list(re.finditer(re.escape(literal), context))
            if len(original_matches) != 1 or len(contained) != 1:
                raise SourceEvidenceError("Source occurrence context ambiguous or absent")
            start = original_matches[0].start() + contained[0].start()
            end = start + len(literal)
            if original[start:end] != literal:
                raise SourceEvidenceError("Source occurrence changed")
        return SourceAnchor(start, end)

    main = locate(primary, primary_context)
    seen = {main}
    siblings = []
    for literal, context in zip(supporting, supporting_contexts, strict=True):
        span = locate(literal, context)
        if span not in seen:
            siblings.append(span)
            seen.add(span)
    return AnchoredEvidence(main, tuple(siblings))


def anchor_original_partition(original: str, parts: Sequence[str]) -> tuple[SourceAnchor, ...]:
    """Verify contiguous complete coverage with exact source characters.

    N spans, any Note/app domains. Do not skip whitespace, fix boundaries,
    reorder chunks, or infer missing text. Callers own semantic split review.
    """
    if (
        not isinstance(original, str)
        or not original.strip()
        or not isinstance(parts, (list, tuple))
        or not parts
    ):
        raise SourceEvidenceError("Invalid original source partition")
    offsets = []
    start = 0
    for fragment in parts:
        if not isinstance(fragment, str) or not fragment.strip():
            raise SourceEvidenceError("Empty or invalid source partition part")
        end = start + len(fragment)
        if original[start:end] != fragment:
            raise SourceEvidenceError("Source partition changes or skips original characters")
        offsets.append(SourceAnchor(start, end))
        start = end
    if start != len(original):
        raise SourceEvidenceError("Source partition omits original characters")
    return tuple(offsets)
