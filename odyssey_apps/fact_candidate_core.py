"""Narrow Router candidate -> Core source-evidence adapter (not runtime-activated).

Only copies independently grounded source spans and lexical inheritance hints;
Core separately revalidates the material. It cannot call a planner, name a Note,
construct a RequestPlan, or authorize persistence.
"""

from __future__ import annotations

from odyssey_core.candidate_context import (
    CoreCandidate,
    CoreCandidateContext,
    CoreCandidateInheritance,
    CoreCandidateRole,
    CoreSourceSpan,
)

from .fact_candidates import FactCandidateProposal, SourceAnchor
from .router import RouterError


def _source_span(anchor: SourceAnchor) -> CoreSourceSpan:
    """Project locally validated original Unicode positions without rewriting."""
    return CoreSourceSpan(anchor.text, anchor.start, anchor.end)


def to_core_candidate_context(proposal: FactCandidateProposal) -> CoreCandidateContext:
    """Transfer bounded, unverified Router evidence to a Core-owned context.

    Args:
        proposal: Validated original full request and non-executing Router units.

    Returns:
        Core-owned source-anchored immutable evidence suitable for optional
        model planning, never for deciding canonical identity or writing Notes.

    Raises:
        RouterError: If an app-side proposal was forged after validation or
            Core's independently checked type/source/budget contract fails.
    """
    if not isinstance(proposal, FactCandidateProposal):
        raise RouterError("Validated Router proposal is required for Core handoff")
    context = CoreCandidateContext(
        proposal.source,
        tuple(
            CoreCandidate(
                item.candidate_id,
                item.kind,
                item.state,
                tuple(_source_span(anchor) for anchor in item.anchors),
                tuple(
                    CoreCandidateRole(scope.role, _source_span(scope.anchor))
                    for scope in item.scopes
                ),
                tuple(
                    CoreCandidateInheritance(edge.role, edge.from_unit) for edge in item.inheritance
                ),
            )
            for item in proposal.candidates
        ),
    )
    try:
        context.validate(proposal.source)
    except (TypeError, ValueError, AttributeError) as error:
        raise RouterError(
            "Router fact candidates did not pass independent Core preflight"
        ) from error
    return context
