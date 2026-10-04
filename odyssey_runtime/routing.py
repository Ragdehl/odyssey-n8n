"""Bounded ordered execution of validated application route plans.

This module is a runtime adapter: it keeps the Core application result as the only public
completion authority while giving routed subexecutions deterministic, non-delivery locators.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
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
) -> ApplicationResult:
    """Route and execute independent spans sequentially under one outer request identity.

    The whole plan is revalidated before execution.  Route-local exceptions, unavailable apps,
    and invalid correlations become bounded failed route evidence, allowing later independent
    routes to continue.  No route receives sibling current-message text.
    """
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

    subresults: list[ApplicationResult] = []
    for ordinal, route in enumerate(plan.routes):
        locator = route_execution_id(outer_request_id, ordinal)
        subresults.append(
            _execute_route(
                route,
                locator,
                core_execute,
                application_executors,
                temporal_execute,
                authenticated_actor,
                conversation_context,
            )
        )
    return _prepend_router_stage(_aggregate(outer_request_id, subresults), stage)


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
) -> ApplicationResult:
    """Contain one route executor failure and reject substituted route correlation."""
    try:
        if route.capability_id == CORE_CAPABILITY_ID:
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
