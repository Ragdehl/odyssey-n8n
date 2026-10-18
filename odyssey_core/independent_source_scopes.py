"""E2 source-preserving partition of demonstrably independent app operations.

This is a source-integrity validator, NOT a semantic or mutation authority.
The independent Core/app semantic reviewer and Core Writer retain authority.
No punctuation, language, specific name or sample-message heuristics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .source_provenance import SourceEvidenceError, anchor_original_partition


class IndependentSourceScopesError(ValueError):
    """Reject missing, reordered, or overlapping full-source semantic evidence."""


@dataclass(frozen=True, slots=True)
class IndependentSourceScope:
    capability: str
    source: str
    index: int


def verify_independent_source_scopes(
    source: str,
    proposal: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    permitted_capabilities: frozenset[str],
) -> tuple[IndependentSourceScope, ...]:
    """Return bounded ordered exact-source spans after independent full review.

    Every original byte has exactly one owner, including whitespace and
    punctuation. Parsing *cannot* recover the meaning of a shared subject,
    antecedent or date, so the independent model must disallow those splits;
    normal Core and app reviewers must still recheck each resulting source.
    """
    if not isinstance(source, str) or not source.strip() or len(source) > 4096:
        raise IndependentSourceScopesError("Invalid original source")
    if not isinstance(proposal, Mapping) or not isinstance(review, Mapping):
        raise IndependentSourceScopesError("Missing two distinct source attestations")
    if (
        proposal.get("full_source_quote") != source
        or review.get("full_source_quote") != source
        or review.get("complete") is not True
        or review.get("independent") is not True
        or review.get("no_cross_scope_referents") is not True
    ):
        raise IndependentSourceScopesError("Full source independence not proven")
    parts = proposal.get("parts")
    if not isinstance(parts, list) or not 2 <= len(parts) <= 16:
        raise IndependentSourceScopesError("Bounded independent source parts required")
    if permitted_capabilities != frozenset({"core", "tasks"}):
        raise IndependentSourceScopesError("Unsupported independent application set")
    if any(
        not isinstance(item, Mapping) or set(item) != {"capability", "source_quote"}
        for item in parts
    ):
        raise IndependentSourceScopesError("Unexpected model-supplied source fields")
    if any(
        not isinstance(item.get("capability"), str)
        or item["capability"] not in permitted_capabilities
        for item in parts
    ):
        raise IndependentSourceScopesError("Source part has an unsupported capability")
    if {item["capability"] for item in parts} != permitted_capabilities:
        raise IndependentSourceScopesError("Source parts omit a declared capability")
    quotes = [item["source_quote"] for item in parts]
    if not all(isinstance(q, str) and q.strip() and len(q) <= 4096 for q in quotes) or not quotes:
        raise IndependentSourceScopesError("Original bytes were lost, duplicated or reordered")
    try:
        anchor_original_partition(source, quotes)
    except SourceEvidenceError as error:
        raise IndependentSourceScopesError(
            "Original bytes were lost, duplicated or reordered"
        ) from error
    return tuple(
        IndependentSourceScope(item["capability"], quote, i)
        for i, (item, quote) in enumerate(zip(parts, quotes, strict=True))
    )
