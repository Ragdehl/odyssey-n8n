"""Unicode path versions must not force expensive full-index rebuilds on every write."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.context import ContextIndex, ContextIndexError
from odyssey_core.storage import VaultRepository
from tests.core.test_context import KeywordEmbedder, note
from tests.core.test_context_deterministic_projection import write


@pytest.fixture
def schema():
    return json.loads(
        (Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text()
    )


def test_incremental_refresh_skips_unchanged_accented_filename(tmp_path, schema):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    write(repo, "people/Lucía García.md", note("lucia", "person", "Lucía.", name="Lucía"))
    write(repo, "notes/ordinary.md", note("ordinary", "document", "Original."))
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repo, schema, embedder)

    # A separate valid Core write must not treat Lucía's unchanged version as drift.
    write(repo, "notes/ordinary.md", note("ordinary", "document", "Edited."))
    calls = []
    old_embed = embedder.embed_documents

    def count_embeddings(texts):
        calls.append(len(texts))
        return old_embed(texts)

    embedder.embed_documents = count_embeddings
    assert index.refresh_notes(repo, schema, embedder, note_ids=("ordinary",)) == 1
    assert calls == [1]

    # The freshness guard still rejects a truly externally changed Unicode note.
    write(repo, "people/Lucía García.md", note("lucia", "person", "Changed.", name="Lucía"))
    with pytest.raises(ContextIndexError, match="unrelated index drift"):
        index.refresh_notes(repo, schema, embedder, note_ids=("ordinary",))


def test_external_reconciliation_ignores_unchanged_unicode_filenames(tmp_path, schema):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    write(repo, "people/Lucía García.md", note("lucia", "person", "Lucía.", name="Lucía"))
    write(repo, "notes/ordinary.md", note("ordinary", "document", "Original."))
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repo, schema, embedder)

    # Reconciliation should not read unchanged Unicode paths as external edits.
    assert index.reconcile_external_changes(repo, schema, embedder) == 0
    write(repo, "notes/ordinary.md", note("ordinary", "document", "Updated."))
    assert index.reconcile_external_changes(repo, schema, embedder) == 1
    assert index.reconcile_external_changes(repo, schema, embedder) == 0
