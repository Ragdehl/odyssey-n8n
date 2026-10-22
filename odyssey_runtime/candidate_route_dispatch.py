"""Route-local Router → optional Temporal → ordinary Core → verified Markdown.

Source-candidate splitting and typed provenance are implemented by the
independent source_scope_compiler, never by passing sibling source as a Core
request. The active DEV/PROD chat route is not modified.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import replace
from time import perf_counter

from odyssey_apps.catalog import ApplicationCatalog
from odyssey_apps.fact_candidates import FactCandidateProposal
from odyssey_apps.router import Route, RouterError
from odyssey_core.application import ApplicationResult
from odyssey_core.candidate_context import CoreCandidateContext
from odyssey_core.candidate_correction_chain import correction_chain
from odyssey_core.candidate_sensitive_statement import supports_sensitive_literal_candidates
from odyssey_core.execution_context import ExecutionContext
from odyssey_core.git_history import HistoryRecorder
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalStage,
    normalize_provider_usage,
)
from odyssey_core.source_boundary_review import (
    CoreSourceBoundaryInput,
    CoreSourceBoundaryReview,
    CoreSourceBoundaryUnit,
    SourceBoundaryReviewError,
)
from odyssey_runtime.application_bindings import bind_registered_executors
from odyssey_runtime.context_planner_ports import ContextAwareCorePlannerFactory
from odyssey_runtime.registered_scoped_app import (
    RegisteredScopedApp,
    registered_app_index,
)
from odyssey_runtime.scoped_event_handoff import ScopedCoreEventHandoff
from odyssey_runtime.scoped_route_authority import (
    ScopedRouteAuthority,
    missing_inherited_temporal_spans,
)
from odyssey_runtime.scoped_subject_handoff import ScopedCoreSubjectHandoff
from odyssey_runtime.scoped_temporal_handoff import (
    ScopedTemporalHandoff,
    with_scoped_inherited_temporal,
)
from odyssey_runtime.source_scope_compiler import (
    compile_candidate_route_bundle,
    validate_bundle_original_provenance,
)


def _build_core_source_boundary_input(
    source: str, proposal: FactCandidateProposal, bundle: object
) -> CoreSourceBoundaryInput:
    """Project Router's source-only assertions into a Core-owned review envelope."""
    original_to_index = {
        candidate.candidate_id: index for index, candidate in enumerate(proposal.candidates)
    }
    units = []
    for scoped in bundle.units:
        chosen = [original_to_index[cid] for cid in scoped.original_candidate_ids]
        units.append(
            CoreSourceBoundaryUnit(
                scoped.original_start,
                scoped.original_end,
                scoped.route.capability_id,
                tuple(proposal.candidates[i].kind for i in chosen),
                tuple(proposal.semantic_relations[i].kind for i in chosen),
            )
        )
    context = CoreSourceBoundaryInput(source, tuple(units))
    context.validate()
    return context


def review_router_source_before_writes(
    source: str,
    proposal: FactCandidateProposal,
    bundle: object,
    *,
    router: object,
    bundle_compiler: Callable[[FactCandidateProposal], object],
    boundary_reviewer: object | None,
    telemetry_callback: Callable[[str, object, float, bool], None] | None = None,
) -> object:
    """One prewrite Core review and at most ONE bounded Router correction.

    An unsafe split is rejected before Temporal, Planner, Apps, or Markdown
    mutation. Core's final candidate/fact validation remains independent.
    Router's revised source must be the EXACT same immutable user request.
    """
    if proposal.contract_version != 2:
        return bundle
    if boundary_reviewer is None:
        if len(bundle.units) > 1:
            raise SourceBoundaryReviewError("CORE_SOURCE_BOUNDARY_REVIEW_UNAVAILABLE")
        return bundle
    reviewer = getattr(boundary_reviewer, "review", None)
    if not callable(reviewer):
        raise SourceBoundaryReviewError("CORE_SOURCE_BOUNDARY_REVIEW_UNAVAILABLE")
    for attempt in range(2):
        if len(bundle.units) <= 1:
            return bundle  # No cross-route boundary; Core still reviews each planned fact.
        context = _build_core_source_boundary_input(source, proposal, bundle)
        review_started = perf_counter()
        try:
            decision = reviewer(context)
        except Exception:
            if telemetry_callback is not None:
                telemetry_callback(
                    "candidate.source_boundary_review",
                    boundary_reviewer,
                    max(0.0, (perf_counter() - review_started) * 1000),
                    False,
                )
            raise
        if telemetry_callback is not None:
            telemetry_callback(
                "candidate.source_boundary_review",
                boundary_reviewer,
                max(0.0, (perf_counter() - review_started) * 1000),
                True,
            )
        if not isinstance(decision, CoreSourceBoundaryReview):
            raise SourceBoundaryReviewError("CORE_SOURCE_BOUNDARY_REVIEW_INVALID")
        decision.validate(context)
        if decision.decision == "accept":
            return bundle
        if decision.decision == "needs_attention":
            raise SourceBoundaryReviewError("CORE_SOURCE_BOUNDARY_NEEDS_CLARIFICATION")
        # Reviewer is asking the original Router to REVISE only the affected
        # source boundary; Router receives no canonical IDs or written notes.
        if attempt or not callable(getattr(router, "revise", None)):
            raise SourceBoundaryReviewError("CORE_SOURCE_BOUNDARY_REVISION_REQUIRED")
        revision_started = perf_counter()
        try:
            amended = router.revise(source, decision)
        except Exception:
            if telemetry_callback is not None:
                telemetry_callback(
                    "candidate.router_revision",
                    router,
                    max(0.0, (perf_counter() - revision_started) * 1000),
                    False,
                )
            raise
        if telemetry_callback is not None:
            telemetry_callback(
                "candidate.router_revision",
                router,
                max(0.0, (perf_counter() - revision_started) * 1000),
                True,
            )
        if (
            not isinstance(amended, FactCandidateProposal)
            or amended.contract_version != 2
            or amended.source != source
        ):
            raise SourceBoundaryReviewError("CORE_SOURCE_BOUNDARY_REVISION_INVALID")
        proposal = amended
        bundle = bundle_compiler(amended)
    raise SourceBoundaryReviewError("CORE_SOURCE_BOUNDARY_REVISION_REQUIRED")


def _suppress_ambiguous_single_handoff(
    context: CoreCandidateContext,
    successor: Route | None,
    predecessor_ordinal: int,
    result: ApplicationResult,
) -> ApplicationResult:
    """Never promote a sole canonical proof when several source participants compete.

    Alias-derived references may be omitted from a private handoff even when
    the physical Markdown fact safely links them. One surviving proof is not
    authority to choose the later singular pronoun. Do not alter the write
    receipt or verified canonical content; only withhold its unsafe carrier.
    """
    if (
        successor is None
        or successor.depends_on != predecessor_ordinal
        or len(result.canonical_reference_evidence) != 1
    ):
        return result
    participants = {
        (role.span.start, role.span.end)
        for candidate in context.candidates
        for role in candidate.roles
        if role.role == "participants"
    }
    return replace(result, canonical_reference_evidence=()) if len(participants) > 1 else result


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
    core_planner_factory: (
        Callable[[CoreCandidateContext, object | None], object] | ContextAwareCorePlannerFactory
    ),
    candidate_coverage_factory: Callable[[str, CoreCandidateContext, object], object] | None = None,
    core_candidate_attributor: object | None = None,
    known_fact_verifier: object | None = None,
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
    history_recorder: HistoryRecorder | None = None,
    candidate_pending_recorder: Callable[[object], str] | None = None,
    route_ambiguity_recorder: Callable[[object, tuple[object, ...]], str] | None = None,
    bundle_compiler: Callable[[FactCandidateProposal], object] | None = None,
    task_route_executor: object | None = None,
    event_route_executor: object | None = None,
    registered_scoped_apps: tuple[RegisteredScopedApp, ...] = (),
    progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    postwrite_index_refresh: Callable[[Sequence[str]], None] | None = None,
    source_boundary_reviewer: object | None = None,
    authenticated_actor: AuthenticatedActorContext | None = None,
    self_binding_repository: SelfBindingRepository | None = None,
    conversation_context: Sequence[Mapping[str, str]] = (),
) -> object:
    """Execute scoped candidates through existing sequential Core and route guards.

    The full message is sent ONLY to Router, once. On each unit, Temporal
    receives that unit's exact source if needed and the ordinary Core
    planner receives only that selected source + source-rebased candidate
    context. Core's predecessor handoff is guarded by actual canonical
    result evidence; ambiguous references never receive guessed identities.
    The dispatcher itself has no ambient n8n/DEV registration or vault
    selector.  A composition root may inject it only after explicitly binding
    an authenticated DEV actor, conversation, repository, and pending-state
    recorder. Authenticated identity, its trusted self binding, and prior
    conversation context are optional composition-root inputs. They are
    transported unchanged to Core; Router source candidates never establish
    either identity or conversation authority.
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
    from odyssey_core.candidate_dependencies import CandidateDependencyError
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
    if authenticated_actor is not None and not isinstance(
        authenticated_actor, AuthenticatedActorContext
    ):
        raise ValueError("authenticated actor context is invalid")
    if authenticated_actor is not None and (
        not isinstance(actor, Mapping)
        or set(actor) != {"human", "app"}
        or actor["human"] != authenticated_actor.stable_user_id
        or not isinstance(actor["app"], str)
        or not actor["app"].strip()
    ):
        raise ValueError("authenticated actor does not match persistence provenance")
    if self_binding_repository is not None and not isinstance(
        self_binding_repository, SelfBindingRepository
    ):
        raise ValueError("self binding repository is invalid")
    if (candidate_coverage_factory is None) == (core_candidate_attributor is None):
        raise ValueError("Exactly one Core-owned coverage reviewer must be supplied")
    if core_candidate_attributor is not None:
        if not isinstance(core_candidate_attributor, OpenAICoreCandidateAttributor):
            raise ValueError("Use the existing Core fact graph reviewer")

        def coverage(
            text,
            context,
            plan,
            *,
            canonical_binding=None,
            verified_temporal=None,
            qualitative_context=None,
        ):
            return review_model_candidate_fact_coverage(
                text,
                context,
                plan,
                core_candidate_attributor,
                canonical_binding=canonical_binding,
                verified_temporal=verified_temporal,
                qualitative_context=qualitative_context,
            )
    else:
        coverage = candidate_coverage_factory
    if not callable(coverage) or not (
        callable(core_planner_factory)
        or isinstance(core_planner_factory, ContextAwareCorePlannerFactory)
    ):
        raise ValueError("Core planner and coverage callbacks are required")
    if not callable(getattr(router, "propose", None)):
        raise ValueError("Original source requires a validated Router candidate adapter")

    def report_progress(stage: str, payload: dict[str, object] | None = None) -> None:
        """Publish an observed lifecycle boundary without changing route execution."""
        if progress_callback is None:
            return
        try:
            progress_callback(stage, payload or {})
        except Exception:
            return

    candidate_started = perf_counter()
    prewrite_stages: list[OperationalStage] = []

    def completed_with_wall(result: ApplicationResult) -> ApplicationResult:
        """Measure the full source→Core envelope without inferring local stage offsets."""
        return replace(
            result,
            operational=replace(
                result.operational,
                total_duration_ms=max(0.0, (perf_counter() - candidate_started) * 1000),
            ),
        )

    def record_provider_stage(name: str, provider: object, duration_ms: float, ok: bool) -> None:
        """Keep bounded provider evidence without source text or decision traces."""
        model = getattr(provider, "model", None)
        if model is None and name in {"candidate.source_proposal", "candidate.router_revision"}:
            from odyssey_apps.router import ROUTER_MODEL

            model = ROUTER_MODEL
        prewrite_stages.append(
            OperationalStage(
                name,
                OperationalOutcome.COMPLETED if ok else OperationalOutcome.FAILED,
                duration_ms,
                model=model,
                reasoning_effort=getattr(provider, "reasoning_effort", None),
                usage=normalize_provider_usage(getattr(provider, "last_usage", None)),
                error_category=(
                    None
                    if ok
                    else getattr(provider, "last_error_category", None) or "ProviderError"
                ),
            )
        )

    def reject_unrepresentable_source(stage_name: str, error: Exception, started: float):
        """Return a safe typed NO-WRITE outcome with the real failure category.

        An unproven Router inheritance or impossible source partition cannot
        reach Core and must not become an opaque HTTP error, a guessed write,
        or an unlimited model retry. No user text or provider message escapes.
        """
        failed_stage = OperationalStage(
            stage_name,
            OperationalOutcome.FAILED,
            max(0.0, (perf_counter() - started) * 1000),
            error_category=type(error).__name__[:100],
        )
        blocked = ApplicationResult(
            request_id_factory(),
            ApplicationStatus.NEEDS_ATTENTION,
            (),
            (),
            clarification_code="CANDIDATE_SOURCE_COMPILATION_UNREPRESENTABLE",
            planning_error=(
                "SOURCE_DEPENDENCY_UNVERIFIED"
                if type(error).__name__ == "CandidateDependencyError"
                else "SOURCE_PROVENANCE_UNREPRESENTABLE"
            ),
        )
        report_progress("routing.boundary_review_required")
        return completed_with_wall(
            replace(
                blocked,
                operational=replace(blocked.operational, stages=(*prewrite_stages, failed_stage)),
            )
        )

    report_progress("routing.started")
    router_started = perf_counter()
    try:
        proposal = router.propose(source)
    except RouterError as error:
        record_provider_stage(
            "candidate.source_proposal",
            router,
            max(0.0, (perf_counter() - router_started) * 1000),
            False,
        )
        if source_boundary_reviewer is None:
            raise
        return reject_unrepresentable_source("application.router", error, router_started)
    record_provider_stage(
        "candidate.source_proposal",
        router,
        max(0.0, (perf_counter() - router_started) * 1000),
        True,
    )
    if not isinstance(proposal, FactCandidateProposal) or proposal.source != source:
        raise RouterError("Router did not preserve the original message")
    # The default strict atomic route compiler is unchanged. The explicit
    # opt-in hybrid compiler may group multiple candidates into one *source*
    # request, never into one forced mutation or canonical identity.
    # Resolve the default at call time: historical frozen-reply tests can
    # inject their exact previous compiler without changing new hybrid logic.
    compiler = bundle_compiler or compile_candidate_route_bundle
    compiler_started = perf_counter()
    try:
        bundle = compiler(proposal)
    except (RouterError, CandidateDependencyError) as error:
        if proposal.contract_version != 2:
            raise
        return reject_unrepresentable_source(
            "candidate.source_compilation", error, compiler_started
        )
    if proposal.contract_version == 2:
        # This happens BEFORE a route-local planner or mutator can run.
        # Do not let a missing reviewer silently authorize an independent split.
        report_progress("routing.boundary_review_started")
        try:
            bundle = review_router_source_before_writes(
                source,
                proposal,
                bundle,
                router=router,
                bundle_compiler=compiler,
                boundary_reviewer=source_boundary_reviewer,
                telemetry_callback=record_provider_stage,
            )
        except SourceBoundaryReviewError as error:
            # Only expose stable, source-free diagnostic categories. Never
            # forward arbitrary provider exceptions or free-text model output.
            allowed_detail = {
                "CORE_SOURCE_BOUNDARY_REVIEW_UNAVAILABLE",
                "CORE_SOURCE_BOUNDARY_REVIEW_INVALID",
                "CORE_SOURCE_BOUNDARY_NEEDS_CLARIFICATION",
                "CORE_SOURCE_BOUNDARY_REVISION_REQUIRED",
                "CORE_SOURCE_BOUNDARY_REVISION_INVALID",
            }
            safe_detail = (
                str(error) if str(error) in allowed_detail else "CORE_SOURCE_BOUNDARY_REVIEW_FAILED"
            )
            report_progress("routing.boundary_review_required")
            blocked = ApplicationResult(
                request_id_factory(),
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                clarification_code="CORE_SOURCE_BOUNDARY_REVIEW_REQUIRED",
                planning_error=safe_detail,
            )
            return completed_with_wall(
                replace(
                    blocked, operational=replace(blocked.operational, stages=tuple(prewrite_stages))
                )
            )
        report_progress("routing.boundary_review_ready")
    report_progress("routing.ready", {"route_count": len(bundle.plan.routes)})
    uses_tasks = any(route.capability_id == "tasks" for route in bundle.plan.routes)
    uses_events = any(route.capability_id == "events" for route in bundle.plan.routes)
    registered_extra = registered_app_index(registered_scoped_apps)
    app_kinds = {
        "tasks": "task",
        "events": "event",
        **{app_id: app.candidate_kind for app_id, app in registered_extra.items()},
    }
    routed_extra = {
        route.capability_id
        for route in bundle.plan.routes
        if route.capability_id in registered_extra
    }
    if uses_tasks or uses_events or routed_extra:
        from odyssey_runtime.hybrid_group_compiler import hybrid_enabled_app_catalog

        if bundle_compiler is None or any(
            not scoped.context.hybrid_interpretation_mode
            or not all(
                candidate.kind == app_kinds[scoped.route.capability_id]
                and candidate.state == "candidate"
                for candidate in scoped.context.candidates
            )
            for scoped in bundle.units
            if scoped.route.capability_id in app_kinds
        ):
            raise RouterError("App routing requires validated source-only app groups")
        catalog = hybrid_enabled_app_catalog(
            enable_tasks=uses_tasks,
            enable_events=uses_events,
            registered_apps=tuple(
                app for app_id, app in registered_extra.items() if app_id in routed_extra
            ),
        )
    else:
        catalog = ApplicationCatalog.empty()
    validate_bundle_original_provenance(bundle, catalog=catalog)
    if task_route_executor is not None and not (
        callable(task_route_executor)
        or callable(getattr(task_route_executor, "execute_scoped", None))
    ):
        raise ValueError("Tasks execution must be a trusted application executor")
    if event_route_executor is not None and not callable(event_route_executor):
        raise ValueError("Events execution must be a trusted application executor")
    outer_id = request_id_factory()
    if not isinstance(outer_id, str) or not outer_id.strip():
        raise ValueError("Outer request id must be non-empty")

    route_scopes = {
        route_execution_id(outer_id, ordinal): (ordinal, item)
        for ordinal, item in enumerate(bundle.units)
    }
    route_authority = ScopedRouteAuthority(
        source, route_scopes, authenticated_actor, tuple(conversation_context)
    )
    temporal_handoff = ScopedTemporalHandoff(source)
    subject_handoff = ScopedCoreSubjectHandoff(source)
    event_handoff = ScopedCoreEventHandoff(source)

    def run_task_route(
        unit_source: str,
        locator: str,
        authenticated_actor: object = None,
        prior_turns: object = (),
    ):
        """Invoke an optional Tasks scoped hook without changing ordinary executors."""
        from odyssey_apps.tasks import TaskScopedEvidence, TaskScopedExecution
        from odyssey_core.temporal_interpretation import TemporalInterpretation

        ordinal, scoped = route_authority.verify(
            source=unit_source,
            locator=locator,
            capability="tasks",
            actor=authenticated_actor,
            conversation=prior_turns,
        )
        inherited = temporal_handoff.inherited(
            scoped.context,
            current_route_index=ordinal,
            start=scoped.original_start,
            end=scoped.original_end,
        )
        scoped_execute = getattr(task_route_executor, "execute_scoped", None)
        if missing_inherited_temporal_spans(scoped.context, inherited):
            if not callable(scoped_execute):
                from odyssey_core.application import ApplicationResult

                return ApplicationResult(
                    locator,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="TASK_SCOPED_TEMPORAL_EVIDENCE_UNSUPPORTED",
                )
            raise ValueError("Inherited Task date has no verified earlier Temporal result")
        evidence = TaskScopedEvidence(
            unit_source,
            hashlib.sha256(source.encode("utf-8")).hexdigest(),
            ordinal,
            inherited,
            tuple(role for role in scoped.context.source_provenance if role.role == "modality"),
        )
        evidence.validate(source)
        if callable(scoped_execute):
            report_progress("planner.started")
            receipt = scoped_execute(
                unit_source, locator, authenticated_actor, prior_turns, scoped_evidence=evidence
            )
            report_progress("planner.ready")
            if not isinstance(receipt, TaskScopedExecution):
                raise ValueError("Scoped Tasks executor returned an invalid receipt")
            interpretation = receipt.temporal_interpretation
            local_temporal = any(
                role.role in {"date", "date_scope", "time", "time_approx"}
                for candidate in scoped.context.candidates
                for role in candidate.roles
            )
            if local_temporal and not isinstance(interpretation, TemporalInterpretation):
                raise ValueError("Task route omitted its actual local Temporal interpretation")
            if interpretation is not None:
                temporal_handoff.remember(
                    interpretation,
                    route_index=ordinal,
                    start=scoped.original_start,
                    end=scoped.original_end,
                )
            return receipt.result
        if inherited:
            # Retain the ordinary four-argument executor contract, but do not
            # let an executor that cannot receive typed proof act on a date it
            # cannot distinguish from lexical Router context.
            from odyssey_core.application import ApplicationResult

            return ApplicationResult(
                locator,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="TASK_SCOPED_TEMPORAL_EVIDENCE_UNSUPPORTED",
            )
        if not callable(task_route_executor):
            raise ValueError("Tasks executor lacks its ordinary execution callback")
        report_progress("planner.started")
        result = task_route_executor(unit_source, locator, authenticated_actor, prior_turns)
        report_progress("planner.ready")
        return result

    def run_event_route(
        unit_source: str,
        locator: str,
        routed_authenticated_actor: AuthenticatedActorContext | None = None,
        routed_prior_turns: Sequence[Mapping[str, str]] = (),
    ) -> ApplicationResult:
        ordinal, scoped = route_authority.verify(
            source=unit_source,
            locator=locator,
            capability="events",
            actor=routed_authenticated_actor,
            conversation=routed_prior_turns,
        )
        if event_route_executor is None:
            raise ValueError("Events executor unavailable")
        inherited = temporal_handoff.inherited(
            scoped.context,
            current_route_index=ordinal,
            start=scoped.original_start,
            end=scoped.original_end,
        )
        if inherited:
            # Do not silently reinterpret a scoped clock from a prior route:
            # future Events integration must explicitly consume the E2 proof.
            return ApplicationResult(
                locator,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="EVENT_SCOPED_TEMPORAL_EVIDENCE_UNSUPPORTED",
            )
        report_progress("events.started")
        result = event_route_executor(
            unit_source, locator, routed_authenticated_actor, routed_prior_turns
        )
        report_progress("events.ready")
        return result

    def run_unit(
        unit_source: str,
        locator: str,
        routed_authenticated_actor: AuthenticatedActorContext | None = None,
        routed_prior_turns: Sequence[Mapping[str, str]] = (),
        *,
        dependent_handoff: object | None = None,
        conversation_context_override: object | None = None,
    ):
        # The ordinary v0 Core adapter forwards recent trusted turns by
        # keyword; Temporal and other scoped executors forward them
        # positionally. Both are the SAME prior-turn contract, not rival
        # histories. Normalize once, then prove exact equality with the
        # outer authenticated snapshot before the Planner can run.
        if conversation_context_override is not None and routed_prior_turns not in ((), None):
            raise ValueError("Two competing route contexts are not allowed")
        route_prior = (
            conversation_context_override
            if conversation_context_override is not None
            else routed_prior_turns
        )
        # The same source/actor/conversation authority applies to Core,
        # Temporal, Tasks and Events; only the domain processing differs.
        core_capability = route_scopes[locator][1].route.capability_id
        if core_capability not in {"core", "temporal"}:
            raise ValueError("Core executor cannot handle application-owned routes")
        ordinal, scoped = route_authority.verify(
            source=unit_source,
            locator=locator,
            capability=core_capability,
            actor=routed_authenticated_actor,
            conversation=route_prior,
        )
        # Preserve the exact trusted conversation snapshot for Core planning.
        routed_prior_turns = tuple(route_prior)
        inherited = temporal_handoff.inherited(
            scoped.context,
            current_route_index=ordinal,
            start=scoped.original_start,
            end=scoped.original_end,
        )
        if missing_inherited_temporal_spans(scoped.context, inherited):
            from odyssey_core.temporal_interpretation import TemporalInterpreterError

            raise TemporalInterpreterError(
                "Inherited temporal scope has no verified earlier Temporal result"
            )
        # E2: the exact-name lookup is independent of Temporal. Start one
        # read-only canonical vault scan while Temporal may call its provider.
        # An inherited Core proof is still resolved only after its predecessor
        # has persisted; no future route is prefetched across write barriers.
        # An optional lookup budget overflow must NOT block the normal Planner.
        from odyssey_core.canonical_source_context import source_note_role_spans
        from odyssey_core.execution_context import PendingContext, run_context_stage
        from odyssey_core.note_lookup_batch import (
            MAX_MENTION_LOOKUPS,
            NoteLookupRequest,
            ParallelExactNoteLookup,
        )

        context_timezone = getattr(temporal, "timezone", None) or os.environ.get("TZ", "UTC")
        prepared_note_context = None
        note_lookup_budget_exceeded = False
        lookup_stage = None
        if isinstance(core_planner_factory, ContextAwareCorePlannerFactory):
            spans = source_note_role_spans(scoped.context)
            if len(spans) > MAX_MENTION_LOOKUPS:
                note_lookup_budget_exceeded = True
            elif spans:
                lookup_stage = ParallelExactNoteLookup(
                    requests=tuple(
                        NoteLookupRequest(span.text, span.start, span.end) for span in spans
                    ),
                    repository=repository,
                    schema=schema,
                )
        with (
            ThreadPoolExecutor(max_workers=1) if lookup_stage is not None else nullcontext() as pool
        ):
            lookup_future = None
            if lookup_stage is not None:
                initial = ExecutionContext(
                    request_id=locator,
                    source=unit_source,
                    captured_at=now,
                    timezone=context_timezone,
                    authenticated_actor=routed_authenticated_actor,
                )
                report_progress("core.notes.started")
                lookup_future = pool.submit(run_context_stage, initial, lookup_stage)
            interpretation = None
            domain = None
            composed_shared_clock = False
            temporal_stage: OperationalStage | None = None
            if scoped.route.capability_id == "temporal":
                if temporal is None or not callable(getattr(temporal, "interpret", None)):
                    raise ValueError("Temporal resolution is unavailable for dated route")
                report_progress("temporal.started")
                temporal_started = perf_counter()
                try:
                    if inherited:
                        interpretation = temporal.interpret(
                            unit_source, inherited_temporal=inherited
                        )
                    else:
                        interpretation = temporal.interpret(unit_source)
                except Exception as error:
                    temporal_stage = OperationalStage(
                        "candidate.temporal_interpretation",
                        OperationalOutcome.FAILED,
                        max(0.0, (perf_counter() - temporal_started) * 1000),
                        model=getattr(temporal, "model", None),
                        reasoning_effort=getattr(temporal, "reasoning_effort", None),
                        usage=normalize_provider_usage(getattr(temporal, "last_usage", None)),
                        error_category=type(error).__name__[:100],
                    )
                    return ApplicationResult(
                        locator,
                        ApplicationStatus.FAILED,
                        (),
                        (),
                        planning_error="TEMPORAL_INTERPRETATION_REQUIRED",
                        operational=OperationalEvidence(
                            total_duration_ms=temporal_stage.duration_ms,
                            stages=(temporal_stage,),
                        ),
                    )
                report_progress("temporal.ready")
                temporal_stage = OperationalStage(
                    "candidate.temporal_interpretation",
                    OperationalOutcome.COMPLETED,
                    max(0.0, (perf_counter() - temporal_started) * 1000),
                    model=getattr(temporal, "model", None),
                    reasoning_effort=getattr(temporal, "reasoning_effort", None),
                    usage=normalize_provider_usage(getattr(temporal, "last_usage", None)),
                )
                if interpretation.source_text != unit_source:
                    raise ValueError("Temporal must interpret only its routed source")
                from odyssey_core.temporal_interpretation import TemporalInterpreterError

                try:
                    domain = interpretation.core_domain_interpretation()
                except TemporalInterpreterError:
                    if bundle_compiler is None:
                        raise
                    from odyssey_core.temporal_group_composition import compose_shared_clock_group

                    try:
                        if len(scoped.context.candidates) < 2:
                            raise TemporalInterpreterError("No multi-candidate clock composition")
                        domain = compose_shared_clock_group(
                            interpretation,
                            scoped.context,
                            timezone=getattr(temporal, "timezone", None),
                        )
                        composed_shared_clock = True
                    except TemporalInterpreterError:
                        # Keep genuinely approximate source wording literal;
                        # only exact independently validated dates/clocks may
                        # be used as calendar targets or time coordinates.
                        from odyssey_core.temporal_approximation_handoff import (
                            compose_safe_approximate_group,
                        )

                        domain = compose_safe_approximate_group(interpretation, scoped.context)
                if not composed_shared_clock:
                    temporal_handoff.remember(
                        interpretation,
                        route_index=ordinal,
                        start=scoped.original_start,
                        end=scoped.original_end,
                        verified_domain=domain,
                    )
                # Two different instants sourced from one shared clock cannot be
                # cached as one unique cross-group clock handoff. The group owns
                # the two independently dated values; later groups fail closed.
            if lookup_future is not None:
                prepared_note_context = lookup_future.result()
                report_progress("core.notes.ready")
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
        # properties use separately persisted same-subject Core proof; a
        # changed-subject affirmative purchase needs verified predecessor
        # event content, never the old buyer identity. Any unsupported event
        # shape stays pending rather than copying a Router lexical hint.
        inherited_fact_roles = {
            role.role
            for role in scoped.context.source_provenance
            if role.role in {"predicate", "predicate_relation", "object", "transaction"}
        }
        event = None
        if inherited_fact_roles and subject is None:
            event = event_handoff.inherit(
                context=scoped.context,
                route_index=ordinal,
                start=scoped.original_start,
                end=scoped.original_end,
                repository=repository,
                schema=schema,
            )
            if event is None:
                raise ValueError("Inherited predicate requires Core-verified predecessor fact")
        if event is not None and guard is not None:
            raise ValueError("Mixed predecessor-event and canonical-reference proof is unsupported")
        route_context = (
            resolve_scoped_reference_with_core_proof(scoped.context, guard, repository, schema)
            if guard is not None
            else scoped.context
        )
        if subject is not None:
            route_context = replace(route_context, verified_inherited_subject=subject)
        if event is not None:
            route_context = replace(route_context, verified_inherited_event=event)
        if (
            route_context.hybrid_interpretation_mode
            and len(route_context.candidates) >= 2
            and domain is not None
            and domain.capability_id == "temporal"
        ):
            route_context = replace(route_context, verified_route_temporal=domain)
        if composed_shared_clock:
            route_context = replace(route_context, verified_group_temporal=domain)
        if (
            route_context.hybrid_interpretation_mode
            and correction_chain(route_context.candidates) is not None
            and domain is not None
        ):
            route_context = replace(route_context, verified_correction_temporal=domain)
        if (
            route_context.hybrid_interpretation_mode
            and domain is not None
            and supports_sensitive_literal_candidates(route_context.candidates)
        ):
            route_context = replace(route_context, verified_sensitive_temporal=domain)
        route_context.validate(unit_source)
        # The same *exact-source* Temporal proof is needed by Core coverage;
        # Router's lexical time_approx alone cannot authorize this binding.
        from odyssey_core.temporal_qualifier_handoff import source_bound_qualitative_times

        verified_qualitative = source_bound_qualitative_times(
            interpretation, route_context, domain, timezone=context_timezone
        )
        if verified_qualitative and route_context.verified_route_temporal is None:
            route_context = replace(route_context, verified_route_temporal=domain)
            route_context.validate(unit_source)
        # E2 seam: bind existing CoreCandidateContext, DomainInterpretation and
        # runtime-authenticated actor to ONE validated, immutable handoff.
        # The context is a structural guard, not a second semantic authority.
        # It is intentionally assembled only after all Core-owned inheritance
        # and scoped evidence have already been independently verified.
        execution_context = ExecutionContext(
            request_id=locator,
            source=unit_source,
            captured_at=now,
            timezone=context_timezone,
            authenticated_actor=routed_authenticated_actor,
            candidates=route_context,
            domains=(domain,) if domain is not None else (),
            note_mentions=(
                prepared_note_context.note_mentions if prepared_note_context is not None else ()
            ),
            source_note_hints=(
                prepared_note_context.source_note_hints if prepared_note_context is not None else ()
            ),
            pending=(
                prepared_note_context.pending
                if prepared_note_context is not None
                else (
                    (PendingContext("core.note_lookup_exact", "LOOKUP_BUDGET_EXCEEDED"),)
                    if note_lookup_budget_exceeded
                    else ()
                )
            ),
            qualitative_times=verified_qualitative,
        )
        # Subsequent stages consume the validated carrier, not new copies of
        # the original planner/actor arguments.
        route_context = execution_context.candidates
        domain = execution_context.domains[0] if execution_context.domains else None
        from odyssey_core.scoped_event_evidence import CoreInheritedEventWriteGuard
        from odyssey_core.scoped_subject_evidence import CoreInheritedSubjectWriteGuard

        subject_guard = CoreInheritedSubjectWriteGuard(subject) if subject is not None else None
        event_guard = (
            CoreInheritedEventWriteGuard(event, unit_source, route_context.candidates[0])
            if event is not None
            else None
        )
        if isinstance(core_planner_factory, ContextAwareCorePlannerFactory):
            planner = core_planner_factory.create_for_context(execution_context)
        else:
            planner = core_planner_factory(route_context, domain)
        if route_context.hybrid_interpretation_mode:
            from odyssey_core.canonical_source_context import matching_canonical_source_names
            from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner

            if isinstance(planner, OpenAILunaExperimentalPlanner):
                if isinstance(core_planner_factory, ContextAwareCorePlannerFactory):
                    # Normal E2 path: this evidence was gathered during the
                    # same canonical Note batch, concurrently with Temporal.
                    # On budget overflow, retain the historic bounded hint
                    # lookup rather than silently changing planner prompts.
                    names = (
                        matching_canonical_source_names(route_context, repository, schema)
                        if note_lookup_budget_exceeded
                        else execution_context.source_note_hints
                    )
                else:
                    names = matching_canonical_source_names(route_context, repository, schema)
                if names:
                    planner.bind_verified_source_note_names(names)
        if not callable(getattr(planner, "plan", None)):
            raise ValueError("Only the ordinary Core planner may interpret a scoped route")
        captured: dict[str, RequestPlan] = {}

        class RecordingCorePlanner:
            """Observe the original planner's output without changing its actions."""

            def plan(self, request: str, conversation_context: Sequence[Mapping[str, str]] = ()):
                if request != unit_source:
                    raise ValueError("Core was given a sibling or full original message")
                if tuple(conversation_context) != tuple(routed_prior_turns):
                    raise ValueError("Core planner received untrusted conversation context")
                result = (
                    planner.plan(request, conversation_context)
                    if conversation_context
                    else planner.plan(request)
                )
                if isinstance(result, RequestPlan):
                    if isinstance(core_planner_factory, ContextAwareCorePlannerFactory):
                        from odyssey_core.qualitative_fact_preservation import (
                            preserve_qualitative_day_facts,
                        )

                        # Different verified dates have unique Day owners. Same-day
                        # multi-facts require the EXISTING Core attributor first;
                        # it prepares a final plan+manifest in its single call.
                        dates = [q.date for q in execution_context.qualitative_times]
                        if len(dates) == len(set(dates)):
                            result = preserve_qualitative_day_facts(
                                result, context=execution_context
                            )
                    captured["plan"] = result
                return result

            def __getattr__(self, name):
                return getattr(planner, name)

        from odyssey_core.candidate_coverage import PreparedCoreCandidateCoverage

        def reviewed_coverage(text, candidate_ctx, core_plan):
            """Use the existing Core review once; record the FINAL validated plan.

            The Core prewrite path will validate its reviewed manifest against
            the exact enriched plan before any physical mutation. This callback
            only observes that plan for the existing Markdown readback.
            """
            if core_candidate_attributor is not None:
                reviewed = coverage(
                    text,
                    candidate_ctx,
                    core_plan,
                    canonical_binding=guard,
                    verified_temporal=(
                        domain
                        if route_context.hybrid_interpretation_mode
                        and domain is not None
                        and domain.capability_id == "temporal"
                        and domain.intent == "TEMPORAL_RESOLUTION"
                        else None
                    ),
                    qualitative_context=(
                        execution_context
                        if len({q.date for q in execution_context.qualitative_times})
                        != len(execution_context.qualitative_times)
                        else None
                    ),
                )
            elif guard is not None:
                reviewed = coverage(text, candidate_ctx, core_plan, canonical_binding=guard)
            else:
                reviewed = coverage(text, candidate_ctx, core_plan)
            if isinstance(reviewed, PreparedCoreCandidateCoverage):
                captured["plan"] = reviewed.plan
            return reviewed

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
            candidate_coverage_factory=reviewed_coverage,
            candidate_pending_recorder=candidate_pending_recorder,
            history_recorder=history_recorder,
            progress_callback=progress_callback,
            write_preflight_guard=subject_guard or event_guard or guard,
            known_fact_verifier=known_fact_verifier,
            authenticated_actor=execution_context.authenticated_actor,
            self_binding_repository=self_binding_repository,
            conversation_context=tuple(routed_prior_turns),
        )
        if temporal_stage is not None:
            result = replace(
                result,
                operational=replace(
                    result.operational,
                    stages=(temporal_stage, *result.operational.stages),
                ),
            )
        if result.status is ApplicationStatus.COMPLETED and "plan" in captured:
            try:
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
                        item.status not in {"verified_in_markdown", "verified_existing_knowledge"}
                        for item in evidence.persisted_facts
                    ):
                        raise ValueError("Core's routed physical Markdown readback failed")
                    # Only a later sibling route might read derived indexes
                    # inside THIS same request. Preserve that read-after-write
                    # barrier using the existing incremental maintainer;
                    # the last route is refreshed ONCE by Runtime's ordinary
                    # asynchronous post-request coordinator. No full vault
                    # embeddings on the critical path for a one-note message.
                    # The provider-free standalone dispatcher keeps its prior
                    # index refresh contract when no coordinator is injected.
                    if postwrite_index_refresh is None:
                        context_index.rebuild(repository, schema, embedder)
                        semantic_index.rebuild(repository, schema, embedder)
                    elif ordinal + 1 < len(bundle.units):
                        postwrite_index_refresh(result.affected_stable_note_ids)
                    event_handoff.remember(
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
                    # A verified canonical WRITE target may itself be the sole
                    # antecedent of the immediately next source reference.
                    # This is distinct from a helper wikilink in the source fact.
                    # Never use Router's lexical role as identity proof, and
                    # never choose among multiple possible antecedents.
                    if ordinal + 1 < len(bundle.units) and not result.canonical_reference_evidence:
                        next_route = bundle.units[ordinal + 1]
                        candidate_roles = [
                            role
                            for candidate in next_route.context.candidates
                            for role in candidate.roles
                        ]
                        pronoun_roles = [
                            role for role in candidate_roles if role.role == "reference"
                        ]
                        if (
                            next_route.route.depends_on == ordinal
                            and len(next_route.context.candidates) == 1
                            and len(pronoun_roles) == 1
                            and pronoun_roles[0].span.text == next_route.route.dependent_mention
                            and any(
                                role.role in {"subject", "object", "participants"}
                                and role.span == pronoun_roles[0].span
                                for role in candidate_roles
                            )
                        ):
                            antecedent = subject_handoff.reference_from_verified_direct_target(
                                context=route_context,
                                route_index=ordinal,
                                start=scoped.original_start,
                                end=scoped.original_end,
                                repository=repository,
                                schema=schema,
                            )
                            if antecedent is not None:
                                result = replace(
                                    result,
                                    canonical_reference_evidence=(antecedent,),
                                )
                result = _suppress_ambiguous_single_handoff(
                    route_context,
                    bundle.units[ordinal + 1].route if ordinal + 1 < len(bundle.units) else None,
                    ordinal,
                    result,
                )
            except Exception as error:
                # Core has already returned a write receipt. A later readback,
                # index or handoff failure must not erase successful writes
                # or allow dependent branches to infer a canonical identity.
                failed_stage = OperationalStage(
                    "candidate.postwrite_verification",
                    OperationalOutcome.FAILED,
                    0.0,
                    error_category=type(error).__name__[:100],
                )
                return replace(
                    result,
                    status=(
                        ApplicationStatus.PARTIAL
                        if result.affected_stable_note_ids
                        else ApplicationStatus.NEEDS_ATTENTION
                    ),
                    planning_error="ROUTE_POSTWRITE_VERIFICATION_REQUIRED",
                    canonical_reference_evidence=(),
                    operational=replace(
                        result.operational,
                        stages=(*result.operational.stages, failed_stage),
                    ),
                )
        return result

    def preserve_route_ambiguity(route, locator, predecessor):
        if route_ambiguity_recorder is None or not callable(route_ambiguity_recorder):
            return None
        original = route_scopes.get(locator)
        if original is None:
            return None
        ordinal, scoped = original
        if (
            route != scoped.route
            or route.depends_on is None
            or route.depends_on != ordinal - 1
            or not 0 <= route.depends_on < len(bundle.units)
        ):
            return None
        from odyssey_runtime.ambiguous_route_pending import (
            preserve_unresolved_dependent_reference,
        )

        return preserve_unresolved_dependent_reference(
            original_source=source,
            route=route,
            scoped=scoped,
            predecessor_source=bundle.units[route.depends_on].route.source_text,
            predecessor=predecessor,
            locator=locator,
            repository=repository,
            schema=schema,
            recorder=route_ambiguity_recorder,
        )

    selected_router = SimpleNamespace(route=lambda current, _prior=(): bundle.plan)
    # The candidate bundle may contain only Core/Temporal. Bind only entries
    # in its validated catalog, never phantom Tasks/Events registrations.
    trusted_app_handlers = {
        "tasks": run_task_route if task_route_executor is not None else None,
        "events": run_event_route if event_route_executor is not None else None,
    }

    def scoped_extra_handler(app: RegisteredScopedApp):
        def execute(
            unit_source: str,
            locator: str,
            routed_authenticated_actor: AuthenticatedActorContext | None = None,
            routed_prior_turns: Sequence[Mapping[str, str]] = (),
        ) -> ApplicationResult:
            _ordinal, scoped = route_authority.verify(
                source=unit_source,
                locator=locator,
                capability=app.descriptor.id,
                actor=routed_authenticated_actor,
                conversation=routed_prior_turns,
            )
            if scoped.route.depends_on is not None or scoped.context.source_provenance:
                # Third-party routes have no typed predecessor carrier yet.
                # Lexical shared roles are not authority to infer an identity or time.
                return ApplicationResult(
                    locator,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    planning_error="APP_SCOPED_INHERITED_EVIDENCE_UNSUPPORTED",
                )
            report_progress("application.started", {"capability": app.descriptor.id})
            result = app.execute(
                unit_source, locator, routed_authenticated_actor, routed_prior_turns
            )
            report_progress("application.ready", {"capability": app.descriptor.id})
            if not isinstance(result, ApplicationResult):
                raise ValueError("Registered application returned an invalid receipt")
            return result

        return execute

    trusted_app_handlers.update(
        (app_id, scoped_extra_handler(app))
        for app_id, app in registered_extra.items()
        if app_id in routed_extra
    )
    bound_app_executors = bind_registered_executors(
        catalog,
        {cap.id: trusted_app_handlers.get(cap.id) for cap in catalog.capabilities()},
    )
    result = execute_routed_request(
        user_request=source,
        outer_request_id=outer_id,
        router=selected_router,
        catalog=catalog,
        core_execute=run_unit,
        temporal_execute=run_unit,
        application_executors=bound_app_executors,
        dependent_pending_executor=(
            preserve_route_ambiguity if route_ambiguity_recorder is not None else None
        ),
        authenticated_actor=authenticated_actor,
        conversation_context=conversation_context,
    )
    # ``selected_router`` adapts an already validated bundle to the generic
    # executor. Its zero-duration stage is not a provider call, so retaining
    # it would misstate the actual Router latency recorded above.
    result = replace(
        result,
        operational=replace(
            result.operational,
            stages=tuple(
                stage for stage in result.operational.stages if stage.name != "application.router"
            ),
        ),
    )
    if not prewrite_stages:
        return completed_with_wall(result)
    return completed_with_wall(
        replace(
            result,
            operational=replace(
                result.operational, stages=(*prewrite_stages, *result.operational.stages)
            ),
        )
    )
