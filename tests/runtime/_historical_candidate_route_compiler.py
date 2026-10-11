"""Historical compiler for replaying already-captured ORIGINAL model prompts.

TEST FIXTURE ONLY. This is deliberately NOT used in product routing; previous
real model outputs cannot be treated as replies to a different divided source.
"""

from __future__ import annotations

from dataclasses import dataclass

from odyssey_apps.catalog import ApplicationCatalog
from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import FactCandidateProposal
from odyssey_apps.router import Route, RouteOutcome, RoutePlan, RouterError, validate_route_plan
from odyssey_core.candidate_context import (
    CoreCandidate,
    CoreCandidateContext,
    CoreCandidateInheritance,
    CoreCandidateRole,
    CoreSourceSpan,
)
from odyssey_core.candidate_dependencies import trace_core_candidate_dependencies


@dataclass(frozen=True, slots=True)
class ScopedCandidateRoute:
    """One exact route and untrusted Core candidate hints rebased to its source."""

    route: Route
    context: CoreCandidateContext
    original_start: int
    original_end: int
    original_candidate_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateRouteBundle:
    """Complete immutable original and executable route-local Core boundaries."""

    original_source: str
    plan: RoutePlan
    units: tuple[ScopedCandidateRoute, ...]


_TEMPORAL_ROLES = frozenset({"date", "date_scope", "time", "time_approx"})


def _candidate_interval(candidate: CoreCandidate) -> tuple[int, int]:
    """Span the literal role evidence needed to understand one proposal."""
    positions = [(span.start, span.end) for span in candidate.anchors] + [
        (role.span.start, role.span.end) for role in candidate.roles
    ]
    return min(start for start, _ in positions), max(end for _, end in positions)


def _local_context(
    original: CoreCandidateContext, first: int, last: int, start: int, end: int
) -> CoreCandidateContext:
    """Rebase only selected candidate spans; retain no sibling model context."""
    text = original.source[start:end]

    def shift(span: CoreSourceSpan) -> CoreSourceSpan:
        if span.start < start or span.end > end:
            raise RouterError("Route-local evidence references a sibling route")
        return CoreSourceSpan(span.text, span.start - start, span.end - start)

    selected = []
    for ordinal, candidate in enumerate(original.candidates[first:last], start=1):
        selected.append(
            CoreCandidate(
                f"candidate-{ordinal}",
                candidate.kind,
                candidate.state,
                tuple(shift(anchor) for anchor in candidate.anchors),
                tuple(CoreCandidateRole(role.role, shift(role.span)) for role in candidate.roles),
                tuple(
                    CoreCandidateInheritance(edge.role, edge.from_unit - first)
                    for edge in candidate.inherits
                ),
            )
        )
    context = CoreCandidateContext(text, tuple(selected))
    context.validate(text)
    return context


def compile_candidate_route_bundle(proposal: FactCandidateProposal) -> CandidateRouteBundle:
    """Group inseparable source scopes and dispatch other candidates independently.

    The grouping decision is structural: overlapping source-role evidence or
    declared source-context inheritance requires a common route. Explicit
    reference pronouns between separate routes declare an execution dependency
    but NEVER a canonical identity. No phrase-specific classification occurs.

    Raises:
        RouterError: Non-monotonic or ungrounded source boundaries, unverifiable
            candidate inheritance, or a successor that cannot be scoped safely.
    """
    original = to_core_candidate_context(proposal)
    source = original.source
    trace_core_candidate_dependencies(source, original)

    # Each member is an ORIGINAL 0-based candidate index. Same-role lexical
    # inheritance and overlapping evidence are inseparable until the relevant
    # structured role can be transmitted with independent Core validation.
    groups: list[list[int]] = []
    ends: list[int] = []
    for index, candidate in enumerate(original.candidates):
        lo, hi = _candidate_interval(candidate)
        if groups and lo < _candidate_interval(original.candidates[groups[-1][0]])[0]:
            # A candidate with shared earlier source is merged, never forwarded
            # as a possibly overlapping independent slice.
            if hi < _candidate_interval(original.candidates[groups[-1][0]])[0]:
                raise RouterError("Router candidate source order is invalid")
        if not groups:
            groups.append([index])
            ends.append(hi)
            continue
        inherited_predecessors = {edge.from_unit - 1 for edge in candidate.inherits}
        if lo < ends[-1] or inherited_predecessors.intersection(groups[-1]):
            groups[-1].append(index)
            ends[-1] = max(ends[-1], hi)
        else:
            if inherited_predecessors:
                raise RouterError("Source inheritance crosses a route boundary")
            groups.append([index])
            ends.append(hi)

    # Earlier and later groups must not share source role spans. If a late
    # lexical hint still overlaps, refuse instead of letting both plan it.
    boundaries = [0]
    for group in groups[1:]:
        first = group[0]
        boundary, _ = _candidate_interval(original.candidates[first])
        if boundary < ends[groups.index(group) - 1] or boundary <= boundaries[-1]:
            raise RouterError("Router route boundaries overlap")
        boundaries.append(boundary)
    boundaries.append(len(source))
    routes: list[Route] = []
    units: list[ScopedCandidateRoute] = []
    for route_index, group in enumerate(groups):
        start, end = boundaries[route_index : route_index + 2]
        text = source[start:end]
        if not text.strip():
            raise RouterError("Router generated an empty work unit")
        context = _local_context(original, group[0], group[-1] + 1, start, end)
        references = [
            role.span.text
            for candidate in context.candidates
            for role in candidate.roles
            if role.role == "reference"
        ]
        if len(references) > 1:
            raise RouterError("Multiple dependent mentions require explicit Core review")
        # A source pronoun in a later route waits for a UNIQUE authoritative
        # Core reference from its predecessor. The edge NEVER guesses which
        # named identity the pronoun represents.
        if references:
            if not route_index:
                raise RouterError("Unbound initial reference needs Core clarification")
            predecessor = route_index - 1
            mention = references[0]
        else:
            predecessor, mention = None, None
        temporal = any(
            role.role in _TEMPORAL_ROLES
            for candidate in context.candidates
            for role in candidate.roles
        )
        route = Route(
            "temporal" if temporal else "core",
            text,
            depends_on=predecessor,
            dependent_mention=mention,
        )
        routes.append(route)
        units.append(
            ScopedCandidateRoute(
                route,
                context,
                start,
                end,
                tuple(original.candidates[i].candidate_id for i in group),
            )
        )
    plan = RoutePlan(RouteOutcome.ROUTE, tuple(routes))
    validate_route_plan(plan, source, ApplicationCatalog.empty())
    return CandidateRouteBundle(source, plan, tuple(units))
