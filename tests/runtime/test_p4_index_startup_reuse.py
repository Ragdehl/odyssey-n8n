"""Optional P4 restart reuses complete derived indexes, never a stale source."""

from __future__ import annotations

import os
import sqlite3

import pytest

from odyssey_core.context import ContextIndex
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_runtime.index_startup import p4_indexes_reusable
from tests.core.test_context import KeywordEmbedder, note
from tests.core.test_context import schema as loaded_schema
from tests.core.test_context_deterministic_projection import write


@pytest.fixture
def fx(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = VaultRepository(root)
    schema = loaded_schema.__wrapped__()
    write(repo, "people/ana.md", note("ana", "person", "Known.", name="Ana"))
    write(repo, "people/old.md", note("old", "person", "Old.", name="Old", deleted=True))
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    embedder = KeywordEmbedder()
    context.rebuild(repo, schema, embedder)
    semantic.rebuild(repo, schema, embedder)
    return repo, schema, embedder, context, semantic


def ready(fx):
    repo, schema, embedder, context, semantic = fx
    return p4_indexes_reusable(repo, schema, embedder, context, semantic, {})


def test_p4_startup_reuse_keeps_both_indexes_byte_identical(fx):
    _repo, _schema, _embedder, context, semantic = fx
    before = (context.path.read_bytes(), semantic.path.read_bytes())
    assert ready(fx)
    assert (context.path.read_bytes(), semantic.path.read_bytes()) == before


def test_p4_reuses_app_index_when_schema_and_sources_match(fx, tmp_path):
    repo, schema, embedder, context, semantic = fx
    task_semantic = SemanticEntityIndex(tmp_path / "semantic-tasks.sqlite3")
    task_semantic.rebuild(repo, schema, embedder)
    assert p4_indexes_reusable(
        repo, schema, embedder, context, semantic, {"tasks": (task_semantic, schema)}
    )
    with sqlite3.connect(task_semantic.path) as conn:
        conn.execute("UPDATE metadata SET value='different' WHERE key='model_version'")
    assert not p4_indexes_reusable(
        repo, schema, embedder, context, semantic, {"tasks": (task_semantic, schema)}
    )


def test_source_modified_added_deleted_or_moved_forces_p4_rebuild(fx):
    repo, _schema, _embedder, context, semantic = fx
    source = repo.root / "people/ana.md"
    prior = source.read_text()
    timestamp = source.stat().st_mtime_ns
    source.write_text(prior.replace("Known.", "Newly."), encoding="utf-8")
    os.utime(source, ns=(timestamp, timestamp))
    assert not ready(fx)
    source.write_text(prior, encoding="utf-8")
    assert not ready(fx)
    # Restore by rebuilding; then an added Note, soft-deleted note deletion and
    # path rename must each separately invalidate the reuse claim.
    context.rebuild(repo, fx[1], fx[2])
    semantic.rebuild(repo, fx[1], fx[2])
    assert ready(fx)
    write(repo, "new.md", note("new", "person", "New.", name="New"))
    assert not ready(fx)
    (repo.root / "new.md").unlink()
    # The source is once again identical to the indexed snapshot; reuse is safe.
    assert ready(fx)
    context.rebuild(repo, fx[1], fx[2])
    semantic.rebuild(repo, fx[1], fx[2])
    assert ready(fx)
    (repo.root / "people/old.md").unlink()
    assert not ready(fx)


def test_index_model_schema_missing_index_and_corrupt_rows_never_reuse(fx, tmp_path):
    repo, schema, embedder, context, semantic = fx
    other = type("OtherEmbedder", (), {"model_name": "different", "model_version": "1"})()
    assert not p4_indexes_reusable(repo, schema, other, context, semantic, {})
    assert not p4_indexes_reusable(
        repo, {**schema, "schema_version": 99}, embedder, context, semantic, {}
    )
    fake = SemanticEntityIndex(tmp_path / "absent.sqlite3")
    assert not p4_indexes_reusable(repo, schema, embedder, context, fake, {})
    with sqlite3.connect(context.path) as conn:
        conn.execute("DELETE FROM notes WHERE id='ana'")
    assert not ready(fx)
