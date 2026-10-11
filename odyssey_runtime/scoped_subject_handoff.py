"""Core-owned inherited grammatical subject, from a verified earlier write.

A Router source subject cannot identify a canonical Note. Only a prior
successful ordinary Core WRITE with independently checked Markdown readback
may supply the stable identity for a later elliptical route. Otherwise the
dependent claim stays pending; source-predicate inheritance never guesses a
target or creates a task.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from odyssey_core.application import (
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    UnitStatus,
    _current_canonical_reference,
)
from odyssey_core.candidate_context import CoreCandidateContext
from odyssey_core.candidate_fact_readback import CandidateFactReadback
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.scoped_subject_evidence import (
    CoreVerifiedInheritedSubject,
    original_digest,
)
from odyssey_core.storage import VaultRepository


@dataclass(slots=True)
class ScopedCoreSubjectHandoff:
    original: str
    _proved: dict[tuple[int, int], CoreVerifiedInheritedSubject] = field(default_factory=dict)

    def remember(
        self,
        *,
        context: CoreCandidateContext,
        plan: RequestPlan,
        result: ApplicationResult,
        readback: CandidateFactReadback,
        repository: VaultRepository,
        schema: dict,
        start: int,
        end: int,
        route_index: int,
    ) -> None:
        """Remember only one unambiguous already-written subject and its fact."""
        if (
            not isinstance(context, CoreCandidateContext)
            or context.source != self.original[start:end]
            or result.status is not ApplicationStatus.COMPLETED
            or type(route_index) is not int
            or route_index < 0
            or not isinstance(readback, CandidateFactReadback)
        ):
            return
        subjects = [
            role.span
            for candidate in context.candidates
            for role in candidate.roles
            if role.role == "subject"
        ]
        if len(subjects) != 1:
            return
        subject = subjects[0]
        if not any(
            candidate.state == "candidate" and subject in candidate.anchors
            for candidate in context.candidates
        ):
            return
        if not readback.persisted_facts or any(
            f.status != "verified_in_markdown" for f in readback.persisted_facts
        ):
            return
        matches = []
        for action_index, action in enumerate(plan.actions):
            if not isinstance(action, WriteAction):
                continue
            if action_index >= len(result.action_results):
                return
            outcome = result.action_results[action_index]
            if outcome.status is not ActionStatus.COMPLETED:
                return
            for unit_index, unit in enumerate(action.units):
                if unit.reference_lookup_only or not unit.facts:
                    continue
                if unit.target.query != subject.text:
                    continue
                confirmations = [
                    r
                    for r in outcome.unit_results
                    if r.unit_index == unit_index
                    and r.status is UnitStatus.SUCCEEDED
                    and r.stable_note_id
                ]
                receipts = [
                    f
                    for f in readback.persisted_facts
                    if f.action_index == action_index
                    and f.unit_index == unit_index
                    and f.status == "verified_in_markdown"
                ]
                if len(confirmations) != 1 or len(receipts) != len(unit.facts):
                    return
                if len(unit.facts) != 1:
                    return
                if any(f.note_id != confirmations[0].stable_note_id for f in receipts):
                    return
                matches.append((confirmations[0].stable_note_id, unit.facts[0]))
        if len(matches) != 1:
            return
        stable_id, fact = matches[0]
        canonical = _current_canonical_reference(repository, schema, stable_id)
        if canonical is None:
            return
        note_type, name, guard = canonical
        if not any(
            unit.target.entity == name
            for action in plan.actions
            if isinstance(action, WriteAction)
            for unit in action.units
            if unit.target.query == subject.text
        ) or not (
            subject.text.casefold() == name.casefold()
            or subject.text.casefold().endswith(" " + name.casefold())
        ):
            return
        proof = CoreVerifiedInheritedSubject(
            subject.text,
            start + subject.start,
            start + subject.end,
            original_digest(self.original),
            route_index,
            stable_id,
            name,
            note_type,
            guard,
            fact,
        )
        proof.validate()
        self._proved[(proof.original_start, proof.original_end)] = proof

    def inherit(
        self,
        *,
        context: CoreCandidateContext,
        route_index: int,
        start: int,
        end: int,
        repository: VaultRepository,
        schema: dict,
    ) -> CoreVerifiedInheritedSubject | None:
        """One inherited subject at most, with a fresh canonical Markdown guard."""
        from odyssey_core.application import _current_canonical_reference

        if context.source != self.original[start:end]:
            raise ValueError("Inherited subject route source changed")
        subjects = [r for r in context.source_provenance if r.role == "subject"]
        if not subjects:
            return None
        if len({(r.original_start, r.original_end) for r in subjects}) != 1:
            raise ValueError("Multiple inherited subjects lack unique canonical provenance")
        role = subjects[0]
        proof = self._proved.get((role.original_start, role.original_end))
        if (
            proof is None
            or proof.source_text != role.text
            or proof.original_sha256 != role.original_sha256
            or not proof.predecessor_route_index < route_index
            or proof.original_end > start
        ):
            raise ValueError("Inherited subject lacks a completed Core predecessor")
        proof.validate()
        canonical = _current_canonical_reference(repository, schema, proof.canonical_note_id)
        if canonical != (
            proof.canonical_type,
            proof.canonical_name,
            proof.canonical_content_guard,
        ):
            raise ValueError("Inherited subject Core identity is stale")
        return proof
