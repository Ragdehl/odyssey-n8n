"""Durable on-device, read-only scan progress; no shared online service."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from odyssey_core.notes import Note, serialize_note
from odyssey_core.schema_retrospection_jobs import LocalSchemaScanError, LocalSchemaScanJobs
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]


def _scenario(tmp_path: Path) -> tuple[Path, VaultRepository, dict]:
    state = tmp_path / "device-private-state"
    state.mkdir(mode=0o700)
    vault = tmp_path / "device-private-vault"
    vault.mkdir(mode=0o700)
    base = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    base["types"].append(
        {"id": "book", "name": "Book", "description": "Books", "examples": [], "properties": []}
    )
    for i in range(5):
        data = Note(
            {
                "id": f"note-{i}",
                "name": f"Person {i}",
                "type": "person",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "created_by": {"human": None, "app": "tests"},
                "updated_by": {"human": None, "app": "tests"},
                "revision": 1,
                "schema_version": 3,
                "aliases": [],
                "tags": [],
            },
            f"# Added 01-01-2026\n- Leí un libro único {i}\n"
            f"<!-- odyssey:fact request=source{i} ordinal=0 -->\n",
        )
        (vault / f"{i}.md").write_text(serialize_note(data), encoding="utf-8")
    return state, VaultRepository(vault), base


def _advance(store: LocalSchemaScanJobs, schema: dict, *, limit: int = 2):
    return store.advance(
        job_id="new-books", schema=schema, kind="discover_type", target_type_id="book", limit=limit
    )


def test_local_job_survives_restart_and_writes_no_markdown_or_source_text(tmp_path: Path):
    state, repo, schema = _scenario(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    one = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-profile-a")
    first = _advance(one, schema)
    assert (first.scanned_paths, first.eligible_notes) == (2, 2)
    assert not first.complete
    receipt = next((state / "schema-retrospection-jobs").glob("*.json"))
    raw = receipt.read_text(encoding="utf-8")
    assert "Leí" not in raw and '"facts"' not in raw
    second_session = LocalSchemaScanJobs(
        state_root=state, repository=repo, actor_id="local-profile-a"
    )
    assert second_session.read("new-books") == first
    second = _advance(second_session, schema)
    assert second.scanned_paths == 4
    assert second.next_cursor is not None
    last = _advance(second_session, schema)
    assert last.complete
    assert last.scanned_paths == last.eligible_notes == 5
    assert _advance(second_session, schema) == last  # no duplicate page on completed retry
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_local_profile_separation_and_vault_binding(tmp_path: Path):
    state, repo, schema = _scenario(tmp_path)
    a = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="profile-a")
    _advance(a, schema)
    b = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="profile-b")
    assert b.read("new-books") is None
    assert _advance(b, schema).scanned_paths == 2
    assert len(list((state / "schema-retrospection-jobs").glob("*.json"))) == 2
    # Even with the same local actor alias, another vault is not this job's owner.
    changed_vault = tmp_path / "other-vault"
    changed_vault.mkdir()
    other = LocalSchemaScanJobs(
        state_root=state, repository=VaultRepository(changed_vault), actor_id="profile-a"
    )
    with pytest.raises(LocalSchemaScanError, match="scope"):
        other.read("new-books")


def test_changed_vault_stops_resume_without_discarding_checkpoint(tmp_path: Path):
    state, repo, schema = _scenario(tmp_path)
    store = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-profile")
    first = _advance(store, schema, limit=2)
    (repo.root / "3.md").write_text((repo.root / "3.md").read_text() + "edited\n")
    with pytest.raises(LocalSchemaScanError, match="Stale"):
        _advance(store, schema)
    assert store.read("new-books") == first
    fresh = store.advance(
        job_id="restart-explicit",
        schema=schema,
        kind="discover_type",
        target_type_id="book",
        limit=1,
    )
    assert fresh.scanned_paths == 1


def test_schema_or_target_change_fails_closed(tmp_path: Path):
    state, repo, schema = _scenario(tmp_path)
    store = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-profile")
    before = _advance(store, schema)
    with pytest.raises(LocalSchemaScanError, match="target"):
        store.advance(
            job_id="new-books", schema=schema, kind="discover_type", target_type_id="person"
        )
    changed = json.loads(json.dumps(schema))
    changed["types"][-1]["description"] = "Different meaning"
    with pytest.raises(LocalSchemaScanError, match="Stale"):
        _advance(store, changed)
    assert store.read("new-books") == before


def test_corrupted_or_symlinked_receipt_is_not_repaired_silently(tmp_path: Path):
    state, repo, schema = _scenario(tmp_path)
    store = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-profile")
    _advance(store, schema)
    receipt = next((state / "schema-retrospection-jobs").glob("*.json"))
    receipt.write_text("{broken", encoding="utf-8")
    with pytest.raises(LocalSchemaScanError, match="unreadable"):
        _advance(store, schema)
    receipt.unlink()
    receipt.symlink_to(repo.root / "0.md")
    with pytest.raises(LocalSchemaScanError, match="unsafe"):
        _advance(store, schema)


def test_prevent_state_inside_vault_and_invalid_job_ids(tmp_path: Path):
    state, repo, schema = _scenario(tmp_path)
    with pytest.raises(LocalSchemaScanError, match="separate"):
        LocalSchemaScanJobs(state_root=repo.root, repository=repo, actor_id="profile")
    with pytest.raises(LocalSchemaScanError, match="separate"):
        LocalSchemaScanJobs(state_root=tmp_path, repository=repo, actor_id="profile")
    store = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="profile")
    for bad in ("../other", "", "x/y", "a" * 65):
        with pytest.raises(LocalSchemaScanError, match="job ID"):
            store.read(bad)
    assert not any(repo.root.rglob("*.json"))


def test_two_cooperating_workers_process_each_page_once(tmp_path: Path):
    state, repo, schema = _scenario(tmp_path)
    left = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="profile")
    right = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="profile")
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda store: _advance(store, schema), (left, right)))
    assert sorted(x.scanned_paths for x in results) == [2, 4]
    last = _advance(left, schema)
    assert last.complete and last.scanned_paths == 5


def test_empty_vault_completes_without_network_or_notes(tmp_path: Path):
    state = tmp_path / "state"
    vault = tmp_path / "vault"
    state.mkdir()
    vault.mkdir()
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    store = LocalSchemaScanJobs(
        state_root=state, repository=VaultRepository(vault), actor_id="only-on-device"
    )
    page = store.advance(
        job_id="empty", schema=schema, kind="discover_type", target_type_id="person"
    )
    assert page.complete and page.scanned_paths == 0
    assert store.read("empty") == page


def test_completed_job_refuses_a_stale_canonical_inventory(tmp_path: Path):
    state, repo, schema = _scenario(tmp_path)
    store = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="profile")
    completed = _advance(store, schema, limit=25)
    assert completed.complete
    (repo.root / "0.md").write_text((repo.root / "0.md").read_text() + "changed")
    with pytest.raises(LocalSchemaScanError, match="Stale"):
        _advance(store, schema)
    assert store.read("new-books") == completed


def test_completed_retry_validates_input_limit_and_long_valid_note_id(tmp_path: Path):
    state, repo, schema = _scenario(tmp_path)
    store = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="profile")
    # Canonical Note IDs are strings, not universally limited to 256 chars.
    long_id = "long-" + "A" * 300
    raw = (repo.root / "0.md").read_text()
    (repo.root / "0.md").write_text(raw.replace("note-0", long_id))
    progress = _advance(store, schema, limit=25)
    assert progress.complete and long_id in progress.seen_note_ids
    assert _advance(store, schema, limit=25) == progress
    with pytest.raises(LocalSchemaScanError, match="page limit"):
        _advance(store, schema, limit=26)


def test_large_operational_scan_resumes_without_repeating_whole_inventory(
    tmp_path: Path, monkeypatch
):
    """SQLite stores operational uniqueness, not a second note/source authority."""
    from odyssey_core import schema_large_scan_jobs

    monkeypatch.setattr(schema_large_scan_jobs, "_LARGE_THRESHOLD", 3)
    state, repo, schema = _scenario(tmp_path)
    snapshots = []
    original = repo.note_version_snapshot

    def counted():
        snapshots.append(True)
        return original()

    monkeypatch.setattr(repo, "note_version_snapshot", counted)
    left = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-a")
    first = _advance(left, schema, limit=2)
    assert first.scanned_paths == 2 and first.eligible_notes == 2
    assert not first.complete
    receipt = list((state / "schema-retrospection-jobs").glob("*.sqlite3"))
    assert len(receipt) == 1
    assert not list((state / "schema-retrospection-jobs").glob("*.json"))
    # First advance freezes physical inventory and validates source arguments.
    first_snapshots = len(snapshots)
    second = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-a").advance(
        job_id="new-books",
        schema=schema,
        kind="discover_type",
        target_type_id="book",
        limit=2,
    )
    assert second.scanned_paths == 4
    assert len(snapshots) == first_snapshots, "Intermediate pages must not restat entire vault"
    third = _advance(left, schema)
    assert third.complete and third.scanned_paths == third.eligible_notes == 5
    assert _advance(left, schema) == third
    assert left.read("new-books") == third
    schema_changed = json.loads(json.dumps(schema))
    schema_changed["types"][-1]["description"] = "Changed after completion"
    with pytest.raises(LocalSchemaScanError, match="Large scan"):
        left.advance(
            job_id="new-books",
            schema=schema_changed,
            kind="discover_type",
            target_type_id="book",
            limit=2,
        )
    # The v2 progress receipt never serializes the entire set into one JSON.
    assert third.seen_note_ids == frozenset()
    assert third.identity_proof == "external"
    from odyssey_core.schema_retrospection import (
        SchemaRetrospectionError,
        accumulate_schema_scan,
        scan_schema_sources,
    )

    # Public APIs must never mistake the compact v2 progress for a complete
    # in-memory ID uniqueness witness.
    first_page = scan_schema_sources(
        repository=repo,
        schema=schema,
        kind="discover_type",
        target_type_id="book",
        cursor=None,
        limit=2,
    )
    with pytest.raises(SchemaRetrospectionError, match="Stale or out-of-order"):
        accumulate_schema_scan(first_page, third)


def test_large_scan_detects_duplicates_across_pages_and_refuses_completion(
    tmp_path: Path, monkeypatch
):
    from odyssey_core import schema_large_scan_jobs

    monkeypatch.setattr(schema_large_scan_jobs, "_LARGE_THRESHOLD", 3)
    state, repo, schema = _scenario(tmp_path)
    source = (repo.root / "4.md").read_text(encoding="utf-8")
    (repo.root / "4.md").write_text(source.replace("note-4", "note-0"))
    worker = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-a")
    assert _advance(worker, schema, limit=2).scanned_paths == 2
    assert _advance(worker, schema, limit=2).scanned_paths == 4
    with pytest.raises(LocalSchemaScanError, match="Large scan"):
        _advance(worker, schema, limit=2)
    assert worker.read("new-books").scanned_paths == 4
    assert not worker.read("new-books").complete


def test_large_scan_external_edit_before_last_page_fails_closed(tmp_path: Path, monkeypatch):
    from odyssey_core import schema_large_scan_jobs

    monkeypatch.setattr(schema_large_scan_jobs, "_LARGE_THRESHOLD", 3)
    state, repo, schema = _scenario(tmp_path)
    worker = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-a")
    _advance(worker, schema, limit=2)
    _advance(worker, schema, limit=2)
    (repo.root / "0.md").write_text((repo.root / "0.md").read_text() + "external edit")
    with pytest.raises(LocalSchemaScanError, match="Large scan"):
        _advance(worker, schema, limit=2)
    assert worker.read("new-books").scanned_paths == 4


def test_large_scan_actor_schema_and_database_tamper_are_rejected(tmp_path: Path, monkeypatch):
    import sqlite3

    from odyssey_core import schema_large_scan_jobs

    monkeypatch.setattr(schema_large_scan_jobs, "_LARGE_THRESHOLD", 3)
    state, repo, schema = _scenario(tmp_path)
    worker = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-a")
    _advance(worker, schema, limit=2)
    assert (
        LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-b").read("new-books")
        is None
    )
    changed = json.loads(json.dumps(schema))
    changed["types"][-1]["description"] = "Different schema"
    with pytest.raises(LocalSchemaScanError, match="Large scan"):
        worker.advance(
            job_id="new-books",
            schema=changed,
            kind="discover_type",
            target_type_id="book",
            limit=2,
        )
    receipt = next((state / "schema-retrospection-jobs").glob("*.sqlite3"))
    with sqlite3.connect(receipt) as conn:
        conn.execute("DELETE FROM seen WHERE note_id='note-0'")
    _advance(worker, schema, limit=2)
    with pytest.raises(LocalSchemaScanError, match="Large scan"):
        _advance(worker, schema, limit=2)
    assert worker.read("new-books").scanned_paths == 4
    receipt.unlink()
    receipt.symlink_to(repo.root / "0.md")
    with pytest.raises(LocalSchemaScanError, match="Unsafe"):
        worker.read("new-books")


def test_large_scan_missing_metadata_never_resets_checkpoint(tmp_path, monkeypatch):
    import sqlite3

    from odyssey_core import schema_large_scan_jobs

    monkeypatch.setattr(schema_large_scan_jobs, "_LARGE_THRESHOLD", 3)
    state, repo, schema = _scenario(tmp_path)
    worker = LocalSchemaScanJobs(state_root=state, repository=repo, actor_id="local-a")
    assert _advance(worker, schema, limit=2).scanned_paths == 2
    receipt = next((state / "schema-retrospection-jobs").glob("*.sqlite3"))
    with sqlite3.connect(receipt) as conn:
        conn.execute("DELETE FROM scan_meta")
    with pytest.raises(LocalSchemaScanError, match="Large scan"):
        _advance(worker, schema, limit=2)
    with pytest.raises(LocalSchemaScanError, match="unreadable"):
        worker.read("new-books")
