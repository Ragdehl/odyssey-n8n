"""Source-grounded compiler from Router candidates to independent work units.

Unlike the retired overlap-merging adapter, source-role reuse does not cause
unrelated facts to be planned together. Each exact-text route is a partition
of the original, while shared or inherited words are *typed source provenance*.
No source role grants Core permission to invent a date, canonical identity,
fact, or Note write.
"""

from __future__ import annotations

import hashlib
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
    CoreSourceRoleProvenance,
    CoreSourceSpan,
)
from odyssey_core.candidate_dependencies import trace_core_candidate_dependencies

_TEMPORAL_ROLES = frozenset({"date", "date_scope", "time", "time_approx"})


@dataclass(frozen=True, slots=True)
class ScopedCandidateRoute:
    """One original-text route and exactly its selected local candidate hints."""

    route: Route
    context: CoreCandidateContext
    original_start: int
    original_end: int
    original_candidate_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateRouteBundle:
    """Immutable original source plus independent validated execution units."""

    original_source: str
    plan: RoutePlan
    units: tuple[ScopedCandidateRoute, ...]


def _same_joint_event(left: CoreCandidate, right: CoreCandidate) -> bool:
    """Do not split one shared property or one coordinated purchase transaction."""
    if any(
        role.role == "replacement"
        and any(
            role.span.start <= anchor.start and anchor.end <= role.span.end
            for anchor in left.anchors
        )
        for role in right.roles
    ):
        # A correction retracts the earlier alternative: never commit it first.
        return True
    if left.kind == right.kind == "purchase_item":
        # One coordinated purchase with several objects, NOT separate buyers.
        return not any(role.role == "subject" for role in right.roles) and any(
            x.role == "transaction" and x.from_unit == int(left.candidate_id.split("-")[1])
            for x in right.inherits
        )
    if left.kind == right.kind == "property" and not right.inherits:
        for role in ("predicate", "location"):
            a = {r.span for r in left.roles if r.role == role}
            b = {r.span for r in right.roles if r.role == role}
            if not a or a != b:
                return False
        return True
    return False


def _primary_anchors(
    candidates: tuple[CoreCandidate, ...],
) -> tuple[tuple[CoreSourceSpan, ...], ...]:
    """Repeated original anchors mean shared evidence, not a new owned span."""
    occupied: set[tuple[int, int]] = set()
    result: list[tuple[CoreSourceSpan, ...]] = []
    for candidate in candidates:
        new = tuple(a for a in candidate.anchors if (a.start, a.end) not in occupied)
        if not new:
            raise RouterError("A candidate has no independently located source anchor")
        occupied.update((a.start, a.end) for a in new)
        result.append(new)
    return tuple(result)


def _group_candidates(
    candidates: tuple[CoreCandidate, ...],
    primary: tuple[tuple[CoreSourceSpan, ...], ...],
) -> list[list[int]]:
    groups: list[list[int]] = []
    for i, candidate in enumerate(candidates):
        lo = min(a.start for a in primary[i])
        if not groups:
            groups.append([i])
            continue
        previous = groups[-1][-1]
        prev_lo = min(a.start for j in groups[-1] for a in primary[j])
        prev_hi = max(a.end for j in groups[-1] for a in primary[j])
        if lo < prev_lo or (
            lo < prev_hi and not _same_joint_event(candidates[previous], candidate)
        ):
            raise RouterError(
                "Candidate spans overlap or are reordered; unsafe independent dispatch"
            )
        if lo < prev_hi or _same_joint_event(candidates[previous], candidate):
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def _route_boundaries(
    original: CoreCandidateContext,
    primary: tuple[tuple[CoreSourceSpan, ...], ...],
    groups: list[list[int]],
) -> list[int]:
    source = original.source
    cuts = [0]
    for previous, following in zip(groups, groups[1:], strict=False):
        prev_anchor_end = max(a.end for i in previous for a in primary[i])
        next_anchor_start = min(a.start for i in following for a in primary[i])
        # Prefer the beginning of explicit local evidence in the successor,
        # such as 'mañana' before its verb; shared old roles are excluded.
        following_spans = [
            r.span
            for i in following
            for r in original.candidates[i].roles
            if prev_anchor_end <= r.span.start < next_anchor_start
        ]
        proposed_start = min([next_anchor_start, *(s.start for s in following_spans)])
        previous_local_roles = [
            r.span.end
            for i in previous
            for r in original.candidates[i].roles
            if r.span.start < proposed_start and r.span.end <= proposed_start
        ]
        previous_end = max([prev_anchor_end, *previous_local_roles])
        if previous_end > proposed_start or previous_end <= cuts[-1]:
            raise RouterError("Cannot isolate current source without overlapping semantic anchors")
        # Glue between independently evidenced clauses belongs with the
        # successor (' y', ' pero', punctuation), never duplicated or erased.
        # Previous text ends at the last proven preceding token.
        boundary = previous_end
        if not 0 < boundary < len(source):
            raise RouterError("Invalid exact-text unit boundary")
        cuts.append(boundary)
    cuts.append(len(source))
    return cuts


def _local_context(
    original: CoreCandidateContext,
    traced: tuple,
    group: list[int],
    primary: tuple[tuple[CoreSourceSpan, ...], ...],
    start: int,
    end: int,
) -> CoreCandidateContext:
    text = original.source[start:end]
    digest = hashlib.sha256(original.source.encode("utf-8")).hexdigest()
    selected = []
    provenance = []
    observed: set[tuple] = set()

    def local(span: CoreSourceSpan) -> bool:
        return start <= span.start < span.end <= end

    def rebase(span: CoreSourceSpan) -> CoreSourceSpan:
        return CoreSourceSpan(span.text, span.start - start, span.end - start)

    for offset, index in enumerate(group, start=1):
        candidate = original.candidates[index]
        candidate_id = f"candidate-{offset}"

        def carry(role: str, span: CoreSourceSpan, origin: str, target_id: str = candidate_id):
            # The immutable full original is used only to prove origin.
            span.validate(original.source)
            key = (target_id, role, span.start, span.end, origin)
            if key not in observed:
                observed.add(key)
                provenance.append(
                    CoreSourceRoleProvenance(
                        target_id, role, span.text, span.start, span.end, digest, origin
                    )
                )

        anchors = tuple(rebase(a) for a in primary[index] if local(a))
        for anchor in candidate.anchors:
            if not local(anchor):
                carry("source_anchor", anchor, candidate.candidate_id)
        roles = []
        for role in candidate.roles:
            if local(role.span):
                roles.append(CoreCandidateRole(role.role, rebase(role.span)))
            else:
                carry(role.role, role.span, candidate.candidate_id)
        inherits = []
        for edge in candidate.inherits:
            if edge.from_unit - 1 in group:
                inherits.append(
                    CoreCandidateInheritance(edge.role, group.index(edge.from_unit - 1) + 1)
                )
        for entry in traced[index].roles:
            if entry.inherited and entry.source_candidate_id not in (
                original.candidates[i].candidate_id for i in group
            ):
                carry(entry.role, entry.span, entry.source_candidate_id)
        if not anchors:
            raise RouterError("One candidate cannot be scoped to its own original text")
        selected.append(
            CoreCandidate(
                candidate_id,
                candidate.kind,
                candidate.state,
                anchors,
                tuple(roles),
                tuple(inherits),
            )
        )
    result = CoreCandidateContext(
        text, tuple(selected), tuple(provenance), scoped_route_source=True
    )
    result.validate(text)
    return result


def compile_candidate_route_bundle(proposal: FactCandidateProposal) -> CandidateRouteBundle:
    """Compile per-candidate routes, conservatively grouping only joint events."""
    original = to_core_candidate_context(proposal)
    source = original.source
    traced = trace_core_candidate_dependencies(source, original)
    primary = _primary_anchors(original.candidates)
    groups = _group_candidates(original.candidates, primary)
    boundaries = _route_boundaries(original, primary, groups)

    routes = []
    units = []
    for route_index, group in enumerate(groups):
        start, end = boundaries[route_index : route_index + 2]
        context = _local_context(original, traced, group, primary, start, end)
        references = [
            role.span.text
            for candidate in context.candidates
            for role in candidate.roles
            if role.role == "reference"
        ]
        if len(references) > 1:
            raise RouterError("Multiple references need explicit Core-owned review")
        if references:
            if route_index == 0:
                raise RouterError("Unbound first-route reference cannot be guessed")
            depends_on = route_index - 1
            mention = references[0]
        else:
            depends_on, mention = None, None
        temporal = any(
            role.role in _TEMPORAL_ROLES
            for candidate in context.candidates
            for role in candidate.roles
        )
        route = Route(
            "temporal" if temporal else "core",
            context.source,
            depends_on=depends_on,
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


def validate_bundle_original_provenance(bundle: CandidateRouteBundle) -> None:
    """Recheck every external lexical witness against the immutable original."""
    source = bundle.original_source
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    validate_route_plan(bundle.plan, source, ApplicationCatalog.empty())
    for scoped in bundle.units:
        scoped.context.validate(scoped.route.source_text)
        for role in scoped.context.source_provenance:
            if (
                role.original_sha256 != digest
                or source[role.original_start : role.original_end] != role.text
            ):
                raise RouterError("Shared context does not match original source")
