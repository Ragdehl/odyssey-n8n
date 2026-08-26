"""Deterministic Phase 16.6 CREATE materialization coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core import (
    EntityAlreadyExistsError,
    KnowledgeReference,
    KnowledgeUnit,
    MaterializationError,
    PersistenceOperation,
    SelectionCriteria,
    TagChange,
    UnitTargetPreflight,
    WriteTargetOutcome,
    create_entity,
    materialize_create,
)
from odyssey_core.notes import Note, parse_note, validate_note
from odyssey_core.request_planning import PropertyChange
from odyssey_core.storage import NoteAlreadyExistsError, VaultRepository

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
NOW = "2026-08-27T12:00:00+02:00"


def unit(
    *,
    query: str = "Marta",
    entity: str | None = "Marta",
    note_type: str = "person",
    properties: tuple[PropertyChange, ...] = (),
    tags: tuple[TagChange, ...] = (),
    facts: tuple[str, ...] = (),
    references: tuple[KnowledgeReference, ...] = (),
) -> KnowledgeUnit:
    """Build one validated-shaped CREATE record unit for deterministic tests."""
    return KnowledgeUnit(
        SelectionCriteria(entity, query, note_type, (), None),
        "record",
        properties,
        tags,
        facts,
        references,
    )


def preflight(
    *,
    index: int = 0,
    stable_id: str = "marta-id",
    name: str = "Marta",
    path: str = "Marta - marta-id.md",
) -> UnitTargetPreflight:
    """Build one already-authorized CREATE identity allocation."""
    return UnitTargetPreflight(index, WriteTargetOutcome.CREATE, stable_id, name, path)


@pytest.fixture
def repository(tmp_path: Path) -> VaultRepository:
    """Provide an empty disposable vault with a root creation directory."""
    return VaultRepository(tmp_path)


def create(
    repository: VaultRepository,
    knowledge: KnowledgeUnit,
    target: UnitTargetPreflight | None = None,
    *,
    rendered_facts: tuple[str, ...] | None = None,
):
    """Execute the public deterministic CREATE materialization boundary."""
    return materialize_create(
        knowledge,
        target or preflight(),
        repository=repository,
        schema=SCHEMA,
        actor="phase16-test",
        now=NOW,
        rendered_facts=rendered_facts,
    )


def read_note(repository: VaultRepository, path: str) -> Note:
    """Read and parse the one note produced by a CREATE test."""
    return parse_note(repository.read_text(path))


def test_preallocated_identity_and_path_are_reused_exactly(repository: VaultRepository) -> None:
    """Use preflight's ID, path, and canonical name without deriving replacements."""
    target = preflight(
        stable_id="full-preallocated-id",
        name="Contextual Marta",
        path="Contextual Marta - full-preallocated-id.md",
    )
    result = create(repository, unit(entity=None, query="la amiga de Marta"), target)

    assert result.operation is PersistenceOperation.CREATED
    assert result.id == "full-preallocated-id"
    assert result.path == "Contextual Marta - full-preallocated-id.md"
    note = read_note(repository, result.path)
    assert note.metadata["id"] == "full-preallocated-id"
    assert note.metadata["name"] == "Contextual Marta"
    assert note.metadata["type"] == "person"


def test_properties_and_tags_are_deterministic_and_body_is_empty(
    repository: VaultRepository,
) -> None:
    """Persist structured-only CREATE metadata once without a writer or body formatting."""
    result = create(
        repository,
        unit(
            properties=(PropertyChange("relationship_to_user", "set", "friend"),),
            tags=(TagChange("add", "idea"), TagChange("add", "review")),
        ),
    )
    note = read_note(repository, result.path)
    assert result.operation is PersistenceOperation.CREATED
    assert note.metadata["relationship_to_user"] == "friend"
    assert note.metadata["tags"] == ["idea", "review"]
    assert note.content == ""


def test_reference_only_create_accepts_bound_facts_or_empty_facts(
    repository: VaultRepository,
) -> None:
    """Allow an identity-only reference target while requiring prepared facts when present."""
    reference_only = create(repository, unit(facts=()))
    assert read_note(repository, reference_only.path).content == ""

    linked = unit(
        query="Bea",
        entity="Bea",
        facts=("Bea works with {{ref:0}}.",),
        references=(KnowledgeReference(1, "person", "Marta"),),
    )
    target = preflight(stable_id="bea-id", name="Bea", path="Bea - bea-id.md")
    result = create(
        repository,
        linked,
        target,
        rendered_facts=("Bea works with [[Marta - marta-id|Marta]].",),
    )
    assert read_note(repository, result.path).content == (
        "Bea works with [[Marta - marta-id|Marta]]."
    )


def test_facts_are_preserved_in_order_with_one_newline(repository: VaultRepository) -> None:
    """Copy every prepared fact byte-for-byte and join only adjacent facts with one newline."""
    facts = ("  first  ", "second\nwith a newline", "third")
    result = create(repository, unit(facts=facts))
    assert read_note(repository, result.path).content == "  first  \nsecond\nwith a newline\nthird"


def test_missing_required_metadata_fails_before_writing(repository: VaultRepository) -> None:
    """Reject a journal CREATE without its required domain date before creating a file."""
    with pytest.raises(ValueError, match="entry_date"):
        create(repository, unit(note_type="journal_entry"))
    assert repository.list_markdown_paths() == []


def test_raw_reference_markers_are_rejected(repository: VaultRepository) -> None:
    """Never allow an unresolved internal marker to reach canonical Markdown."""
    with pytest.raises(MaterializationError, match="Raw reference markers"):
        create(repository, unit(facts=("mentions {{ref:0}}",)))
    assert repository.list_markdown_paths() == []


def test_required_bound_links_and_repetitions_survive_exactly(repository: VaultRepository) -> None:
    """Persist prepared Core-bound wikilinks without rewriting target or display text."""
    link = "[[projects/Odyssey-id|Odyssey]]"
    facts = (f"Works with {link} and {link}.", f"Also supports {link}.")
    knowledge = unit(
        facts=("Works with {{ref:0}} and {{ref:0}}.", "Also supports {{ref:0}}."),
        references=(KnowledgeReference(1, "project", "Odyssey"),),
    )
    result = create(repository, knowledge, rendered_facts=facts)
    assert read_note(repository, result.path).content == "\n".join(facts)


def test_duplicate_id_and_occupied_path_never_overwrite(repository: VaultRepository) -> None:
    """Delegate collision safety to Phase 12 create semantics without partial replacement."""
    create_entity(
        repository,
        SCHEMA,
        path="existing.md",
        entity_id="existing-id",
        metadata={"name": "Existing", "type": "person"},
        content="original",
        actor="test",
        now=NOW,
    )
    with pytest.raises(EntityAlreadyExistsError):
        create(repository, unit(), preflight(stable_id="existing-id", path="new.md"))
    with pytest.raises(NoteAlreadyExistsError):
        create(repository, unit(), preflight(stable_id="new-id", path="existing.md"))
    assert read_note(repository, "existing.md").content == "original"


def test_result_is_schema_valid_revision_one(repository: VaultRepository) -> None:
    """Confirm the single persisted result is a canonical revision-one note."""
    result = create(
        repository,
        unit(
            properties=(PropertyChange("relationship_to_user", "set", "friend"),),
            facts=("A fact.",),
        ),
    )
    note = read_note(repository, result.path)
    validate_note(note, SCHEMA)
    assert note.metadata["revision"] == 1
