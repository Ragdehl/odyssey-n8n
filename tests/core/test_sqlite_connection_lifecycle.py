"""Real disposable Core indexes must release SQLite descriptors immediately.

Python's `with sqlite3.connect(...)` commits or rolls back, but DOES NOT close.
Without explicit close, a large pytest session leaked >950 descriptors and
subsequent subprocess/agent and embedding tests failed on select() limits.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from odyssey_core.context import ContextIndex, ContextIndexError
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from tests.core.test_context import KeywordEmbedder as ContextEmbedder
from tests.core.test_context import note, write_note
from tests.core.test_semantic import KeywordEmbedder as SemanticEmbedder


class TrackedConnection(sqlite3.Connection):
    closed = False

    def close(self) -> None:
        super().close()
        self.closed = True


@pytest.fixture
def tracked_connections(monkeypatch):
    """Hold every SQLite handle alive so GC cannot conceal an unclosed handle."""
    original = sqlite3.connect
    opened = []

    def track(*args, **kwargs):
        assert "factory" not in kwargs
        connection = original(*args, factory=TrackedConnection, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", track)
    return opened


def test_indexes_and_queries_release_all_sqlite_handles_without_gc(
    tmp_path: Path, tracked_connections
) -> None:
    schema = json.loads((Path(__file__).parents[2] / "config/note-schema.json").read_text())
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "concept.md", note("item1", "concept", "Sample generic knowledge."))
    repo = VaultRepository(vault)
    context = ContextIndex(tmp_path / "derived" / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "derived" / "semantic.sqlite3")
    assert context.rebuild(repo, schema, ContextEmbedder()) == 1
    assert semantic.rebuild(repo, schema, SemanticEmbedder()) == 1
    assert len(context.find_candidates(schema, ContextEmbedder(), "sample", limit=2)) == 1
    assert len(semantic.find_candidates(SemanticEmbedder(), "sample", limit=2)) == 1
    assert len(tracked_connections) >= 4
    leaked = [connection for connection in tracked_connections if not connection.closed]
    assert not leaked, f"Core returned with {len(leaked)} SQLite connections still open"


def test_failed_index_lookup_also_closes_its_database(tmp_path: Path, tracked_connections) -> None:
    """A rejected stale index cannot retain a reader or conceal a lock."""
    schema = json.loads((Path(__file__).parents[2] / "config/note-schema.json").read_text())
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "concept.md", note("item1", "concept", "Sample knowledge."))
    index = ContextIndex(tmp_path / "derived" / "context.sqlite3")
    assert index.rebuild(VaultRepository(vault), schema, ContextEmbedder()) == 1
    with closing(sqlite3.connect(index.path)) as connection, connection:
        connection.execute("UPDATE metadata SET value = 'corrupt' WHERE key = 'format_version'")
    with pytest.raises(ContextIndexError, match="incompatible"):
        index.find_candidates(schema, ContextEmbedder(), "sample", limit=1)
    assert all(connection.closed for connection in tracked_connections)
