"""Calendar's deterministic HTTP-query application boundary."""

from __future__ import annotations

from .presentation import calendar_to_response
from .queries import CalendarQueryService


class CalendarApplication:
    """Own Calendar v0 query dispatch, validation, and presentation without mutation authority."""

    def __init__(self, queries: CalendarQueryService) -> None:
        """Bind Calendar's deterministic query service supplied by runtime composition."""
        self._queries = queries

    def query(self, operation: str, payload: dict[str, object]) -> dict[str, object]:
        """Execute one closed Calendar read operation and return its public projection.

        Raises:
            ValueError: If the operation or payload has fields outside Calendar's v0 contract.
            CalendarQueryError: If canonical state cannot safely ground the requested projection.
        """
        if operation == "month":
            if set(payload) != {"month"} or not isinstance(payload.get("month"), str):
                raise ValueError("Calendar month payload is invalid")
            return calendar_to_response(self._queries.month(payload["month"]))
        if operation == "day":
            if set(payload) != {"date"} or not isinstance(payload.get("date"), str):
                raise ValueError("Calendar day payload is invalid")
            return calendar_to_response(self._queries.day(payload["date"]))
        raise ValueError("Calendar operation is unsupported")
