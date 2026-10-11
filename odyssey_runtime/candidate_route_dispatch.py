"""Bridge validated Router v1 candidates onto EXISTING route-local execution.

This module restores the approved route boundary. Router receives the complete
message once to propose original-source evidence; each later model sees ONLY
its exact local routed slice, never all siblings as a new planning request.
Shared source-role evidence is grouped rather than copied as invented prose.
Canonical referents are supplied solely by the ordinary Core result handoff.
This opt-in capability does NOT replace active DEV/PROD routing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

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


def resolve_scoped_reference_with_core_proof(
    context: CoreCandidateContext,
    handoff: object,
    repository: object,
    schema: dict,
) -> CoreCandidateContext:
    """Refresh ONLY the dependent source candidate's provisional ambiguity.

    Router marks a pronoun ambiguous before Core knows the predecessor's
    canonical identity. A completed predecessor can resolve that SAME exact
    pronoun when Core's persisted identity and source fact are both current.
    Nothing else in Router's proposal becomes trusted or writable; the
    incoming DependentReferenceGuard is separately checked again at write
    time, after independent graph review.
    """
    from odyssey_core.application import (
        DependentReferenceGuard,
        _dependent_evidence_is_current,
    )
    from odyssey_core.storage import VaultRepository

    context.validate(context.source)
    if not isinstance(handoff, DependentReferenceGuard):
        raise ValueError("Core-proven dependent identity guard required")
    if not isinstance(repository, VaultRepository) or not isinstance(schema, dict):
        raise ValueError("Canonical proof requires a trusted vault/schema")
    if not _dependent_evidence_is_current(handoff.evidence, repository, schema):
        raise ValueError("Core predecessor identity proof is no longer valid")
    matches = [
        index
        for index, candidate in enumerate(context.candidates)
        if any(
            role.role == "reference" and role.span.text == handoff.mention
            for role in candidate.roles
        )
    ]
    if (
        len(matches) != 1
        or sum(
            len([role for role in candidate.roles if role.role == "reference"])
            for candidate in context.candidates
        )
        != 1
    ):
        raise ValueError("Dependent source does not have one exact referring candidate")
    position = matches[0]
    target = context.candidates[position]
    if target.state != "ambiguous_identity":
        return context
    candidates = list(context.candidates)
    candidates[position] = replace(target, state="candidate")
    refreshed = CoreCandidateContext(context.source, tuple(candidates))
    refreshed.validate(context.source)
    return refreshed


def execute_candidate_routed_message(
    source: str,
    *,
    router: object,
    temporal: object | None,
    core_planner_factory: Callable[[CoreCandidateContext, object | None], object],
    candidate_coverage_factory: Callable[[str, CoreCandidateContext, object], object] | None = None,
    core_candidate_attributor: object | None = None,
    repository: object,
    schema: dict,
    context_index: object,
    semantic_index: object,
    embedder: object,
    contextual_reasoner: object,
    actor: object,
    now: str,
    context_limit: int,
    request_id_factory: Callable[[], str],
    candidate_pending_recorder: Callable[[object], str] | None = None,
) -> object:
    """Execute scoped candidates through existing sequential Core and route guards.

    The full message is sent ONLY to Router, once. On each unit, Temporal
    receives that unit's exact source if needed and the ordinary Core
    planner receives only that selected source + source-rebased candidate
    context. Core's predecessor handoff is guarded by actual canonical
    result evidence; ambiguous references never receive guessed identities.
    This test-only entry has no n8n/DEV registration or real vault selector.
    """
    from types import SimpleNamespace

    from odyssey_core.application import (
        ApplicationStatus,
        DependentReferenceGuard,
        execute_request,
    )
    from odyssey_core.candidate_attribution import (
        OpenAICoreCandidateAttributor,
        review_model_candidate_fact_coverage,
    )
    from odyssey_core.candidate_fact_readback import readback_core_facts
    from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
    from odyssey_core.request_planning import RequestPlan, WriteAction
    from odyssey_core.storage import VaultRepository
    from odyssey_runtime.routing import (
        DependentRouteHandoff,
        execute_routed_request,
        route_execution_id,
    )

    if not isinstance(repository, VaultRepository):
        raise ValueError("An explicitly bound canonical repository is required")
    if (candidate_coverage_factory is None) == (core_candidate_attributor is None):
        raise ValueError("Exactly one Core-owned coverage reviewer must be supplied")
    if core_candidate_attributor is not None:
        if not isinstance(core_candidate_attributor, OpenAICoreCandidateAttributor):
            raise ValueError("Use the existing Core fact graph reviewer")

        def coverage(text, context, plan, *, canonical_binding=None):
            return review_model_candidate_fact_coverage(
                text,
                context,
                plan,
                core_candidate_attributor,
                canonical_binding=canonical_binding,
            )
    else:
        coverage = candidate_coverage_factory
    if not callable(coverage) or not callable(core_planner_factory):
        raise ValueError("Core planner and coverage callbacks are required")
    if not callable(getattr(router, "propose", None)):
        raise ValueError("Original source requires a validated Router candidate adapter")
    proposal = router.propose(source)
    if not isinstance(proposal, FactCandidateProposal) or proposal.source != source:
        raise RouterError("Router did not preserve the original message")
    bundle = compile_candidate_route_bundle(proposal)
    outer_id = request_id_factory()
    if not isinstance(outer_id, str) or not outer_id.strip():
        raise ValueError("Outer request id must be non-empty")

    route_scopes = {
        route_execution_id(outer_id, ordinal): item for ordinal, item in enumerate(bundle.units)
    }

    def run_unit(
        unit_source: str,
        locator: str,
        _authenticated_actor: object = None,
        _prior_turns: object = (),
        *,
        dependent_handoff: object | None = None,
        conversation_context_override: object | None = None,
    ):
        # The existing v0 Core route executor passes prior-turn context as a
        # keyword. It must never be repurposed to carry sibling route text.
        if conversation_context_override is not None and _prior_turns not in ((), None):
            raise ValueError("Two competing route contexts are not allowed")
        scoped = route_scopes[locator]
        if scoped.route.source_text != unit_source:
            raise ValueError("Route source changed before Core interpretation")
        interpretation = None
        domain = None
        if scoped.route.capability_id == "temporal":
            if temporal is None or not callable(getattr(temporal, "interpret", None)):
                raise ValueError("Temporal resolution is unavailable for dated route")
            interpretation = temporal.interpret(unit_source)
            if interpretation.source_text != unit_source:
                raise ValueError("Temporal must interpret only its routed source")
            domain = interpretation.core_domain_interpretation()
        guard = None
        if dependent_handoff is not None:
            if not isinstance(dependent_handoff, DependentRouteHandoff):
                raise ValueError("Core dependency handoff is invalid")
            reference = dependent_handoff.evidence
            canonical = DomainEvidence(
                "canonical_reference",
                dependent_handoff.mention,
                f"{reference.note_type}:{reference.canonical_name}",
            )
            if domain is None:
                domain = DomainInterpretation(
                    "core", unit_source, "CANONICAL_REFERENCE", (canonical,)
                )
            else:
                domain = replace(domain, evidence=(*domain.evidence, canonical))
            guard = DependentReferenceGuard(dependent_handoff.mention, dependent_handoff.evidence)
        route_context = (
            resolve_scoped_reference_with_core_proof(scoped.context, guard, repository, schema)
            if guard is not None
            else scoped.context
        )
        planner = core_planner_factory(route_context, domain)
        if not callable(getattr(planner, "plan", None)):
            raise ValueError("Only the ordinary Core planner may interpret a scoped route")
        captured: dict[str, RequestPlan] = {}

        class RecordingCorePlanner:
            """Observe the original planner's output without changing its actions."""

            def plan(self, request):
                if request != unit_source:
                    raise ValueError("Core was given a sibling or full original message")
                result = planner.plan(request)
                if isinstance(result, RequestPlan):
                    captured["plan"] = result
                return result

            def __getattr__(self, name):
                return getattr(planner, name)

        result = execute_request(
            unit_source,
            planner=RecordingCorePlanner(),
            repository=repository,
            schema=schema,
            context_index=context_index,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            actor=actor,
            now=now,
            context_limit=context_limit,
            request_id_factory=lambda: locator,
            candidate_context=route_context,
            candidate_coverage_factory=(
                (lambda text, ctx, plan: coverage(text, ctx, plan, canonical_binding=guard))
                if core_candidate_attributor is not None
                else (
                    (lambda text, ctx, plan: coverage(text, ctx, plan, canonical_binding=guard))
                    if guard is not None
                    else coverage
                )
            ),
            candidate_pending_recorder=candidate_pending_recorder,
            write_preflight_guard=guard,
        )
        if result.status is ApplicationStatus.COMPLETED and "plan" in captured:
            plan = captured["plan"]
            if any(isinstance(action, WriteAction) for action in plan.actions):
                evidence = readback_core_facts(
                    unit_source,
                    route_context,
                    plan,
                    result,
                    repository,
                    schema,
                    incoming_reference=guard,
                )
                if not evidence.persisted_facts or any(
                    item.status != "verified_in_markdown" for item in evidence.persisted_facts
                ):
                    raise ValueError("Core's routed physical Markdown readback failed")
                # Rebuild only derived indexes, after the authoritative writer.
                # This test-only composition uses a disposable canonical vault.
                context_index.rebuild(repository, schema, embedder)
                semantic_index.rebuild(repository, schema, embedder)
        return result

    selected_router = SimpleNamespace(route=lambda current, _prior=(): bundle.plan)
    return execute_routed_request(
        user_request=source,
        outer_request_id=outer_id,
        router=selected_router,
        catalog=ApplicationCatalog.empty(),
        core_execute=run_unit,
        temporal_execute=run_unit,
        application_executors={},
    )
