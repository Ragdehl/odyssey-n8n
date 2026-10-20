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
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    CanonicalReferenceEvidence,
    DependentReferenceGuard,
    UnitStatus,
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
    # Select by the reviewed antecedent occurrence, never by result order or
    # the last referenced identity. A direct newly created Note has its own
    # Writer receipt, separate from ordinary materialized backlink proofs.
    action_proofs = tuple(
        proof
        for action in predecessor.action_results
        if action.status is ActionStatus.COMPLETED
        for proof in (
            *action.canonical_reference_evidence,
            *action.canonical_direct_target_evidence,
        )
        if proof.action_index == action.action_index
        and proof.source_mention == proof.canonical_name
        and len(
            re.findall(
                r"(?<!\w)" + re.escape(proof.source_mention) + r"(?!\w)",
                antecedent_quote,
            )
        )
        == 1
    )
    # An explicit reviewed dependent name can select one of several Core-created
    # people. An anaphoric mention cannot: with multiple receipts its identity
    # is not proven by the source alone, so fail closed.
    explicitly_named = tuple(
        proof for proof in action_proofs if proof.canonical_name == exact_dependent_mention
    )
    if explicitly_named:
        action_proofs = explicitly_named
    # Several independently persisted Core receipts can prove the same
    # canonical identity (e.g. direct Person CREATE plus a Day backlink).
    # Identity uniqueness, not receipt-count uniqueness, is the boundary.
    if (
        not action_proofs
        or any(not isinstance(p, CanonicalReferenceEvidence) for p in action_proofs)
        or len({p.stable_note_id for p in action_proofs}) != 1
        or any(not _dependent_evidence_is_current(p, repository, schema) for p in action_proofs)
    ):
        raise SourceBoundDependencyError("Predecessor has no unique materialized Core fact")
    evidence = next((p for p in action_proofs if p.source_reference_index == -1), action_proofs[0])
    if (
        evidence.source_note_id not in predecessor.affected_stable_note_ids
        or evidence.source_reference_index < -1
        or (
            evidence.source_reference_index >= 0
            and predecessor.canonical_reference_evidence.count(evidence) != 1
        )
        or (
            evidence.source_reference_index == -1
            and not (
                evidence.source_note_id == evidence.stable_note_id
                and evidence.source_content_guard == evidence.canonical_content_guard
                and any(
                    proof == evidence
                    and any(
                        unit.unit_index == evidence.source_unit_index
                        and unit.status is UnitStatus.SUCCEEDED
                        and unit.operation == "CREATED"
                        and unit.stable_note_id == evidence.stable_note_id
                        for unit in action.unit_results
                    )
                    for action in predecessor.action_results
                    for proof in action.canonical_direct_target_evidence
                )
            )
        )
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
