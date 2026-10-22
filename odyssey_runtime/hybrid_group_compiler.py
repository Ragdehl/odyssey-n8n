"""Source-grounded interpretation grouping; no new identity or write authority.

An atomic Router candidate is not a model call. Linguistically dependent
neighbouring candidates may be interpreted from one contiguous original
source group; independent candidates retain separate routes and outcomes.
This compiler is opt-in and does not change active routing.
"""

from __future__ import annotations

from dataclasses import replace

from odyssey_apps.catalog import ApplicationCatalog, ApplicationDescriptor, ApplicationRegistry
from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import (
    DEPENDENT_SOURCE_RELATIONS,
    SOURCE_RELATION_KINDS,
    CandidateSourceRelation,
    FactCandidateProposal,
)
from odyssey_apps.router import Route, RouteOutcome, RoutePlan, RouterError, validate_route_plan
from odyssey_core.candidate_context import CoreCandidate, CoreCandidateContext
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
    if (
        {left.kind, right.kind} == {"negative", "occurrence"}
        and all(any(role.role == "polarity" for role in c.roles) for c in (left, right))
        and any(edge.role in {"date", "date_scope"} for edge in right.inherits)
    ):
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


def _requires_shared_clause_review(
    source: str,
    left_end: int,
    right_start: int,
    left: CoreCandidate,
    right: CoreCandidate,
) -> bool:
    """Do not dispatch an unproven same-clause fragment as a standalone fact.

    Grouping retains every source candidate for independent Core review: it
    neither decides fact identity nor authorizes a write. Sentence boundaries
    are kept, as are genuinely new predicates with their own or inherited
    semantic predicate. We never merge across the Tasks capability boundary.
    """
    if (
        left.kind == "task"
        or right.kind == "task"
        or left.state != "candidate"
        or right.state != "candidate"
        or not 0 <= left_end <= right_start <= len(source)
    ):
        return False
    # Structural sentence termination, independent of any names or verbs.
    if any(mark in source[left_end:right_start] for mark in ".;!?\n"):
        return False
    new_predicate = any(
        role.role in {"predicate", "predicate_relation", "transaction"}
        and role.span.start >= left_end
        for role in right.roles
    )
    # An explicit new clock belongs to a distinct assertion even if the
    # Router anchored its verb but omitted a redundant predicate scope.
    # A shared earlier clock is not fresh independent source evidence.
    new_temporal_scope = any(
        role.role in _TEMPORAL_ROLES and role.span.start >= left_end for role in right.roles
    )
    return not (new_predicate or new_temporal_scope)


def _semantic_source_groups(
    original: CoreCandidateContext,
    atomic_groups: list[list[int]],
    proposal: FactCandidateProposal,
    primary: tuple[tuple, ...],
) -> list[list[int]]:
    """Group v2 source candidates without trusting model-declared independence.

    Explicit source relations are input hints, never authority to split. A
    new route needs its own anchored predicate and either a distinct sentence
    boundary or a new temporal anchor. Same-clause actions remain distinct
    CANDIDATES in the joint Core group, so one plan can write N facts.
    Cross-capability grouping is rejected rather than silently rewritten.
    """
    if proposal.contract_version != 2 or len(proposal.semantic_relations) != len(
        original.candidates
    ):
        raise RouterError("Semantic grouping requires the complete versioned relation contract")
    source = original.source
    # Recheck even a hand-built proposal: Router's dataclass is a hint, not
    # a trusted carrier across independently callable runtime boundaries.
    for ordinal, relation in enumerate(proposal.semantic_relations, 1):
        if not isinstance(relation, CandidateSourceRelation):
            raise RouterError("Semantic relation has invalid type")
        parent = relation.parent_unit
        if (
            type(relation.unit) is not int
            or relation.unit != ordinal
            or relation.kind not in SOURCE_RELATION_KINDS
            or type(parent) is not int
            or not 0 <= parent < ordinal
            or (relation.kind == "independent_assertion" and parent != 0)
            or (relation.kind in DEPENDENT_SOURCE_RELATIONS and parent == 0)
        ):
            raise RouterError("Semantic source contract cannot authorize route splitting")
        evidence = relation.evidence
        candidate = proposal.candidates[ordinal - 1]
        allowed = (*candidate.anchors, *(r.anchor for r in candidate.scopes))
        if (
            not any(
                evidence.start == a.start and evidence.end == a.end and evidence.text == a.text
                for a in allowed
            )
            or source[evidence.start : evidence.end] != evidence.text
        ):
            raise RouterError("Semantic relation witness is not anchored in the original source")
    source = original.source
    groups: list[list[int]] = []
    for unit in atomic_groups:
        if not groups:
            groups.append(list(unit))
            continue
        previous = groups[-1]
        right_index = unit[0]
        link = proposal.semantic_relations[right_index]
        if link.unit != right_index + 1:
            raise RouterError("Semantic unit index does not match source order")
        left_end = max(span.end for i in previous for span in primary[i])
        right_start = min(span.start for i in unit for span in primary[i])
        if not 0 <= left_end <= right_start <= len(source):
            raise RouterError("Semantic candidates cannot be ordered safely")
        between = source[left_end:right_start]
        new_sentence = any(mark in between for mark in ".;!?\n")
        independent_new_time = any(
            role.role in _TEMPORAL_ROLES and role.span.start >= left_end
            for c in (original.candidates[i] for i in unit)
            for role in c.roles
        )
        independently_anchored_predicate = any(
            role.role == "predicate" and role.span.start >= left_end
            for c in (original.candidates[i] for i in unit)
            for role in c.roles
        )
        needs_parent = link.kind in DEPENDENT_SOURCE_RELATIONS or (
            link.kind == "unresolved" and link.parent_unit != 0
        )
        if needs_parent and link.parent_unit - 1 not in previous:
            raise RouterError("Nonadjacent semantic dependency needs independent source review")
        # A model's "independent_assertion" is NOT enough to split.
        # The new statement must also bring its OWN explicit predicate and
        # a structural sentence/clock boundary. A date, adjective or purpose
        # alone cannot become an executable route by model self-labeling.
        positive_boundary = independently_anchored_predicate and (
            new_sentence or independent_new_time
        )
        join = needs_parent or link.kind == "unresolved" or not positive_boundary
        if join:
            kinds = {original.candidates[i].kind == "task" for i in (*previous, *unit)}
            if len(kinds) > 1:
                raise RouterError("Mixed Task/Core source dependency requires safe clarification")
            if True in kinds:
                # Direct lifecycle operations have independent semantics.
                # Grouped Task candidates are not supported by that adapter.
                raise RouterError("Grouped Task lifecycle candidates need separate authority")
            previous.extend(unit)
        else:
            groups.append(list(unit))
    return groups


def candidate_decision_trace(
    proposal: FactCandidateProposal,
    bundle: CandidateRouteBundle,
) -> dict[str, object]:
    """Bounded observed evidence; NOT model chain-of-thought or a write plan.

    Pure, non-persistent diagnostic projection. It can be made available in
    authenticated DEV only after independent data contract and privacy tests.
    """
    import hashlib

    if proposal.source != bundle.original_source:
        raise RouterError("Decision trace source must match immutable original")
    if proposal.contract_version != 2:
        raise RouterError("Decision trace requires relation contract v2")
    if len(proposal.semantic_relations) != len(proposal.candidates):
        raise RouterError("Incomplete decision trace candidate relations")
    candidates = []
    for candidate, relation in zip(proposal.candidates, proposal.semantic_relations, strict=True):
        candidates.append(
            {
                "id": candidate.candidate_id,
                "kind": candidate.kind,
                "state": candidate.state,
                "anchors": [[a.start, a.end] for a in candidate.anchors],
                "roles": [
                    [role.role, role.anchor.start, role.anchor.end] for role in candidate.scopes
                ],
                "relation": relation.kind,
                "parent_unit": relation.parent_unit,
                "evidence": [relation.evidence.start, relation.evidence.end],
            }
        )
    routes = [
        {
            "source_range": [unit.original_start, unit.original_end],
            "candidate_ids": list(unit.original_candidate_ids),
            "capability": unit.route.capability_id,
        }
        for unit in bundle.units
    ]
    decisions = []
    group_of = {
        cid: index for index, unit in enumerate(bundle.units) for cid in unit.original_candidate_ids
    }
    for index in range(1, len(proposal.candidates)):
        earlier = proposal.candidates[index - 1].candidate_id
        current = proposal.candidates[index].candidate_id
        decisions.append(
            {
                "earlier": earlier,
                "current": current,
                "decision": "group" if group_of[earlier] == group_of[current] else "split",
                "validation": (
                    "declared_source_dependency"
                    if (
                        group_of[earlier] == group_of[current]
                        and proposal.semantic_relations[index].kind in DEPENDENT_SOURCE_RELATIONS
                    )
                    else "unresolved_independence_grouped"
                    if group_of[earlier] == group_of[current]
                    else "positive_source_boundary"
                ),
            }
        )
    return {
        "version": 1,
        "source_sha256": hashlib.sha256(proposal.source.encode("utf-8")).hexdigest(),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "routes": routes,
        "boundaries": decisions,
    }


def hybrid_tasks_catalog() -> ApplicationCatalog:
    """Explicitly registered Tasks app, never an inferred Core write."""
    descriptor = ApplicationDescriptor(
        "tasks", "Task lifecycle interpretation and canonical Task mutation", ("core",)
    )
    return ApplicationRegistry((descriptor,)).catalog(enabled_ids=("tasks",))


def hybrid_enabled_app_catalog(*, enable_tasks: bool, enable_events: bool) -> ApplicationCatalog:
    descriptors = []
    ids = []
    if enable_tasks:
        descriptors.append(
            ApplicationDescriptor(
                "tasks", "Task lifecycle interpretation and canonical Task mutation", ("core",)
            )
        )
        ids.append("tasks")
    if enable_events:
        descriptors.append(
            ApplicationDescriptor(
                "events", "Dated and recurring calendar Event lifecycle", ("temporal",)
            )
        )
        ids.append("events")
    return ApplicationRegistry(tuple(descriptors)).catalog(enabled_ids=tuple(ids))


def compile_hybrid_candidate_bundle(
    proposal: FactCandidateProposal, *, enable_tasks: bool = False, enable_events: bool = False
) -> CandidateRouteBundle:
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

    if proposal.contract_version == 2:
        groups = _semantic_source_groups(original, atomic_groups, proposal, primary)
    elif proposal.contract_version == 1 and not proposal.semantic_relations:
        # Preserve the exact legacy v1/v5 semantics until opt-in v2 gates pass.
        groups: list[list[int]] = []
        for group in atomic_groups:
            if groups:
                preceding = groups[-1]
                last_end = max(a.end for i in preceding for a in primary[i])
                first_start = min(a.start for i in group for a in primary[i])
                join = _needs_joint_interpretation(
                    original.candidates[preceding[-1]], original.candidates[group[0]]
                ) or _requires_shared_clause_review(
                    source,
                    last_end,
                    first_start,
                    original.candidates[preceding[-1]],
                    original.candidates[group[0]],
                )
                if join:
                    preceding.extend(group)
                    continue
            groups.append(list(group))
    else:
        raise RouterError("Unsupported or incomplete candidate source-relation contract")
    boundaries = _route_boundaries(original, primary, groups)
    units: list[ScopedCandidateRoute] = []
    routes: list[Route] = []
    for ordinal, group in enumerate(groups):
        start, end = boundaries[ordinal : ordinal + 2]
        context = replace(
            _local_context(original, traced, group, primary, start, end),
            hybrid_interpretation_mode=True,
        )
        references = [
            role.span.text
            for candidate in context.candidates
            for role in candidate.roles
            if role.role == "reference"
            # A reference to the same clock is not a reference to a
            # canonical Person/Note identity. The temporal interpreter
            # handles that semantic dependency within this source group,
            # and Core still checks every actual clock and write target.
            and not any(
                clock.role == "time_relation" and clock.span == role.span
                for clock in candidate.roles
            )
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
        all_tasks = all(candidate.kind == "task" for candidate in context.candidates)
        all_events = all(candidate.kind == "event" for candidate in context.candidates)
        route = Route(
            "tasks"
            if enable_tasks and all_tasks
            else "events"
            if enable_events and all_events
            else ("temporal" if temporal else "core"),
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
    catalog = hybrid_enabled_app_catalog(enable_tasks=enable_tasks, enable_events=enable_events)
    validate_route_plan(result.plan, source, catalog)
    validate_bundle_original_provenance(result, catalog=catalog)
    return result
