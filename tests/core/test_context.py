"""Focused deterministic tests for Phase 13 general knowledge retrieval."""

from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path

import pytest

from odyssey_core.context import (
    ContextFilter,
    ContextIndex,
    ContextIndexError,
    ContextRetrievalError,
    build_context_retrieval_text,
    get_context,
)
from odyssey_core.notes import Note, serialize_note
from odyssey_core.semantic import build_semantic_retrieval_text
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]


class KeywordEmbedder:
    """Provide a deterministic small vector space without model downloads."""

    model_name = "tests/context-embedder"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed note projections in input order."""
        return [self._embed(text) for text in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed query projections in input order."""
        return [self._embed(text) for text in texts]

    @staticmethod
    def _embed(text: str) -> list[float]:
        """Map fixture text to stable keyword dimensions."""
        lowered = text.casefold()
        return [
            float("odyssey" in lowered),
            float("interface" in lowered or "gui" in lowered),
            float("mobile" in lowered),
            float("idea" in lowered),
            0.25,
        ]


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def note(note_id: str, note_type: str, content: str, **metadata: object) -> Note:
    """Build a schema-valid test note."""
    return Note(
        metadata={
            "id": note_id,
            "type": note_type,
            "created_at": "2026-08-16T12:00:00Z",
            "updated_at": "2026-08-16T12:00:00Z",
            "created_by": "pytest",
            "updated_by": "pytest",
            "revision": 1,
            "schema_version": 1,
            **metadata,
        },
        content=content,
    )  # type: ignore[arg-type]


def write_note(vault: Path, path: str, value: Note) -> None:
    """Write one fixture note."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialize_note(value), encoding="utf-8")


def copy_schema(schema: dict) -> dict:
    """Return an isolated in-memory schema variant for compatibility tests."""
    return deepcopy(schema)


def test_context_projection_includes_tags_and_excludes_lifecycle() -> None:
    """Project general knowledge fields and readable wikilinks, not lifecycle clutter."""
    value = note(
        "gui",
        "concept",
        "Build [[Odyssey|the project]] interface.",
        tags=["idea", "explore"],
        aliases=["GUI"],
        subtype="system",
    )
    projection = build_context_retrieval_text(value, "ideas/Odyssey GUI.md")
    assert "Name: Odyssey GUI" in projection
    assert "Aliases: GUI" in projection
    assert "Tags: idea, explore" in projection
    assert "Subtype: system" in projection
    assert "Build the project interface." in projection
    assert "created_at" not in projection
    assert "schema_version" not in projection
    assert "[[" not in projection
    assert "Tags:" not in build_semantic_retrieval_text(value, "ideas/Odyssey GUI.md")


def test_context_filters_tags_before_limit_and_returns_authoritative_content(
    tmp_path: Path, schema: dict
) -> None:
    """Apply all-tag filtering before top-N and return current Markdown content."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "ideas/Odyssey GUI.md",
        note("gui", "concept", "Original GUI idea.", tags=["idea", "explore"]),
    )
    write_note(
        vault, "ideas/Mobile.md", note("mobile", "concept", "Mobile capture.", tags=["idea"])
    )
    write_note(
        vault,
        "reference/Odyssey.md",
        note("reference", "document", "Reference only.", tags=["idea", "explore"]),
    )
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "derived" / "context.sqlite3")
    embedder = KeywordEmbedder()
    assert index.rebuild(repository, schema, embedder) == 3
    package = get_context(
        repository,
        schema,
        index,
        embedder,
        query="Odyssey interface idea",
        limit=1,
        required_tags=("idea", "explore"),
    )
    assert package.query == "Odyssey interface idea"
    assert [item.id for item in package.items] == ["gui"]
    assert package.items[0].content == "Original GUI idea."
    assert package.items[0].tags == ("idea", "explore")


def test_context_contract_rejects_invalid_query_limit_and_filters(
    tmp_path: Path, schema: dict
) -> None:
    """Reject invalid explicit query, limit, type, tag, and duplicate-tag contracts."""
    vault = tmp_path / "vault"
    vault.mkdir()
    index = ContextIndex(tmp_path / "context.sqlite3")
    index.rebuild(VaultRepository(vault), schema, KeywordEmbedder())
    repository = VaultRepository(vault)
    cases = [
        {"query": "", "limit": 1},
        {"query": "x", "limit": 0},
        {"query": "x", "limit": 1, "type": "unknown"},
        {"query": "x", "limit": 1, "required_tags": ("unknown",)},
        {"query": "x", "limit": 1, "required_tags": ("idea", "idea")},
    ]
    for kwargs in cases:
        with pytest.raises(ValueError):
            get_context(repository, schema, index, KeywordEmbedder(), **kwargs)


def test_context_type_filter_excludes_other_canonical_types(tmp_path: Path, schema: dict) -> None:
    """Apply the exact type filter before ranking and return only that type."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "ideas/GUI.md", note("gui", "concept", "Odyssey interface idea."))
    write_note(vault, "reference/GUI.md", note("doc", "document", "Odyssey interface idea."))
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    package = get_context(
        repository,
        schema,
        index,
        embedder,
        query="Odyssey interface idea",
        limit=2,
        type="concept",
    )
    assert [item.id for item in package.items] == ["gui"]


def test_structured_property_equality_and_in_filters(tmp_path: Path, schema: dict) -> None:
    """Filter schema-declared domain properties through one structured API."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "people/Ada.md",
        note("ada", "person", "Engineer.", relationship_to_user="colleague", aliases=["Ada"]),
    )
    write_note(
        vault,
        "people/Bea.md",
        note("bea", "person", "Friend.", relationship_to_user="friend", aliases=["Bea"]),
    )
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    package = get_context(
        repository,
        schema,
        index,
        embedder,
        query="person",
        limit=2,
        filters=(ContextFilter("relationship_to_user", "eq", "colleague"),),
    )
    assert [item.id for item in package.items] == ["ada"]
    package = get_context(
        repository,
        schema,
        index,
        embedder,
        query="person",
        limit=2,
        filters=({"field": "aliases", "op": "contains", "value": "Bea"},),
    )
    assert [item.id for item in package.items] == ["bea"]
    package = get_context(
        repository,
        schema,
        index,
        embedder,
        query="person",
        limit=2,
        filters=({"field": "relationship_to_user", "op": "in", "value": ["friend", "colleague"]},),
    )
    assert [item.id for item in package.items] == ["ada", "bea"]


def test_structured_created_at_range_is_half_open(tmp_path: Path, schema: dict) -> None:
    """Use normalized bounds with inclusive lower and exclusive upper semantics."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "february.md",
        note("february", "concept", "Odyssey idea.", created_at="2026-02-01T00:00:00+00:00"),
    )
    write_note(
        vault,
        "march.md",
        note("march", "concept", "Odyssey idea.", created_at="2026-03-01T00:00:00+00:00"),
    )
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    package = get_context(
        repository,
        schema,
        index,
        embedder,
        query="Odyssey idea",
        limit=2,
        filters=(
            {"field": "created_at", "op": "gte", "value": "2026-02-01"},
            {"field": "created_at", "op": "lt", "value": "2026-03-01"},
        ),
    )
    assert [item.id for item in package.items] == ["february"]


def test_structured_filters_reduce_candidates_before_ranking(tmp_path: Path, schema: dict) -> None:
    """Exclude a stronger semantic match outside deterministic date constraints."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "outside.md",
        note(
            "outside", "concept", "Odyssey interface idea.", created_at="2026-01-31T23:59:59+00:00"
        ),
    )
    write_note(
        vault,
        "inside.md",
        note("inside", "concept", "Odyssey idea.", created_at="2026-02-01T00:00:00+00:00"),
    )
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    package = get_context(
        repository,
        schema,
        index,
        embedder,
        query="Odyssey interface idea",
        limit=2,
        filters=({"field": "created_at", "op": "gte", "value": "2026-02-01"},),
    )
    assert [item.id for item in package.items] == ["inside"]


@pytest.mark.parametrize(
    "filters",
    [
        ({"field": "unknown", "op": "eq", "value": "x"},),
        ({"field": "created_by", "op": "eq", "value": "pytest"},),
        ({"field": "created_at", "op": "contains", "value": "2026"},),
        ({"field": "created_at", "op": "gte", "value": 2026},),
    ],
)
def test_invalid_structured_filters_fail_explicitly(
    tmp_path: Path, schema: dict, filters: tuple[dict[str, object], ...]
) -> None:
    """Reject unknown, non-filterable, incompatible, and malformed constraints."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    with pytest.raises(ValueError):
        get_context(repository, schema, index, embedder, query="x", limit=1, filters=filters)


def test_injection_like_filter_value_is_plain_data(tmp_path: Path, schema: dict) -> None:
    """Treat SQL-looking values as bound data and leave the index usable."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "person.md", note("person", "person", "A person."))
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    malicious = "'; DROP TABLE notes; --"
    assert (
        get_context(
            repository,
            schema,
            index,
            embedder,
            query="person",
            limit=1,
            filters=(ContextFilter("relationship_to_user", "eq", malicious),),
        ).items
        == ()
    )
    assert get_context(repository, schema, index, embedder, query="person", limit=1).items


def test_context_index_rejects_changed_tag_registry(tmp_path: Path, schema: dict) -> None:
    """Reject queries using a tag registry newer than the built index."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    changed_schema = copy_schema(schema)
    changed_schema["tags"].append({"id": "urgent", "description": "Urgent context."})
    with pytest.raises(ContextIndexError, match="incompatible or stale"):
        get_context(repository, changed_schema, index, embedder, query="anything", limit=1)


def test_context_index_rejects_changed_type_registry(tmp_path: Path, schema: dict) -> None:
    """Reject queries against a type registry different from the built index."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    changed_schema = copy_schema(schema)
    changed_schema["types"].append(
        {"id": "new_type", "description": "New type.", "subtypes": [], "properties": []}
    )
    with pytest.raises(ContextIndexError, match="incompatible or stale"):
        get_context(repository, changed_schema, index, embedder, query="anything", limit=1)


def test_failed_rebuild_preserves_previous_index_and_index_is_outside_vault(
    tmp_path: Path, schema: dict
) -> None:
    """Preserve a usable derived file when a later source rebuild fails."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    write_note(vault, "ideas/GUI.md", note("gui", "concept", "Interface idea."))
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    before = index.path.read_bytes()
    (vault / "broken.md").write_text("not canonical markdown", encoding="utf-8")
    with pytest.raises(ContextIndexError, match="invalid note"):
        index.rebuild(repository, schema, embedder)
    assert index.path.read_bytes() == before
    with pytest.raises(ContextIndexError, match="outside"):
        ContextIndex(vault / "context.sqlite3").rebuild(repository, schema, embedder)


def test_stale_selected_source_fails_closed(tmp_path: Path, schema: dict) -> None:
    """Reject selected notes whose authoritative raw Markdown changed after indexing."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "ideas/GUI.md", note("gui", "concept", "Interface idea."))
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    (vault / "ideas/GUI.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ContextRetrievalError, match="stale"):
        get_context(repository, schema, index, embedder, query="interface", limit=1)


def test_empty_match_is_valid_and_ties_are_deterministic(tmp_path: Path, schema: dict) -> None:
    """Return an empty package for filters with no matches and stable tie ordering."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "ideas/Zed.md", note("z", "concept", "General."))
    write_note(vault, "ideas/Amy.md", note("a", "concept", "General."))
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "context.sqlite3")
    embedder = KeywordEmbedder()
    index.rebuild(repository, schema, embedder)
    package = get_context(
        repository, schema, index, embedder, query="unknown", limit=2, type="person"
    )
    assert package.items == ()
    ranked = get_context(repository, schema, index, embedder, query="unknown", limit=2)
    assert [item.path for item in ranked.items] == ["ideas/Amy.md", "ideas/Zed.md"]


def test_duplicate_ids_fail_rebuild(tmp_path: Path, schema: dict) -> None:
    """Reject duplicate stable IDs before replacing the derived index."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "one.md", note("same", "concept", "One."))
    write_note(vault, "two.md", note("same", "concept", "Two."))
    with pytest.raises(ContextIndexError, match="duplicate note ID"):
        ContextIndex(tmp_path / "context.sqlite3").rebuild(
            VaultRepository(vault), schema, KeywordEmbedder()
        )
