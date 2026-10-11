"""Transfer only verified Core event content, never the former actor identity."""

from __future__ import annotations

from dataclasses import dataclass, field

from odyssey_core.application import (
    ApplicationStatus,
    UnitStatus,
    _current_canonical_reference,
)
from odyssey_core.candidate_context import CoreCandidateContext
from odyssey_core.candidate_fact_readback import CandidateFactReadback
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.scoped_event_evidence import (
    CoreVerifiedInheritedEvent,
    EventRole,
)
from odyssey_core.scoped_subject_evidence import original_digest


@dataclass(slots=True)
class ScopedCoreEventHandoff:
    original: str
    _proved: dict[int, CoreVerifiedInheritedEvent] = field(default_factory=dict)

    def remember(
        self,
        *,
        context: CoreCandidateContext,
        plan: RequestPlan,
        result,
        readback: CandidateFactReadback,
        repository,
        schema: dict,
        start: int,
        end: int,
        route_index: int,
    ) -> None:
        """No inferred event: require a single exact Core-authored purchase."""
        if (
            context.source != self.original[start:end]
            or result.status is not ApplicationStatus.COMPLETED
            or type(route_index) is not int
            or route_index < 0
            or len(context.candidates) != 1
            or len(plan.actions) != 1
            or not isinstance(plan.actions[0], WriteAction)
            or len(plan.actions[0].units) != 1
            or len(result.action_results) != 1
        ):
            return
        candidate = context.candidates[0]
        if (
            candidate.kind != "purchase_item"
            or candidate.state != "candidate"
            or candidate.inherits
            or context.source_provenance
            or any(
                role.role
                in {"condition", "polarity", "reference", "replacement", "modality", "date", "time"}
                for role in candidate.roles
            )
        ):
            return
        subjects = [r.span for r in candidate.roles if r.role == "subject"]
        if len(subjects) != 1 or subjects[0] not in candidate.anchors:
            return
        local_roles = tuple(
            EventRole(r.role, r.span.text, start + r.span.start, start + r.span.end)
            for r in candidate.roles
            if r.role in {"predicate", "object", "transaction"}
        )
        if {r.role for r in local_roles} != {"predicate", "object", "transaction"} or len(
            local_roles
        ) != 3:
            return
        unit = plan.actions[0].units[0]
        actual = result.action_results[0]
        successes = [
            r
            for r in actual.unit_results
            if r.unit_index == 0 and r.status is UnitStatus.SUCCEEDED and r.stable_note_id
        ]
        verified = [
            r
            for r in readback.persisted_facts
            if r.action_index == 0 and r.unit_index == 0 and r.status == "verified_in_markdown"
        ]
        if (
            unit.intent != "record"
            or unit.target.query != subjects[0].text
            or unit.target.entity != subjects[0].text
            or unit.target.type != "person"
            or unit.reference_lookup_only
            or unit.references
            or unit.properties
            or unit.tag_changes
            or unit.fact_temporal_anchors
            or unit.force_create
            or len(unit.facts) != 1
            or len(successes) != 1
            or len(verified) != 1
            or verified[0].note_id != successes[0].stable_note_id
        ):
            return
        note_id = successes[0].stable_note_id
        canonical = _current_canonical_reference(repository, schema, note_id)
        if canonical is None or canonical[:2] != ("person", subjects[0].text):
            return
        proof = CoreVerifiedInheritedEvent(
            original_digest(self.original),
            route_index,
            local_roles,
            unit.facts[0],
            note_id,
            canonical[1],
            canonical[0],
            canonical[2],
        )
        try:
            proof.validate()
        except ValueError:
            return
        self._proved[route_index] = proof

    def inherit(
        self,
        *,
        context: CoreCandidateContext,
        route_index: int,
        start: int,
        end: int,
        repository,
        schema: dict,
    ) -> CoreVerifiedInheritedEvent | None:
        """Bind all external verb/object/transaction roles to one predecessor."""
        if context.source != self.original[start:end]:
            raise ValueError("Inherited event route source changed")
        required = tuple(
            r for r in context.source_provenance if r.role in {"predicate", "object", "transaction"}
        )
        if not required:
            return None
        if (
            len(context.candidates) != 1
            or len(required) != 3
            or {r.role for r in required} != {"predicate", "object", "transaction"}
        ):
            raise ValueError("Inherited event lacks one exact source-role set")
        viable = []
        for index, proof in self._proved.items():
            expected = {(r.role, r.text, r.original_start, r.original_end) for r in proof.roles}
            actual = {(r.role, r.text, r.original_start, r.original_end) for r in required}
            if (
                expected == actual
                and all(r.original_sha256 == proof.original_sha256 for r in required)
                and index < route_index
                and all(role.original_end <= start for role in proof.roles)
            ):
                viable.append(proof)
        if len(viable) != 1:
            raise ValueError("Inherited event lacks one Core-readback verified predecessor")
        proof = viable[0]
        proof.validate()
        current = _current_canonical_reference(repository, schema, proof.predecessor_note_id)
        if current != (
            proof.predecessor_type,
            proof.predecessor_name,
            proof.predecessor_content_guard,
        ):
            raise ValueError("Inherited event predecessor canonical Markdown changed")
        return proof
