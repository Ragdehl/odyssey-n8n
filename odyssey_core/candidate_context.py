"""Core-owned, source-anchored candidate context for opt-in Luna planning.

Router candidates are unverified interpretations, never Notes, identities,
write intents, execution instructions, or app-specific planner replacements.
Core revalidates their literal provenance and bounded shape at this boundary.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .scoped_subject_evidence import CoreVerifiedInheritedSubject

MAX_CORE_CANDIDATE_CONTEXT_BYTES = 16_384
MAX_CORE_CANDIDATES = 26
MAX_CORE_ROLES = 16
MAX_CORE_ANCHORS = 8
ALLOWED_SOURCE_ROLES = frozenset(
    {
        "subject",
        "participants",
        "predicate",
        "predicate_relation",
        "object",
        "date",
        "date_scope",
        "time",
        "time_approx",
        "time_relation",
        "location",
        "polarity",
        "condition",
        "modality",
        "order",
        "transaction",
        "reference",
        "replacement",
    }
)
ALLOWED_CANDIDATE_KINDS = frozenset(
    {
        "occurrence",
        "property",
        "relationship",
        "purchase_item",
        "plan",
        "negative",
        "conditional",
        "task",
    }
)


@dataclass(frozen=True, slots=True)
class CoreSourceSpan:
    """Describe one original source interval validated independently by Core."""

    text: str
    start: int
    end: int

    def validate(self, original: str) -> None:
        """Require exact Python-character-offset correspondence to original text."""
        if (
            not isinstance(self.text, str)
            or not self.text.strip()
            or not isinstance(self.start, int)
            or isinstance(self.start, bool)
            or not isinstance(self.end, int)
            or isinstance(self.end, bool)
            or not 0 <= self.start < self.end <= len(original)
            or self.end - self.start > 400
            or original[self.start : self.end] != self.text
        ):
            raise ValueError("Core candidate source span is ungrounded")

    def to_payload(self) -> dict[str, Any]:
        """Serialize only source evidence without any canonical identity."""
        return {"text": self.text, "start": self.start, "end": self.end}


@dataclass(frozen=True, slots=True)
class CoreCandidateRole:
    """Carry a proposed grammatical role with independent provenance."""

    role: str
    span: CoreSourceSpan

    def validate(self, original: str) -> None:
        """Reject non-context roles and non-original snippets."""
        if not isinstance(self.role, str) or self.role not in ALLOWED_SOURCE_ROLES:
            raise ValueError("Core candidate role is not permitted")
        self.span.validate(original)

    def to_payload(self) -> dict[str, Any]:
        """Return source-only role evidence."""
        return {"role": self.role, "source": self.span.to_payload()}


@dataclass(frozen=True, slots=True)
class CoreCandidateInheritance:
    """Record a source-context hint from an earlier unit, not a write dependency."""

    role: str
    from_unit: int

    def validate(self, ordinal: int) -> None:
        """Require acyclic backwards candidate index and known role."""
        if (
            not isinstance(self.role, str)
            or self.role not in ALLOWED_SOURCE_ROLES
            or not isinstance(self.from_unit, int)
            or isinstance(self.from_unit, bool)
            or not 1 <= self.from_unit < ordinal
        ):
            raise ValueError("Core candidate inheritance is invalid")

    def to_payload(self) -> dict[str, Any]:
        """Serialize lexical dependency without implying canonical mutation order."""
        return {"role": self.role, "from_unit": self.from_unit}


@dataclass(frozen=True, slots=True)
class CoreCandidate:
    """Preserve candidate source shape while leaving Core write ownership undecided."""

    candidate_id: str
    kind: str
    state: str
    anchors: tuple[CoreSourceSpan, ...]
    roles: tuple[CoreCandidateRole, ...]
    inherits: tuple[CoreCandidateInheritance, ...]

    def validate(self, original: str, ordinal: int) -> None:
        """Validate one source-only candidate against the original whole request."""
        if self.candidate_id != f"candidate-{ordinal}":
            raise ValueError("Core candidate ID does not match its ordinal")
        if (
            not isinstance(self.kind, str)
            or not isinstance(self.state, str)
            or self.kind not in ALLOWED_CANDIDATE_KINDS
            or self.state not in {"candidate", "ambiguous_identity"}
        ):
            raise ValueError("Core candidate kind or ambiguity state is invalid")
        if (
            not isinstance(self.anchors, tuple)
            or not 1 <= len(self.anchors) <= MAX_CORE_ANCHORS
            or not isinstance(self.roles, tuple)
            or len(self.roles) > MAX_CORE_ROLES
            or not isinstance(self.inherits, tuple)
            or len(self.inherits) > MAX_CORE_ROLES
        ):
            raise ValueError("Core candidate evidence exceeds bounds")
        for anchor in self.anchors:
            if not isinstance(anchor, CoreSourceSpan):
                raise ValueError("Core candidate anchor type invalid")
            anchor.validate(original)
        if len({(a.start, a.end) for a in self.anchors}) != len(self.anchors):
            raise ValueError("Core candidate duplicate source anchor")
        for role in self.roles:
            if not isinstance(role, CoreCandidateRole):
                raise ValueError("Core candidate role type invalid")
            role.validate(original)
        for inheritance in self.inherits:
            if not isinstance(inheritance, CoreCandidateInheritance):
                raise ValueError("Core candidate inheritance type invalid")
            inheritance.validate(ordinal)
        if len({(x.role, x.from_unit) for x in self.inherits}) != len(self.inherits):
            raise ValueError("Core candidate duplicate lexical inheritance")

    def to_payload(self) -> dict[str, Any]:
        """Project one candidate without authorizing any interpretation as a write."""
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind,
            "state": self.state,
            "anchors": [a.to_payload() for a in self.anchors],
            "roles": [r.to_payload() for r in self.roles],
            "inherits": [i.to_payload() for i in self.inherits],
        }


@dataclass(frozen=True, slots=True)
class CoreSourceRoleProvenance:
    """Untrusted source role outside this work unit, rechecked on original text.

    This is lexical provenance, NOT a canonical entity, authorized date,
    inferred fact, or permission to mutate a Note.
    """

    candidate_id: str
    role: str
    text: str
    original_start: int
    original_end: int
    original_sha256: str
    origin_candidate_id: str

    def validate(self) -> None:
        if (
            not isinstance(self.candidate_id, str)
            or not re.fullmatch(r"candidate-[1-9][0-9]*", self.candidate_id)
            or not isinstance(self.origin_candidate_id, str)
            or not re.fullmatch(r"candidate-[1-9][0-9]*", self.origin_candidate_id)
            or not isinstance(self.role, str)
            or self.role not in ALLOWED_SOURCE_ROLES | {"source_anchor"}
            or not isinstance(self.text, str)
            or not self.text.strip()
            or len(self.text) > 400
            or type(self.original_start) is not int
            or type(self.original_end) is not int
            or not 0 <= self.original_start < self.original_end <= 4096
            or self.original_end - self.original_start != len(self.text)
            or not isinstance(self.original_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.original_sha256)
        ):
            raise ValueError("Shared source provenance is malformed")

    def to_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "role": self.role,
            "text": self.text,
            "original_start": self.original_start,
            "original_end": self.original_end,
            "original_sha256": self.original_sha256,
            "origin_candidate_id": self.origin_candidate_id,
        }


@dataclass(frozen=True, slots=True)
class CoreCandidateContext:
    """Bind complete user source to a strictly non-authoritative set of fact hints."""

    source: str
    candidates: tuple[CoreCandidate, ...]
    source_provenance: tuple[CoreSourceRoleProvenance, ...] = ()
    verified_inherited_subject: CoreVerifiedInheritedSubject | None = None

    def validate(self, requested_source: str) -> None:
        """Prohibit stale, altered, oversized or ungrounded candidate hints."""
        if (
            not isinstance(self.source, str)
            or self.source != requested_source
            or not self.source.strip()
            or len(self.source) > 4096
            or not isinstance(self.candidates, tuple)
            or not 1 <= len(self.candidates) <= MAX_CORE_CANDIDATES
        ):
            raise ValueError("Core candidate context must match the full current source")
        for ordinal, candidate in enumerate(self.candidates, start=1):
            if not isinstance(candidate, CoreCandidate):
                raise ValueError("Core candidate item must be a validated candidate")
            candidate.validate(self.source, ordinal)
        if not isinstance(self.source_provenance, tuple) or len(self.source_provenance) > 96:
            raise ValueError("Shared source provenance exceeds bounds")
        for proof in self.source_provenance:
            if not isinstance(proof, CoreSourceRoleProvenance):
                raise ValueError("Shared source provenance type is invalid")
            proof.validate()
            if proof.candidate_id not in {item.candidate_id for item in self.candidates}:
                raise ValueError("Shared source provenance has no local candidate")
        if self.verified_inherited_subject is not None:
            proof = self.verified_inherited_subject
            if not isinstance(proof, CoreVerifiedInheritedSubject):
                raise ValueError("Inherited Core subject proof is invalid")
            proof.validate()
            if not any(
                role.role == "subject"
                and (role.original_start, role.original_end, role.text)
                == (proof.original_start, proof.original_end, proof.source_text)
                and role.original_sha256 == proof.original_sha256
                for role in self.source_provenance
            ):
                raise ValueError("Inherited Core subject has no exact source provenance")
        if len(self.prompt_payload_bytes()) > MAX_CORE_CANDIDATE_CONTEXT_BYTES:
            raise ValueError("Core candidate context is oversized")

    def prompt_payload_bytes(self) -> bytes:
        """Serialize bounded evidence separately from provider/user request text."""
        payload: dict[str, object] = {
            "version": 1,
            "candidates": [c.to_payload() for c in self.candidates],
        }
        if self.verified_inherited_subject is not None:
            payload["core_verified_inherited_subject"] = (
                self.verified_inherited_subject.prompt_payload()
            )
        if self.source_provenance:
            payload["shared_source_provenance"] = [
                item.to_payload() for item in self.source_provenance
            ]
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    def prompt_suffix(self) -> str:
        """Render opt-in *untrusted* source-scope evidence for Core's planner.

        Nothing in this suffix may authorize or demand a Note identity, write,
        fact count or completed event. The normal Core validator remains final.
        """
        self.validate(self.source)
        return (
            "\n\nUnverified source-scoped candidate hints from the Router (NOT canonical facts, "
            "write instructions, identity binding, or proof that the request occurred):\n"
            + self.prompt_payload_bytes().decode("utf-8")
            + (
                "\nUse ONLY this ROUTED user fragment as the planning request. The candidate IDs and lexical "
                if self.source_provenance
                else "\nUse the ORIGINAL user request as the only source. The candidate IDs and lexical "
            )
            + "inheritance are proposed associations, NOT write order. Independently apply Core "
            "selection, identity, reference, facts, ambiguity, time ownership, conditional "
            "and negative-statement policy. A candidate is not necessarily a Core fact or action; "
            "do not force one action or note per candidate. Do not infer canonical people or type "
            "from roles. If representation is unsafe, use the existing safe escalation path."
            + (
                "\nIMPORTANT: This source is ONE selected Router fragment. The "
                "shared_source_provenance entries point to exact words in other "
                "original fragments, with immutable source digests and offsets. "
                "They are read-only lexical context, NOT extra request text, "
                "canonical identity proof, resolved Temporal dates, or mutation "
                "authority. Do not plan sibling operations. If the inherited "
                "role needs validation by another capability, keep that action "
                "pending rather than asserting it as fact."
                if self.source_provenance
                else ""
            )
            + (
                "\nThe separate core_verified_inherited_subject is a verified "
                "PREDECESSOR fact and canonical Note identity, not another "
                "user request. Use it only to resolve the elliptical grammatical "
                "subject of the CURRENT source fragment. Never plan the "
                "predecessor fact again or create a different target. Core "
                "will independently recheck the same Note ID and Markdown "
                "guard before writing anything."
                if self.verified_inherited_subject is not None
                else ""
            )
        )
