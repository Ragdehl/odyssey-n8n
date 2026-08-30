"""Tests for deterministic candidate discovery and exact entity resolution."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from odyssey_core import (
    ExactEntityCandidate,
    ExactEntityLookupError,
    ExactResolutionOutcome,
    MatchKind,
    find_exact_entity_candidates,
    resolve_exact_entity,
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
    extra_metadata: dict[str, object] | None = None,
    content: str = "",
) -> None:
    """Create one valid identity fixture through the raw repository boundary."""
    metadata: dict[str, object] = {
        "id": note_id,
        "name": Path(path).stem,
        "type": note_type,
        "created_at": "2026-08-15T10:00:00+02:00",
        "updated_at": "2026-08-15T10:00:00+02:00",
        "created_by": {"human": None, "app": "test"},
        "updated_by": {"human": None, "app": "test"},
        "revision": 1,
        "schema_version": 3,
    }
    if aliases is not None:
        metadata["aliases"] = aliases
    if extra_metadata is not None:
        metadata.update(extra_metadata)
    repository.create_text(path, serialize_note(Note(metadata=metadata, content=content)))  # type: ignore[arg-type]


def test_find_exact_entity_candidates_finds_primary_name_with_unicode_casefold_and_whitespace(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Match a filename stem exactly after minimal deterministic normalization."""
    _write_note(repository, "stores/Straße.md", note_id="store-1", note_type="store")

    candidates = find_exact_entity_candidates(repository, schema, "  STRASSE  ", type="store")

    assert len(candidates) == 1
    assert isinstance(candidates[0], ExactEntityCandidate)
    assert candidates[0].path == "stores/Straße.md"
    assert candidates[0].id == "store-1"
    assert candidates[0].type == "store"
    assert candidates[0].primary_name == "Straße"
    assert candidates[0].match_kind is MatchKind.PRIMARY_NAME
    assert candidates[0].matched_value == "Straße"


def test_exact_matching_normalizes_canonical_unicode_and_repeated_whitespace(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Treat only canonical Unicode and whitespace-layout variants as equivalent."""
    _write_note(
        repository,
        "stores/Café du Port.md",
        note_id="store-cafe",
        note_type="store",
        aliases=["L’Épicerie   Centrale"],
    )

    primary = find_exact_entity_candidates(repository, schema, "Cafe\u0301\tdu\nPort", type="store")
    alias = find_exact_entity_candidates(repository, schema, "l’épicerie centrale", type="store")

    assert [candidate.id for candidate in primary] == ["store-cafe"]
    assert [candidate.id for candidate in alias] == ["store-cafe"]


@pytest.mark.parametrize("query", ["Cafe du Port", "Café de Port", "Café-du-Port", "Café du Port!"])
def test_exact_matching_preserves_accents_words_hyphens_and_punctuation(
    repository: VaultRepository, schema: dict[str, object], query: str
) -> None:
    """Keep identity-bearing lexical and punctuation differences out of exact matching."""
    _write_note(repository, "stores/Café du Port.md", note_id="store-cafe", note_type="store")

    assert find_exact_entity_candidates(repository, schema, query, type="store") == ()


def test_find_exact_entity_candidates_finds_alias_and_primary_name_takes_precedence(
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

    candidates = find_exact_entity_candidates(repository, schema, "carrefour", type="store")

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

    assert find_exact_entity_candidates(repository, schema, "Auchan", type="store") == ()


def test_type_filter_excludes_exact_cross_type_match(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Constrain identity candidates to the caller's canonical entity type."""
    _write_note(repository, "stores/Carrefour.md", note_id="store-1", note_type="store")
    _write_note(repository, "documents/Carrefour.md", note_id="doc-1", note_type="document")

    candidates = find_exact_entity_candidates(repository, schema, "Carrefour", type="store")

    assert [candidate.id for candidate in candidates] == ["store-1"]


def test_same_exact_name_across_types_is_ambiguous_without_type_filter(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Preserve cross-type ambiguity when the caller supplies no type constraint."""
    _write_note(repository, "stores/Carrefour.md", note_id="store-1", note_type="store")
    _write_note(repository, "documents/Carrefour.md", note_id="doc-1", note_type="document")

    resolution = resolve_exact_entity(repository, schema, "Carrefour")

    assert resolution.outcome is ExactResolutionOutcome.AMBIGUOUS_EXACT_MATCH
    assert [(candidate.type, candidate.id) for candidate in resolution.candidates] == [
        ("document", "doc-1"),
        ("store", "store-1"),
    ]


def test_candidate_order_is_deterministic_across_repeated_discovery(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Order primary matches first, then normalized names and paths deterministically."""
    _write_note(repository, "stores/Carrefour.md", note_id="store-main", note_type="store")
    _write_note(repository, "documents/Carrefour.md", note_id="doc-main", note_type="document")
    _write_note(
        repository,
        "stores/alpha.md",
        note_id="store-alpha",
        note_type="store",
        aliases=["Carrefour"],
    )
    _write_note(
        repository,
        "documents/Alpha.md",
        note_id="doc-alpha",
        note_type="document",
        aliases=["Carrefour"],
    )

    first = find_exact_entity_candidates(repository, schema, "Carrefour")
    second = find_exact_entity_candidates(repository, schema, "Carrefour")

    expected_paths = [
        "documents/Carrefour.md",
        "stores/Carrefour.md",
        "documents/Alpha.md",
        "stores/alpha.md",
    ]
    assert [candidate.path for candidate in first] == expected_paths
    assert second == first


def test_resolve_exact_entity_represents_all_three_normal_outcomes(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Return unique, absent, and ambiguous exact matches as explicit outcomes."""
    _write_note(repository, "stores/Carrefour.md", note_id="store-1", note_type="store")
    _write_note(
        repository,
        "stores/Carrefour Balma.md",
        note_id="store-2",
        note_type="store",
        aliases=["Carrefour"],
    )

    ambiguous = resolve_exact_entity(repository, schema, " Carrefour ", type="store")
    no_exact_match = resolve_exact_entity(repository, schema, "Auchan", type="store")
    exact_match = resolve_exact_entity(repository, schema, "Carrefour Balma", type="store")

    assert ambiguous.outcome is ExactResolutionOutcome.AMBIGUOUS_EXACT_MATCH
    assert ambiguous.query == "Carrefour"
    assert ambiguous.candidate is None
    assert len(ambiguous.candidates) == 2
    assert no_exact_match.outcome is ExactResolutionOutcome.NO_EXACT_MATCH
    assert no_exact_match.candidates == ()
    assert exact_match.outcome is ExactResolutionOutcome.EXACT_MATCH
    assert exact_match.candidate is not None
    assert exact_match.candidate.id == "store-2"


def test_partial_name_is_not_a_candidate_or_resolution(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Never promote a sole partial name to an identity match."""
    _write_note(repository, "stores/Carrefour Balma.md", note_id="store-1", note_type="store")

    assert find_exact_entity_candidates(repository, schema, "Carre", type="store") == ()
    assert (
        resolve_exact_entity(repository, schema, "Carre", type="store").outcome
        is ExactResolutionOutcome.NO_EXACT_MATCH
    )


def test_relationship_context_does_not_become_an_exact_identity_match(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Arbitrary structured properties are not exact identity evidence."""
    schema = deepcopy(schema)
    next(item for item in schema["types"] if item["id"] == "person")["properties"] = [
        {"id": "origin", "value_type": "string", "required": False, "description": "Origin."}
    ]
    _write_note(
        repository,
        "documents/Beatriz.md",
        note_id="person-beatriz",
        note_type="person",
        aliases=["Bea"],
        extra_metadata={"origin": "colleague"},
        content="# Beatriz\n\nThe mother of my children.\n",
    )

    result = resolve_exact_entity(repository, schema, "colleague", type="person")

    assert result.outcome is ExactResolutionOutcome.NO_EXACT_MATCH
    assert result.candidates == ()


def test_invalid_query_and_unknown_type_fail_before_scanning(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Reject unusable references and non-canonical type constraints explicitly."""
    for query in ("", "   ", None):
        with pytest.raises(ValueError):
            find_exact_entity_candidates(  # type: ignore[arg-type]
                repository, schema, query, type="store"
            )
    with pytest.raises(ValueError, match="Unknown canonical note type"):
        find_exact_entity_candidates(repository, schema, "Carrefour", type="supermarket")


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
    """Refuse a potentially unsafe no-exact-match result when an existing note is invalid."""
    repository.create_text("broken.md", markdown)

    with pytest.raises(ExactEntityLookupError, match="broken.md"):
        resolve_exact_entity(repository, schema, "Carrefour", type="store")


def test_candidate_discovery_is_read_only(
    repository: VaultRepository, schema: dict[str, object]
) -> None:
    """Leave note content and vault paths unchanged after lookup."""
    _write_note(repository, "stores/Carrefour.md", note_id="store-1", note_type="store")
    before = repository.read_text("stores/Carrefour.md")
    before_paths = repository.list_markdown_paths()

    resolve_exact_entity(repository, schema, "Carrefour", type="store")

    assert repository.read_text("stores/Carrefour.md") == before
    assert repository.list_markdown_paths() == before_paths
