"""Core-owned, source-anchored candidate context for opt-in Luna planning.

Router candidates are unverified interpretations, never Notes, identities,
write intents, execution instructions, or app-specific planner replacements.
Core revalidates their literal provenance and bounded shape at this boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

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
class CoreCandidateContext:
    """Bind complete user source to a strictly non-authoritative set of fact hints."""

    source: str
    candidates: tuple[CoreCandidate, ...]

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
        if len(self.prompt_payload_bytes()) > MAX_CORE_CANDIDATE_CONTEXT_BYTES:
            raise ValueError("Core candidate context is oversized")

    def prompt_payload_bytes(self) -> bytes:
        """Serialize bounded evidence separately from provider/user request text."""
        return json.dumps(
            {"version": 1, "candidates": [c.to_payload() for c in self.candidates]},
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
            + "\nUse the ORIGINAL user request as the only source. The candidate IDs and lexical "
            "inheritance are proposed associations, NOT write order. Independently apply Core "
            "selection, identity, reference, facts, ambiguity, time ownership, conditional "
            "and negative-statement policy. A candidate is not necessarily a Core fact or action; "
            "do not force one action or note per candidate. Do not infer canonical people or type "
            "from roles. If representation is unsafe, use the existing safe escalation path."
        )
