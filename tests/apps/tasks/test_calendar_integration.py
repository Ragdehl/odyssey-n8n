"""Tasks scheduling metadata projects into Calendar without duplicating task authority."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from odyssey_apps.calendar import CalendarQueryService
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import Note, serialize_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
SCHEMA = compose_application_schema(BASE, (TASK_SCHEMA_EXTENSION,))


class Embedder:
    model_name = "tests/tasks-calendar"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return self.embed_documents(texts)


def _calendar(tmp_path: Path) -> CalendarQueryService:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = Note(
        {
            "id": "task-bank",
            "name": "Llamar al banco",
            "type": "task",
            "status": "completed",
            "target_date": "2026-10-09",
            "deadline_at": "2026-10-12",
            "planned_start_at": "2026-10-09T15:35:00+02:00",
            "planned_end_at": "2026-10-09T17:05:00+02:00",
            "completed_at": "2026-10-10T08:05:00+02:00",
            "created_at": "2026-10-05T07:00:00+02:00",
            "updated_at": "2026-10-10T08:05:00+02:00",
            "created_by": {"human": None, "app": "test"},
            "updated_by": {"human": None, "app": "test"},
            "revision": 1,
            "schema_version": 3,
            "aliases": [],
            "tags": [],
        },
        "- [x] Llamar al banco\n",
    )
    (vault / "llamar al banco - task.md").write_text(serialize_note(note), encoding="utf-8")

    session = Note(
        {
            "id": "session-bank",
            "name": "Work session · Llamar al banco · 2026-10-09T16:10:00+02:00",
            "type": "work_session",
            "task_id": "task-bank",
            "started_at": "2026-10-09T16:10:00+02:00",
            "ended_at": "2026-10-09T16:55:00+02:00",
            "created_at": "2026-10-09T16:10:00+02:00",
            "updated_at": "2026-10-09T16:55:00+02:00",
            "created_by": {"human": None, "app": "tasks"},
            "updated_by": {"human": None, "app": "tasks"},
            "revision": 1,
            "schema_version": 3,
            "aliases": [],
            "tags": [],
        },
        "",
    )
    (vault / "tasks" / "work-sessions").mkdir(parents=True, exist_ok=True)
    (vault / "tasks" / "work-sessions" / "session-bank.md").write_text(
        serialize_note(session), encoding="utf-8"
    )
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    assert index.rebuild(repository, SCHEMA, Embedder()) == 2
    notes = NotesQueryService(repository, SCHEMA, index)
    return CalendarQueryService(repository, SCHEMA, notes)


def test_task_dates_are_calendar_projection_coordinates(tmp_path: Path) -> None:
    calendar = _calendar(tmp_path)
    month = calendar.month("2026-10")
    counts = {day.date: day.task_count for day in month.days if day.task_count}
    assert counts == {"2026-10-09": 1, "2026-10-10": 1, "2026-10-12": 1}
    ninth_month = next(day for day in month.days if day.date == "2026-10-09")
    assert ninth_month.preview_total == 1
    assert [(item.kind, item.source_type, item.label) for item in ninth_month.previews] == [
        ("task", "task", "Llamar al banco")
    ]

    ninth = calendar.day("2026-10-09")
    assert [(item.source.id, item.roles) for item in ninth.tasks] == [
        ("task-bank", ("target", "planned_start", "planned_end"))
    ]
    tenth = calendar.day("2026-10-10")
    assert tenth.tasks[0].roles == ("completed",)
    twelfth = calendar.day("2026-10-12")
    assert twelfth.tasks[0].roles == ("deadline",)


def test_task_schedule_uses_planned_interval_and_keeps_date_only_deadline_all_day(
    tmp_path: Path,
) -> None:
    calendar = _calendar(tmp_path)

    schedule = calendar.schedule("2026-10-09", 7)

    ninth = schedule.days[0]
    assert ninth.all_day == ()
    assert [
        (item.kind, item.label, item.role, item.start_time, item.end_time) for item in ninth.timed
    ] == [
        ("task", "Llamar al banco", "planned", "15:35", "17:05"),
        ("work_session", "Llamar al banco", "work_session", "16:10", "16:55"),
    ]

    twelfth = schedule.days[3]
    assert [(item.kind, item.label, item.role, item.start_time) for item in twelfth.all_day] == [
        ("task", "Llamar al banco", "deadline", None)
    ]

    # completed_at is lifecycle history, not a planning-grid coordinate.
    tenth = schedule.days[1]
    assert tenth.all_day == ()
    assert tenth.timed == ()
