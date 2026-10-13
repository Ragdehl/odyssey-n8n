"""Route-local Router → optional Temporal → ordinary Core → verified Markdown.

Source-candidate splitting and typed provenance are implemented by the
independent source_scope_compiler, never by passing sibling source as a Core
request. The active DEV/PROD chat route is not modified.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace

from odyssey_apps.catalog import ApplicationCatalog
from odyssey_apps.fact_candidates import FactCandidateProposal
from odyssey_apps.router import RouterError
from odyssey_core.candidate_context import CoreCandidateContext
from odyssey_core.candidate_correction_chain import correction_chain
from odyssey_core.candidate_sensitive_statement import supports_sensitive_literal_candidates
from odyssey_core.git_history import HistoryRecorder
from odyssey_runtime.scoped_event_handoff import ScopedCoreEventHandoff
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
    recorder.
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

        def coverage(text, context, plan, *, canonical_binding=None, verified_temporal=None):
            return review_model_candidate_fact_coverage(
                text,
                context,
                plan,
                core_candidate_attributor,
                canonical_binding=canonical_binding,
                verified_temporal=verified_temporal,
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
    # The default strict atomic route compiler is unchanged. The explicit
    # opt-in hybrid compiler may group multiple candidates into one *source*
    # request, never into one forced mutation or canonical identity.
    # Resolve the default at call time: historical frozen-reply tests can
    # inject their exact previous compiler without changing new hybrid logic.
    bundle = (bundle_compiler or compile_candidate_route_bundle)(proposal)
    uses_tasks = any(route.capability_id == "tasks" for route in bundle.plan.routes)
    if uses_tasks:
        from odyssey_runtime.hybrid_group_compiler import hybrid_tasks_catalog

        if bundle_compiler is None or any(
            not scoped.context.hybrid_interpretation_mode
            or not all(
                c.kind == "task" and c.state == "candidate" for c in scoped.context.candidates
            )
            for scoped in bundle.units
            if scoped.route.capability_id == "tasks"
        ):
            raise RouterError("Task routing requires explicitly validated hybrid task groups")
        catalog = hybrid_tasks_catalog()
    else:
        catalog = ApplicationCatalog.empty()
    validate_bundle_original_provenance(bundle, catalog=catalog)
    if task_route_executor is not None and not (
        callable(task_route_executor)
        or callable(getattr(task_route_executor, "execute_scoped", None))
    ):
        raise ValueError("Tasks execution must be a trusted application executor")
    outer_id = request_id_factory()
    if not isinstance(outer_id, str) or not outer_id.strip():
        raise ValueError("Outer request id must be non-empty")

    route_scopes = {
        route_execution_id(outer_id, ordinal): (ordinal, item)
        for ordinal, item in enumerate(bundle.units)
    }
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

        ordinal, scoped = route_scopes[locator]
        if scoped.route.capability_id != "tasks" or scoped.route.source_text != unit_source:
            raise ValueError("Task route source changed before application interpretation")
        inherited = temporal_handoff.inherited(
            scoped.context,
            current_route_index=ordinal,
            start=scoped.original_start,
            end=scoped.original_end,
        )
        scoped_execute = getattr(task_route_executor, "execute_scoped", None)
        required_temporal_origins = {
            (role.original_start, role.original_end)
            for role in scoped.context.source_provenance
            if role.role in {"date", "date_scope", "time", "time_approx"}
        }
        if required_temporal_origins - {
            (proof.original_start, proof.original_end) for proof in inherited
        }:
            if not callable(scoped_execute):
                from odyssey_core.application import ApplicationResult, ApplicationStatus

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
            receipt = scoped_execute(
                unit_source, locator, authenticated_actor, prior_turns, scoped_evidence=evidence
            )
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
            from odyssey_core.application import ApplicationResult, ApplicationStatus

            return ApplicationResult(
                locator,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="TASK_SCOPED_TEMPORAL_EVIDENCE_UNSUPPORTED",
            )
        if not callable(task_route_executor):
            raise ValueError("Tasks executor lacks its ordinary execution callback")
        return task_route_executor(unit_source, locator, authenticated_actor, prior_turns)

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
        composed_shared_clock = False
        if scoped.route.capability_id == "temporal":
            if temporal is None or not callable(getattr(temporal, "interpret", None)):
                raise ValueError("Temporal resolution is unavailable for dated route")
            if inherited:
                interpretation = temporal.interpret(unit_source, inherited_temporal=inherited)
            else:
                interpretation = temporal.interpret(unit_source)
            if interpretation.source_text != unit_source:
                raise ValueError("Temporal must interpret only its routed source")
            from odyssey_core.temporal_interpretation import TemporalInterpreterError

            try:
                domain = interpretation.core_domain_interpretation()
            except TemporalInterpreterError:
                if bundle_compiler is None or len(scoped.context.candidates) < 2:
                    raise
                from odyssey_core.temporal_group_composition import compose_shared_clock_group

                try:
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
        from odyssey_core.scoped_event_evidence import CoreInheritedEventWriteGuard
        from odyssey_core.scoped_subject_evidence import CoreInheritedSubjectWriteGuard

        subject_guard = CoreInheritedSubjectWriteGuard(subject) if subject is not None else None
        event_guard = (
            CoreInheritedEventWriteGuard(event, unit_source, route_context.candidates[0])
            if event is not None
            else None
        )
        planner = core_planner_factory(route_context, domain)
        if route_context.hybrid_interpretation_mode:
            from odyssey_core.canonical_source_context import matching_canonical_source_names
            from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner

            if isinstance(planner, OpenAILunaExperimentalPlanner):
                names = matching_canonical_source_names(route_context, repository, schema)
                if names:
                    planner.bind_verified_source_note_names(names)
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
                (
                    lambda text, ctx, plan: coverage(
                        text,
                        ctx,
                        plan,
                        canonical_binding=guard,
                        verified_temporal=(
                            domain
                            if (
                                route_context.hybrid_interpretation_mode
                                and domain is not None
                                and domain.capability_id == "temporal"
                                and domain.intent == "TEMPORAL_RESOLUTION"
                            )
                            else None
                        ),
                    )
                )
                if core_candidate_attributor is not None
                else (
                    (lambda text, ctx, plan: coverage(text, ctx, plan, canonical_binding=guard))
                    if guard is not None
                    else coverage
                )
            ),
            candidate_pending_recorder=candidate_pending_recorder,
            history_recorder=history_recorder,
            write_preflight_guard=subject_guard or event_guard or guard,
            known_fact_verifier=known_fact_verifier,
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
                    item.status not in {"verified_in_markdown", "verified_existing_knowledge"}
                    for item in evidence.persisted_facts
                ):
                    raise ValueError("Core's routed physical Markdown readback failed")
                # Rebuild only derived indexes, after the authoritative writer.
                # This test-only composition uses a disposable canonical vault.
                context_index.rebuild(repository, schema, embedder)
                semantic_index.rebuild(repository, schema, embedder)
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
                    pronoun_roles = [role for role in candidate_roles if role.role == "reference"]
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
    return execute_routed_request(
        user_request=source,
        outer_request_id=outer_id,
        router=selected_router,
        catalog=catalog,
        core_execute=run_unit,
        temporal_execute=run_unit,
        application_executors=(
            {"tasks": run_task_route} if task_route_executor is not None else {}
        ),
        dependent_pending_executor=(
            preserve_route_ambiguity if route_ambiguity_recorder is not None else None
        ),
    )
