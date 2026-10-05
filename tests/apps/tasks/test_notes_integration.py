"""Tasks remain first-class Notes while lifecycle authority stays with Tasks."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

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
    model_name = "tests/tasks-notes"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return self.embed_documents(texts)


def _write_task(vault: Path) -> None:
    (vault / "llamar al banco - task.md").write_text(
        serialize_note(
            Note(
                {
                    "id": "task-bank",
                    "name": "Llamar al banco",
                    "type": "task",
                    "status": "pending",
                    "target_date": "2026-10-09",
                    "created_at": "2026-10-05T07:00:00+02:00",
                    "updated_at": "2026-10-05T07:00:00+02:00",
                    "created_by": {"human": None, "app": "test"},
                    "updated_by": {"human": None, "app": "test"},
                    "revision": 1,
                    "schema_version": 3,
                    "aliases": [],
                    "tags": [],
                },
                "- [ ] Llamar al banco\n",
            )
        ),
        encoding="utf-8",
    )


def test_task_is_visible_searchable_and_filterable_in_general_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_task(vault)
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    assert index.rebuild(repository, SCHEMA, Embedder()) == 1
    notes = NotesQueryService(repository, SCHEMA, index)

    capabilities = notes.capabilities()
    assert "task" in {item["id"] for item in capabilities.types}
    assert "work_session" not in {item["id"] for item in capabilities.types}
    assert "calendar_day" not in {item["id"] for item in capabilities.types}
    task = next(item for item in capabilities.types if item["id"] == "task")
    canonical_task = next(item for item in SCHEMA["types"] if item["id"] == "task")
    assert task["description"] == canonical_task["description"]
    assert task["properties"] == tuple(
        {
            "id": item["id"],
            "description": item["description"],
            "value_type": item["value_type"],
            "required": item["required"],
            "filterable": item["filterable"],
        }
        for item in canonical_task["properties"]
    )
    status = next(item for item in capabilities.fields if item["id"] == "status")
    assert status["applies_to"] == ("task",)
    assert status["controlled_values"] == (
        "pending",
        "in_progress",
        "completed",
        "cancelled",
    )
    target_date = next(item for item in capabilities.fields if item["id"] == "target_date")
    assert target_date["applies_to"] == ("task",)

    assert [item.id for item in notes.query(mode="feed").items] == ["task-bank"]
    assert [item.id for item in notes.query(mode="local", query="llamar banco").items] == [
        "task-bank"
    ]
    filtered = notes.query(
        mode="feed",
        filters=(
            {"field": "type", "op": "eq", "value": "task"},
            {"field": "status", "op": "eq", "value": "pending"},
        ),
    )
    assert [item.id for item in filtered.items] == ["task-bank"]
