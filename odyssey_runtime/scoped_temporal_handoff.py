"""Core-bound verified inherited Temporal evidence for route-local work units.

This is an execution-time carrier. Router contributes only original source
anchors; a prior completed Temporal interpretation supplies the normalized
value. The complete original message is used to check provenance, not as a
downstream model prompt. No date is guessed or inferred from a lexical role.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from odyssey_core.candidate_context import CoreCandidateContext
from odyssey_core.domain_interpretation import (
    DomainInterpretation,
    InheritedTemporalReference,
)
from odyssey_core.temporal_interpretation import TemporalInterpretation

_TEMPORAL_ROLES = frozenset({"date", "date_scope", "time", "time_approx"})


@dataclass(frozen=True, slots=True)
class _TrustedTemporalSpan:
    start: int
    end: int
    value: str
    route_index: int


@dataclass(slots=True)
class ScopedTemporalHandoff:
    """Bounded current-message Temporal resolutions, keyed by exact offsets."""

    original: str
    _resolved: dict[tuple[int, int], _TrustedTemporalSpan] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.original, str) or not self.original.strip():
            raise ValueError("Original source must be present for Temporal transfer")

    def remember(
        self,
        interpretation: TemporalInterpretation,
        *,
        route_index: int,
        start: int,
        end: int,
    ) -> None:
        """Record only completed, locally checked exact Temporal resolutions."""
        if (
            not isinstance(interpretation, TemporalInterpretation)
            or type(route_index) is not int
            or route_index < 0
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(self.original)
            or self.original[start:end] != interpretation.source_text
        ):
            raise ValueError("Temporal result is not bound to the original route")
        # Converts only EXACT_DATE and EXACT_DATETIME. UNKNOWN, approximate,
        # and conflicting alternatives fail without carrying fake dates.
        domain = interpretation.core_domain_interpretation()
        cursor = 0
        for mention, evidence in zip(interpretation.mentions, domain.evidence, strict=True):
            position = interpretation.source_text.find(mention.temporal_text, cursor)
            if position < 0 or mention.temporal_text != evidence.source_text:
                raise ValueError("Temporal mention is not grounded in its source route")
            cursor = position + len(mention.temporal_text)
            absolute = (start + position, start + cursor)
            existing = self._resolved.get(absolute)
            if existing is not None and existing.value != evidence.value:
                raise ValueError("Temporal returned conflicting values for one source")
            if len(self._resolved) >= 32 and existing is None:
                raise ValueError("Temporal source transfer exceeds bounded capacity")
            self._resolved[absolute] = _TrustedTemporalSpan(*absolute, evidence.value, route_index)

    def inherited(
        self,
        context: CoreCandidateContext,
        *,
        current_route_index: int,
        start: int,
        end: int,
    ) -> tuple[InheritedTemporalReference, ...]:
        """Prove each externally sourced temporal role has a prior exact result."""
        if (
            not isinstance(context, CoreCandidateContext)
            or context.source != self.original[start:end]
            or type(current_route_index) is not int
            or current_route_index < 0
        ):
            raise ValueError("Temporal destination scope is ungrounded")
        digest = hashlib.sha256(self.original.encode("utf-8")).hexdigest()
        authorized = []
        seen: set[tuple[int, int]] = set()
        for role in context.source_provenance:
            if role.role not in _TEMPORAL_ROLES:
                continue
            key = (role.original_start, role.original_end)
            if (
                role.original_sha256 != digest
                or self.original[role.original_start : role.original_end] != role.text
                or role.original_start >= start
                and role.original_end <= end
            ):
                raise ValueError("Inherited Temporal source role was forged or is local")
            if key in seen:
                continue
            seen.add(key)
            prior = self._resolved.get(key)
            if prior is None:
                # Lexical inheritance is NOT normalized time authorization.
                # Other contextual provenance still stays available for Core.
                continue
            if prior.route_index >= current_route_index or prior.end > start:
                raise ValueError("Inherited Temporal proof is not from an earlier route")
            authorized.append(
                InheritedTemporalReference(
                    role.text,
                    prior.value,
                    role.original_start,
                    role.original_end,
                    digest,
                    prior.route_index,
                )
            )
        return tuple(authorized)


def with_scoped_inherited_temporal(
    domain: DomainInterpretation | None,
    *,
    source: str,
    inherited: tuple[InheritedTemporalReference, ...],
) -> DomainInterpretation | None:
    """Join local Temporal with proven predecessor anchors, without word invention."""
    if not inherited:
        return domain
    if domain is None:
        return DomainInterpretation("temporal", source, "TEMPORAL_RESOLUTION", (), inherited)
    if domain.source_text != source:
        raise ValueError("Local domain source changed during temporal transfer")
    if domain.inherited_temporal:
        raise ValueError("Inherited Temporal is already bound; no double authorization")
    return DomainInterpretation(
        domain.capability_id,
        domain.source_text,
        domain.intent,
        domain.evidence,
        inherited,
    )
