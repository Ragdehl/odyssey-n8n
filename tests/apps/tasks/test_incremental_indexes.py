from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION, TaskDirectMutationService
from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
SCHEMA = compose_application_schema(BASE, (TASK_SCHEMA_EXTENSION,))


class Embedder:
    model_name = "tests/task-incremental"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [self._embed(text) for text in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [self._embed(text) for text in texts]

    @staticmethod
    def _embed(text: str) -> list[float]:
        lowered = text.casefold()
        return [float("completed" in lowered), float("pending" in lowered), 0.5]


def test_task_lifecycle_incrementally_refreshes_derived_indexes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "tasks").mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="tasks/bank.md",
        entity_id="task-bank",
        metadata={
            "name": "Llamar al banco",
            "type": "task",
            "status": "pending",
            "target_date": "2026-10-09",
        },
        content="- Llamar al banco.\n",
        actor="fixture",
        now="2026-10-05T09:00:00+02:00",
    )
    embedder = Embedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    assert context.rebuild(repository, SCHEMA, embedder) == 1
    assert semantic.rebuild(repository, SCHEMA, embedder) == 1

    old_raw = repository.read_text("tasks/bank.md")
    old_hash = hashlib.sha256(old_raw.encode()).hexdigest()
    service = TaskDirectMutationService(repository, SCHEMA, None)
    result = service.set_completed(
        note_id="task-bank",
        completed=True,
        expected_revision=1,
        expected_source_hash=old_hash,
        request_id="complete-bank",
        actor="test",
        now="2026-10-05T09:10:00+02:00",
    )
    assert result.status == "completed"
    assert result.path == "tasks/bank.md"
    assert result.source_hash != old_hash

    assert (
        context.refresh_existing_note(
            repository,
            SCHEMA,
            embedder,
            path=result.path,
            expected_source_hash=old_hash,
        )
        == result.source_hash
    )
    assert (
        semantic.refresh_existing_note(
            repository,
            SCHEMA,
            embedder,
            path=result.path,
            expected_source_hash=old_hash,
        )
        == result.source_hash
    )

    with sqlite3.connect(context.path) as connection:
        assert connection.execute(
            "SELECT source_hash FROM notes WHERE id = 'task-bank'"
        ).fetchone() == (result.source_hash,)
        assert connection.execute(
            "SELECT value FROM properties WHERE note_id = 'task-bank' AND field = 'status'"
        ).fetchone() == ("completed",)
        assert connection.execute(
            "SELECT value FROM properties WHERE note_id = 'task-bank' AND field = 'completed_at'"
        ).fetchone() == ("2026-10-05T07:10:00.000000Z",)
    with sqlite3.connect(semantic.path) as connection:
        assert connection.execute(
            "SELECT source_hash FROM notes WHERE id = 'task-bank'"
        ).fetchone() == (result.source_hash,)

    # Lifecycle metadata changed, but ordinary Task knowledge did not.
    assert "- Llamar al banco." in repository.read_text("tasks/bank.md")
