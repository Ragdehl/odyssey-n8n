"""Fail-closed shared context inventory consumed by semantic derived projections."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core.context import ContextIndex
from odyssey_core.schema_types import planning_schema_for_capability
from odyssey_core.semantic import SemanticEntityIndex, SemanticIndexError
from odyssey_core.storage import VaultRepository
from odyssey_core.verified_source_inventory import verified_context_source_inventory
from tests.core.test_context import KeywordEmbedder, note
from tests.core.test_context_deterministic_projection import write


@pytest.fixture
def setup_indexes(tmp_path):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    schema = compose_application_schema(
        json.loads((Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text()),
        (TASK_SCHEMA_EXTENSION,),
    )
    write(repo, "Lucía García.md", note("lucia", "person", "Hola.", name="Lucía García"))
    write(repo, "old.md", note("old", "person", "Old.", name="Old"))
    write(repo, "task.md", note("task", "task", "Task text.", name="Task", status="pending"))
    embedder = KeywordEmbedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    normal = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    tasks = SemanticEntityIndex(tmp_path / "semantic-tasks.sqlite3")
    context.rebuild(repo, schema, embedder)
    normal.rebuild(repo, schema, embedder)
    task_schema = planning_schema_for_capability(schema, "tasks")
    tasks.rebuild(repo, task_schema, embedder)
    return repo, schema, embedder, context, normal, tasks, task_schema


def _rows(index):
    with sqlite3.connect(index.path) as db:
        return db.execute("SELECT * FROM notes ORDER BY id").fetchall()


def test_same_projection_with_shared_inventory_and_no_full_markdown_scan(
    setup_indexes, monkeypatch
):
    repo, schema, embedder, context, normal, tasks, task_schema = setup_indexes
    write(repo, "Lucía García.md", note("lucia", "person", "Updated.", name="Lucía García"))
    context.refresh_notes(repo, schema, embedder, note_ids=("lucia",))
    manifest = verified_context_source_inventory(repo, schema, context.path)
    reads = []
    actual = repo.read_text

    def count(path):
        reads.append(path)
        return actual(path)

    monkeypatch.setattr(repo, "read_text", count)
    assert (
        normal.refresh_notes(
            repo, schema, embedder, note_ids=("lucia",), verified_inventory=manifest
        )
        == 1
    )
    assert (
        tasks.refresh_notes(
            repo, task_schema, embedder, note_ids=("lucia",), verified_inventory=manifest
        )
        == 1
    )
    assert reads == ["Lucía García.md", "Lucía García.md"]
    # The trusted snapshot cannot alter the vectors or identity results.
    comparable = SemanticEntityIndex(context.path.parent / "rebuild.sqlite3")
    comparable.rebuild(repo, schema, embedder)
    assert _rows(normal) == _rows(comparable)


def test_manifest_rejects_source_change_or_new_file(setup_indexes):
    repo, schema, embedder, context, normal, *_ = setup_indexes
    inventory = verified_context_source_inventory(repo, schema, context.path)
    write(repo, "external.md", note("external", "person", "An extra source.", name="External"))
    with pytest.raises(ValueError, match="changed"):
        inventory.assert_unchanged(repo)
    with pytest.raises(SemanticIndexError, match="stale|invalid"):
        normal.refresh_notes(
            repo, schema, embedder, note_ids=("lucia",), verified_inventory=inventory
        )


def test_external_change_during_embedding_rejects_index_write(setup_indexes, monkeypatch):
    repo, schema, embedder, context, normal, *_ = setup_indexes
    write(repo, "Lucía García.md", note("lucia", "person", "Ready.", name="Lucía García"))
    context.refresh_notes(repo, schema, embedder, note_ids=("lucia",))
    inventory = verified_context_source_inventory(repo, schema, context.path)
    prior = _rows(normal)
    actual = embedder.embed_documents

    def external_mutation(texts):
        write(repo, "old.md", note("old", "person", "Altered externally.", name="Old"))
        return actual(texts)

    monkeypatch.setattr(embedder, "embed_documents", external_mutation)
    with pytest.raises(SemanticIndexError, match="changed before semantic index"):
        normal.refresh_notes(
            repo, schema, embedder, note_ids=("lucia",), verified_inventory=inventory
        )
    assert _rows(normal) == prior


def test_deleted_and_type_changed_notes_keep_index_semantics(setup_indexes):
    repo, schema, embedder, context, normal, tasks, task_schema = setup_indexes
    # One soft delete must remove the canonical row; another task changes content.
    write(repo, "old.md", note("old", "person", "Old.", name="Old", deleted=True))
    write(repo, "task.md", note("task", "task", "Changed.", name="Task", status="pending"))
    context.refresh_notes(repo, schema, embedder, note_ids=("old", "task"))
    inventory = verified_context_source_inventory(repo, schema, context.path)
    normal.refresh_notes(
        repo, schema, embedder, note_ids=("old", "task"), verified_inventory=inventory
    )
    tasks.refresh_notes(
        repo, task_schema, embedder, note_ids=("old", "task"), verified_inventory=inventory
    )
    assert "old" not in {r[0] for r in _rows(normal)}
    assert "old" not in {r[0] for r in _rows(tasks)}
    rebuilt = SemanticEntityIndex(context.path.parent / "task-rebuild.sqlite3")
    rebuilt.rebuild(repo, task_schema, embedder)
    assert _rows(tasks) == _rows(rebuilt)
