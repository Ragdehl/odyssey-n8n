"""Calendar application boundary for deterministic v0 queries and later routed execution."""

from odyssey_apps.catalog import ApplicationDescriptor

from .application import CalendarApplication
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
    routing_description="day/date-owned occurrences and Calendar navigation",
    dependencies=("temporal",),
)

__all__ = [
    "CALENDAR_DESCRIPTOR",
    "CalendarApplication",
    "CalendarCapture",
    "CalendarDayView",
    "CalendarJournal",
    "CalendarMonth",
    "CalendarMonthDay",
    "CalendarQueryError",
    "CalendarQueryService",
    "CalendarReference",
    "calendar_to_response",
    "normalize_month",
]
