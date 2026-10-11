"""A narrowly verified preceding event, never a transferable subject identity.

Only a completed Core purchase fact that has physically passed canonical
Markdown readback can yield this proof. It is source-grounded in the original
message and guarded against the predecessor Note changing after observation.
"""

from __future__ import annotations

from dataclasses import dataclass


def _tokens(text: str) -> tuple[str, ...]:
    import re
    import unicodedata

    folded = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return tuple(re.findall(r"[^\W_]+", plain))


_ROLE_SET = frozenset({"predicate", "object", "transaction"})
_ADDITIVE = frozenset({"tambien", "igualmente", "aussi", "too", "also"})


@dataclass(frozen=True, slots=True)
class EventRole:
    role: str
    text: str
    original_start: int
    original_end: int

    def validate(self) -> None:
        if (
            self.role not in _ROLE_SET
            or not isinstance(self.text, str)
            or not self.text.strip()
            or type(self.original_start) is not int
            or type(self.original_end) is not int
            or self.original_start < 0
            or self.original_end - self.original_start != len(self.text)
            or len(self.text) > 300
        ):
            raise ValueError("Verified event role is malformed")


@dataclass(frozen=True, slots=True)
class CoreVerifiedInheritedEvent:
    original_sha256: str
    predecessor_route_index: int
    roles: tuple[EventRole, ...]
    verified_fact: str
    predecessor_note_id: str
    predecessor_name: str
    predecessor_type: str
    predecessor_content_guard: str

    def validate(self) -> None:
        import re

        if (
            not isinstance(self.original_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.original_sha256) is None
            or type(self.predecessor_route_index) is not int
            or self.predecessor_route_index < 0
            or not isinstance(self.roles, tuple)
            or len(self.roles) != 3
            or {x.role for x in self.roles} != _ROLE_SET
            or not all(isinstance(x, EventRole) for x in self.roles)
            or not isinstance(self.verified_fact, str)
            or not self.verified_fact.strip()
            or len(self.verified_fact) > 300
            or not isinstance(self.predecessor_note_id, str)
            or not self.predecessor_note_id.strip()
            or not isinstance(self.predecessor_name, str)
            or not self.predecessor_name.strip()
            or not isinstance(self.predecessor_type, str)
            or not self.predecessor_type.strip()
            or not isinstance(self.predecessor_content_guard, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.predecessor_content_guard) is None
        ):
            raise ValueError("Verified event handoff is malformed")
        for role in self.roles:
            role.validate()
        # Exact normalized word *sequence*, not a set: duplicate/reordered
        # event words must never be laundered by this source-only carrier.
        role_text = " ".join(
            next(role.text for role in self.roles if role.role == kind)
            for kind in ("predicate", "object", "transaction")
        )
        if _tokens(self.verified_fact) != _tokens(role_text):
            raise ValueError("Predecessor event was not an exact source-grounded purchase")

    def prompt_payload(self) -> dict[str, object]:
        self.validate()
        return {
            "event_roles": [{"role": r.role, "original_text": r.text} for r in self.roles],
            "prior_core_verified_fact": self.verified_fact,
            "scope": "read_only_context_for_new_subject_not_a_copy_or_write_order",
        }


def validate_event_target_fact(
    source: str, candidate, unit, fact: str, proof: CoreVerifiedInheritedEvent
) -> None:
    """Prove a single new-subject, positive additive event candidate and plan."""
    from odyssey_core.candidate_context import CoreCandidate
    from odyssey_core.candidate_semantic_veto import normalized_words
    from odyssey_core.request_planning import KnowledgeUnit

    proof.validate()
    if (
        not isinstance(candidate, CoreCandidate)
        or candidate.kind != "purchase_item"
        or candidate.state != "candidate"
        or not isinstance(unit, KnowledgeUnit)
        or len(unit.facts) != 1
        or len(candidate.roles) != 1
        or candidate.roles[0].role != "subject"
        or candidate.roles[0].span not in candidate.anchors
        or len(candidate.anchors) != 2
        or any(
            span != candidate.roles[0].span and not (normalized_words(span.text) & _ADDITIVE)
            for span in candidate.anchors
        )
        or not (normalized_words(source) & _ADDITIVE)
        or any(
            word in normalized_words(source)
            for word in ("no", "nunca", "not", "never", "jamais", "pas", "si", "if")
        )
        or unit.target.entity != candidate.roles[0].span.text
        or unit.target.query != candidate.roles[0].span.text
        or unit.target.type != "person"
        or unit.target.entity == proof.predecessor_name
        or unit.target.filters
        or unit.target.link_scope is not None
        or unit.target.semantic_set is not None
        or unit.target.relational_reference is not None
        or unit.target.self_target is not None
        or unit.reference_lookup_only
        or unit.force_create
        or unit.intent != "record"
        or unit.properties
        or unit.tag_changes
        or unit.references
        or unit.destination_type is not None
        or unit.fact_temporal_anchors
        or _tokens(fact) != _tokens(proof.verified_fact)
    ):
        raise ValueError("Elliptical event cannot be attributed to a verified new subject")


@dataclass(frozen=True, slots=True)
class CoreInheritedEventWriteGuard:
    proof: CoreVerifiedInheritedEvent
    source: str
    candidate: object

    def validate_request_plan(self, plan) -> None:
        from odyssey_core.application import WritePreflightGuardError
        from odyssey_core.request_planning import RequestPlan, WriteAction

        if (
            not isinstance(plan, RequestPlan)
            or len(plan.actions) != 1
            or not isinstance(plan.actions[0], WriteAction)
            or len(plan.actions[0].units) != 1
        ):
            raise WritePreflightGuardError("INHERITED_EVENT_SINGLE_WRITE_REQUIRED")
        try:
            unit = plan.actions[0].units[0]
            validate_event_target_fact(self.source, self.candidate, unit, unit.facts[0], self.proof)
        except (ValueError, IndexError, TypeError) as error:
            raise WritePreflightGuardError("INHERITED_EVENT_FACT_OR_OWNER_INVALID") from error

    def __call__(self, action, preflight, repository, schema) -> None:
        from odyssey_core.application import WritePreflightGuardError, _current_canonical_reference
        from odyssey_core.write_target import WriteTargetOutcome

        current = _current_canonical_reference(repository, schema, self.proof.predecessor_note_id)
        if current != (
            self.proof.predecessor_type,
            self.proof.predecessor_name,
            self.proof.predecessor_content_guard,
        ):
            raise WritePreflightGuardError("INHERITED_EVENT_SOURCE_STALE")
        if len(preflight) != 1 or len(action.units) != 1:
            raise WritePreflightGuardError("INHERITED_EVENT_TARGET_CARDINALITY")
        target = preflight[0]
        local_subject = self.candidate.roles[0].span.text
        if (
            target.outcome is not WriteTargetOutcome.UPDATE
            or not target.stable_id
            or target.stable_id == self.proof.predecessor_note_id
            or target.canonical_name != local_subject
            or _current_canonical_reference(repository, schema, target.stable_id) is None
            or _current_canonical_reference(repository, schema, target.stable_id)[:2]
            != ("person", local_subject)
        ):
            raise WritePreflightGuardError("INHERITED_EVENT_TARGET_NOT_VERIFIED")
