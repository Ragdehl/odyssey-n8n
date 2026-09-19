"""Deterministic UI-2 Core Notes query contract coverage."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from odyssey_core.context import ContextFilter, ContextIndex
from odyssey_core.note_queries import NotesQueryError, NotesQueryService, StaleCursorError
from odyssey_core.notes import Note, serialize_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]


class Embedder:
    """Provide a no-network deterministic embedding seam for Notes fixtures."""

    model_name = "tests/notes"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return fixed normalized-compatible fixture vectors."""
        return [[float("airbus" in text.casefold()), 1.0] for text in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return fixed query vectors without any provider call."""
        return self.embed_documents(texts)


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema used by the real Core validators."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def write(
    vault: Path,
    path: str,
    note_id: str,
    name: str,
    body: str,
    *,
    updated: str,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
) -> None:
    """Write a schema-valid disposable canonical note fixture."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        serialize_note(
            Note(
                {
                    "id": note_id,
                    "name": name,
                    "type": "concept",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": updated,
                    "created_by": {"human": None, "app": "test"},
                    "updated_by": {"human": None, "app": "test"},
                    "revision": 1,
                    "schema_version": 3,
                    "aliases": aliases or [],
                    "tags": tags or [],
                },
                body,
            )
        ),
        encoding="utf-8",
    )


def service(tmp_path: Path, schema: dict) -> NotesQueryService:
    """Build one fully disposable authoritative vault and rebuilt Notes index."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(
        vault,
        "people/ada.md",
        "ada",
        "Ada",
        "Works with [[projects/odyssey|Odyssey]].",
        updated="2026-09-18T00:00:00Z",
        aliases=["Ada Lovelace"],
        tags=["people"],
    )
    write(
        vault,
        "projects/odyssey.md",
        "odyssey",
        "Odyssey",
        "Built for [[Ada]].",
        updated="2026-09-10T00:00:00Z",
        tags=["project"],
    )
    index = ContextIndex(tmp_path / "runtime" / "context.sqlite3")
    index.rebuild(VaultRepository(vault), schema, Embedder())
    return NotesQueryService(VaultRepository(vault), schema, index)


def test_capabilities_and_local_search_are_schema_grounded_and_zero_provider(
    tmp_path: Path, schema: dict
) -> None:
    """Expose shared capability operators and lexical title/alias ranking without providers."""
    notes = service(tmp_path, schema)
    capabilities = notes.capabilities()
    assert {item["id"] for item in capabilities.types} >= {"concept", "person"}
    assert next(item for item in capabilities.fields if item["id"] == "tags")["operators"] == (
        "contains",
    )
    page = notes.query(mode="local", query="Ada Lovelace")
    assert [item.id for item in page.items] == ["ada"]


def test_feed_ties_links_and_chronological_sorts_are_deterministic(
    tmp_path: Path, schema: dict
) -> None:
    """Use the fixed activity/link formula and stable canonical identity tie breaks."""
    notes = service(tmp_path, schema)
    feed = notes.query(mode="feed", as_of="2026-09-19T00:00:00Z")
    assert [item.id for item in feed.items] == ["ada", "odyssey"]
    assert [item.id for item in notes.query(mode="feed", sort="created_asc").items] == [
        "ada",
        "odyssey",
    ]
    assert [item.id for item in notes.query(mode="feed", sort="updated_desc").items] == [
        "ada",
        "odyssey",
    ]


def test_cursor_generation_and_fingerprint_fail_closed(tmp_path: Path, schema: dict) -> None:
    """Reject cursors reused for another query or after the derived generation changes."""
    notes = service(tmp_path, schema)
    first = notes.query(mode="feed", page_size=1, as_of="2026-09-19T00:00:00Z")
    assert first.next_cursor
    assert notes.query(mode="feed", page_size=1, cursor=first.next_cursor).items[0].id == "odyssey"
    with pytest.raises(StaleCursorError):
        notes.query(mode="local", query="Ada", cursor=first.next_cursor)


def test_detail_links_backlinks_and_stale_projection_fail_closed(
    tmp_path: Path, schema: dict
) -> None:
    """Resolve only literal safe links and never read stale index rows as knowledge."""
    notes = service(tmp_path, schema)
    detail = notes.detail("ada")
    assert [(item.target_id, item.label) for item in detail.links] == [("odyssey", "Odyssey")]
    backlinks = notes.backlinks("ada")
    assert [item.source.id for item in backlinks.items] == ["odyssey"]
    vault_note = tmp_path / "vault" / "people" / "ada.md"
    vault_note.write_text(vault_note.read_text(encoding="utf-8") + "\nChanged", encoding="utf-8")
    with pytest.raises(NotesQueryError, match="stale"):
        notes.query()


def test_shared_filters_apply_to_current_markdown(tmp_path: Path, schema: dict) -> None:
    """Reuse ContextFilter validation and current canonical tags rather than UI fields."""
    notes = service(tmp_path, schema)
    page = notes.query(filters=[ContextFilter("tags", "contains", "project")])
    assert [item.id for item in page.items] == ["odyssey"]


def test_historical_snapshot_keeps_deleted_member_position_without_recomputing(
    tmp_path: Path, schema: dict
) -> None:
    """Replay saved IDs from Markdown and expose a missing member instead of dropping it."""
    notes = service(tmp_path, schema)
    (tmp_path / "vault" / "people" / "ada.md").unlink()

    page = notes.query(
        mode="snapshot",
        query="Ada",
        snapshot_ids=["ada", "odyssey"],
        page_size=2,
    )

    assert [item.id for item in page.items] == ["odyssey"]
    assert page.unavailable_ids == ("ada",)
    assert page.total == 2
    assert page.snapshot_offset == 0
