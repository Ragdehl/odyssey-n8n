"""Tests for deterministic candidate discovery and conservative entity resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core import (
    EntityCandidate,
    EntitySearchError,
    MatchKind,
    ResolutionOutcome,
    find_entity_candidates,
    resolve_entity,
)
from odyssey_core.notes import Note, serialize_note
from odyssey_core.storage import VaultRepository

CANONICAL_SCHEMA = Path(__file__).resolve().parents[2] / "config" / "note-schema.json"


@pytest.fixture
def schema() -> dict[str, object]:
    """Return the checked-in canonical schema without duplicating its registry."""
    return json.loads(CANONICAL_SCHEMA.read_text(encoding="utf-8"))


@pytest.fixture
def repository(tmp_path: Path) -> VaultRepository:
    """Return a repository backed by an isolated empty temporary vault."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "stores").mkdir()
    (vault / "documents").mkdir()
    return VaultRepository(vault)


def _write_note(
    repository: VaultRepository,
    path: str,
    *,
    note_id: str,
    note_type: str,
    aliases: list[str] | None = None,
) -> None:
    """Create one valid identity fixture through the raw repository boundary."""
    metadata: dict[str, object] = {
        "id": note_id,
        "type": note_type,
        "created_at": "2026-08-15T10:00:00+02:00",
        "updated_at": "2026-08-15T10:00:00+02:00",
        "created_by": "test",
        "updated_by": "test",
        "revision": 1,
        "schema_version": 1,
    }
    if aliases is not None:
        metadata["aliases"] = aliases
    repository.create_text(path, serialize_note(Note(metadata=metadata, content="")))  # type: ignore[arg-type]


def test_find_entity_candidates_finds_primary_name_with_unicode_casefold_and_whitespace(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Match a filename stem exactly after minimal deterministic normalization."""
    _write_note(repository, "stores/Straße.md", note_id="store-1", note_type="store")

    candidates = find_entity_candidates(repository, schema, "  STRASSE  ", type="store")

    assert len(candidates) == 1
    assert isinstance(candidates[0], EntityCandidate)
    assert candidates[0].path == "stores/Straße.md"
    assert candidates[0].id == "store-1"
    assert candidates[0].type == "store"
    assert candidates[0].primary_name == "Straße"
    assert candidates[0].match_kind is MatchKind.PRIMARY_NAME
    assert candidates[0].matched_value == "Straße"


def test_find_entity_candidates_finds_alias_and_primary_name_takes_precedence(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Use exact aliases while reporting a simultaneous primary-name match as stronger."""
    _write_note(
        repository,
        "stores/Carrefour Balma.md",
        note_id="store-balma",
        note_type="store",
        aliases=["Carrefour"],
    )
    _write_note(
        repository,
        "stores/Carrefour.md",
        note_id="store-main",
        note_type="store",
        aliases=["Carrefour"],
    )

    candidates = find_entity_candidates(repository, schema, "carrefour", type="store")

    assert [candidate.id for candidate in candidates] == ["store-main", "store-balma"]
    assert [candidate.match_kind for candidate in candidates] == [
        MatchKind.PRIMARY_NAME,
        MatchKind.ALIAS,
    ]


def test_empty_valid_alias_does_not_break_candidate_discovery(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Ignore a canonically valid empty alias while evaluating a non-empty query."""
    _write_note(
        repository,
        "stores/Carrefour.md",
        note_id="store-main",
        note_type="store",
        aliases=[""],
    )

    assert find_entity_candidates(repository, schema, "Auchan", type="store") == ()


def test_type_filter_excludes_exact_cross_type_match(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Constrain identity candidates to the caller's canonical entity type."""
    _write_note(repository, "stores/Carrefour.md", note_id="store-1", note_type="store")
    _write_note(repository, "documents/Carrefour.md", note_id="doc-1", note_type="document")

    candidates = find_entity_candidates(repository, schema, "Carrefour", type="store")

    assert [candidate.id for candidate in candidates] == ["store-1"]


def test_resolve_entity_represents_all_three_normal_outcomes(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Return resolved, not-found, and ambiguous as explicit domain outcomes."""
    _write_note(repository, "stores/Carrefour.md", note_id="store-1", note_type="store")
    _write_note(
        repository,
        "stores/Carrefour Balma.md",
        note_id="store-2",
        note_type="store",
        aliases=["Carrefour"],
    )

    ambiguous = resolve_entity(repository, schema, " Carrefour ", type="store")
    not_found = resolve_entity(repository, schema, "Auchan", type="store")
    resolved = resolve_entity(repository, schema, "Carrefour Balma", type="store")

    assert ambiguous.outcome is ResolutionOutcome.AMBIGUOUS
    assert ambiguous.query == "Carrefour"
    assert ambiguous.candidate is None
    assert len(ambiguous.candidates) == 2
    assert not_found.outcome is ResolutionOutcome.NOT_FOUND
    assert not_found.candidates == ()
    assert resolved.outcome is ResolutionOutcome.RESOLVED
    assert resolved.candidate is not None
    assert resolved.candidate.id == "store-2"


def test_partial_name_is_not_a_candidate_or_resolution(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Never promote a sole partial name to an identity match."""
    _write_note(repository, "stores/Carrefour Balma.md", note_id="store-1", note_type="store")

    assert find_entity_candidates(repository, schema, "Carre", type="store") == ()
    assert (
        resolve_entity(repository, schema, "Carre", type="store").outcome
        is ResolutionOutcome.NOT_FOUND
    )


def test_invalid_query_and_unknown_type_fail_before_scanning(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Reject unusable references and non-canonical type constraints explicitly."""
    for query in ("", "   ", None):
        with pytest.raises(ValueError):
            find_entity_candidates(repository, schema, query, type="store")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unknown canonical note type"):
        find_entity_candidates(repository, schema, "Carrefour", type="supermarket")


@pytest.mark.parametrize(
    "markdown",
    [
        "not frontmatter",
        "---\nid: broken\ntype: store\n---\n\n# Missing required metadata\n",
    ],
)
def test_invalid_existing_note_fails_closed(
    repository: VaultRepository, schema: dict[str, object], markdown: str
) -> None:
    """Refuse a potentially unsafe not-found result when any existing note is invalid."""
    repository.create_text("broken.md", markdown)

    with pytest.raises(EntitySearchError, match="broken.md"):
        resolve_entity(repository, schema, "Carrefour", type="store")


def test_candidate_discovery_is_read_only(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Leave note content and vault paths unchanged after lookup."""
    _write_note(repository, "stores/Carrefour.md", note_id="store-1", note_type="store")
    before = repository.read_text("stores/Carrefour.md")
    before_paths = repository.list_markdown_paths()

    resolve_entity(repository, schema, "Carrefour", type="store")

    assert repository.read_text("stores/Carrefour.md") == before
    assert repository.list_markdown_paths() == before_paths
