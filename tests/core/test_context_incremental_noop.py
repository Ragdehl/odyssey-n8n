"""Unchanged linked Notes must not trigger re-embeddings during a sibling write."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from odyssey_core.context import ContextIndex, ContextIndexError
from odyssey_core.storage import VaultRepository
from tests.core.test_context import KeywordEmbedder, note
from tests.core.test_context_deterministic_projection import write


@pytest.fixture
def fx(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = VaultRepository(vault)
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text()
    )
    write(repo, "people/Lucía.md", note("lucia", "person", "Original.", name="Lucía"))
    write(repo, "people/marta.md", note("marta", "person", "Original.", name="Marta"))
    embedder = KeywordEmbedder()
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, schema, embedder)
    return repo, schema, embedder, index


def test_unchanged_requested_note_keeps_vector_and_aliases_when_sibling_changes(fx, monkeypatch):
    repo, schema, embedder, index = fx
    with sqlite3.connect(index.path) as db:
        original = db.execute("SELECT embedding FROM notes WHERE id='lucia'").fetchone()
    write(repo, "people/marta.md", note("marta", "person", "Updated.", name="Marta"))
    embedded = []
    previous_embed = embedder.embed_documents

    def record(texts):
        embedded.append(len(texts))
        return previous_embed(texts)

    monkeypatch.setattr(embedder, "embed_documents", record)
    assert index.refresh_notes(repo, schema, embedder, note_ids=("lucia", "marta")) == 1
    assert embedded == [1]
    with sqlite3.connect(index.path) as db:
        assert db.execute("SELECT embedding FROM notes WHERE id='lucia'").fetchone() == original
        assert db.execute("SELECT id FROM notes ORDER BY id").fetchall() == [("lucia",), ("marta",)]


def test_repeating_same_requested_note_requires_zero_embeddings(fx, monkeypatch):
    repo, schema, embedder, index = fx

    def forbidden(_texts):
        raise AssertionError("Unchanged physical Note should never be re-embedded")

    monkeypatch.setattr(embedder, "embed_documents", forbidden)
    assert index.refresh_notes(repo, schema, embedder, note_ids=("lucia",)) == 0


def test_corrupted_old_index_for_unchanged_requested_note_fails_closed(fx):
    repo, schema, embedder, index = fx
    with sqlite3.connect(index.path) as db:
        db.execute("DELETE FROM notes WHERE id='lucia'")
    with pytest.raises(ContextIndexError, match="unrelated index drift"):
        index.refresh_notes(repo, schema, embedder, note_ids=("lucia",))


def test_reembedding_selected_note_still_rejects_external_sibling_change(fx, monkeypatch):
    repo, schema, embedder, index = fx
    write(repo, "people/marta.md", note("marta", "person", "Updated.", name="Marta"))
    original = embedder.embed_documents

    def external_change(texts):
        write(repo, "people/Lucía.md", note("lucia", "person", "Externally changed.", name="Lucía"))
        return original(texts)

    monkeypatch.setattr(embedder, "embed_documents", external_change)
    with pytest.raises(ContextIndexError, match="changed before committing"):
        index.refresh_notes(repo, schema, embedder, note_ids=("lucia", "marta"))


def test_new_target_relinks_existing_source_without_reembedding_it(fx, monkeypatch):
    repo, schema, embedder, index = fx
    write(
        repo,
        "people/Lucía.md",
        note("lucia", "person", "Conocí a [[people/nueva|Nueva]].", name="Lucía"),
    )
    index.rebuild(repo, schema, embedder)
    with sqlite3.connect(index.path) as db:
        assert db.execute("SELECT * FROM note_links WHERE source_id='lucia'").fetchall() == []
    write(repo, "people/nueva.md", note("nueva", "person", "", name="Nueva"))
    lengths = []
    original = embedder.embed_documents

    def record(texts):
        lengths.append(len(texts))
        return original(texts)

    monkeypatch.setattr(embedder, "embed_documents", record)
    assert index.refresh_notes(repo, schema, embedder, note_ids=("lucia", "nueva")) == 1
    assert lengths == [1]
    with sqlite3.connect(index.path) as db:
        assert db.execute(
            "SELECT source_id,target_id FROM note_links WHERE source_id='lucia'"
        ).fetchall() == [("lucia", "nueva")]
