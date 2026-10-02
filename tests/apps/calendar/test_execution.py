"""Deterministic Calendar route execution over the shared Core result boundary."""

from __future__ import annotations

import json
from pathlib import Path

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
from odyssey_core.semantic_write import (
    ApplyTo,
    IdentityBinding,
    IdentityIntent,
    IdentityPart,
    LiteralPart,
    SemanticFact,
    SemanticWriteIntent,
    SemanticWriteOperation,
    TemporalReferencePart,
)
from odyssey_core.temporal import DateRange

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def schema() -> dict:
    """Load the active canonical schema used for Core semantic lowering."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


class FixedPlanner:
    """Return one deterministic Calendar plan and retain exact planner inputs."""

    def __init__(self, result: CalendarPlan | Exception) -> None:
        """Retain one local plan or simulated provider failure."""
        self.result = result
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def plan(self, source: str, conversation_context=()):  # type: ignore[no-untyped-def]
        """Retain the exact routed source and prior context without model execution."""
        self.calls.append((source, tuple(conversation_context)))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def completed(request_id: str, affected: tuple[str, ...] = ()) -> ApplicationResult:
    """Return compact successful route evidence."""
    return ApplicationResult(request_id, ApplicationStatus.COMPLETED, (), affected)


def exact_day_plan(date: str = "2026-10-03") -> CalendarPlan:
    """Build one exact Day-owned literal plan."""
    return CalendarPlan(
        CalendarPlanOutcome.PLAN,
        CalendarIntentKind.DAY_LITERAL_CAPTURE,
        TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date=date),
    )


def fail_plan(code: CalendarFailureCode, temporal: TemporalResolution) -> CalendarPlan:
    """Build one understood but non-executable Calendar plan."""
    return CalendarPlan(CalendarPlanOutcome.FAIL_CLOSED, None, temporal, failure_code=code)


def marta_plan() -> CalendarPlan:
    """Build one Core-owned semantic write containing an exact temporal reference."""
    marta = IdentityIntent("Marta", IdentityBinding.DESCRIBED, "Marta", "person")
    airbus = IdentityIntent("Airbus", IdentityBinding.DESCRIBED, "Airbus", None)
    semantic = SemanticWriteIntent(
        (
            SemanticWriteOperation(
                marta,
                ApplyTo.ONE,
                "record",
                (
                    SemanticFact(
                        (
                            LiteralPart("Empieza "),
                            TemporalReferencePart("mañana", "2026-10-03"),
                            LiteralPart(" a trabajar en "),
                            IdentityPart("Airbus", airbus),
                            LiteralPart("."),
                        )
                    ),
                ),
            ),
        )
    )
    return CalendarPlan(
        CalendarPlanOutcome.PLAN,
        CalendarIntentKind.CORE_SEMANTIC_WRITE,
        TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-03"),
        semantic,
    )


def test_exact_day_route_preserves_source_and_prior_context(schema: dict) -> None:
    """Pass the untouched routed source to Day capture and only prior turns to Calendar planning."""
    planner = FixedPlanner(exact_day_plan())
    captures: list[tuple[object, ...]] = []
    source = "Mañana viene el fontanero"
    prior = ({"role": "user", "text": "antes"},)

    def capture(date, literal, request_id, actor):  # type: ignore[no-untyped-def]
        captures.append((date, literal, request_id, actor))
        return completed(request_id, (f"date:{date}",))

    executor = CalendarRouteExecutor(
        planner,
        schema=schema,
        capture_day_literal=capture,
        execute_core_write=lambda *_args: pytest.fail("Core write must not run"),
    )
    result = executor(source, "route-1", None, prior)

    assert result.status is ApplicationStatus.COMPLETED
    assert captures == [("2026-10-03", source, "route-1", None)]
    assert planner.calls == [(source, prior)]


def test_range_vague_and_out_of_scope_fail_closed_without_any_mutation(schema: dict) -> None:
    """Never coerce ranges, vagueness, or foreign semantics into a fake exact Day capture."""
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
            schema=schema,
            capture_day_literal=lambda *_args: pytest.fail("capture must not run"),
            execute_core_write=lambda *_args: pytest.fail("Core write must not run"),
        )
        result = executor("temporal source", "route-x")
        assert result.status is ApplicationStatus.NEEDS_ATTENTION
        assert (result.clarification_code == code) is clarifies
        assert (result.planning_error == code) is (not clarifies)


def test_entity_owned_temporal_statement_compiles_through_core_semantic_write(schema: dict) -> None:
    """Let Calendar normalize time while Core still owns reference and write mechanics."""
    planner = FixedPlanner(marta_plan())
    seen: list[object] = []

    def execute_core(plan, source, request_id, actor, context):  # type: ignore[no-untyped-def]
        seen.append((plan, source, request_id, actor, tuple(context)))
        fact = plan.actions[0].units[0].facts[0]
        assert "[[calendar/days/2026-10-03|mañana]]" in fact
        assert plan.actions[0].units[0].references[0].mention == "Airbus"
        return completed(request_id)

    source = "Marta empieza mañana a trabajar en Airbus."
    prior = ({"role": "assistant", "text": "context"},)
    executor = CalendarRouteExecutor(
        planner,
        schema=schema,
        capture_day_literal=lambda *_args: pytest.fail("Day capture must not run"),
        execute_core_write=execute_core,
    )
    result = executor(source, "route-2", None, prior)

    assert result.status is ApplicationStatus.COMPLETED
    assert seen and seen[0][1:] == (source, "route-2", None, prior)


def test_planner_failure_produces_no_executable_side_effect(schema: dict) -> None:
    """Contain provider/planner failure before either Calendar or Core mutation callback runs."""
    executor = CalendarRouteExecutor(
        FixedPlanner(RuntimeError("provider failed")),
        schema=schema,
        capture_day_literal=lambda *_args: pytest.fail("capture must not run"),
        execute_core_write=lambda *_args: pytest.fail("Core write must not run"),
    )
    result = executor("Mañana viene el fontanero", "route-3")
    assert result.status is ApplicationStatus.FAILED
    assert result.planning_error == "CALENDAR_PLANNER_INVALID"
