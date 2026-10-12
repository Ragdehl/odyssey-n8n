"""Closed evidence contract for opt-in split-route Tasks execution.

This carrier transports checked source context to Tasks without turning Router
roles into operation, Task-type, identity, or mutation authority.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from odyssey_core.candidate_context import CoreSourceRoleProvenance
from odyssey_core.domain_interpretation import InheritedTemporalReference
from odyssey_core.temporal_interpretation import TemporalInterpretation


@dataclass(frozen=True, slots=True)
class TaskScopedEvidence:
    """Bind inherited exact dates and lexical modality to one original task route."""

    source_text: str
    original_sha256: str
    route_index: int
    inherited_temporal: tuple[InheritedTemporalReference, ...]
    modality_provenance: tuple[CoreSourceRoleProvenance, ...] = ()

    def validate(self, original: str) -> None:
        """Reject altered source, unordered evidence, and non-modality lexical carryover."""
        if (
            not isinstance(original, str)
            or hashlib.sha256(original.encode("utf-8")).hexdigest() != self.original_sha256
            or not isinstance(self.source_text, str)
            or not self.source_text.strip()
            or type(self.route_index) is not int
            or self.route_index < 0
            or not isinstance(self.inherited_temporal, tuple)
            or not isinstance(self.modality_provenance, tuple)
        ):
            raise ValueError("Task scoped evidence is malformed")
        for reference in self.inherited_temporal:
            if (
                not isinstance(reference, InheritedTemporalReference)
                or reference.original_sha256 != self.original_sha256
                or reference.origin_route_index >= self.route_index
                or original[reference.original_start : reference.original_end]
                != reference.source_text
            ):
                raise ValueError("Task inherited Temporal evidence is invalid")
        for proof in self.modality_provenance:
            proof.validate()
            if (
                proof.role != "modality"
                or proof.original_sha256 != self.original_sha256
                or original[proof.original_start : proof.original_end] != proof.text
            ):
                raise ValueError("Task modality provenance is invalid")


@dataclass(frozen=True, slots=True)
class TaskScopedExecution:
    """Return a route result plus optional actual local Temporal interpretation.

    The dispatcher validates and records the temporal result only for later
    source scopes; it never derives a date from this receipt itself.
    """

    result: object
    temporal_interpretation: TemporalInterpretation | None = None
