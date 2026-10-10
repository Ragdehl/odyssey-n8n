"""Read-only linking of source-grounded fact roles to existing Temporal evidence.

This module never asks for provider inference, writes Markdown, chooses an app,
or translates a candidate unit into Core mutation authority. Temporal remains the
only normalizer. The link is proposed evidence for later reviewed preflight.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from odyssey_core.temporal_interpretation import TemporalInterpretation
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind

from .fact_candidates import (
    FactCandidateProposal,
    SourceAnchor,
    SourceInheritance,
)
from .router import RouterError

TEMPORAL_SOURCE_ROLES = frozenset({"date", "date_scope", "time", "time_approx", "time_relation"})


@dataclass(frozen=True, slots=True)
class CandidateTemporalEvidence:
    """Associate an existing source role with one source-grounded Temporal result.

    This is *not* a Core-authorized temporal anchor. The consumer must review
    applicability and preserve approximation, ordering and unsupported ranges.
    """

    candidate_id: str
    role: str
    source: SourceAnchor
    origin: Literal["explicit", "inherited"]
    status: Literal["matched", "missing"]
    resolution: TemporalResolution | None
    temporal_text: str | None
    has_exact_source_shape: bool


def _original_scope(
    proposal: FactCandidateProposal, edge: SourceInheritance
) -> SourceAnchor | None:
    """Find same-role original evidence without rewriting or extrapolating it."""
    previous = proposal.candidates[edge.from_unit - 1]
    for scope in previous.scopes:
        if scope.role == edge.role:
            return scope.anchor
    for previous_edge in previous.inheritance:
        if previous_edge.role == edge.role:
            return _original_scope(proposal, previous_edge)
    return None


def _ordered_temporal_spans(
    source: str, interpretation: TemporalInterpretation
) -> list[tuple[int, int, str, TemporalResolution]]:
    """Resolve literal Temporal mentions only when their ordered offsets are unique.

    Temporal currently supplies text, not occurrence indices. Choosing the first
    occurrence is unsafe if fewer repeated mentions are reported than appear
    in the original source. Compare earliest and latest non-overlapping ordered
    alignments; different positions mean the source mapping is unproven.
    """
    if interpretation.source_text != source:
        raise RouterError("Temporal interpretation does not match original fact source")
    mentions = interpretation.mentions
    earliest: list[int] = []
    cursor = 0
    for mention in mentions:
        text = mention.temporal_text
        position = source.find(text, cursor)
        if position < 0:
            raise RouterError("Temporal source mention is not grounded in the current source")
        earliest.append(position)
        cursor = position + len(text)
    latest: list[int] = []
    cursor = len(source)
    for mention in reversed(mentions):
        text = mention.temporal_text
        position = source.rfind(text, 0, cursor)
        if position < 0:
            raise RouterError("Temporal source mention is not grounded in the current source")
        latest.append(position)
        cursor = position
    latest.reverse()
    if earliest != latest:
        raise RouterError("Temporal source mention occurrence is ambiguous")
    return [
        (position, position + len(mention.temporal_text), mention.temporal_text, mention.resolution)
        for position, mention in zip(earliest, mentions, strict=True)
    ]


def bind_temporal_to_fact_candidates(
    proposal: FactCandidateProposal,
    interpretation: TemporalInterpretation | None,
) -> tuple[CandidateTemporalEvidence, ...]:
    """Attach an existing Temporal reading to exact candidate-local source spans.

    Args:
        proposal: Validated request-local candidates, retaining the entire
            original immutable user input and locally resolved source offsets.
        interpretation: Optional interpretation already supplied by the Temporal
            capability for *that same original full source*.

    Returns:
        Only source-grounded candidate/role associations. An absent or unknown
        temporal reading remains `missing` or `UNSPECIFIED`; approximate and
        relational clock scopes never receive exact Core authority here.

    Raises:
        RouterError: When source identity, exact offsets, or temporal scope
            evidence is inconsistent. No model call or write is performed.
    """
    if not isinstance(proposal, FactCandidateProposal):
        raise RouterError("Validated fact candidate proposal required")
    if interpretation is not None and not isinstance(interpretation, TemporalInterpretation):
        raise RouterError("Temporal interpretation must be the validated Temporal result")
    spans = _ordered_temporal_spans(proposal.source, interpretation) if interpretation else []
    results: list[CandidateTemporalEvidence] = []
    for candidate in proposal.candidates:
        mentions = [
            (scope.role, scope.anchor, "explicit")
            for scope in candidate.scopes
            if scope.role in TEMPORAL_SOURCE_ROLES
        ]
        explicit_roles = {scope.role for scope in candidate.scopes}
        for edge in candidate.inheritance:
            if edge.role not in TEMPORAL_SOURCE_ROLES or edge.role in explicit_roles:
                # A newly expressed date/time overrides inherited same-role
                # wording without changing any unrelated inherited role.
                continue
            anchor = _original_scope(proposal, edge)
            if anchor is None:
                # Never fabricate inherited source role text when it cannot be
                # traced through exact ancestor roles.
                continue
            mentions.append((edge.role, anchor, "inherited"))
        for role, anchor, origin in mentions:
            if proposal.source[anchor.start : anchor.end] != anchor.text:
                raise RouterError("Fact candidate has a mismatched original source anchor")
            matching = [
                (text, resolution)
                for start, end, text, resolution in spans
                if start < anchor.end and end > anchor.start
            ]
            if len(matching) > 1:
                # Multiple interpretations overlap one source scope; avoid
                # choosing arbitrarily between distinct temporal claims.
                raise RouterError("Temporal evidence overlaps one scope ambiguously")
            text, resolution = matching[0] if matching else (None, None)
            exact = resolution is not None and (
                (
                    role == "date"
                    and resolution.kind
                    in {
                        TemporalResolutionKind.EXACT_DATE,
                        TemporalResolutionKind.EXACT_DATETIME,
                    }
                )
                or (role == "time" and resolution.kind is TemporalResolutionKind.EXACT_DATETIME)
            )
            results.append(
                CandidateTemporalEvidence(
                    candidate.candidate_id,
                    role,
                    anchor,
                    origin,
                    "matched" if resolution is not None else "missing",
                    resolution,
                    text,
                    exact,
                )
            )
    return tuple(results)
