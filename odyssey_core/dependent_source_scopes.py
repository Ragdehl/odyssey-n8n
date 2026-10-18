"""E2 exact-original-source proof for one Core→Tasks dependent handoff.

Only validates an untrusted proposal's byte ownership. A separate pair of
semantic model reviews, Core canonical link provenance and Task interpretation
must ALL agree before any dependent mutation is permissible.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .source_provenance import SourceEvidenceError, anchor_original_partition


class DependentSourceScopesError(ValueError):
    """The proposed handoff lacks complete, exact source provenance."""


@dataclass(frozen=True, slots=True)
class DependentSourceScopes:
    original: str
    antecedent: str
    dependent: str
    mention: str


def verify_dependent_source_scopes(
    original: str, proposal: Mapping[str, object]
) -> DependentSourceScopes:
    """Return literal source spans, never synthesized Task names or identities."""
    if (
        not isinstance(original, str)
        or not original.strip()
        or len(original) > 4096
        or not isinstance(proposal, Mapping)
        or set(proposal)
        != {"full_source_quote", "antecedent_quote", "dependent_quote", "dependent_mention"}
    ):
        raise DependentSourceScopesError("Unverified dependent-source proposal")
    before = proposal["antecedent_quote"]
    after = proposal["dependent_quote"]
    mention = proposal["dependent_mention"]
    if (
        proposal["full_source_quote"] != original
        or not isinstance(before, str)
        or not isinstance(after, str)
        or not isinstance(mention, str)
        or not before.strip()
        or not after.strip()
        or not mention.strip()
        or len(mention) > 120
        or after.strip().count(mention) != 1
    ):
        raise DependentSourceScopesError("Changed or ambiguous dependent source")
    try:
        anchor_original_partition(original, (before, after))
    except SourceEvidenceError as error:
        raise DependentSourceScopesError("Changed or ambiguous dependent source") from error
    return DependentSourceScopes(original, before, after, mention)
