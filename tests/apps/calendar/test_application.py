"""Deterministic coverage for Calendar's application-owned query boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from odyssey_apps.calendar import (
    CalendarApplication,
    CalendarDayView,
    CalendarMonth,
    CalendarMonthDay,
    CalendarMonthPreview,
    CalendarSchedule,
    CalendarScheduleDay,
    CalendarScheduleItem,
)


def test_calendar_application_dispatches_closed_month_and_day_queries() -> None:
    """Keep runtime transport free of Calendar operation semantics and presentation rules."""
    calls: list[tuple[str, str]] = []
    month = CalendarMonth(
        "2026-10",
        (
            CalendarMonthDay(
                "2026-10-01",
                False,
                False,
                0,
                0,
                0,
                previews=(CalendarMonthPreview("journal", "journal_entry", "Diario", "Texto."),),
                preview_total=1,
            ),
        ),
    )
    day = CalendarDayView("2026-10-01", False, (), (), (), ())

    queries = SimpleNamespace(
        month=lambda value: calls.append(("month", value)) or month,
        day=lambda value: calls.append(("day", value)) or day,
    )
    application = CalendarApplication(queries)

    assert application.query("month", {"month": "2026-10"}) == {
        "kind": "calendar_month",
        "month": "2026-10",
        "days": [
            {
                "date": "2026-10-01",
                "materialized": False,
                "has_content": False,
                "journal_count": 0,
                "captured_fact_count": 0,
                "reference_count": 0,
                "task_count": 0,
                "preview_total": 1,
                "previews": [
                    {
                        "kind": "journal",
                        "source_type": "journal_entry",
                        "label": "Diario",
                        "text": "Texto.",
                    }
                ],
            }
        ],
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


def test_calendar_application_dispatches_and_serializes_schedule_queries() -> None:
    schedule = CalendarSchedule(
        "2026-10-06",
        3,
        (
            CalendarScheduleDay(
                "2026-10-06",
                (
                    CalendarScheduleItem(
                        "fact", "marta", "person", "Marta", "Viaja a París.", "semantic_date"
                    ),
                ),
                (
                    CalendarScheduleItem(
                        "task",
                        "task-1",
                        "task",
                        "Pintar la pared",
                        None,
                        "planned",
                        "14:00",
                        "16:00",
                    ),
                ),
            ),
            CalendarScheduleDay("2026-10-07", (), ()),
            CalendarScheduleDay("2026-10-08", (), ()),
        ),
    )
    calls: list[tuple[str, str, int]] = []
    application = CalendarApplication(
        SimpleNamespace(
            schedule=lambda start, count: calls.append(("schedule", start, count)) or schedule
        )
    )

    response = application.query("schedule", {"start_date": "2026-10-06", "day_count": 3})

    assert response == {
        "kind": "calendar_schedule",
        "start_date": "2026-10-06",
        "day_count": 3,
        "days": [
            {
                "date": "2026-10-06",
                "all_day": [
                    {
                        "kind": "fact",
                        "source_id": "marta",
                        "source_type": "person",
                        "label": "Marta",
                        "text": "Viaja a París.",
                        "role": "semantic_date",
                    }
                ],
                "timed": [
                    {
                        "kind": "task",
                        "source_id": "task-1",
                        "source_type": "task",
                        "label": "Pintar la pared",
                        "role": "planned",
                        "start_time": "14:00",
                        "end_time": "16:00",
                    }
                ],
            },
            {"date": "2026-10-07", "all_day": [], "timed": []},
            {"date": "2026-10-08", "all_day": [], "timed": []},
        ],
    }
    assert calls == [("schedule", "2026-10-06", 3)]


def test_calendar_application_serializes_bounded_month_previews() -> None:
    """Expose only the bounded presentation union alongside the existing monthly counts."""
    month = CalendarMonth(
        "2026-10",
        (
            CalendarMonthDay(
                date="2026-10-01",
                materialized=True,
                has_content=True,
                journal_count=1,
                captured_fact_count=2,
                reference_count=1,
                preview_total=5,
                previews=(CalendarMonthPreview("capture", "person", "Marta", "Empezó en Airbus."),),
            ),
        ),
    )
    application = CalendarApplication(
        SimpleNamespace(month=lambda _value: month, day=lambda _value: None)
    )

    response = application.query("month", {"month": "2026-10"})

    assert response["days"][0]["preview_total"] == 5
    assert response["days"][0]["previews"] == [
        {
            "kind": "capture",
            "source_type": "person",
            "label": "Marta",
            "text": "Empezó en Airbus.",
        }
    ]


@pytest.mark.parametrize(
    ("operation", "payload"),
    [
        ("month", {}),
        ("month", {"month": "2026-10", "extra": True}),
        ("month", {"month": 202610}),
        ("day", {}),
        ("day", {"date": "2026-10-01", "extra": True}),
        ("day", {"date": 20261001}),
        ("schedule", {}),
        ("schedule", {"start_date": "2026-10-01"}),
        ("schedule", {"start_date": "2026-10-01", "day_count": "3"}),
        ("schedule", {"start_date": "2026-10-01", "day_count": 3, "extra": True}),
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
