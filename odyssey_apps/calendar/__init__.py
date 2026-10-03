"""Calendar application boundary for deterministic v0 queries and later routed execution."""

from odyssey_apps.catalog import ApplicationDescriptor

from .application import CalendarApplication
from .mutations import CalendarLiteralCaptureResult, CalendarLiteralCaptureService
from .planning import (
    CALENDAR_PLANNER_MODEL,
    CALENDAR_PLANNER_REASONING_EFFORT,
    CalendarFailureCode,
    CalendarIntentKind,
    CalendarPlan,
    CalendarPlannerError,
    CalendarPlanOutcome,
    CalendarRouteExecutor,
    OpenAICalendarPlanner,
    TemporalResolution,
    TemporalResolutionKind,
    calendar_plan_json_schema,
    parse_calendar_plan,
    render_calendar_prompt,
    validate_calendar_plan_for_source,
)
from .presentation import calendar_to_response
from .queries import (
    CalendarCapture,
    CalendarDayView,
    CalendarJournal,
    CalendarMonth,
    CalendarMonthDay,
    CalendarQueryError,
    CalendarQueryService,
    CalendarReference,
    normalize_month,
)

CALENDAR_DESCRIPTOR = ApplicationDescriptor(
    id="calendar",
    routing_description="temporal interpretation of date-qualified statements, day/date-owned occurrences, and Calendar navigation",
    dependencies=("temporal",),
)

__all__ = [
    "CALENDAR_DESCRIPTOR",
    "CalendarApplication",
    "CalendarLiteralCaptureResult",
    "CalendarLiteralCaptureService",
    "CalendarFailureCode",
    "CalendarIntentKind",
    "CalendarPlan",
    "CalendarPlanOutcome",
    "CalendarPlannerError",
    "CalendarRouteExecutor",
    "CalendarCapture",
    "CalendarDayView",
    "CalendarJournal",
    "CalendarMonth",
    "CalendarMonthDay",
    "CalendarQueryError",
    "CalendarQueryService",
    "CalendarReference",
    "CALENDAR_PLANNER_MODEL",
    "CALENDAR_PLANNER_REASONING_EFFORT",
    "OpenAICalendarPlanner",
    "TemporalResolution",
    "TemporalResolutionKind",
    "calendar_plan_json_schema",
    "calendar_to_response",
    "normalize_month",
    "parse_calendar_plan",
    "render_calendar_prompt",
    "validate_calendar_plan_for_source",
]
