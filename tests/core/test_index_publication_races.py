"""Real external-process writes before index commit cannot publish stale evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from odyssey_core.context import ContextIndexError
from odyssey_core.notes import serialize_note
from tests.core.test_context import KeywordEmbedder, note
from tests.core.test_indexed_queries_and_freshness import setup


@pytest.fixture
def schema_fixture():
    return json.loads((Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text())


def _outside_process_changes_file(path: Path, content: str) -> None:
    """Change Markdown from a SEPARATE OS process, not the mocked repository."""
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(sys.argv[2],encoding='utf-8')",
            str(path),
            content,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


class InterleavingEmbedder(KeywordEmbedder):
    def __init__(self, action):
        super().__init__()
        self._action = action
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        if self.calls == 1:
            self._action()
        return super().embed_documents(texts)


def test_incremental_external_process_writes_after_markdown_read_before_sql_transaction(
    tmp_path, schema_fixture
):
    repo, index, queries = setup(tmp_path, schema_fixture)
    source = repo.root / "people/ana.md"
    # The scheduled canonical mutation changed the note; the index remains old.
    first = serialize_note(note("ana", "person", "First new.", name="Ana", aliases=["Annie"]))
    source.write_text(first, encoding="utf-8")
    external = serialize_note(
        note("ana", "person", "Second external.", name="Ana", aliases=["Annette"])
    )
    before = index.path.read_bytes()
    embedder = InterleavingEmbedder(lambda: _outside_process_changes_file(source, external))
    with pytest.raises(ContextIndexError, match="changed before committing"):
        index.refresh_notes(repo, schema_fixture, embedder, note_ids=("ana",))
    assert embedder.calls == 1
    assert index.path.read_bytes() == before
    assert source.read_text() == external
    with pytest.raises(Exception, match="stale|incomplete"):
        queries.exact_names("Annie")
    # An explicit next reconciliation can safely index the actual external state.
    assert index.reconcile_external_changes(repo, schema_fixture, KeywordEmbedder()) == 1
    assert queries.exact_names("Annie") == ()
    assert [hit.note.metadata["id"] for hit in queries.exact_names("Annette")] == ["ana"]


def test_full_rebuild_does_not_replace_index_after_external_process_changes_source(
    tmp_path, schema_fixture
):
    repo, index, queries = setup(tmp_path, schema_fixture)
    source = repo.root / "people/ana.md"
    old_index_bytes = index.path.read_bytes()
    external = serialize_note(
        note("ana", "person", "External after read.", name="Ana", aliases=["External"])
    )
    embedder = InterleavingEmbedder(lambda: _outside_process_changes_file(source, external))
    with pytest.raises(ContextIndexError, match="changed before publishing"):
        index.rebuild(repo, schema_fixture, embedder)
    assert index.path.read_bytes() == old_index_bytes
    assert source.read_text() == external
    with pytest.raises(Exception, match="stale|incomplete"):
        queries.exact_names("External")
    index.rebuild(repo, schema_fixture, KeywordEmbedder())
    assert [x.note.metadata["id"] for x in queries.exact_names("External")] == ["ana"]


def test_metadata_only_refresh_rejects_external_change_during_embedding(tmp_path, schema_fixture):
    repo, index, queries = setup(tmp_path, schema_fixture)
    source = repo.root / "people/ana.md"
    previous = index.path.read_bytes()
    replacement = serialize_note(
        note("ana", "person", "Changed outside.", name="Ana", aliases=["Later"])
    )
    old_hash = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    embedder = InterleavingEmbedder(lambda: _outside_process_changes_file(source, replacement))
    with pytest.raises(ContextIndexError, match="changed during metadata refresh"):
        index.refresh_existing_note(
            repo,
            schema_fixture,
            embedder,
            path="people/ana.md",
            expected_source_hash=old_hash,
        )
    assert index.path.read_bytes() == previous
    assert source.read_text() == replacement
    with pytest.raises(Exception, match="stale|incomplete"):
        queries.exact_names("Later")


def test_refresh_external_process_edit_after_sql_rows_but_before_commit(
    tmp_path, schema_fixture, monkeypatch
):
    from odyssey_core import context as context_module

    repo, index, queries = setup(tmp_path, schema_fixture)
    source = repo.root / "people/ana.md"
    source.write_text(
        serialize_note(note("ana", "person", "New desired.", name="Ana")),
        encoding="utf-8",
    )
    outside = serialize_note(note("ana", "person", "Last second.", name="Ana"))
    previous_index = index.path.read_bytes()
    real = context_module._refresh_derived_links

    def interleave(connection):
        result = real(connection)
        _outside_process_changes_file(source, outside)
        return result

    monkeypatch.setattr(context_module, "_refresh_derived_links", interleave)
    with pytest.raises(ContextIndexError, match="changed before committing"):
        index.refresh_notes(repo, schema_fixture, KeywordEmbedder(), note_ids=("ana",))
    assert source.read_text() == outside
    assert index.path.read_bytes() == previous_index
    with pytest.raises(Exception, match="stale|incomplete"):
        queries.by_id("ana")


def test_rebuild_external_process_edit_after_sql_rows_but_before_replace(
    tmp_path, schema_fixture, monkeypatch
):
    from odyssey_core import context as context_module

    repo, index, queries = setup(tmp_path, schema_fixture)
    source = repo.root / "people/ana.md"
    outside = serialize_note(note("ana", "person", "Last second.", name="Ana"))
    previous_index = index.path.read_bytes()
    real = context_module._refresh_derived_links

    def interleave(connection):
        result = real(connection)
        _outside_process_changes_file(source, outside)
        return result

    monkeypatch.setattr(context_module, "_refresh_derived_links", interleave)
    with pytest.raises(ContextIndexError, match="changed before publishing"):
        index.rebuild(repo, schema_fixture, KeywordEmbedder())
    assert source.read_text() == outside
    assert index.path.read_bytes() == previous_index
    with pytest.raises(Exception, match="stale|incomplete"):
        queries.by_id("ana")


def test_metadata_only_external_change_in_final_sql_alias_step_rolls_back(
    tmp_path, schema_fixture, monkeypatch
):
    import hashlib

    from odyssey_core import context as context_module

    repo, index, queries = setup(tmp_path, schema_fixture)
    source = repo.root / "people/ana.md"
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_text(
        serialize_note(note("ana", "person", "Ana.", name="Ana", aliases=["Anita"])),
        encoding="utf-8",
    )
    outside = serialize_note(note("ana", "person", "External last moment.", name="Ana"))
    previous_index = index.path.read_bytes()
    real = context_module.note_alias_rows

    def interleave(note_id, parsed_note):
        result = real(note_id, parsed_note)
        _outside_process_changes_file(source, outside)
        return result

    monkeypatch.setattr(context_module, "note_alias_rows", interleave)
    with pytest.raises(ContextIndexError, match="changed before committing metadata"):
        index.refresh_existing_note(
            repo,
            schema_fixture,
            KeywordEmbedder(),
            path="people/ana.md",
            expected_source_hash=old_hash,
        )
    assert index.path.read_bytes() == previous_index
    assert source.read_text() == outside
    with pytest.raises(Exception, match="stale|incomplete"):
        queries.by_id("ana")
