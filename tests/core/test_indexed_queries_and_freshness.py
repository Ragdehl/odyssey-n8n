"""SQLite candidate selection never outranks live Markdown and source integrity."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from odyssey_core.context import ContextIndex
from odyssey_core.indexed_queries import CoreIndexedQueries, IndexedQueryUnavailable
from odyssey_core.storage import VaultRepository
from odyssey_core.verified_metadata_catalog import (
    scoped_verified_metadata_catalog,
    verified_catalog_if_active,
)
from tests.core.test_context import KeywordEmbedder, note
from tests.core.test_context_deterministic_projection import write


@pytest.fixture
def schema_fixture():
    import json

    return json.loads((Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text())


def setup(tmp_path, schema):
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    write(repo, "people/ana.md", note("ana", "person", "Ana.", name="Ana", aliases=["Anita"]))
    write(repo, "people/old.md", note("old", "person", "Retired.", name="Old", deleted=True))
    write(
        repo, "project.md", note("project", "project", "Vi a [[people/ana|Ana]].", name="Proyecto")
    )
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, schema, KeywordEmbedder())
    return repo, index, CoreIndexedQueries(repo, schema, index.path)


def test_scoped_index_avoids_markdown_reads_for_complete_inventory(tmp_path, schema_fixture):
    repo, index, _queries = setup(tmp_path, schema_fixture)
    reads = [0]
    actual = repo.read_text

    def read(path):
        reads[0] += 1
        return actual(path)

    repo.read_text = read
    with (
        repo.scoped_unchanged_reads(),
        scoped_verified_metadata_catalog(index_path=str(index.path)),
    ):
        snapshot = verified_catalog_if_active(repo, schema_fixture)
        assert len(snapshot.rows) == 3
        assert reads[0] == 0, "SQLite + physical versions must avoid parsing all Notes"
        assert len([row for row in snapshot.rows if row.type == "person"]) == 2
        assert any(row.deleted for row in snapshot.rows)
        assert verified_catalog_if_active(repo, schema_fixture) == snapshot
        assert reads[0] == 0


def test_typed_indexed_queries_for_name_alias_id_attributes_and_edges(tmp_path, schema_fixture):
    _repo, _index, q = setup(tmp_path, schema_fixture)
    assert [x.note.metadata["id"] for x in q.exact_names("ANITA", type="person")] == ["ana"]
    assert [x.note.metadata["id"] for x in q.exact_names("Ana")] == ["ana"]
    assert q.exact_names("Old") == ()
    assert [x.note.metadata["id"] for x in q.exact_names("Old", include_deleted=True)] == ["old"]
    assert q.by_id("missing") is None
    assert q.by_id("ana").note.metadata["name"] == "Ana"
    assert [x.note.metadata["id"] for x in q.by_attribute("name", "Ana")] == ["ana"]
    assert q.links("ana", incoming=True) == (("project", "ana", "people/ana"),)
    assert q.links("project") == (("project", "ana", "people/ana"),)
    assert q.facts("project") == ()


def test_external_new_note_blocks_sql_negative_until_index_refresh(tmp_path, schema_fixture):
    repo, index, q = setup(tmp_path, schema_fixture)
    assert q.exact_names("Eva") == ()
    write(repo, "people/eva.md", note("eva", "person", "Eva.", name="Eva"))
    with pytest.raises(IndexedQueryUnavailable, match="stale|incomplete"):
        q.exact_names("Eva")
    with (
        repo.scoped_unchanged_reads(),
        scoped_verified_metadata_catalog(index_path=str(index.path)),
    ):
        # A stale index cannot prove any negative; old physical fallback sees Eva.
        snapshot = verified_catalog_if_active(repo, schema_fixture)
        assert any(row.id == "eva" for row in snapshot.rows)
    index.refresh_notes(repo, schema_fixture, KeywordEmbedder(), note_ids=("eva",))
    assert [x.note.metadata["id"] for x in q.exact_names("Eva")] == ["eva"]


def test_modified_deleted_and_symlink_notes_block_stale_index(tmp_path, schema_fixture):
    repo, index, q = setup(tmp_path, schema_fixture)
    assert q.exact_names("Anita")
    write(repo, "people/ana.md", note("ana", "person", "Ana.", name="Ana", aliases=["Annie"]))
    with pytest.raises(IndexedQueryUnavailable):
        q.exact_names("Anita")
    index.refresh_notes(repo, schema_fixture, KeywordEmbedder(), note_ids=("ana",))
    assert q.exact_names("Anita") == ()
    assert len(q.exact_names("Annie")) == 1
    note_path = repo.root / "people/ana.md"
    note_path.unlink()
    with pytest.raises(IndexedQueryUnavailable):
        q.by_id("ana")
    outside = tmp_path / "not-mine.md"
    outside.write_text("untrusted", encoding="utf-8")
    note_path.symlink_to(outside)
    with pytest.raises(IndexedQueryUnavailable):
        q.exact_names("Annie")


def test_restored_mtime_does_not_hide_changed_source(tmp_path, schema_fixture):
    repo, index, q = setup(tmp_path, schema_fixture)
    path = repo.root / "people/ana.md"
    before = path.stat().st_mtime_ns
    old = path.read_text()
    path.write_text(old.replace("Anita", "Annie"), encoding="utf-8")
    os.utime(path, ns=(before, before))
    with pytest.raises(IndexedQueryUnavailable):
        q.exact_names("Anita")


def test_tampered_index_hash_can_never_serve_positive(tmp_path, schema_fixture):
    _repo, index, q = setup(tmp_path, schema_fixture)
    with sqlite3.connect(index.path) as db:
        db.execute("UPDATE vault_inventory SET source_hash=? WHERE note_id='ana'", ("0" * 64,))
    with pytest.raises(IndexedQueryUnavailable, match="hash"):
        q.exact_names("Anita")


def test_old_index_and_schema_change_fail_closed(tmp_path, schema_fixture):
    _repo, index, q = setup(tmp_path, schema_fixture)
    with sqlite3.connect(index.path) as db:
        db.execute("UPDATE metadata SET value='5' WHERE key='format_version'")
    with pytest.raises(IndexedQueryUnavailable):
        q.by_id("ana")
    with sqlite3.connect(index.path) as db:
        db.execute("UPDATE metadata SET value='6' WHERE key='format_version'")
    changed = {**schema_fixture, "schema_version": 55}
    other = CoreIndexedQueries(q.repository, changed, index.path)
    with pytest.raises(IndexedQueryUnavailable):
        other.by_id("ana")


def test_deleted_notes_are_in_inventory_even_if_not_in_search_projection(tmp_path, schema_fixture):
    _repo, index, q = setup(tmp_path, schema_fixture)
    assert q.by_id("old").note.metadata.get("deleted") is True
    with sqlite3.connect(index.path) as db:
        assert db.execute("SELECT note_id FROM vault_inventory ORDER BY note_id").fetchall() == [
            ("ana",),
            ("old",),
            ("project",),
        ]
        assert db.execute("SELECT id FROM notes WHERE id='old'").fetchall() == []


def test_external_reconciliation_updates_alias_without_full_rebuild(tmp_path, schema_fixture):
    repo, index, query = setup(tmp_path, schema_fixture)
    assert index.reconcile_external_changes(repo, schema_fixture, KeywordEmbedder()) == 0
    write(repo, "people/ana.md", note("ana", "person", "Ana.", name="Ana", aliases=["Annie"]))
    with pytest.raises(IndexedQueryUnavailable):
        query.exact_names("Annie")
    assert index.reconcile_external_changes(repo, schema_fixture, KeywordEmbedder()) == 1
    assert query.exact_names("Anita") == ()
    assert len(query.exact_names("Annie")) == 1


def test_external_create_delete_and_move_reconcile_every_target(tmp_path, schema_fixture):
    repo, index, query = setup(tmp_path, schema_fixture)
    original = repo.root / "people/ana.md"
    moved = repo.root / "people/renamed.md"
    original.rename(moved)
    write(repo, "people/nora.md", note("nora", "person", "Nora.", name="Nora"))
    (repo.root / "people/old.md").unlink()
    count = index.reconcile_external_changes(repo, schema_fixture, KeywordEmbedder())
    assert count == 3
    assert query.by_id("ana").path == "people/renamed.md"
    assert query.by_id("nora").note.metadata["name"] == "Nora"
    assert query.by_id("old") is None
    assert query.links("ana", incoming=True) == ()
    assert query.exact_names("Nora")


def test_external_reconciliation_resolves_old_unlinked_target(tmp_path, schema_fixture):
    repo, index, query = setup(tmp_path, schema_fixture)
    write(
        repo,
        "project.md",
        note("project", "project", "Vi a [[people/nora|Nora]].", name="Proyecto"),
    )
    assert index.reconcile_external_changes(repo, schema_fixture, KeywordEmbedder()) == 1
    assert query.links("project") == ()
    write(repo, "people/nora.md", note("nora", "person", "Nora.", name="Nora"))
    assert index.reconcile_external_changes(repo, schema_fixture, KeywordEmbedder()) == 1
    assert query.links("project") == (("project", "nora", "people/nora"),)


def test_external_unsafe_source_never_mutates_previous_index(tmp_path, schema_fixture):
    repo, index, query = setup(tmp_path, schema_fixture)
    old = index.path.read_bytes()
    (repo.root / "bad.md").write_text("---\nid: unclosed", encoding="utf-8")
    with pytest.raises(Exception, match="invalid|unsafe|canonical"):
        index.reconcile_external_changes(repo, schema_fixture, KeywordEmbedder())
    assert index.path.read_bytes() == old
    with pytest.raises(IndexedQueryUnavailable):
        query.exact_names("Ana")


def test_external_duplicate_stable_id_fails_atomic_reconciliation(tmp_path, schema_fixture):
    repo, index, _query = setup(tmp_path, schema_fixture)
    old = index.path.read_bytes()
    write(repo, "people/duplicate.md", note("ana", "person", "Duplicate.", name="Other Ana"))
    with pytest.raises(Exception, match="duplicate"):
        index.reconcile_external_changes(repo, schema_fixture, KeywordEmbedder())
    assert index.path.read_bytes() == old


def test_refresh_only_reads_modified_markdown_in_large_unchanged_inventory(
    tmp_path, schema_fixture
):
    repo, index, _query = setup(tmp_path, schema_fixture)
    for n in range(140):
        write(
            repo,
            f"people/filler-{n:03}.md",
            note(f"filler-{n}", "person", "Filler.", name=f"Filler {n}"),
        )
    index.rebuild(repo, schema_fixture, KeywordEmbedder())
    write(repo, "people/ana.md", note("ana", "person", "Changed.", name="Ana", aliases=["Anita"]))
    actual = repo.read_text
    accessed = []

    def trace(path):
        accessed.append(path)
        return actual(path)

    repo.read_text = trace
    try:
        assert index.refresh_notes(repo, schema_fixture, KeywordEmbedder(), note_ids=("ana",)) == 1
    finally:
        repo.read_text = actual
    assert accessed == ["people/ana.md"]
    assert _query.exact_names("Anita")


def test_reconcile_external_changed_batch_is_bounded(tmp_path, schema_fixture):
    repo, index, _query = setup(tmp_path, schema_fixture)
    old = index.path.read_bytes()
    for n in range(3):
        write(repo, f"new{n}.md", note(f"new{n}", "concept", "text.", name=f"New {n}"))
    with pytest.raises(Exception, match="budget"):
        index.reconcile_external_changes(repo, schema_fixture, KeywordEmbedder(), max_changed=2)
    assert index.path.read_bytes() == old


def test_tampered_alias_or_incorrect_link_target_is_never_grounded(tmp_path, schema_fixture):
    repo, index, q = setup(tmp_path, schema_fixture)
    with sqlite3.connect(index.path) as db:
        db.execute("INSERT INTO vault_aliases VALUES ('ana','Fake','fake')")
    with pytest.raises(IndexedQueryUnavailable, match="name/alias"):
        q.exact_names("Fake")
    with sqlite3.connect(index.path) as db:
        db.execute("DELETE FROM vault_aliases WHERE alias='Fake'")
        db.execute("UPDATE note_links SET target_id='project' WHERE source_id='project'")
    with pytest.raises(IndexedQueryUnavailable, match="Graph link"):
        q.links("project")
