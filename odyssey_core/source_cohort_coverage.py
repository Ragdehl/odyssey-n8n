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
    rf"\s*(?:,\s*(?:{_COORDINATION}\s+)?|{_COORDINATION}\s+)(?:(?:a|à|to)\s+)?",
    flags=re.IGNORECASE,
)
_PREFIX_LIST_MEMBER = re.compile(
    rf"(?i)\b[^\W\d_]+\s*(?:,|\b{_COORDINATION}\b)\s*(?:(?:a|à|to)\s*)?$"
)
_SUFFIX_LIST_MEMBER = re.compile(
    rf"(?i)^\s*(?:,\s*|\b{_COORDINATION}\b\s+)(?:(?:a|à|to)\s+)?[^\W\d_]+"
)
# Only known syntactic introductions may precede the FIRST cited member.
# Otherwise a quote could begin halfway through a multiword lowercase name:
# "a ana maría y a luis" with only "maría" selected. This is a veto,
# never an attempt to recognize a Person or invent a canonical identity.
_FIRST_MEMBER_START = re.compile(
    rf"(?ix)(?:^\s*|[,;:]\s*|\b(?:a|à|to|{_COORDINATION}|met|meet|saw|knew|"
    r"rencontré|rencontrée|croisé|croisée|conocí|conocido|conocimos|visited)\s+)$"
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
    if not _FIRST_MEMBER_START.search(source[: ordered[0][0]]):
        raise SourceCohortCoverageError("Unreviewed partial source name before first member")
    for (_, left_end), (right_start, _) in zip(ordered, ordered[1:], strict=False):
        if not _GRAMMATICAL_GAP.fullmatch(source[left_end:right_start]):
            raise SourceCohortCoverageError("Unreviewed member between finite source quotes")
    if _PREFIX_LIST_MEMBER.search(source[: ordered[0][0]]):
        raise SourceCohortCoverageError("Unreviewed member before finite source quotes")
    trailing = source[ordered[-1][1] :]
    if _SUFFIX_LIST_MEMBER.match(trailing):
        raise SourceCohortCoverageError("Unreviewed member after finite source quotes")
    # Permit a bounded modifier of the SAME source predicate (place/time),
    # never an extra clause or an additional list member. A non-name lexical
    # continuation still needs the independently reviewed Core source group.
    # Exclude "con"/"with": those can add an unquoted Person in lowercase.
    modifier = r"(?:hoy|ayer|mañana|today|yesterday|tomorrow)?\s*(?:en|por|durante|in|at|on|during|dans|à|pendant)\s+[^;.!?\n]+"
    stripped = trailing.strip()
    if stripped and re.fullmatch(r"[.!?;,]+", stripped) is None:
        core = stripped.rstrip(".!?").strip()
        # Place/time modifiers cannot smuggle a second finite predicate by
        # using a relative or subordinating clause ("donde conocí a marta",
        # "where I met bob", "pendant que ..."). Veto only: no inference.
        subordinate_clause = re.search(
            r"\b(?:donde|adonde|mientras|cuando|where|while|when|où|lorsque|quand)\b",
            core,
            flags=re.IGNORECASE,
        )
        if (
            not re.fullmatch(modifier, core, flags=re.IGNORECASE)
            or subordinate_clause
            or re.search(
                r"\b(?:y|et|and|e|con|with|avec)\b\s+(?:a\s+)?[^\W\d_]+",
                core,
                flags=re.IGNORECASE,
            )
        ):
            raise SourceCohortCoverageError("Unreviewed finite source trailing clause")
    leading = source[: ordered[0][0]]
    if re.search(r"[.;!?]\s*\S", leading):
        raise SourceCohortCoverageError("Unreviewed finite source preceding clause")
    for token in _CAPITALIZED.finditer(source):
        start, end = token.span()
        # Sentence-initial capitals are grammar, not independent referents.
        preceding = source[:start].rstrip()
        if not preceding or preceding[-1] in ".!?":
            continue
        if not any(lo <= start and end <= hi for lo, hi in spans):
            raise SourceCohortCoverageError("Unreviewed capitalized source referent")
