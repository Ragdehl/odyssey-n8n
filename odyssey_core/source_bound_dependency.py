"""E2: actor-scope-private, read-only provenance for a dependent source mention.

This does NOT resolve an anaphor, choose a Task or authorize a write. It can
carry one Core-authored canonical reference for a later independently reviewed
source scope. The actual consumer MUST use Core's DependentReferenceGuard at
preflight and a domain-specific resolution of the requested operation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .application import (
    ApplicationResult,
    ApplicationStatus,
    CanonicalReferenceEvidence,
    DependentReferenceGuard,
    _dependent_evidence_is_current,
)
from .storage import VaultRepository


class SourceBoundDependencyError(ValueError):
    """No uniquely current source-bound canonical predecessor proof exists."""


@dataclass(frozen=True, slots=True, repr=False)
class SourceBoundDependency:
    """Internal-only proof; caller must not serialize its canonical target."""

    source_quote: str
    dependent_quote: str
    mention: str
    evidence: CanonicalReferenceEvidence

    def core_write_guard(self) -> DependentReferenceGuard:
        """Use the EXISTING E2/E3 Core time-of-use validator, never bypass it."""
        return DependentReferenceGuard(self.mention, self.evidence)


def prove_source_bound_dependency(
    *,
    complete_original_source: str,
    antecedent_quote: str,
    dependent_quote: str,
    exact_dependent_mention: str,
    predecessor: ApplicationResult,
    repository: VaultRepository,
    schema: dict[str, Any],
) -> SourceBoundDependency:
    """Require exactly one persisted Core reference and two exact source spans.

    The dependent identity relation is NOT inferred from this lexical proof.
    A separate semantic reviewer must establish the pronoun/antecedent link;
    callers must never skip that reviewer or the subsequent Core guard.
    """
    if (
        not isinstance(complete_original_source, str)
        or not complete_original_source.strip()
        or len(complete_original_source) > 4096
        or not isinstance(antecedent_quote, str)
        or not antecedent_quote.strip()
        or not isinstance(dependent_quote, str)
        or not dependent_quote.strip()
        or not isinstance(exact_dependent_mention, str)
        or not exact_dependent_mention.strip()
        or len(exact_dependent_mention) > 120
        or not isinstance(predecessor, ApplicationResult)
        or not isinstance(repository, VaultRepository)
        or not isinstance(schema, dict)
    ):
        raise SourceBoundDependencyError("Malformed dependent Core provenance")
    # Preserve exact source order while allowing boundary whitespace exactly
    # once. No synthetic subject/name rewriting or dropped conjunction.
    if not complete_original_source.startswith(antecedent_quote):
        raise SourceBoundDependencyError("Predecessor is not the first source span")
    tail = complete_original_source[len(antecedent_quote) :]
    if tail != dependent_quote:
        raise SourceBoundDependencyError("Dependent source has changed or is incomplete")
    if predecessor.status is not ApplicationStatus.COMPLETED:
        raise SourceBoundDependencyError("A pending predecessor has no handoff authority")
    proofs = predecessor.canonical_reference_evidence
    if len(proofs) != 1 or not isinstance(proofs[0], CanonicalReferenceEvidence):
        raise SourceBoundDependencyError("Exactly one Core-proven antecedent required")
    evidence = proofs[0]
    # The private carrier must ALSO agree with the actual completed Core
    # action and materialized source Note, not merely an attached tuple of
    # CoreReferenceEvidence values from an arbitrary earlier response.
    action_proofs = tuple(
        proof
        for action in predecessor.action_results
        for proof in action.canonical_reference_evidence
    )
    if (
        len(action_proofs) != 1
        or action_proofs[0] != evidence
        or evidence.source_note_id not in predecessor.affected_stable_note_ids
    ):
        raise SourceBoundDependencyError("Predecessor has no unique materialized Core fact")
    if (
        not evidence.source_mention
        or not evidence.canonical_name
        or evidence.source_mention != evidence.canonical_name
        or len(
            re.findall(
                r"(?<!\w)" + re.escape(evidence.source_mention) + r"(?!\w)", antecedent_quote
            )
        )
        != 1
        or len(
            re.findall(
                r"(?<!\w)" + re.escape(exact_dependent_mention) + r"(?!\w)",
                dependent_quote,
                flags=re.IGNORECASE,
            )
        )
        != 1
    ):
        raise SourceBoundDependencyError("Antecedent or dependent mention is not unique")
    if not _dependent_evidence_is_current(evidence, repository, schema):
        raise SourceBoundDependencyError("Canonical source or target has changed")
    return SourceBoundDependency(
        antecedent_quote, dependent_quote, exact_dependent_mention, evidence
    )
