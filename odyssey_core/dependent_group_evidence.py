"""E2 per-edge canonical evidence for a reviewed N:M source graph.

This read-only pre-consumer boundary does NOT run a dependent operation.
Each exact antecedent mention must match a Core-authored materialized link;
a reviewer-proposed graph and its ordinals never select a stable Note ID.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
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
from .dependent_group_graph import ReviewedSourceGraph
from .dependent_reference_form import referenced_finite_cardinality, supported_anaphoric_form
from .storage import VaultRepository


class CanonicalGroupEvidenceError(ValueError):
    """One N:M predecessor edge lacks an exact, uniquely current Core proof."""


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalGroupEdge:
    predecessor_index: int
    consumer_index: int
    antecedent_mention: str
    dependent_mention: str
    evidence: CanonicalReferenceEvidence

    def require_current(self, repository: VaultRepository, schema: dict[str, Any]) -> str:
        """Refresh-check BOTH physical Notes at the dependent consumer boundary."""
        if not _dependent_evidence_is_current(self.evidence, repository, schema):
            raise CanonicalGroupEvidenceError("Canonical N:M edge is stale or missing")
        return self.evidence.stable_note_id

    def core_write_guard(self) -> DependentReferenceGuard:
        """Re-use Core's preflight guard; this carrier never grants write authority."""
        return DependentReferenceGuard(self.dependent_mention, self.evidence)


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalGroupHandoff:
    consumer_index: int
    edges: tuple[CanonicalGroupEdge, ...]

    def require_all_current(
        self, repository: VaultRepository, schema: dict[str, Any]
    ) -> tuple[str, ...]:
        """Fail atomically if ANY predecessor changes, with no partial targets."""
        return tuple(edge.require_current(repository, schema) for edge in self.edges)


def _unique_source_occurrence(text: str, mention: str) -> bool:
    """Match a full original-source expression, not a substring of another name."""
    return (
        len(re.findall(r"(?<!\w)" + re.escape(mention) + r"(?!\w)", text, flags=re.IGNORECASE)) == 1
    )


def _require_complete_person_cohort(
    edges: tuple[CanonicalGroupEdge, ...],
    predecessors: Mapping[int, ApplicationResult],
) -> None:
    """A finite 'los dos' refers to EVERY physical Person in its Core cohort.

    No subset may be selected from a larger group merely because GPT omitted
    an edge. This check supplements, never replaces, individual E2 receipts.
    """
    # Check the source's finite cardinal even with ONE reviewed edge. A one-
    # edge graph is precisely the unsafe subset that older validation skipped.
    if not any(
        edge.evidence.note_type == "person"
        and referenced_finite_cardinality(edge.dependent_mention)
        for edge in edges
    ):
        return
    mentions = {edge.dependent_mention for edge in edges}
    if len(mentions) != 1 or any(edge.evidence.note_type != "person" for edge in edges):
        raise CanonicalGroupEvidenceError("Finite Person cohort has mixed or incomplete edges")
    cardinality = referenced_finite_cardinality(next(iter(mentions)))
    if cardinality is None or len(edges) != cardinality:
        raise CanonicalGroupEvidenceError("Finite Person cohort cardinality is not complete")
    selected = {edge.evidence.stable_note_id for edge in edges}
    all_people = {
        proof.stable_note_id
        for parent in {edge.predecessor_index for edge in edges}
        for result in (predecessors[parent],)
        for action in result.action_results
        if action.status is ActionStatus.COMPLETED
        for proof in (
            *action.canonical_reference_evidence,
            *action.canonical_direct_target_evidence,
        )
        if proof.note_type == "person"
        and proof.source_mention.casefold() == proof.canonical_name.casefold()
    }
    if len(selected) != cardinality or selected != all_people:
        raise CanonicalGroupEvidenceError(
            "Plural Person selection omits a physical Core antecedent"
        )


def prove_canonical_group_handoff(
    *,
    graph: ReviewedSourceGraph,
    consumer_index: int,
    predecessors: Mapping[int, ApplicationResult],
    repository: VaultRepository,
    schema: dict[str, Any],
) -> CanonicalGroupHandoff:
    """Map EACH reviewed source edge to its unique physical Core reference.

    Unlike 1:1 provenance, one predecessor result MAY contain several Core
    links: the reviewed *antecedent_mention* selects one occurrence only when
    exactly one action-bound physical Core proof matches it. Different edges
    may reuse a single predecessor proof, or join proofs from many results.
    No result's last reference is ever treated as a default identity.
    """
    if (
        not isinstance(graph, ReviewedSourceGraph)
        or not isinstance(consumer_index, int)
        or isinstance(consumer_index, bool)
        or not 0 <= consumer_index < len(graph.groups)
        or not isinstance(predecessors, Mapping)
        or not isinstance(repository, VaultRepository)
        or not isinstance(schema, dict)
    ):
        raise CanonicalGroupEvidenceError("Invalid N:M proof boundary")
    consumer = graph.groups[consumer_index]
    if not consumer.dependencies:
        raise CanonicalGroupEvidenceError("Consumer has no reviewed dependency")
    edges: list[CanonicalGroupEdge] = []
    for dependency in consumer.dependencies:
        parent = dependency.predecessor_index
        if parent >= consumer_index or graph.groups[parent].capability != "core":
            # Other app/Task provenance requires its own Core-authored proof;
            # a Tasks result cannot be treated as Core reference evidence.
            raise CanonicalGroupEvidenceError("Non-Core predecessor has no link authority")
        result = predecessors.get(parent)
        if (
            not isinstance(result, ApplicationResult)
            or result.status is not ApplicationStatus.COMPLETED
        ):
            raise CanonicalGroupEvidenceError("Predecessor was not completed by Core")
        if any(
            not isinstance(proof, CanonicalReferenceEvidence)
            for action in result.action_results
            for proof in (
                *action.canonical_reference_evidence,
                *action.canonical_direct_target_evidence,
            )
        ) or any(
            not isinstance(proof, CanonicalReferenceEvidence)
            for proof in result.canonical_reference_evidence
        ):
            raise CanonicalGroupEvidenceError("Malformed Core receipt carrier")
        antecedent = graph.groups[parent].source
        reviewed_core_source = antecedent.strip()
        if result.core_source_digest != sha256(reviewed_core_source.encode("utf-8")).hexdigest():
            raise CanonicalGroupEvidenceError("Core result belongs to a different source group")
        if not _unique_source_occurrence(
            antecedent, dependency.antecedent_mention
        ) or not _unique_source_occurrence(consumer.source, dependency.mention):
            raise CanonicalGroupEvidenceError("Source occurrence is missing or ambiguous")
        proofs = tuple(
            proof
            for action in result.action_results
            if action.status is ActionStatus.COMPLETED
            for proof in (
                *action.canonical_reference_evidence,
                *action.canonical_direct_target_evidence,
            )
            if isinstance(proof, CanonicalReferenceEvidence)
            and proof.source_mention.casefold() == dependency.antecedent_mention.casefold()
            and proof.canonical_name.casefold() == dependency.antecedent_mention.casefold()
        )
        # A result's top-level proof is optional (may be absent when multiple
        # actions linked different targets), but if present it must agree with
        # the per-action proof. Never trust an uncorroborated top-level carrier.
        duplicate_carriers = len(result.canonical_reference_evidence) != len(
            set(result.canonical_reference_evidence)
        )
        if (
            not proofs
            or len({proof.stable_note_id for proof in proofs}) != 1
            or len(proofs) != len(set(proofs))
            or duplicate_carriers
            or (
                result.canonical_reference_evidence
                and any(
                    proof
                    not in tuple(
                        p
                        for action in result.action_results
                        for p in action.canonical_reference_evidence
                    )
                    for proof in result.canonical_reference_evidence
                )
            )
        ):
            raise CanonicalGroupEvidenceError("No unique Core-materialized reference occurrence")
        # Multiple receipts may refer to one canonical identity; every receipt
        # must still be current, not just the selected representative.
        if any(
            not materialized_core_receipt(proof, action, result, repository, schema)
            for action in result.action_results
            if action.status is ActionStatus.COMPLETED
            for proof in (
                *action.canonical_reference_evidence,
                *action.canonical_direct_target_evidence,
            )
            if proof in proofs
        ):
            raise CanonicalGroupEvidenceError("Predecessor receipt lacks materialized provenance")
        proof = next((p for p in proofs if p.source_reference_index == -1), proofs[0])
        # A reviewed graph edge names its preferred antecedent, but that
        # model-generated choice cannot disambiguate a pronoun between two
        # independently materialized Persons in a single-target edge. Multi-
        # edge N:M references to several targets retain their prior semantics.
        # A literal
        # canonical name may select one; a name of ANOTHER materialized target
        # must never silently authorize this one. Apply the same guard for
        # Persons and Tasks, without a fixed pronoun/name vocabulary.
        candidates = tuple(
            receipt
            for action in result.action_results
            for receipt in (
                *action.canonical_reference_evidence,
                *action.canonical_direct_target_evidence,
            )
            if isinstance(receipt, CanonicalReferenceEvidence)
            and receipt.note_type == proof.note_type
            and receipt.source_mention.casefold() == receipt.canonical_name.casefold()
        )
        explicitly_named_ids = {
            receipt.stable_note_id
            for receipt in candidates
            if receipt.canonical_name.casefold() == dependency.mention.casefold()
        }
        if (explicitly_named_ids and proof.stable_note_id not in explicitly_named_ids) or (
            not explicitly_named_ids
            and (
                not supported_anaphoric_form(dependency.mention)
                or (
                    proof.note_type == "person"
                    and len(consumer.dependencies) == 1
                    and len({receipt.stable_note_id for receipt in candidates}) != 1
                )
            )
        ):
            raise CanonicalGroupEvidenceError(
                "Dependent mention does not uniquely identify this canonical target"
            )
        edges.append(
            CanonicalGroupEdge(
                parent, consumer_index, dependency.antecedent_mention, dependency.mention, proof
            )
        )
    _require_complete_person_cohort(tuple(edges), predecessors)
    # Recheck everything at the very end: an external editor may modify the
    # first Note while we inspect later edges. This is not a multiwriter lock;
    # each real consumer must also call require_all_current immediately before
    # Core's existing write preflight and E3 CAS.
    handoff = CanonicalGroupHandoff(consumer_index, tuple(edges))
    handoff.require_all_current(repository, schema)
    return handoff
