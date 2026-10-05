"""Deterministic coverage for Calendar's application-owned query boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from odyssey_apps.calendar import CalendarApplication, CalendarDayView, CalendarMonth


def test_calendar_application_dispatches_closed_month_and_day_queries() -> None:
    """Keep runtime transport free of Calendar operation semantics and presentation rules."""
    calls: list[tuple[str, str]] = []
    month = CalendarMonth("2026-10", ())
    day = CalendarDayView("2026-10-01", False, (), (), (), ())

    queries = SimpleNamespace(
        month=lambda value: calls.append(("month", value)) or month,
        day=lambda value: calls.append(("day", value)) or day,
    )
    application = CalendarApplication(queries)

    assert application.query("month", {"month": "2026-10"}) == {
        "kind": "calendar_month",
        "month": "2026-10",
        "days": [],
    }
    assert application.query("day", {"date": "2026-10-01"}) == {
        "kind": "calendar_day",
        "date": "2026-10-01",
        "materialized": False,
        "content": [],
        "journals": [],
        "captures": [],
        "references": [],
        "tasks": [],
    }
    assert calls == [("month", "2026-10"), ("day", "2026-10-01")]


@pytest.mark.parametrize(
    ("operation", "payload"),
    [
        ("month", {}),
        ("month", {"month": "2026-10", "extra": True}),
        ("month", {"month": 202610}),
        ("day", {}),
        ("day", {"date": "2026-10-01", "extra": True}),
        ("day", {"date": 20261001}),
        ("week", {"date": "2026-10-01"}),
    ],
)
def test_calendar_application_rejects_operations_outside_v0_contract(
    operation: str, payload: dict[str, object]
) -> None:
    """Fail locally before malformed transport input can reach Calendar's canonical scan."""
    application = CalendarApplication(SimpleNamespace())

    with pytest.raises(ValueError):
        application.query(operation, payload)
