"""E2: actor-scope-private, read-only provenance for a dependent source mention.

This does NOT resolve an anaphor, choose a Task or authorize a write. It can
carry one Core-authored canonical reference for a later independently reviewed
source scope. The actual consumer MUST use Core's DependentReferenceGuard at
preflight and a domain-specific resolution of the requested operation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from .application import (
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    CanonicalReferenceEvidence,
    DependentReferenceGuard,
    _dependent_evidence_is_current,
)
from .canonical_receipt_provenance import materialized_core_receipt
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
    reviewed_core_source = antecedent_quote.strip()
    if predecessor.core_source_digest != sha256(reviewed_core_source.encode("utf-8")).hexdigest():
        raise SourceBoundDependencyError("Core result belongs to a different source span")
    if any(
        not isinstance(proof, CanonicalReferenceEvidence)
        for action in predecessor.action_results
        for proof in (
            *action.canonical_reference_evidence,
            *action.canonical_direct_target_evidence,
        )
    ) or any(
        not isinstance(proof, CanonicalReferenceEvidence)
        for proof in predecessor.canonical_reference_evidence
    ):
        raise SourceBoundDependencyError("Malformed Core receipt carrier")
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
        if proof.source_mention == proof.canonical_name
        and len(
            re.findall(
                r"(?<!\w)" + re.escape(proof.source_mention) + r"(?!\w)",
                antecedent_quote,
                flags=re.IGNORECASE,
            )
        )
        == 1
    )
    # The request-level carrier must agree with its action receipts. A single
    # link must not disappear from the top-level carrier, and a forged or
    # repeated top-level entry must never gain independent authority.
    action_links = tuple(
        proof
        for action in predecessor.action_results
        for proof in action.canonical_reference_evidence
    )
    aggregate_links = predecessor.canonical_reference_evidence
    if (
        len(aggregate_links) != len(set(aggregate_links))
        or any(proof not in action_links for proof in aggregate_links)
        or (len(action_links) == 1 and not aggregate_links)
    ):
        raise SourceBoundDependencyError("Predecessor has no unique materialized Core fact")
    # An explicit reviewed dependent name can select one of several Core-created
    # people. An anaphoric mention cannot: with multiple receipts its identity
    # is not proven by the source alone, so fail closed.
    explicitly_named = tuple(
        proof
        for proof in action_proofs
        if proof.canonical_name.casefold() == exact_dependent_mention.casefold()
    )
    if explicitly_named:
        action_proofs = explicitly_named
    elif any(word[0].isupper() for word in re.findall(r"[^\W\d_][\w-]*", exact_dependent_mention)):
        # A different explicitly capitalized name is NOT an anaphor. The
        # two model attestations cannot turn an unmatched name into the sole
        # Core Person/Task by elimination. Fail closed for unproven aliases;
        # a later typed alias resolution may explicitly authorize one.
        raise SourceBoundDependencyError("Named dependent reference does not match Core target")
    # Several independently persisted Core receipts can prove the same
    # canonical identity (e.g. direct Person CREATE plus a Day backlink).
    # Identity uniqueness, not receipt-count uniqueness, is the boundary.
    if (
        not action_proofs
        or any(not isinstance(p, CanonicalReferenceEvidence) for p in action_proofs)
        or len({p.stable_note_id for p in action_proofs}) != 1
        or len(action_proofs) != len(set(action_proofs))
        or any(not _dependent_evidence_is_current(p, repository, schema) for p in action_proofs)
        or any(
            not materialized_core_receipt(p, action, predecessor, repository, schema)
            for action in predecessor.action_results
            if action.status is ActionStatus.COMPLETED
            for p in (
                *action.canonical_reference_evidence,
                *action.canonical_direct_target_evidence,
            )
            if p in action_proofs
        )
    ):
        if any(not _dependent_evidence_is_current(p, repository, schema) for p in action_proofs):
            raise SourceBoundDependencyError("Canonical source or target has changed")
        raise SourceBoundDependencyError("Predecessor has no unique materialized Core fact")
    evidence = next((p for p in action_proofs if p.source_reference_index == -1), action_proofs[0])
    if (
        not evidence.source_mention
        or not evidence.canonical_name
        or evidence.source_mention != evidence.canonical_name
        or len(
            re.findall(
                r"(?<!\w)" + re.escape(evidence.source_mention) + r"(?!\w)",
                antecedent_quote,
                flags=re.IGNORECASE,
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
