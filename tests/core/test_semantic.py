"""Focused deterministic tests for Phase 10 semantic candidate retrieval."""

from __future__ import annotations

import json
import sqlite3
import sys
import types
from collections.abc import Sequence
from pathlib import Path

import pytest

from odyssey_core.notes import Note, serialize_note
from odyssey_core.semantic import (
    FastEmbedTextEmbedder,
    SemanticEntityIndex,
    SemanticIndexError,
    build_semantic_retrieval_text,
    find_semantic_entity_candidates,
)
from odyssey_core.storage import VaultRepository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class KeywordEmbedder:
    """Provide stable semantic-like vectors without a downloaded model in CI."""

    model_name = "tests/keyword-embedder"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed fixture notes using deterministic domain keywords."""
        return [self._embed(text) for text in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed fixture queries using the same deterministic keyword space."""
        return [self._embed(text) for text in texts]

    @staticmethod
    def _embed(text: str) -> list[float]:
        lowered = text.casefold()
        return [
            float(any(word in lowered for word in ("wife", "spouse", "femme", "mujer"))),
            float(any(word in lowered for word in ("xavi", "partner"))),
            float(any(word in lowered for word in ("carrefour", "store", "balma"))),
            float(any(word in lowered for word in ("project", "odyssey"))),
            0.25,
        ]


def test_fastembed_defaults_to_local_files_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pass the offline-only default through to FastEmbed without loading a real model."""
    captured: dict[str, object] = {}

    class FakeTextEmbedding:
        """Capture constructor arguments for the optional FastEmbed boundary test."""

        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    fake_fastembed = types.ModuleType("fastembed")
    fake_fastembed.TextEmbedding = FakeTextEmbedding  # type: ignore[attr-defined]
    fake_fastembed.__version__ = "test"
    monkeypatch.setitem(sys.modules, "fastembed", fake_fastembed)

    embedder = FastEmbedTextEmbedder(cache_dir=Path("/tmp/phase16-test-cache"))

    assert captured["local_files_only"] is True
    assert captured["cache_dir"] == "/tmp/phase16-test-cache"
    assert embedder.model_version == "fastembed-test"


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema used by production validation."""
    return json.loads((REPOSITORY_ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def valid_note(note_id: str, note_type: str, content: str, **metadata: object) -> Note:
    """Create one schema-valid note fixture with optional domain metadata."""
    values = {
        "id": note_id,
        "type": note_type,
        "created_at": "2026-08-16T12:00:00Z",
        "updated_at": "2026-08-16T12:00:00Z",
        "created_by": "pytest",
        "updated_by": "pytest",
        "revision": 1,
        "schema_version": 1,
        **metadata,
    }
    return Note(metadata=values, content=content)  # type: ignore[arg-type]


def write_note(vault: Path, path: str, note: Note) -> None:
    """Write a controlled canonical Markdown fixture beneath a temporary vault."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialize_note(note), encoding="utf-8")


def test_projection_includes_useful_fields_and_human_wikilink_text() -> None:
    """Project names, aliases, type, domain metadata, and readable link labels."""
    note = valid_note(
        "person-beatriz",
        "person",
        "Partner of [[people/Xavi|Xavi]]. Related to [[Atomic notes]].",
        aliases=["Bea"],
        relationship_to_user="spouse",
    )

    projection = build_semantic_retrieval_text(note, "people/Beatriz Alonso.md")

    assert "Name: Beatriz Alonso" in projection
    assert "Aliases: Bea" in projection
    assert "Type: person" in projection
    assert "Relationship To User: spouse" in projection
    assert "Partner of Xavi. Related to Atomic notes." in projection
    assert "created_at" not in projection
    assert "[[" not in projection


def test_projection_excludes_controlled_tags_from_identity_text() -> None:
    """Changing classification facets must not change semantic identity input."""
    base = valid_note("person-beatriz", "person", "Partner of [[Xavi]].")
    tagged = valid_note("person-beatriz", "person", "Partner of [[Xavi]].", tags=["idea"])
    assert build_semantic_retrieval_text(
        tagged, "people/Beatriz.md"
    ) == build_semantic_retrieval_text(base, "people/Beatriz.md")


def test_rebuild_replaces_and_delete_removes_only_derived_index(
    tmp_path: Path, schema: dict
) -> None:
    """Fully rebuild a disposable index and delete it without changing source notes."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/Beatriz.md", valid_note("beatriz", "person", "My wife."))
    source = vault / "people/Beatriz.md"
    original = source.read_bytes()
    source_mode = source.stat().st_mode
    source.chmod(0o444)
    index = SemanticEntityIndex(tmp_path / "derived" / "semantic.sqlite3")

    try:
        assert index.rebuild(VaultRepository(vault), schema, KeywordEmbedder()) == 1
        first_size = index.path.stat().st_size
        write_note(
            vault,
            "stores/Carrefour Balma.md",
            valid_note("carrefour-balma", "store", "My normal Carrefour store."),
        )
        assert index.rebuild(VaultRepository(vault), schema, KeywordEmbedder()) == 2
        assert index.path.stat().st_size == first_size
        assert source.read_bytes() == original
        index.delete()
        assert not index.path.exists()
        assert source.read_bytes() == original
    finally:
        source.chmod(source_mode)


def test_delete_refuses_arbitrary_existing_file(tmp_path: Path) -> None:
    """Leave an arbitrary configured file untouched when index identity cannot be verified."""
    target = tmp_path / "important.txt"
    target.write_text("canonical data", encoding="utf-8")

    with pytest.raises(SemanticIndexError, match="unverified semantic index"):
        SemanticEntityIndex(target).delete()

    assert target.read_text(encoding="utf-8") == "canonical data"


@pytest.mark.parametrize("malformed", [True, False])
def test_delete_refuses_non_odyssey_sqlite(tmp_path: Path, *, malformed: bool) -> None:
    """Leave malformed and structurally valid non-Odyssey SQLite files untouched."""
    target = tmp_path / "other.sqlite3"
    if malformed:
        target.write_bytes(b"not sqlite")
    else:
        with sqlite3.connect(target) as connection:
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO metadata VALUES ('application', 'someone-else')")
    before = target.read_bytes()

    with pytest.raises(SemanticIndexError, match="unverified semantic index"):
        SemanticEntityIndex(target).delete()

    assert target.read_bytes() == before


def test_delete_missing_index_is_a_no_op(tmp_path: Path) -> None:
    """Allow cleanup callers to delete an already-absent index harmlessly."""
    SemanticEntityIndex(tmp_path / "missing.sqlite3").delete()


def test_type_filter_top_n_context_and_candidate_only_contract(
    tmp_path: Path, schema: dict
) -> None:
    """Filter before top-N and return ranking evidence without final resolution claims."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/Beatriz A.md", valid_note("a", "person", "The user's wife."))
    write_note(vault, "people/Beatriz B.md", valid_note("b", "person", "Xavi's wife."))
    write_note(vault, "people/Xavi.md", valid_note("xavi", "person", "Partner of Beatriz B."))
    write_note(vault, "stores/Carrefour.md", valid_note("store", "store", "Carrefour store."))
    index = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    index.rebuild(VaultRepository(vault), schema, KeywordEmbedder())

    candidates = find_semantic_entity_candidates(
        index,
        KeywordEmbedder(),
        "the other Beatriz",
        context="Dinner with Xavi and his partner",
        type="person",
        limit=2,
    )

    assert {candidate.id for candidate in candidates} == {"b", "xavi"}
    assert len(candidates) == 2
    assert all(candidate.type == "person" for candidate in candidates)
    assert all(
        not hasattr(candidate, field)
        for candidate in candidates
        for field in ("resolved", "confidence", "outcome")
    )


def test_equal_scores_use_stable_name_path_id_order(tmp_path: Path, schema: dict) -> None:
    """Break cosine ties deterministically instead of depending on SQLite row order."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/Zed.md", valid_note("1", "person", "Colleague."))
    write_note(vault, "archive/amy.md", valid_note("3", "person", "Colleague."))
    write_note(vault, "people/Amy.md", valid_note("2", "person", "Colleague."))
    index = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    index.rebuild(VaultRepository(vault), schema, KeywordEmbedder())

    candidates = index.find_candidates(KeywordEmbedder(), "unknown person", limit=3)

    assert [candidate.path for candidate in candidates] == [
        "archive/amy.md",
        "people/Amy.md",
        "people/Zed.md",
    ]


@pytest.mark.parametrize(
    "source",
    [
        "# missing frontmatter",
        "---\nid: bad\ntype: definitely-unknown\n---\n\nInvalid schema type",
    ],
)
def test_invalid_source_fails_without_replacing_existing_index(
    tmp_path: Path, schema: dict, source: str
) -> None:
    """Fail closed on malformed/schema-invalid Markdown and preserve the last good index."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/Good.md", valid_note("good", "person", "A person."))
    index = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    index.rebuild(VaultRepository(vault), schema, KeywordEmbedder())
    before = index.path.read_bytes()
    (vault / "bad.md").write_text(source, encoding="utf-8")

    with pytest.raises(SemanticIndexError, match="invalid note: bad.md"):
        index.rebuild(VaultRepository(vault), schema, KeywordEmbedder())

    assert index.path.read_bytes() == before
    assert [candidate.id for candidate in index.find_candidates(KeywordEmbedder(), "person")] == [
        "good"
    ]


def test_invalid_query_constraints_fail_clearly(tmp_path: Path, schema: dict) -> None:
    """Reject empty references, unknown types, and non-positive limits."""
    vault = tmp_path / "vault"
    vault.mkdir()
    index = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    index.rebuild(VaultRepository(vault), schema, KeywordEmbedder())

    with pytest.raises(ValueError, match="must not be empty"):
        index.find_candidates(KeywordEmbedder(), " ")
    with pytest.raises(ValueError, match="Unknown canonical"):
        index.find_candidates(KeywordEmbedder(), "person", type="unknown")
    with pytest.raises(ValueError, match="positive integer"):
        index.find_candidates(KeywordEmbedder(), "person", limit=0)


def test_missing_index_fails_safely(tmp_path: Path) -> None:
    """Require an explicitly rebuilt derived index rather than scanning during lookup."""
    index = SemanticEntityIndex(tmp_path / "missing.sqlite3")

    with pytest.raises(SemanticIndexError, match="compatible semantic index"):
        index.find_candidates(KeywordEmbedder(), "my wife")


def test_index_cannot_be_stored_inside_authoritative_vault(tmp_path: Path, schema: dict) -> None:
    """Enforce that disposable semantic state stays outside canonical Markdown knowledge."""
    vault = tmp_path / "vault"
    vault.mkdir()
    index = SemanticEntityIndex(vault / ".derived" / "semantic.sqlite3")

    with pytest.raises(SemanticIndexError, match="outside the Markdown vault"):
        index.rebuild(VaultRepository(vault), schema, KeywordEmbedder())

    assert not index.path.exists()


def test_empty_vault_returns_no_candidates(tmp_path: Path, schema: dict) -> None:
    """Treat a valid empty derived index as an empty candidate set."""
    vault = tmp_path / "vault"
    vault.mkdir()
    index = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    index.rebuild(VaultRepository(vault), schema, KeywordEmbedder())

    assert index.find_candidates(KeywordEmbedder(), "my wife") == ()


def test_rebuild_accepts_a_read_only_vault(tmp_path: Path, schema: dict) -> None:
    """Require only canonical source reads while writing derived state elsewhere."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "Beatriz.md", valid_note("beatriz", "person", "My wife."))
    original_mode = vault.stat().st_mode
    vault.chmod(0o555)
    index = SemanticEntityIndex(tmp_path / "runtime" / "semantic.sqlite3")

    try:
        assert index.rebuild(VaultRepository(vault), schema, KeywordEmbedder()) == 1
    finally:
        vault.chmod(original_mode)
