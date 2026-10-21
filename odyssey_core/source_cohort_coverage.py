"""Fail-closed source coverage for explicit finite sets, not an identity resolver.

A source quotation is untrusted even when two models agree. This check catches
unreviewed proper-name tokens without assigning canonical identities or types.
It deliberately rejects uncertain named sources rather than guessing members;
unnamed or lowercase referents still need independent semantic/physical proof.
"""

from __future__ import annotations

import re

# Upper-case Unicode initial, including the Spanish/French/English proper names
# accepted by source quotation contracts. No names, roles or note IDs are inferred.
_CAPITALIZED = re.compile(r"(?<!\w)[A-ZÀ-ÖØ-Þ][^\W\d_]*(?:[-’][A-ZÀ-ÖØ-Þ][^\W\d_]*)*(?!\w)")

# Structural coordination, independent of capitalization and concrete names.
# This is a *veto* when source contains an uncovered list member, never a way
# to infer who that member is or authorize a write.
_COORDINATION = r"(?:y|e|et|and|und|&)"
_GRAMMATICAL_GAP = re.compile(
    rf"\s*,?\s*(?:{_COORDINATION}\s+)?(?:(?:a|à|to)\s*)?",
    flags=re.IGNORECASE,
)
_PREFIX_LIST_MEMBER = re.compile(
    rf"(?i)\b[^\W\d_]+\s*(?:,|\b{_COORDINATION}\b)\s*(?:(?:a|à|to)\s*)?$"
)
_SUFFIX_LIST_MEMBER = re.compile(
    rf"(?i)^\s*(?:,\s*|\b{_COORDINATION}\b\s+)(?:(?:a|à|to)\s+)?[^\W\d_]+"
)


class SourceCohortCoverageError(ValueError):
    """An explicit source mention is missing from the proposed finite set."""


def require_explicit_cohort_coverage(source: str, quoted_members: tuple[str, ...]) -> None:
    """Refuse unreviewed mid-sentence proper names in finite-source groups.

    This is a one-way *veto* on missing spans, never permission to add a Person.
    No stored identity is constructed, and lexical uncertainty fails closed.
    """
    if not isinstance(source, str) or not source.strip() or not quoted_members:
        raise SourceCohortCoverageError("Missing finite source evidence")
    spans = []
    for mention in quoted_members:
        if not isinstance(mention, str) or not mention or mention != mention.strip():
            raise SourceCohortCoverageError("Invalid cited member")
        matches = list(re.finditer(r"(?<!\w)" + re.escape(mention) + r"(?!\w)", source))
        if len(matches) != 1:
            raise SourceCohortCoverageError("Member is not unique and source-bound")
        spans.append(matches[0].span())
    if len({(lo, hi) for lo, hi in spans}) != len(spans) or any(
        lo < end and start < hi for i, (lo, hi) in enumerate(spans) for start, end in spans[i + 1 :]
    ):
        raise SourceCohortCoverageError("Overlapping member mentions")
    # Source-anchored coordination guards omissions that lexical capitalization
    # cannot find: lowercase names and names at the beginning of a sentence.
    # A gap that contains an additional word cannot be silently interpreted
    # as punctuation joining only the selected two/three participants.
    ordered = sorted(spans)
    for (_, left_end), (right_start, _) in zip(ordered, ordered[1:], strict=False):
        if not _GRAMMATICAL_GAP.fullmatch(source[left_end:right_start]):
            raise SourceCohortCoverageError("Unreviewed member between finite source quotes")
    if _PREFIX_LIST_MEMBER.search(source[: ordered[0][0]]):
        raise SourceCohortCoverageError("Unreviewed member before finite source quotes")
    if _SUFFIX_LIST_MEMBER.match(source[ordered[-1][1] :]):
        raise SourceCohortCoverageError("Unreviewed member after finite source quotes")
    for token in _CAPITALIZED.finditer(source):
        start, end = token.span()
        # Sentence-initial capitals are grammar, not independent referents.
        preceding = source[:start].rstrip()
        if not preceding or preceding[-1] in ".!?":
            continue
        if not any(lo <= start and end <= hi for lo, hi in spans):
            raise SourceCohortCoverageError("Unreviewed capitalized source referent")
