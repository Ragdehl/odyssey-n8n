"""Bounded ordered execution of validated application route plans.

This module is a runtime adapter: it keeps the Core application result as the only public
completion authority while giving routed subexecutions deterministic, non-delivery locators.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Protocol

from odyssey_apps import (
    CORE_CAPABILITY_ID,
    TEMPORAL_CAPABILITY_ID,
    ApplicationCatalog,
    Route,
    RouteOutcome,
    RoutePlan,
    validate_route_plan,
)
from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    PendingWorkStatus,
)
from odyssey_core.git_history import GitHistoryResult, HistoryStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalStage,
    ProviderCallEvidence,
    normalize_provider_usage,
)


class ApplicationRouter(Protocol):
    """Return a closed route plan without receiving execution authority."""

    def route(
        self, original_request: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> RoutePlan:
        """Classify exact request spans into a locally validated route plan."""


class ApplicationExecutor(Protocol):
    """Execute one application-owned exact route through the Core result boundary."""

    def __call__(
        self,
        source_text: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
    ) -> ApplicationResult:
        """Return route evidence using only its source and bounded prior conversation context."""


_ROUTE_LOCATOR = re.compile(r"route-([1-9][0-9]*)-([0-9a-f]{64})\Z")
_MAX_ROUTE_ORDINAL = 999_999_999

# A preparer may interpret one independently validated exact span but may not
# retrieve canonical state or execute its write. Its returned callback executes
# synchronously in the original route order through the normal result boundary.
RoutePreparer = Callable[
    [str, Sequence[Mapping[str, str]]],
    ApplicationExecutor,
]


@dataclass(frozen=True, slots=True)
class PreparedExecution:
    """Carry trusted preflight facts from a pure application interpretation.

    Dates come from typed validated Temporal output. They never grant Core mutation authority.
    ``None`` means that an application has no temporal preflight metadata.
    """

    executor: ApplicationExecutor
    temporal_dates: tuple[str, ...] | None = None
    temporal_resolved: bool | None = None
    temporal_stage: OperationalStage | None = None
    temporal_evidence: tuple[tuple[str, str], ...] = ()

    def __call__(
        self,
        source_text: str,
        request_id: str,
        authenticated_actor: AuthenticatedActorContext | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
    ) -> ApplicationResult:
        """Execute the original validated callback without extra preparation or mutation."""
        return self.executor(source_text, request_id, authenticated_actor, conversation_context)


def _temporal_cohort_issue(
    routes: Sequence[Route], prepared: Mapping[int, ApplicationExecutor]
) -> str | None:
    """Reject contradictory split date evidence before any canonical route write.

    A connected batch of two or more standalone Temporal routes cannot commit partially
    when any part lacks an exact date, or when unqualified routes disagree about years.
    Explicit year-qualified references may legitimately span multiple calendar years.
    Unknown third-party preparers provide no semantic evidence and remain unchanged.
    """
    temporal = [
        (i, route)
        for i, route in enumerate(routes)
        if route.capability_id == TEMPORAL_CAPABILITY_ID
    ]
    if len(temporal) < 2:
        return None
    if not all(isinstance(prepared.get(i), PreparedExecution) for i, _ in temporal):
        # Existing third-party adapters remain unchanged. If at least one
        # built-in Temporal route is present, a missing sibling preparation
        # must never permit earlier writes before the failure is discovered.
        return (
            "TEMPORAL_COHORT_UNRESOLVED"
            if any(isinstance(prepared.get(i), PreparedExecution) for i, _ in temporal)
            else None
        )
    snapshots = [prepared[i] for i, _ in temporal]
    if any(item.temporal_resolved is None for item in snapshots):
        return None
    if any(not item.temporal_resolved or not item.temporal_dates for item in snapshots):
        return "TEMPORAL_COHORT_UNRESOLVED"
    years = {date[:4] for item in snapshots for date in item.temporal_dates or ()}
    if len(years) > 1:
        explicit = {
            year
            for _, route in temporal
            for year in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", route.source_text)
        }
        if not years.issubset(explicit):
            return "TEMPORAL_COHORT_YEAR_CONFLICT"
    return None


def _cohort_blocked_result(
    locator: str, prepared: ApplicationExecutor | None, issue: str
) -> ApplicationResult:
    """Retain real Temporal preparation evidence without executing any blocked mutation."""
    observed = prepared if isinstance(prepared, PreparedExecution) else None
    stages: tuple[OperationalStage, ...] = (
        (observed.temporal_stage,) if observed and observed.temporal_stage is not None else ()
    )
    stage = OperationalStage(
        "temporal.coherence", OperationalOutcome.FAILED, 0.0, error_category=issue
    )
    references = (
        [
            {"source": source[:120], "value": date[:80]}
            for source, date in observed.temporal_evidence[:8]
        ]
        if observed is not None
        else []
    )
    return ApplicationResult(
        locator,
        ApplicationStatus.NEEDS_ATTENTION,
        (),
        (),
        planning_error=issue,
        operational=OperationalEvidence(stages=(*stages, stage)),
        execution_flow={"temporal": references},
    )


def route_execution_id(outer_request_id: str, ordinal: int) -> str:
    """Derive a safe deterministic internal locator without creating a delivery identity.

    The locator is used only by request-scoped Core adapters (pending work and Git history) so
    independent route projections cannot collide.  It is never returned as the aggregate request
    ID and is not accepted by the delivery-result store as a distinct client delivery.
    """
    if not isinstance(outer_request_id, str) or not outer_request_id:
        raise ValueError("outer request ID is invalid")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        raise ValueError("route ordinal is invalid")
    if ordinal > _MAX_ROUTE_ORDINAL:
        raise ValueError("route ordinal is too large")
    return f"route-{ordinal + 1}-{hashlib.sha256(outer_request_id.encode('utf-8')).hexdigest()}"


def is_route_execution_id(outer_request_id: str, locator: str) -> bool:
    """Return whether a locator is a deterministic subordinate of this outer delivery ID."""
    if not isinstance(outer_request_id, str) or not outer_request_id:
        return False
    if not isinstance(locator, str):
        return False
    match = _ROUTE_LOCATOR.fullmatch(locator)
    if match is None:
        return False
    ordinal = int(match.group(1))
    return (
        1 <= ordinal <= _MAX_ROUTE_ORDINAL + 1
        and match.group(2) == hashlib.sha256(outer_request_id.encode("utf-8")).hexdigest()
    )


def _route_stage_io(source: str, result: ApplicationResult) -> list[dict[str, str]]:
    """Project actual validated application-stage I/O into bounded, read-only text.

    An absent typed result produces an empty output, not a guessed model response.
    This never inspects raw provider requests, hidden reasoning or vault contents.
    """
    evidence = result.execution_flow or {}
    temporal = evidence.get("temporal") or ()
    plan = evidence.get("plan") or ()
    entities = evidence.get("entities") or ()
    writes = evidence.get("writes") or ()
    task = evidence.get("task") or {}
    date_lines = [f"{item['source']} → {item['value']}" for item in temporal[:8]]
    plan_lines = [
        f"{item['operation']} · {item['type']} → {item['target']}"
        + (f" · {item['fact']}" if item["fact"] else "")
        for item in plan[:6]
    ]
    changes = [f"{item['status']}: {item['operation']} · {item['target']}" for item in writes[:6]]
    links = [
        f"{item['mention']} → {item['name'] if item['status'] == 'resolved' else 'No confirmada'}"
        for item in entities[:6]
    ]
    steps: list[dict[str, str]] = []
    for stage in result.operational.stages[:16]:
        name = stage.name
        incoming = source[:512]
        outgoing = ""
        if name == "tasks.interpretation":
            if task:
                outgoing = f"Operación: {task['operation']}"
                if task.get("reference"):
                    outgoing += f" · Tarea: {task['reference']}"
        elif name == "temporal.interpretation":
            if date_lines:
                incoming = "; ".join(item["source"] for item in temporal[:8])[:512]
                outgoing = "\n".join(date_lines)
        elif name == "planner":
            if date_lines:
                incoming = (source + "\nContexto temporal: " + "; ".join(date_lines))[:512]
            outgoing = "\n".join(plan_lines)
        elif name.startswith("action."):
            incoming = "\n".join(plan_lines)[:512]
            outgoing = "\n".join([*changes, *links])
        elif name == "git":
            incoming = f"{len(result.affected_stable_note_ids)} notas afectadas"
            outgoing = result.history.status.value
        elif name == "pending":
            incoming = "Resultado de Core"
            outgoing = stage.outcome.value
        else:
            # Preserve verified stage status without inventing semantic output.
            incoming = source[:512]
        steps.append({"name": name[:80], "input": incoming[:512], "output": outgoing[:768]})
    return steps


def execute_routed_request(
    *,
    user_request: str,
    outer_request_id: str,
    router: ApplicationRouter,
    catalog: ApplicationCatalog,
    core_execute: Callable[..., ApplicationResult],
    application_executors: Mapping[str, ApplicationExecutor],
    temporal_execute: ApplicationExecutor | None = None,
    authenticated_actor: AuthenticatedActorContext | None = None,
    conversation_context: Sequence[Mapping[str, str]] = (),
    progress_callback: Callable[[str, Mapping[str, object]], None] | None = None,
    route_preparers: Mapping[str, RoutePreparer] | None = None,
    max_parallel_preparations: int = 2,
) -> ApplicationResult:
    """Interpret independent spans concurrently and execute Core writes in original order.

    The whole plan is revalidated before execution.  Route-local exceptions, unavailable apps,
    and invalid correlations become bounded failed route evidence, allowing later independent
    routes to continue.  No route receives sibling current-message text.
    """
    if progress_callback is not None:
        progress_callback("routing.started", {})
    router_started = perf_counter()
    try:
        plan = router.route(user_request, conversation_context)
        plan = validate_route_plan(plan, user_request, catalog)
    except Exception as error:
        stage = _router_stage(router, router_started, error)
        return _prepend_router_stage(
            _router_failure(outer_request_id, "ROUTER_INVALID", error), stage
        )
    stage = _router_stage(router, router_started)
    if progress_callback is not None:
        progress_callback("routing.ready", {"route_count": len(plan.routes)})
    if plan.outcome is RouteOutcome.CLARIFY:
        return _prepend_router_stage(_router_outcome(outer_request_id, "ROUTER_CLARIFY"), stage)
    if plan.outcome is RouteOutcome.NEEDS_CAPABILITY:
        return _prepend_router_stage(
            _router_outcome(outer_request_id, "ROUTER_NEEDS_CAPABILITY"), stage
        )
    if plan.outcome is not RouteOutcome.ROUTE:  # Defensive against a malicious Protocol adapter.
        return _prepend_router_stage(
            _router_failure(outer_request_id, "ROUTER_INVALID", TypeError("unknown outcome")),
            stage,
        )

    if max_parallel_preparations < 1 or max_parallel_preparations > 2:
        raise ValueError("route interpretation concurrency must be one or two")
    subresults: list[ApplicationResult] = []
    scheduled_routes = False
    # For a single route or unsupported destinations preserve the original path.
    preparers = route_preparers or {}
    if len(plan.routes) < 2 or not any(route.capability_id in preparers for route in plan.routes):
        for ordinal, route in enumerate(plan.routes):
            subresults.append(
                _execute_route(
                    route,
                    route_execution_id(outer_request_id, ordinal),
                    core_execute,
                    application_executors,
                    temporal_execute,
                    authenticated_actor,
                    conversation_context,
                )
            )
    else:
        scheduled_routes = True
        # Only pure domain interpreters run in workers. No Core execution or Git
        # mutation is submitted to the pool. Consume callbacks serially in route order.
        with ThreadPoolExecutor(max_workers=max_parallel_preparations) as workers:
            scheduled = {
                ordinal: workers.submit(
                    preparers[route.capability_id], route.source_text, tuple(conversation_context)
                )
                for ordinal, route in enumerate(plan.routes)
                if route.capability_id in preparers
            }
            # Resolve all pure interpretations before any Core/Git mutation.
            # This check cannot run after the first route has already written.
            prepared_callbacks: dict[int, ApplicationExecutor] = {}
            failed_preparations: set[int] = set()
            for ordinal, future in scheduled.items():
                try:
                    callback = future.result()
                    if not callable(callback):
                        raise TypeError("route preparer returned no executor")
                    prepared_callbacks[ordinal] = callback
                except Exception:
                    failed_preparations.add(ordinal)
            issue = _temporal_cohort_issue(plan.routes, prepared_callbacks)
            if issue is not None:
                subresults.extend(
                    _cohort_blocked_result(
                        route_execution_id(outer_request_id, ordinal),
                        prepared_callbacks.get(ordinal),
                        issue,
                    )
                    for ordinal, route in enumerate(plan.routes)
                )
                return _routed_result(
                    outer_request_id, user_request, plan.routes, subresults, scheduled_routes, stage
                )
            for ordinal, route in enumerate(plan.routes):
                locator = route_execution_id(outer_request_id, ordinal)
                callback: ApplicationExecutor | None = None
                if ordinal in failed_preparations:
                    subresults.append(_route_failure(locator, "APPLICATION_PREPARATION_FAILED"))
                    continue
                if ordinal in scheduled:
                    callback = prepared_callbacks[ordinal]
                subresults.append(
                    _execute_route(
                        route,
                        locator,
                        core_execute,
                        application_executors,
                        temporal_execute,
                        authenticated_actor,
                        conversation_context,
                        prepared_executor=callback,
                    )
                )
    return _routed_result(
        outer_request_id, user_request, plan.routes, subresults, scheduled_routes, stage
    )


def _routed_result(
    outer_request_id: str,
    user_request: str,
    routes: Sequence[Route],
    subresults: Sequence[ApplicationResult],
    scheduled_routes: bool,
    stage: OperationalStage,
) -> ApplicationResult:
    """Attach real route-local steps, including blocked preflight branches, in source order."""
    # Group flattened stage telemetry using the true per-route result boundaries.
    # Preparing route models may overlap; canonical execution remains serial.
    route_flow = {
        "version": 1,
        "input": user_request[:4096],
        "parallel_preparation": bool(len(routes) > 1 and scheduled_routes),
        "routes": [
            {
                "capability": route.capability_id,
                "text": route.source_text[:4096],
                "stage_count": len(result.operational.stages),
                "status": result.status.value,
                "temporal": list((result.execution_flow or {}).get("temporal", []))[:8],
                "plan": list((result.execution_flow or {}).get("plan", []))[:8],
                "entities": list((result.execution_flow or {}).get("entities", []))[:8],
                "writes": list((result.execution_flow or {}).get("writes", []))[:8],
                "steps": _route_stage_io(route.source_text, result),
            }
            for route, result in zip(routes, subresults, strict=True)
        ],
    }
    return _prepend_router_stage(
        replace(_aggregate(outer_request_id, subresults), execution_flow=route_flow), stage
    )


def _router_stage(
    router: ApplicationRouter, started: float, error: Exception | None = None
) -> OperationalStage:
    """Expose bounded router provider metadata without retaining route prompt or response content."""
    duration_ms = max(0.0, (perf_counter() - started) * 1000)
    usage = normalize_provider_usage(getattr(router, "last_usage", None))
    provider_status = getattr(router, "last_provider_status", None)
    attempted = bool(getattr(router, "last_call", False))
    calls: tuple[ProviderCallEvidence, ...] = ()
    if attempted:
        calls = (
            ProviderCallEvidence(
                name="application.router",
                outcome=(
                    OperationalOutcome.COMPLETED
                    if provider_status == "completed"
                    else OperationalOutcome.FAILED
                ),
                duration_ms=duration_ms,
                model=getattr(router, "model", None),
                reasoning_effort=getattr(router, "reasoning_effort", None),
                usage=usage,
                error_category=getattr(router, "last_error_category", None),
                response_id=getattr(router, "last_response_id", None),
                provider_status=provider_status,
                attempt_count=1,
                ordinal=1,
            ),
        )
    return OperationalStage(
        "application.router",
        OperationalOutcome.FAILED if error is not None else OperationalOutcome.COMPLETED,
        duration_ms,
        model=getattr(router, "model", None),
        reasoning_effort=getattr(router, "reasoning_effort", None),
        usage=usage,
        error_category=type(error).__name__ if error is not None else None,
        provider_calls=calls,
    )


def _prepend_router_stage(result: ApplicationResult, stage: OperationalStage) -> ApplicationResult:
    """Retain one router stage ahead of all route-local operational evidence."""
    return replace(
        result,
        operational=OperationalEvidence(
            total_duration_ms=result.operational.total_duration_ms,
            stages=(stage, *result.operational.stages),
        ),
    )


def _execute_route(
    route: Route,
    locator: str,
    core_execute: Callable[..., ApplicationResult],
    application_executors: Mapping[str, ApplicationExecutor],
    temporal_execute: ApplicationExecutor | None,
    authenticated_actor: AuthenticatedActorContext | None,
    conversation_context: Sequence[Mapping[str, str]],
    prepared_executor: ApplicationExecutor | None = None,
) -> ApplicationResult:
    """Contain one route executor failure and reject substituted route correlation."""
    try:
        if prepared_executor is not None:
            result = prepared_executor(
                route.source_text, locator, authenticated_actor, conversation_context
            )
        elif route.capability_id == CORE_CAPABILITY_ID:
            result = _invoke_core(
                core_execute,
                route.source_text,
                locator,
                authenticated_actor,
                conversation_context,
            )
        elif route.capability_id == TEMPORAL_CAPABILITY_ID:
            if temporal_execute is None:
                return _route_failure(locator, "TEMPORAL_EXECUTOR_UNAVAILABLE")
            result = temporal_execute(
                route.source_text, locator, authenticated_actor, conversation_context
            )
        else:
            executor = application_executors.get(route.capability_id)
            if executor is None:
                return _route_failure(locator, "APPLICATION_EXECUTOR_UNAVAILABLE")
            result = executor(route.source_text, locator, authenticated_actor, conversation_context)
        if not isinstance(result, ApplicationResult):
            return _route_failure(locator, "APPLICATION_RESULT_INVALID")
        if result.request_id != locator:
            return _route_failure(locator, "APPLICATION_CORRELATION_INVALID")
        return result
    except Exception:
        return _route_failure(locator, "APPLICATION_EXECUTION_FAILED")


def _invoke_core(
    core_execute: Callable[..., ApplicationResult],
    source_text: str,
    locator: str,
    authenticated_actor: AuthenticatedActorContext | None,
    conversation_context: Sequence[Mapping[str, str]],
) -> ApplicationResult:
    """Call Core with one exact source and the outer request's captured prior context."""
    return core_execute(
        source_text,
        locator,
        authenticated_actor,
        conversation_context_override=conversation_context,
    )


def _router_outcome(outer_request_id: str, code: str) -> ApplicationResult:
    """Map a non-executable closed router outcome to bounded Core result evidence."""
    if code == "ROUTER_CLARIFY":
        return ApplicationResult(
            outer_request_id,
            ApplicationStatus.NEEDS_ATTENTION,
            (),
            (),
            clarification_code=code,
        )
    return ApplicationResult(
        outer_request_id,
        ApplicationStatus.NEEDS_ATTENTION,
        (),
        (),
        planning_error=code,
    )


def _router_failure(outer_request_id: str, code: str, error: Exception) -> ApplicationResult:
    """Return one content-free router failure without exposing provider exception details."""
    del error
    return ApplicationResult(
        outer_request_id,
        ApplicationStatus.FAILED,
        (ActionResult(0, "route", ActionStatus.FAILED, reason=code),),
        (),
        planning_error=code,
    )


def _route_failure(locator: str, reason: str) -> ApplicationResult:
    """Create bounded failed evidence for one route that did not yield a Core result."""
    return ApplicationResult(
        locator,
        ApplicationStatus.FAILED,
        (ActionResult(0, "route", ActionStatus.FAILED, reason=reason),),
        (),
        planning_error=reason,
    )


def _aggregate(outer_request_id: str, subresults: Sequence[ApplicationResult]) -> ApplicationResult:
    """Project route results into one truthful outer Core result without mutating subresults."""
    actions: list[ActionResult] = []
    affected: list[str] = []
    for result in subresults:
        if result.action_results:
            first_action_index = len(actions)
            actions.extend(
                replace(action, action_index=first_action_index + offset)
                for offset, action in enumerate(result.action_results)
            )
        elif result.planning_error is not None:
            actions.append(
                ActionResult(
                    len(actions), "route", ActionStatus.FAILED, reason=result.planning_error
                )
            )
        for stable_id in result.affected_stable_note_ids:
            if stable_id not in affected:
                affected.append(stable_id)
    return ApplicationResult(
        outer_request_id,
        _aggregate_status(subresults),
        tuple(actions),
        tuple(affected),
        planning_error=_scalar_evidence(subresults, "planning_error", "MULTIPLE_ROUTE_ERRORS"),
        clarification_code=_scalar_evidence(
            subresults, "clarification_code", "MULTIPLE_ROUTE_CLARIFICATIONS"
        ),
        pending_work=_aggregate_pending(subresults),
        history=_aggregate_history(subresults),
        operational=OperationalEvidence(
            stages=tuple(stage for result in subresults for stage in result.operational.stages)
        ),
    )


def _aggregate_status(results: Sequence[ApplicationResult]) -> ApplicationStatus:
    """Apply the v0 ordered-route completion truth table."""
    if all(result.status is ApplicationStatus.COMPLETED for result in results):
        return ApplicationStatus.COMPLETED
    success = any(
        result.status in {ApplicationStatus.COMPLETED, ApplicationStatus.PARTIAL}
        for result in results
    )
    if success:
        return ApplicationStatus.PARTIAL
    if any(result.status is ApplicationStatus.NEEDS_ATTENTION for result in results):
        return ApplicationStatus.NEEDS_ATTENTION
    return ApplicationStatus.FAILED


def _scalar_evidence(
    results: Sequence[ApplicationResult], attribute: str, conflict: str
) -> str | None:
    """Preserve one equal scalar or expose a bounded conflict instead of silently choosing one."""
    values = {
        getattr(result, attribute) for result in results if getattr(result, attribute) is not None
    }
    if not values:
        return None
    return values.pop() if len(values) == 1 else conflict


def _aggregate_pending(results: Sequence[ApplicationResult]) -> PendingWorkStatus:
    """Retain one route projection or fail closed when scalar public evidence cannot represent many."""
    pending = [result.pending_work for result in results if result.pending_work.required]
    if not pending:
        return PendingWorkStatus()
    if len(pending) == 1:
        return pending[0]
    return PendingWorkStatus(required=True, error="MULTIPLE_ROUTE_PENDING_WORK")


def _aggregate_history(results: Sequence[ApplicationResult]) -> GitHistoryResult:
    """Retain one history outcome or state that multiple route-local outcomes are unrepresentable."""
    history = [
        result.history for result in results if result.history.status is not HistoryStatus.DISABLED
    ]
    if not history:
        return GitHistoryResult.disabled()
    if len(history) == 1:
        return history[0]
    return GitHistoryResult(HistoryStatus.FAILED, reason="MULTIPLE_ROUTE_HISTORY")
