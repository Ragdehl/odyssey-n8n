"""Source-grounded interpretation grouping; no new identity or write authority.

An atomic Router candidate is not a model call. Linguistically dependent
neighbouring candidates may be interpreted from one contiguous original
source group; independent candidates retain separate routes and outcomes.
This compiler is opt-in and does not change active routing.
"""

from __future__ import annotations

from odyssey_apps.catalog import ApplicationCatalog
from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import FactCandidateProposal
from odyssey_apps.router import Route, RouteOutcome, RoutePlan, RouterError, validate_route_plan
from odyssey_core.candidate_context import CoreCandidate
from odyssey_core.candidate_dependencies import trace_core_candidate_dependencies
from odyssey_runtime.source_scope_compiler import (
    _TEMPORAL_ROLES,
    CandidateRouteBundle,
    ScopedCandidateRoute,
    _group_candidates,
    _local_context,
    _primary_anchors,
    _route_boundaries,
    validate_bundle_original_provenance,
)

# A pure shared date is *not* a semantic reason to merge independently
# understandable actions. An omitted verb or actor is, provided the source
# dependency is explicitly anchored and traceable.
_GRAMMATICAL_DEPENDENCIES = frozenset(
    {"participants", "subject", "predicate", "predicate_relation", "object", "transaction"}
)
_SCOPED_POLARITY = frozenset({"polarity", "condition"})


def _needs_joint_interpretation(left: CoreCandidate, right: CoreCandidate) -> bool:
    """Return whether adjacent candidates have verifiable shared syntax.

    This predicate never infers a Core identity or a write. It only decides
    whether a *single original source text slice* is needed for interpretation.
    A missing/ambiguous proof still causes ordinary Core review to fail closed.
    """
    if left.kind == "task" or right.kind == "task":
        # A property plus a requested repair may need joint interpretation
        # when both cite the SAME original actor. This is never authority to
        # create a Task, and unrelated task intents remain isolated.
        left_subjects = {(r.span.start, r.span.end) for r in left.roles if r.role == "subject"}
        right_subjects = {(r.span.start, r.span.end) for r in right.roles if r.role == "subject"}
        return (
            {left.kind, right.kind} == {"property", "task"}
            and bool(left_subjects & right_subjects)
            and not any(r.role == "modality" for r in right.roles)
        )
    if right.state != "candidate" or left.state != "candidate":
        return False
    if any(
        edge.from_unit == int(left.candidate_id.rsplit("-", 1)[1])
        and edge.role in _GRAMMATICAL_DEPENDENCIES
        for edge in right.inherits
    ):
        return True
    left_roles = {(r.role, r.span.start, r.span.end) for r in left.roles}
    right_roles = {(r.role, r.span.start, r.span.end) for r in right.roles}
    common = {role for role, _start, _end in left_roles & right_roles}
    if "predicate" in common and (
        "time" in common
        or "time_approx" in common
        or "date_scope" in common
        or "polarity" in common
        or "condition" in common
    ):
        return True
    # Same exact source subject, but different predicates can still be
    # distinct facts about one entity (F25) in one interpretation group.
    if "subject" in common and left.kind != "task" and right.kind != "task":
        return True
    if left.kind == right.kind == "negative" and "polarity" in common:
        return True
    if any(r.role == "condition" for r in left.roles) and any(
        r.role == "condition" for r in right.roles
    ):
        return True
    # Shared date + a source-anchored ordering cue links the chronology of
    # two occurrences (F04), but date alone must not merge F06 or F22.
    if (
        left.kind == right.kind == "occurrence"
        and any(e.role in {"date", "date_scope"} for e in right.inherits)
        and any(r.role in {"order", "time_relation"} for r in right.roles)
        and not any(r.role == "subject" for r in right.roles)
    ):
        return True
    return False


def compile_hybrid_candidate_bundle(proposal: FactCandidateProposal) -> CandidateRouteBundle:
    """Build exact-source groups while retaining every candidate independently.

    Raises RouterError/CandidateDependencyError for invalid overlaps, missing
    role sources or non-representable partitions. Never reconstructs a
    standalone sentence or transfers canonical meaning from Router.
    """
    original = to_core_candidate_context(proposal)
    source = original.source
    traced = trace_core_candidate_dependencies(source, original)
    primary = _primary_anchors(original.candidates)
    atomic_groups = _group_candidates(original.candidates, primary)

    groups: list[list[int]] = []
    for group in atomic_groups:
        if groups and _needs_joint_interpretation(
            original.candidates[groups[-1][-1]], original.candidates[group[0]]
        ):
            groups[-1].extend(group)
        else:
            groups.append(list(group))
    boundaries = _route_boundaries(original, primary, groups)
    units: list[ScopedCandidateRoute] = []
    routes: list[Route] = []
    for ordinal, group in enumerate(groups):
        start, end = boundaries[ordinal : ordinal + 2]
        context = _local_context(original, traced, group, primary, start, end)
        references = [
            role.span.text
            for candidate in context.candidates
            for role in candidate.roles
            if role.role == "reference"
        ]
        if len(references) > 1:
            raise RouterError("A grouped reference must be reviewed without guessed antecedents")
        if references:
            if ordinal == 0:
                raise RouterError("First group reference lacks verified prior identity")
            dependency, mention = ordinal - 1, references[0]
        else:
            dependency, mention = None, None
        temporal = any(
            role.role in _TEMPORAL_ROLES
            for candidate in context.candidates
            for role in candidate.roles
        )
        route = Route(
            "temporal" if temporal else "core",
            context.source,
            depends_on=dependency,
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
    result = CandidateRouteBundle(
        source, RoutePlan(RouteOutcome.ROUTE, tuple(routes)), tuple(units)
    )
    validate_route_plan(result.plan, source, ApplicationCatalog.empty())
    validate_bundle_original_provenance(result)
    return result
