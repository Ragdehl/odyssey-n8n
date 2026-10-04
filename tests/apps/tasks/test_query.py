"""Deterministic Tasks query semantics over canonical Markdown."""

from __future__ import annotations

import json
from pathlib import Path

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION, TaskQueryScope, TaskQueryService
from odyssey_core import create_entity
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]


def build(tmp_path: Path):  # type: ignore[no-untyped-def]
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    base = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    schema = compose_application_schema(base, (TASK_SCHEMA_EXTENSION,))
    rows = (
        ("today-date", "Due today date", "pending", "2026-10-04"),
        ("past-date", "Past date", "pending", "2026-10-03"),
        ("past-time", "Past time", "in_progress", "2026-10-04T20:00:00+02:00"),
        ("future-time", "Future time", "pending", "2026-10-04T22:00:00+02:00"),
        ("done", "Done", "completed", "2026-10-03"),
    )
    for task_id, name, status, deadline in rows:
        create_entity(
            repository,
            schema,
            path=f"{task_id}.md",
            entity_id=task_id,
            metadata={"name": name, "type": "task", "status": status, "deadline_at": deadline},
            content=f"- {name}.\n",
            actor="fixture",
            now="2026-10-04T19:00:00+02:00",
        )
    return TaskQueryService(repository, schema)


def test_overdue_does_not_invent_time_for_date_only_deadline(tmp_path: Path) -> None:
    service = build(tmp_path)
    result = service.query(
        "¿Qué tareas tengo vencidas?",
        TaskQueryScope.OVERDUE,
        now="2026-10-04T21:36:00+02:00",
    )
    assert {item.id for item in result.items} == {"past-date", "past-time"}
    assert "today-date" not in {item.id for item in result.items}


def test_open_and_completed_are_lifecycle_collections(tmp_path: Path) -> None:
    service = build(tmp_path)
    open_result = service.query("pendientes", TaskQueryScope.OPEN, now="2026-10-04T21:36:00+02:00")
    assert {item.id for item in open_result.items} == {
        "today-date",
        "past-date",
        "past-time",
        "future-time",
    }
    completed = service.query(
        "completadas", TaskQueryScope.COMPLETED, now="2026-10-04T21:36:00+02:00"
    )
    assert [item.id for item in completed.items] == ["done"]
