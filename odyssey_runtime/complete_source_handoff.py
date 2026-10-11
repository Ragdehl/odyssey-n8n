"""Read-only handoff of a complete Router/Temporal message to ordinary Core.

A Router candidate is evidence about original source wording, not a Core fact,
action or Note. This adapter never partitions the original message into
independently planned mini-requests. Core receives *all* the source, all source
hints, and separately computed Temporal evidence in its normal one-shot
planning interface. Only Core's existing execute_request/coverage checks may
later authorize writes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import FactCandidateProposal
from odyssey_apps.fact_temporal import CandidateTemporalEvidence, bind_temporal_to_fact_candidates
from odyssey_core.candidate_context import CoreCandidateContext
from odyssey_core.candidate_dependencies import (
    CoreDependencyUnit,
    trace_core_candidate_dependencies,
)
from odyssey_core.domain_interpretation import DomainInterpretation
from odyssey_core.temporal_interpretation import TemporalInterpretation


class CandidateSourceRouter(Protocol):
    """Existing Router may only propose source-grounded candidate roles."""

    def propose(self, source: str) -> FactCandidateProposal:
        """Return source evidence for the exact entire user message."""


class SourceTemporalInterpreter(Protocol):
    """Temporal reads the whole original message independently of Router."""

    def interpret(self, source: str) -> TemporalInterpretation:
        """Return verified temporal mentions or an empty interpretation."""


class OrdinaryCorePlanner(Protocol):
    """Existing Core planner, not an application-specific planning substitute."""

    def plan(self, request: str) -> object:
        """Interpret the complete original request in Core."""


@dataclass(frozen=True, slots=True)
class CompleteSourceEvidence:
    """Untrusted source-role hints plus separately validated temporal output."""

    source: str
    context: CoreCandidateContext
    dependency_trace: tuple[CoreDependencyUnit, ...]
    temporal_interpretation: TemporalInterpretation | None
    temporal_bindings: tuple[CandidateTemporalEvidence, ...]
    domain_interpretation: DomainInterpretation | None

    def validate(self) -> None:
        """Recheck full-source identity and every source-dependent role."""
        self.context.validate(self.source)
        if self.dependency_trace != trace_core_candidate_dependencies(self.source, self.context):
            raise ValueError("Source role dependency trace is stale or mismatched")
        # Router only *locates* possible time wording. Temporal alone
        # normalizes it, and its whole-message interpretation is separate.
        from odyssey_apps.fact_temporal import TEMPORAL_SOURCE_ROLES

        expected = tuple(
            (
                unit.candidate_id,
                role.role,
                role.span.start,
                role.span.end,
                role.inherited,
            )
            for unit in self.dependency_trace
            for role in unit.roles
            if role.role in TEMPORAL_SOURCE_ROLES
        )
        bound = tuple(
            (
                binding.candidate_id,
                binding.role,
                binding.source.start,
                binding.source.end,
                binding.origin == "inherited",
            )
            for binding in self.temporal_bindings
        )
        if expected != bound:
            raise ValueError("Temporal roles were lost, added or assigned to another source unit")
        if self.temporal_interpretation is None:
            if expected or self.domain_interpretation is not None:
                raise ValueError("Source time roles need the independent Temporal interpreter")
        else:
            if self.temporal_interpretation.source_text != self.source:
                raise ValueError("Temporal interpretation does not match the original message")
            if (
                self.domain_interpretation
                != self.temporal_interpretation.core_domain_interpretation()
            ):
                raise ValueError("Core temporal evidence differs from the original interpretation")
            mentions = tuple(
                (mention.temporal_text, mention.resolution)
                for mention in self.temporal_interpretation.mentions
            )
            for binding in self.temporal_bindings:
                if self.source[binding.source.start : binding.source.end] != binding.source.text:
                    raise ValueError("Temporal role is not an original source span")
                if (
                    binding.status == "matched"
                    and (binding.temporal_text, binding.resolution) not in mentions
                ):
                    raise ValueError("Temporal role claims an unverified normalized time")
                if binding.status == "missing" and (
                    binding.temporal_text is not None or binding.resolution is not None
                ):
                    raise ValueError("Unresolved temporal role contains invented evidence")


def collect_complete_source_evidence(
    source: str,
    *,
    router: CandidateSourceRouter,
    temporal: SourceTemporalInterpreter | None = None,
) -> CompleteSourceEvidence:
    """Collect N Router candidates and independently interpret whole-source time.

    No linguistic punctuation, conjunction, candidate kind or source count
    controls which plan Core may eventually produce. Technical source length
    and candidate-count caps still belong to existing source contracts.

    Args:
        source: Exact original user message.
        router: Existing non-authoritative candidate-producing Router.
        temporal: Optional independent full-source Temporal capability.
            When supplied, it runs on the original message regardless of
            which temporal roles Router did or did not spot.

    Returns:
        Read-only source evidence. Missing/approximate dates are retained as
        evidence, never silently turned into exact dates or write authority.

    Raises:
        ValueError: Altered/unverified source, role inheritance or clock link.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError("An unchanged, nonempty user message is required")
    proposal = router.propose(source)
    if not isinstance(proposal, FactCandidateProposal) or proposal.source != source:
        raise ValueError("Router did not preserve the original user message")
    context = to_core_candidate_context(proposal)
    context.validate(source)
    trace = trace_core_candidate_dependencies(source, context)
    interpretation = temporal.interpret(source) if temporal is not None else None
    if interpretation is not None and (
        not isinstance(interpretation, TemporalInterpretation)
        or interpretation.source_text != source
    ):
        raise ValueError("Temporal returned evidence for a different user message")
    bindings = bind_temporal_to_fact_candidates(proposal, interpretation)
    domain = interpretation.core_domain_interpretation() if interpretation is not None else None
    evidence = CompleteSourceEvidence(source, context, trace, interpretation, bindings, domain)
    evidence.validate()
    return evidence


def plan_complete_source_with_core(
    evidence: CompleteSourceEvidence,
    *,
    core_planner_factory: Callable[
        [CoreCandidateContext, DomainInterpretation | None], OrdinaryCorePlanner
    ],
) -> object:
    """Invoke the SAME ordinary Core planner exactly once on the whole source.

    The factory supplies Core's existing model/prompt and passes validated
    context and Temporal evidence to it. A candidate is not required to
    yield one Core action or fact; clarification/escalation remain possible.
    Neither this function nor Router authorizes writes or fabricates a plan.
    """
    if not isinstance(evidence, CompleteSourceEvidence):
        raise ValueError("Core requires validated complete source evidence")
    evidence.validate()
    if not callable(core_planner_factory):
        raise ValueError("Ordinary Core planner factory is required")
    planner = core_planner_factory(evidence.context, evidence.domain_interpretation)
    if not callable(getattr(planner, "plan", None)):
        raise ValueError("Ordinary Core planner interface is missing")
    return planner.plan(evidence.source)


def execute_complete_source_with_core(
    evidence: CompleteSourceEvidence,
    *,
    core_planner_factory: Callable[
        [CoreCandidateContext, DomainInterpretation | None], OrdinaryCorePlanner
    ],
    candidate_coverage_factory: Callable[..., object],
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
    """Execute the whole request through the EXISTING Core Planner and Writer.

    This is an inactive, explicitly injected integration entry for isolated
    end-to-end testing. It does not register a new public route, rebuild Core,
    make a second semantic plan or decide a candidate->fact mapping.

    The independently supplied Core review must account for all candidates
    and all planned facts. Crucially, the integrator MUST NOT synthesize one
    coverage claim per Router candidate or derive claim ordinals from Router
    order. Core's existing prewrite validator refuses absent, false, or
    semantically unsupported mappings BEFORE any canonical write. This
    currently means some otherwise legitimate complex requests remain
    unwriteable pending the general Core coverage review, not silently lost.
    """
    from odyssey_core.application import execute_request
    from odyssey_core.storage import VaultRepository

    if not isinstance(evidence, CompleteSourceEvidence):
        raise ValueError("Validated whole-message evidence required")
    evidence.validate()
    if not callable(core_planner_factory) or not callable(candidate_coverage_factory):
        raise ValueError("Original Core planner and independent Core coverage review required")
    if not isinstance(repository, VaultRepository):
        raise ValueError("Core requires an explicitly bound canonical repository")
    planner = core_planner_factory(evidence.context, evidence.domain_interpretation)
    if not callable(getattr(planner, "plan", None)):
        raise ValueError("Existing Core planner is unavailable")
    # Same validated Planner -> identity/preflight -> Writer as all ordinary
    # Odyssey requests. Core, not this handoff, controls whether any write is safe.
    return execute_request(
        evidence.source,
        planner=planner,
        repository=repository,
        schema=schema,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=contextual_reasoner,
        actor=actor,
        now=now,
        context_limit=context_limit,
        request_id_factory=request_id_factory,
        candidate_context=evidence.context,
        candidate_coverage_factory=candidate_coverage_factory,
        candidate_pending_recorder=candidate_pending_recorder,
    )


def execute_complete_message_with_core(
    source: str,
    *,
    router: CandidateSourceRouter,
    temporal: SourceTemporalInterpreter,
    core_planner_factory: Callable[
        [CoreCandidateContext, DomainInterpretation | None], OrdinaryCorePlanner
    ],
    candidate_coverage_factory: Callable[..., object] | None = None,
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
    """Run the existing entire-message adapters as one isolated vertical entry.

    This is only composition: it adds no semantic branch, planner, candidate
    ownership rule, fallback, public HTTP route or deployment registration.
    Router and Temporal each receive the original full source; ordinary Core
    interprets it once, then the existing coverage and Writer gates execute.

    Accepts the independent existing Core model attributor OR a previously
    verified review callback. Proposed model edges must pass the unchanged
    Core prewrite validator; neither route ordinals nor output order can
    silently determine semantic ownership. Callers must supply an isolated repository
    while evaluating this inactive integration.
    """
    if (candidate_coverage_factory is None) == (core_candidate_attributor is None):
        raise ValueError("Independent Core coverage review required: provide exactly one source")
    if core_candidate_attributor is not None:
        from odyssey_core.candidate_attribution import (
            OpenAICoreCandidateAttributor,
            review_model_candidate_fact_coverage,
        )

        if not isinstance(core_candidate_attributor, OpenAICoreCandidateAttributor):
            raise ValueError("Use the existing independent Core candidate attributor")

        def model_review(source: str, context: CoreCandidateContext, plan: object) -> object:
            return review_model_candidate_fact_coverage(
                source, context, plan, core_candidate_attributor
            )

        candidate_coverage_factory = model_review
    evidence = collect_complete_source_evidence(
        source,
        router=router,
        temporal=temporal,
    )
    return execute_complete_source_with_core(
        evidence,
        core_planner_factory=core_planner_factory,
        candidate_coverage_factory=candidate_coverage_factory,
        repository=repository,
        schema=schema,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=contextual_reasoner,
        actor=actor,
        now=now,
        context_limit=context_limit,
        request_id_factory=request_id_factory,
        candidate_pending_recorder=candidate_pending_recorder,
    )
