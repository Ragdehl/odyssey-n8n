"""Calendar route execution keeps app authority minimal and returns shared work to Core."""

from __future__ import annotations

import pytest

from odyssey_apps.calendar import (
    CalendarFailureCode,
    CalendarIntentKind,
    CalendarPlan,
    CalendarPlanOutcome,
    CalendarRouteExecutor,
    TemporalResolution,
    TemporalResolutionKind,
)
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainInterpretation,
)
from odyssey_core.temporal import DateRange


class FixedPlanner:
    """Return one deterministic Calendar interpretation and retain exact inputs."""

    def __init__(self, result: CalendarPlan | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def plan(self, source: str, conversation_context=()):  # type: ignore[no-untyped-def]
        self.calls.append((source, tuple(conversation_context)))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def completed(request_id: str, affected: tuple[str, ...] = ()) -> ApplicationResult:
    return ApplicationResult(request_id, ApplicationStatus.COMPLETED, (), affected)


def exact_day_plan(date: str = "2026-10-03") -> CalendarPlan:
    return CalendarPlan(
        CalendarPlanOutcome.PLAN,
        CalendarIntentKind.DAY_LITERAL_CAPTURE,
        TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date=date),
    )


def delegate_plan(text: str = "mañana", date: str = "2026-10-03") -> CalendarPlan:
    return CalendarPlan(
        CalendarPlanOutcome.PLAN,
        CalendarIntentKind.DELEGATE_TO_CORE,
        TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date=date),
        temporal_text=text,
    )


def fail_plan(code: CalendarFailureCode, temporal: TemporalResolution) -> CalendarPlan:
    return CalendarPlan(CalendarPlanOutcome.FAIL_CLOSED, None, temporal, failure_code=code)


def test_day_owned_occurrence_preserves_exact_source_and_never_calls_core() -> None:
    planner = FixedPlanner(exact_day_plan())
    captures: list[tuple[object, ...]] = []
    source = "Mañana viene el fontanero"
    prior = ({"role": "user", "text": "antes"},)

    def capture(date, literal, request_id, actor):  # type: ignore[no-untyped-def]
        captures.append((date, literal, request_id, actor))
        return completed(request_id, (f"date:{date}",))

    executor = CalendarRouteExecutor(
        planner,
        capture_day_literal=capture,
        execute_core=lambda *_args: pytest.fail("Day-owned capture must not call Core planner"),
    )
    result = executor(source, "route-1", None, prior)
    assert result.status is ApplicationStatus.COMPLETED
    assert captures == [("2026-10-03", source, "route-1", None)]
    assert planner.calls == [(source, prior)]


def test_durable_temporal_statement_hands_only_domain_interpretation_to_core() -> None:
    planner = FixedPlanner(delegate_plan())
    seen: list[tuple[object, ...]] = []
    source = "Marta empieza mañana a trabajar en Airbus."
    prior = ({"role": "assistant", "text": "context"},)

    def execute_core(
        routed_source,
        request_id,
        actor,
        context,
        interpretation,  # type: ignore[no-untyped-def]
    ):
        seen.append((routed_source, request_id, actor, tuple(context), interpretation))
        assert isinstance(interpretation, DomainInterpretation)
        assert interpretation.capability_id == "calendar"
        assert interpretation.source_text == source
        assert interpretation.intent == "TEMPORAL_ANNOTATION"
        assert len(interpretation.evidence) == 1
        temporal = interpretation.evidence[0]
        assert temporal.kind == TEMPORAL_REFERENCE_EVIDENCE
        assert temporal.source_text == "mañana"
        assert temporal.value == "2026-10-03"
        # No RequestPlan, target, identity, fact, or candidate scope comes from Calendar.
        assert set(interpretation.to_prompt_payload()) == {"capability_id", "intent", "evidence"}
        return completed(request_id)

    executor = CalendarRouteExecutor(
        planner,
        capture_day_literal=lambda *_args: pytest.fail("durable knowledge is not a Day literal"),
        execute_core=execute_core,
    )
    result = executor(source, "route-2", None, prior)
    assert result.status is ApplicationStatus.COMPLETED
    assert len(seen) == 1
    assert seen[0][:4] == (source, "route-2", None, prior)


def test_range_vague_and_foreign_semantics_fail_closed_without_callbacks() -> None:
    cases = [
        (
            fail_plan(
                CalendarFailureCode.RANGE_REQUIRES_RANGE_AWARE_OPERATION,
                TemporalResolution(
                    TemporalResolutionKind.DATE_RANGE,
                    date_range=DateRange("2026-10-05", "2026-10-12"),
                ),
            ),
            "RANGE_REQUIRES_RANGE_AWARE_OPERATION",
            False,
        ),
        (
            fail_plan(
                CalendarFailureCode.TEMPORAL_UNRESOLVED,
                TemporalResolution(TemporalResolutionKind.UNSPECIFIED),
            ),
            "TEMPORAL_UNRESOLVED",
            True,
        ),
        (
            fail_plan(
                CalendarFailureCode.OUT_OF_SCOPE,
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-09"),
            ),
            "OUT_OF_SCOPE",
            False,
        ),
    ]
    for plan, code, clarifies in cases:
        executor = CalendarRouteExecutor(
            FixedPlanner(plan),
            capture_day_literal=lambda *_args: pytest.fail("capture must not run"),
            execute_core=lambda *_args: pytest.fail("Core must not run"),
        )
        result = executor("temporal source", "route-x")
        assert result.status is ApplicationStatus.NEEDS_ATTENTION
        assert (result.clarification_code == code) is clarifies
        assert (result.planning_error == code) is (not clarifies)


def test_planner_failure_produces_no_executable_side_effect() -> None:
    executor = CalendarRouteExecutor(
        FixedPlanner(RuntimeError("provider failed")),
        capture_day_literal=lambda *_args: pytest.fail("capture must not run"),
        execute_core=lambda *_args: pytest.fail("Core must not run"),
    )
    result = executor("Mañana viene el fontanero", "route-3")
    assert result.status is ApplicationStatus.FAILED
    assert result.planning_error == "CALENDAR_PLANNER_INVALID"
