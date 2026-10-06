"""Calendar deterministic read/presentation boundary.

Calendar does not participate in conversational routing or mutation planning. Temporal
normalization belongs to Core's temporal boundary; Calendar only projects canonical
state for month/day UI surfaces.
"""

from .application import CalendarApplication
from .presentation import calendar_to_response
from .queries import (
    CalendarCapture,
    CalendarDayView,
    CalendarJournal,
    CalendarMonth,
    CalendarMonthDay,
    CalendarMonthPreview,
    CalendarQueryError,
    CalendarQueryService,
    CalendarReference,
    normalize_month,
)

__all__ = [
    "CalendarApplication",
    "CalendarCapture",
    "CalendarDayView",
    "CalendarJournal",
    "CalendarMonth",
    "CalendarMonthDay",
    "CalendarMonthPreview",
    "CalendarQueryError",
    "CalendarQueryService",
    "CalendarReference",
    "calendar_to_response",
    "normalize_month",
]
