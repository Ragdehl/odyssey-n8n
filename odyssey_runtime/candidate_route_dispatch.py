"""Route-local Router → optional Temporal → ordinary Core → verified Markdown.

Source-candidate splitting and typed provenance are implemented by the
independent source_scope_compiler, never by passing sibling source as a Core
request. The active DEV/PROD chat route is not modified.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from odyssey_apps.catalog import ApplicationCatalog
from odyssey_apps.fact_candidates import FactCandidateProposal
from odyssey_apps.router import RouterError
from odyssey_core.candidate_context import CoreCandidateContext
from odyssey_runtime.scoped_subject_handoff import ScopedCoreSubjectHandoff
from odyssey_runtime.scoped_temporal_handoff import (
    ScopedTemporalHandoff,
    with_scoped_inherited_temporal,
)
from odyssey_runtime.source_scope_compiler import (
    compile_candidate_route_bundle,
    validate_bundle_original_provenance,
)


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
    refreshed = replace(context, candidates=tuple(candidates))
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
    validate_bundle_original_provenance(bundle)
    outer_id = request_id_factory()
    if not isinstance(outer_id, str) or not outer_id.strip():
        raise ValueError("Outer request id must be non-empty")

    route_scopes = {
        route_execution_id(outer_id, ordinal): (ordinal, item)
        for ordinal, item in enumerate(bundle.units)
    }
    temporal_handoff = ScopedTemporalHandoff(source)
    subject_handoff = ScopedCoreSubjectHandoff(source)

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
        ordinal, scoped = route_scopes[locator]
        if scoped.route.source_text != unit_source:
            raise ValueError("Route source changed before Core interpretation")
        inherited = temporal_handoff.inherited(
            scoped.context,
            current_route_index=ordinal,
            start=scoped.original_start,
            end=scoped.original_end,
        )
        required_temporal_origins = {
            (role.original_start, role.original_end)
            for role in scoped.context.source_provenance
            if role.role in {"date", "date_scope", "time", "time_approx"}
        }
        proven_temporal_origins = {
            (proof.original_start, proof.original_end) for proof in inherited
        }
        if required_temporal_origins - proven_temporal_origins:
            from odyssey_core.temporal_interpretation import TemporalInterpreterError

            raise TemporalInterpreterError(
                "Inherited temporal scope has no verified earlier Temporal result"
            )
        interpretation = None
        domain = None
        if scoped.route.capability_id == "temporal":
            if temporal is None or not callable(getattr(temporal, "interpret", None)):
                raise ValueError("Temporal resolution is unavailable for dated route")
            if inherited:
                interpretation = temporal.interpret(unit_source, inherited_temporal=inherited)
            else:
                interpretation = temporal.interpret(unit_source)
            if interpretation.source_text != unit_source:
                raise ValueError("Temporal must interpret only its routed source")
            domain = interpretation.core_domain_interpretation()
            temporal_handoff.remember(
                interpretation,
                route_index=ordinal,
                start=scoped.original_start,
                end=scoped.original_end,
            )
        domain = with_scoped_inherited_temporal(domain, source=unit_source, inherited=inherited)
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
        subject = subject_handoff.inherit(
            context=scoped.context,
            route_index=ordinal,
            start=scoped.original_start,
            end=scoped.original_end,
            repository=repository,
            schema=schema,
        )
        if subject is not None and guard is not None:
            raise ValueError("Mixed canonical subject and reference guards require explicit review")
        # Lexical Router reuse of a predicate, object or transaction is not
        # Core-certified event evidence. Never infer a second participant\u0027s
        # action solely from a shared source verb. Same-target elliptical
        # properties can use the separately persisted Core subject/fact guard;
        # changed-subject continuations need a future independently reviewed
        # Core predecessor-event carrier and must not write yet.
        inherited_fact_roles = {
            role.role
            for role in scoped.context.source_provenance
            if role.role in {"predicate", "predicate_relation", "object", "transaction"}
        }
        if inherited_fact_roles and subject is None:
            raise ValueError("Inherited predicate requires Core-verified predecessor fact")
        route_context = (
            resolve_scoped_reference_with_core_proof(scoped.context, guard, repository, schema)
            if guard is not None
            else scoped.context
        )
        if subject is not None:
            route_context = replace(route_context, verified_inherited_subject=subject)
            route_context.validate(unit_source)
        from odyssey_core.scoped_subject_evidence import CoreInheritedSubjectWriteGuard

        subject_guard = CoreInheritedSubjectWriteGuard(subject) if subject is not None else None
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
            write_preflight_guard=subject_guard or guard,
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
                subject_handoff.remember(
                    context=route_context,
                    plan=plan,
                    result=result,
                    readback=evidence,
                    repository=repository,
                    schema=schema,
                    start=scoped.original_start,
                    end=scoped.original_end,
                    route_index=ordinal,
                )
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
