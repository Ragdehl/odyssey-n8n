"""Non-default, provider-injected Router -> Temporal -> Core dependent-fact pilot.

This thin runtime assembly calls existing specialist adapters in their
normal order. Router proposes source spans, Temporal alone resolves date
phrases, and the existing Core planner alone decides the facts and targets.
It never makes a substitute application planner or grants Router write access.

Only an explicit private preview callback may use this assembly; neither
the HTTP endpoint nor normal routing instantiates it. The entire original
message and source evidence are independently revalidated before execution.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import FactCandidateProposal, OpenAIFactCandidateRouter
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_core.candidate_dependent_scope import preview_dependent_clause_scopes
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.request_planning import RequestPlan
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_core.temporal_resolution import TemporalResolutionKind


class CoreFactPlanner(Protocol):
    """Existing Core planner interface; no runtime semantic decisions."""

    def plan(self, request: str) -> object:
        """Return Core's current independently validated planning decision."""


@dataclass(frozen=True, slots=True)
class PreparedDependentCoreFacts:
    """Full original source, untouched Core context, independent Core plans."""

    source: str
    context: object
    plans: tuple[RequestPlan, RequestPlan]


class DependentCandidatePipeline:
    """Provider-injected experimental assembly for source-proven coordinated facts.

    A single user message must have exactly two source-validated candidates
    and satisfy the existing Core dependent-coordination preflight. Temporal
    runs on the full unchanged source only when Router reports a temporal
    source role; each selected exact date is carried to the selected Core
    request as a non-authoritative, Core-validated domain interpretation.

    The original Core planning schema, prompts, model and write guards
    remain owned by existing modules. No provider retry or write occurs
    in prepare().
    """

    def __init__(
        self,
        router: OpenAIFactCandidateRouter,
        temporal: OpenAITemporalInterpreter,
        core_planner_factory: Callable[[DomainInterpretation | None], CoreFactPlanner],
    ) -> None:
        if (
            not isinstance(router, OpenAIFactCandidateRouter)
            or not isinstance(temporal, OpenAITemporalInterpreter)
            or not callable(core_planner_factory)
        ):
            raise TypeError("Existing Router, Temporal and Core provider adapters are required")
        self._router = router
        self._temporal = temporal
        self._planner_factory = core_planner_factory

    def prepare(self, original_source: str) -> PreparedDependentCoreFacts:
        """Interpret one complete message without mutating canonical Notes.

        Fails closed before any Core planning when source structure is not
        proven, a temporal role cannot be grounded/exact, or a model
        returns anything other than one Core RequestPlan per source unit.
        """
        proposal: FactCandidateProposal = self._router.propose(original_source)
        if proposal.source != original_source:
            raise ValueError("Router rewrote the original message")
        context = to_core_candidate_context(proposal)
        scopes = preview_dependent_clause_scopes(original_source, context)
        temporal_scopes = {
            candidate.candidate_id
            for candidate in proposal.candidates
            if any(
                role.role in {"date", "date_scope", "time", "time_approx", "time_relation"}
                for role in candidate.scopes
            )
            or any(
                edge.role in {"date", "date_scope", "time", "time_approx", "time_relation"}
                for edge in candidate.inheritance
            )
        }
        interpretation = self._temporal.interpret(original_source) if temporal_scopes else None
        boundaries = bind_temporal_to_fact_candidates(proposal, interpretation)
        scoped_requests: list[tuple[str, DomainInterpretation | None]] = []
        for unit in scopes.units:
            source_edges = tuple(
                edge for edge in boundaries if edge.candidate_id == unit.candidate_id
            )
            if unit.candidate_id in temporal_scopes and not source_edges:
                raise ValueError("Temporal scope lost between Router and Core")
            evidences: list[DomainEvidence] = []
            for edge in source_edges:
                resolution = edge.resolution
                if (
                    edge.status != "matched"
                    or not edge.has_exact_source_shape
                    or resolution is None
                    or edge.role not in {"date", "time"}
                ):
                    raise ValueError(
                        "Unresolved or approximate temporal evidence cannot authorize Core"
                    )
                if edge.role == "date":
                    value = resolution.exact_date
                    if resolution.kind is TemporalResolutionKind.EXACT_DATETIME:
                        value = resolution.exact_datetime
                else:
                    value = resolution.exact_datetime
                if not isinstance(value, str) or not value:
                    raise ValueError("Temporal evidence has no canonical resolved value")
                if unit.selected_quote.find(edge.source.text) == -1:
                    # An inherited date can be meaningful, but it needs a
                    # separately reviewed scoped-context Core contract.
                    # Do not silently treat predecessor wording as a date
                    # introduced by the present selected clause.
                    raise ValueError("Inherited temporal source is not within selected unit")
                evidences.append(
                    DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, edge.source.text, value)
                )
            request = unit.planner_request()
            domain = (
                DomainInterpretation(
                    "temporal",
                    request,
                    "TEMPORAL_RESOLUTION",
                    tuple(evidences),
                )
                if evidences
                else None
            )
            scoped_requests.append((request, domain))
        # Resolve *all* original date and source scopes before paying for
        # any independent Core plan. An unresolved later source unit must
        # not allow an earlier orphan plan or unnecessary provider call.
        plans: list[RequestPlan] = []
        for request, domain in scoped_requests:
            planner = self._planner_factory(domain)
            plan = planner.plan(request)
            if not isinstance(plan, RequestPlan):
                raise ValueError("Core must independently plan this one selected fact")
            plans.append(plan)
        if len(plans) != 2:
            raise ValueError("Original source requires exactly two independently planned units")
        return PreparedDependentCoreFacts(original_source, context, (plans[0], plans[1]))
