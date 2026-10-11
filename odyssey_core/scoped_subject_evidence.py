"""Current Core-verified subject for an elliptical, separately routed fragment.

The Router supplies only exact source span provenance; after Core actually
writes the predecessor fact, the runtime may add this bounded typed evidence.
The stable identity and canonical content guard remain private. A separate
Core prewrite guard rechecks them against the selected write target.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CoreVerifiedInheritedSubject:
    source_text: str
    original_start: int
    original_end: int
    original_sha256: str
    predecessor_route_index: int
    canonical_note_id: str
    canonical_name: str
    canonical_type: str
    canonical_content_guard: str
    predecessor_fact: str

    def validate(self) -> None:
        if (
            not isinstance(self.source_text, str)
            or not self.source_text.strip()
            or len(self.source_text) > 400
            or type(self.original_start) is not int
            or type(self.original_end) is not int
            or self.original_start < 0
            or self.original_end - self.original_start != len(self.source_text)
            or type(self.predecessor_route_index) is not int
            or self.predecessor_route_index < 0
            or not isinstance(self.original_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.original_sha256) is None
            or not isinstance(self.canonical_note_id, str)
            or not self.canonical_note_id.strip()
            or not isinstance(self.canonical_name, str)
            or not self.canonical_name.strip()
            or not isinstance(self.canonical_type, str)
            or not self.canonical_type.strip()
            or not isinstance(self.canonical_content_guard, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.canonical_content_guard)
            or not isinstance(self.predecessor_fact, str)
            or not self.predecessor_fact.strip()
            or len(self.predecessor_fact) > 512
        ):
            raise ValueError("Inherited subject is not a bounded Core proof")

    def prompt_payload(self) -> dict[str, object]:
        self.validate()
        # The canonical Note ID/contents digest never go to the LLM;
        # they are checked independently at the write preflight boundary.
        return {
            "source_subject": self.source_text,
            "original_start": self.original_start,
            "original_end": self.original_end,
            "original_sha256": self.original_sha256,
            "canonical_name": self.canonical_name,
            "canonical_type": self.canonical_type,
            "verified_predecessor_fact": self.predecessor_fact,
            "provenance": "core_persisted_and_readback_verified",
            "scope": "context_only_not_mutation_authority",
        }


@dataclass(frozen=True, slots=True)
class CoreInheritedSubjectWriteGuard:
    subject: CoreVerifiedInheritedSubject

    def validate_request_plan(self, plan: object) -> None:
        from odyssey_core.application import WritePreflightGuardError
        from odyssey_core.request_planning import RequestPlan, WriteAction

        if not isinstance(plan, RequestPlan):
            raise WritePreflightGuardError("INHERITED_SUBJECT_PLAN_INVALID")
        if (
            len(plan.actions) != 1
            or not isinstance(plan.actions[0], WriteAction)
            or len(plan.actions[0].units) != 1
            or plan.actions[0].units[0].reference_lookup_only
            or len(plan.actions[0].units[0].facts) != 1
        ):
            raise WritePreflightGuardError("INHERITED_SUBJECT_ONE_ATOMIC_WRITE_REQUIRED")

    def __call__(self, action, preflight, repository, schema) -> None:
        from odyssey_core.application import WritePreflightGuardError, _current_canonical_reference

        self.subject.validate()
        current = _current_canonical_reference(repository, schema, self.subject.canonical_note_id)
        if current != (
            self.subject.canonical_type,
            self.subject.canonical_name,
            self.subject.canonical_content_guard,
        ):
            raise WritePreflightGuardError("INHERITED_SUBJECT_CANONICAL_STALE")
        if len(preflight) != len(action.units):
            raise WritePreflightGuardError("INHERITED_SUBJECT_PREFLIGHT_INVALID")
        for unit, result in zip(action.units, preflight, strict=True):
            if (
                unit.reference_lookup_only
                or not unit.facts
                or result.stable_id != self.subject.canonical_note_id
                or result.canonical_name != self.subject.canonical_name
            ):
                raise WritePreflightGuardError("INHERITED_SUBJECT_WRONG_TARGET")


def original_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()
