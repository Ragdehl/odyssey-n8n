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


def test_metadata_only_refresh_preserves_link_graph_without_global_rebuild(fx, monkeypatch):
    """Backfill updates filters and inventory but cannot change fixed-body links."""
    from odyssey_core import context as context_module
    from odyssey_core.notes import Note

    repo, schema, embedder, index = fx
    source = "people/Lucía.md"
    destination = "people/marta.md"
    previous = note(
        "lucia",
        "person",
        "Conocí a [[people/marta|Marta]].",
        name="Lucía",
    )
    write(repo, source, previous)
    index.rebuild(repo, schema, embedder)
    with sqlite3.connect(index.path) as conn:
        links_before = conn.execute(
            "SELECT * FROM note_links ORDER BY source_id,target_id"
        ).fetchall()
        mentions_before = conn.execute(
            "SELECT * FROM note_mentions ORDER BY source_id,target_id"
        ).fetchall()

    updated = Note(
        {**previous.metadata, "revision": previous.metadata["revision"] + 1},
        previous.content,
    )
    write(repo, source, updated)

    def unexpected_links(_connection):
        raise AssertionError("Metadata-only refresh must not rebuild every wikilink")

    monkeypatch.setattr(context_module, "_refresh_derived_links", unexpected_links)
    assert index.refresh_notes(repo, schema, embedder, note_ids=("lucia",)) == 1
    with sqlite3.connect(index.path) as conn:
        assert (
            conn.execute("SELECT * FROM note_links ORDER BY source_id,target_id").fetchall()
            == links_before
        )
        assert (
            conn.execute("SELECT * FROM note_mentions ORDER BY source_id,target_id").fetchall()
            == mentions_before
        )
        revision = dict(
            conn.execute("SELECT field,value_json FROM note_attributes WHERE note_id='lucia'")
        )
        assert json.loads(revision["revision"]) == updated.metadata["revision"]
    assert destination in repo.list_markdown_paths()


def test_body_change_still_rebuilds_global_links(fx, monkeypatch):
    """A newly linked target must never take the metadata-only shortcut."""
    from odyssey_core import context as context_module

    repo, schema, embedder, index = fx
    calls = []
    original = context_module._refresh_derived_links

    def count_links(conn):
        calls.append(True)
        return original(conn)

    monkeypatch.setattr(context_module, "_refresh_derived_links", count_links)
    write(
        repo,
        "people/Lucía.md",
        note("lucia", "person", "Visité [[people/marta|Marta]].", name="Lucía"),
    )
    assert index.refresh_notes(repo, schema, embedder, note_ids=("lucia",)) == 1
    assert calls == [True]
    with sqlite3.connect(index.path) as conn:
        assert conn.execute(
            "SELECT source_id,target_id FROM note_links WHERE source_id='lucia'"
        ).fetchall() == [("lucia", "marta")]


def test_corrupt_fact_projection_disables_metadata_only_shortcut(fx, monkeypatch):
    """A mismatched existing fact projection forces derived links to be repaired."""
    from odyssey_core import context as context_module
    from odyssey_core.notes import Note, parse_note

    repo, schema, embedder, index = fx
    with sqlite3.connect(index.path) as db:
        db.execute("UPDATE note_fact_integrity SET status='malformed' WHERE note_id='lucia'")
    before = parse_note(repo.read_text("people/Lucía.md"))
    write(
        repo,
        "people/Lucía.md",
        Note({**before.metadata, "revision": before.metadata["revision"] + 1}, before.content),
    )
    calls = []
    original = context_module._refresh_derived_links

    def record(conn):
        calls.append(True)
        return original(conn)

    monkeypatch.setattr(context_module, "_refresh_derived_links", record)
    assert index.refresh_notes(repo, schema, embedder, note_ids=("lucia",)) == 1
    assert calls == [True]
    with sqlite3.connect(index.path) as db:
        assert db.execute(
            "SELECT status FROM note_fact_integrity WHERE note_id='lucia'"
        ).fetchone() == ("valid",)
