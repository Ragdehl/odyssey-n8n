"""WAL on disposable context indexes: no read-write stalls, safe full rebuilds."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

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
    write(repo, "people/ana.md", note("ana", "person", "Original.", name="Ana"))
    embedder = KeywordEmbedder()
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(repo, schema, embedder)
    index.enable_concurrent_reads()
    return repo, schema, embedder, index


def test_concurrent_reader_preserves_old_snapshot_and_does_not_stall_writer(fx):
    repo, schema, embedder, index = fx
    write(repo, "people/ana.md", note("ana", "person", "Updated.", name="Ana"))
    with sqlite3.connect(index.path, isolation_level=None) as reader:
        assert reader.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        reader.execute("BEGIN")
        assert reader.execute(
            "SELECT body_text FROM note_projection WHERE note_id='ana'"
        ).fetchone() == ("Original.",)
        with ThreadPoolExecutor(max_workers=1) as pool:
            t0 = perf_counter()
            assert (
                pool.submit(index.refresh_notes, repo, schema, embedder, note_ids=("ana",)).result(
                    timeout=2
                )
                == 1
            )
            assert perf_counter() - t0 < 0.5
        # The in-flight reader is not switched onto a half-updated snapshot.
        assert reader.execute(
            "SELECT body_text FROM note_projection WHERE note_id='ana'"
        ).fetchone() == ("Original.",)
        reader.execute("ROLLBACK")
        assert reader.execute(
            "SELECT body_text FROM note_projection WHERE note_id='ana'"
        ).fetchone() == ("Updated.",)


def test_full_rebuild_publishes_into_existing_wal_without_orphaning_sidecar(fx):
    repo, schema, embedder, index = fx
    write(repo, "people/ana.md", note("ana", "person", "Rebuilt.", name="Ana"))
    with sqlite3.connect(index.path, isolation_level=None) as reader:
        reader.execute("BEGIN")
        assert reader.execute(
            "SELECT body_text FROM note_projection WHERE note_id='ana'"
        ).fetchone() == ("Original.",)
        with ThreadPoolExecutor(max_workers=1) as pool:
            t0 = perf_counter()
            assert pool.submit(index.rebuild, repo, schema, embedder).result(timeout=2) == 1
            assert perf_counter() - t0 < 0.5
        assert reader.execute(
            "SELECT body_text FROM note_projection WHERE note_id='ana'"
        ).fetchone() == ("Original.",)
        reader.execute("ROLLBACK")
        assert reader.execute(
            "SELECT body_text FROM note_projection WHERE note_id='ana'"
        ).fetchone() == ("Rebuilt.",)
        assert reader.execute("PRAGMA journal_mode").fetchone() == ("wal",)


def test_failed_full_rebuild_keeps_prior_wal_index(fx):
    repo, schema, embedder, index = fx
    (repo.root / "people/ana.md").write_text("invalid yaml!", encoding="utf-8")
    with pytest.raises((ContextIndexError, ValueError)):
        index.rebuild(repo, schema, embedder)
    with sqlite3.connect(index.path) as connection:
        assert connection.execute(
            "SELECT body_text FROM note_projection WHERE note_id='ana'"
        ).fetchone() == ("Original.",)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)


def test_wal_cleanup_when_deleting_derived_index(fx):
    _repo, _schema, _embedder, index = fx
    index.delete()
    assert not index.path.exists()
    assert not Path(str(index.path) + "-wal").exists()
    assert not Path(str(index.path) + "-shm").exists()
