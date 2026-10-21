"""E5: canonical Events project into Calendar without becoming Tasks.

Synthetic Core persistence is intentional: this proves the generic Writer-
compatible note representation and Calendar readback, NOT the GPT/Router/E3
chat mutation path, which needs its own later acceptance gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.calendar import CalendarQueryError, CalendarQueryService
from odyssey_apps.events import EVENT_SCHEMA_EXTENSION
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core import create_entity, update_entity
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import NoteValidationError, parse_note
from odyssey_core.storage import VaultRepository
from tests.apps.calendar.test_queries import Embedder

ROOT = Path(__file__).resolve().parents[3]
CLOCK = "2026-10-21T10:00:00+02:00"


def setup(tmp_path):
    base = json.loads((ROOT / "config/note-schema.json").read_text())
    schema = compose_application_schema(base, (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION))
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "events").mkdir()
    repo = VaultRepository(vault)
    return schema, repo


def calendar(tmp_path, repo, schema):
    index = ContextIndex(tmp_path / "index" / "context.sqlite3")
    index.rebuild(repo, schema, Embedder())
    return CalendarQueryService(repo, schema, NotesQueryService(repo, schema, index))


def add_event(repo, schema, name="Campamento", **properties):
    return create_entity(
        repo,
        schema,
        path="events/school-camp.md",
        entity_id="event-camp-1",
        metadata={"type": "event", "name": name, "event_status": "scheduled", **properties},
        content="Material necesario: gorra y agua.",
        actor="fixture",
        now=CLOCK,
    )


def test_event_schema_is_generic_core_managed_persistence(tmp_path):
    schema, repo = setup(tmp_path)
    add_event(repo, schema, name="Foto colegio", start_date="2026-11-22")
    note = parse_note(repo.read_text("events/school-camp.md"))
    assert note.metadata["type"] == "event"
    assert note.metadata["event_status"] == "scheduled"
    assert note.metadata["start_date"] == "2026-11-22"
    query = calendar(tmp_path, repo, schema)
    assert query.month("2026-11").days[21].event_count == 1
    assert query.month("2026-11").days[21].task_count == 0
    assert [(item.source.name, item.roles) for item in query.day("2026-11-22").events] == [
        ("Foto colegio", ("occurrence",))
    ]
    item = query.schedule("2026-11-22", 1).days[0].all_day
    assert len(item) == 1 and item[0].kind == "event" and item[0].source_id == "event-camp-1"
    assert query.schedule("2026-11-21", 1).days[0].all_day == ()


def test_multiday_interval_is_one_canonical_event_and_three_day_views(tmp_path):
    schema, repo = setup(tmp_path)
    add_event(repo, schema, start_date="2027-07-04", end_date="2027-07-08")
    query = calendar(tmp_path, repo, schema)
    window = query.schedule("2027-07-03", 7).days
    assert [sum(i.kind == "event" for i in day.all_day) for day in window] == [0, 1, 1, 1, 1, 1, 0]
    assert all(query.month("2027-07").days[n - 1].event_count == 1 for n in range(4, 9))
    assert len(list(repo.list_markdown_paths())) == 1
    assert query.day("2027-07-07").events[0].source.name == "Campamento"


def test_timed_event_projects_hour_without_invented_end(tmp_path):
    schema, repo = setup(tmp_path)
    add_event(
        repo,
        schema,
        name="Teatro",
        start_date="2026-11-22",
        start_at="2026-11-22T17:45:00+01:00",
    )
    day = calendar(tmp_path, repo, schema).schedule("2026-11-22", 1).days[0]
    assert day.all_day == ()
    assert len(day.timed) == 1
    assert day.timed[0].start_time == "17:45" and day.timed[0].end_time is None


def test_cancelled_event_remains_markdown_but_disappears_from_calendar(tmp_path):
    schema, repo = setup(tmp_path)
    add_event(repo, schema, start_date="2026-11-22")
    update_entity(
        repo,
        schema,
        path="events/school-camp.md",
        expected_id="event-camp-1",
        expected_revision=1,
        set_metadata={"event_status": "cancelled"},
        actor="fixture",
        now="2026-10-21T11:00:00+02:00",
    )
    assert (
        parse_note(repo.read_text("events/school-camp.md")).metadata["event_status"] == "cancelled"
    )
    query = calendar(tmp_path, repo, schema)
    assert query.month("2026-11").days[21].event_count == 0
    assert query.day("2026-11-22").events == ()
    assert query.schedule("2026-11-22", 1).days[0].all_day == ()


@pytest.mark.parametrize(
    "properties",
    [
        {},
        {"start_date": "2026-02-30"},
        {"start_date": "2026-11-22", "start_at": "2026-11-22T09:00:00"},
        {"start_date": "2026-11-22", "event_status": "unknown"},
    ],
)
def test_canonical_event_schema_rejects_missing_or_unverified_temporal_data(tmp_path, properties):
    schema, repo = setup(tmp_path)
    with pytest.raises(NoteValidationError):
        add_event(repo, schema, **properties)
    assert tuple(repo.list_markdown_paths()) == ()


@pytest.mark.parametrize(
    "properties",
    [
        {"start_date": "2027-07-08", "end_date": "2027-07-04"},
        {"start_date": "2026-11-22", "start_at": "2026-11-23T09:00:00+01:00"},
        {
            "start_date": "2026-11-22",
            "start_at": "2026-11-22T13:00:00+01:00",
            "end_at": "2026-11-22T12:00:00+01:00",
        },
    ],
)
def test_calendar_fails_closed_on_inconsistent_event_interval(tmp_path, properties):
    schema, repo = setup(tmp_path)
    add_event(repo, schema, **properties)
    with pytest.raises(CalendarQueryError):
        calendar(tmp_path, repo, schema).month("2026-11")


def test_weekly_recurrence_is_finite_and_only_on_the_declared_weekday(tmp_path):
    schema, repo = setup(tmp_path)
    add_event(
        repo,
        schema,
        name="Piscina",
        start_date="2027-04-05",
        end_date="2027-06-28",
        recurrence_weekday=0,  # ISO Monday, validated as integer in Event schema
    )
    query = calendar(tmp_path, repo, schema)
    month = query.month("2027-04")
    active = [day.date for day in month.days if day.event_count]
    assert active == ["2027-04-05", "2027-04-12", "2027-04-19", "2027-04-26"]
    window = query.schedule("2027-04-05", 7).days
    assert [len(day.all_day) for day in window] == [1, 0, 0, 0, 0, 0, 0]
    assert query.day("2027-04-06").events == ()
    assert query.day("2027-06-28").events[0].source.name == "Piscina"
    assert query.day("2027-07-05").events == ()
    assert len(tuple(repo.list_markdown_paths())) == 1


@pytest.mark.parametrize(
    "properties",
    [
        {"start_date": "2027-04-05", "recurrence_weekday": 0},
        {
            "start_date": "2027-04-05",
            "end_date": "2027-06-28",
            "recurrence_weekday": 0,
            "start_at": "2027-04-05T09:00:00+02:00",
        },
    ],
)
def test_calendar_rejects_unbounded_or_naive_weekly_recurrence(tmp_path, properties):
    schema, repo = setup(tmp_path)
    add_event(repo, schema, **properties)
    with pytest.raises(CalendarQueryError, match="recurrence"):
        calendar(tmp_path, repo, schema).month("2027-04")


@pytest.mark.parametrize("weekday", [-1, 7, "0", True])
def test_event_schema_rejects_invalid_weekday(tmp_path, weekday):
    schema, repo = setup(tmp_path)
    with pytest.raises(NoteValidationError):
        add_event(
            repo,
            schema,
            start_date="2027-04-05",
            end_date="2027-06-28",
            recurrence_weekday=weekday,
        )
