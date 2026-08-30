"""Tests for deterministic Phase 12 entity persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core import (
    EntityAlreadyExistsError,
    EntityIdentityMismatchError,
    PersistenceOperation,
    ProtectedMetadataError,
    create_entity,
    update_entity,
)
from odyssey_core.notes import NoteFormatError, NoteValidationError
from odyssey_core.storage import InvalidNotePath, VaultRepository

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
NOW = "2026-08-18T10:00:00+02:00"


@pytest.fixture
def repository(tmp_path: Path) -> VaultRepository:
    """Provide a disposable vault with an existing directory for nested notes."""
    (tmp_path / "people").mkdir()
    return VaultRepository(tmp_path)


def create_person(repository: VaultRepository, path: str = "people/bea.md", **kwargs: object):
    """Create the common valid person fixture used by persistence cases."""
    arguments = {
        "path": path,
        "entity_id": "person-bea",
        "metadata": {"name": "Bea", "type": "person"},
        "content": "# Bea\n\nOriginal body.",
        "actor": "phase12-test",
        "now": NOW,
    }
    arguments.update(kwargs)
    arguments["metadata"] = {"name": "Bea", **arguments["metadata"]}
    return create_entity(repository, SCHEMA, **arguments)


def test_create_serializes_domain_data_and_core_lifecycle(repository: VaultRepository) -> None:
    """Create writes exact caller content and canonical lifecycle metadata."""
    result = create_person(repository, metadata={"type": "person", "aliases": ["Bea"]})

    assert result.operation is PersistenceOperation.CREATED
    assert result.revision == 1
    raw = repository.read_text("people/bea.md")
    assert 'aliases: ["Bea"]' in raw
    assert raw.endswith("# Bea\n\nOriginal body.")
    assert 'created_at: "2026-08-18T10:00:00+02:00"' in raw
    assert 'created_by: {"app": "phase12-test", "human": null}' in raw
    assert "revision: 1" in raw


def test_create_persists_valid_controlled_tags(repository: VaultRepository) -> None:
    """Persist canonical tags through the existing generic metadata path."""
    create_person(repository, metadata={"type": "person", "tags": ["idea", "explore"]})
    assert 'tags: ["idea", "explore"]' in repository.read_text("people/bea.md")


def test_create_accepts_arbitrary_tags(repository: VaultRepository) -> None:
    """Persist free-form tags without a Core registry."""
    create_person(repository, metadata={"type": "person", "tags": ["invented"]})
    assert 'tags: ["invented"]' in repository.read_text("people/bea.md")


def test_create_rejects_duplicate_path_without_overwrite(repository: VaultRepository) -> None:
    """Create-only storage preserves an existing note."""
    create_person(repository, metadata={"type": "person", "aliases": ["Bea"]})
    with pytest.raises(OSError):
        create_person(repository, content="replacement")
    assert repository.read_text("people/bea.md").endswith("# Bea\n\nOriginal body.")


def test_create_rejects_duplicate_stable_id_elsewhere(repository: VaultRepository) -> None:
    """Stable IDs remain unique even when physical paths differ."""
    create_person(repository)
    with pytest.raises(EntityAlreadyExistsError):
        create_person(repository, path="people/other.md")


def test_create_validates_before_write_and_rejects_protected_metadata(
    repository: VaultRepository,
) -> None:
    """Invalid domain data and caller lifecycle injection leave no target."""
    with pytest.raises(NoteValidationError):
        create_person(repository, metadata={"type": "person", "retired_field": "x"})
    assert "people/bea.md" not in repository.list_markdown_paths()
    with pytest.raises(ProtectedMetadataError):
        create_person(repository, metadata={"type": "person", "revision": 99})


def test_update_sets_properties_and_preserves_creation_lifecycle(
    repository: VaultRepository,
) -> None:
    """Explicit property patches update only managed update lifecycle fields."""
    create_person(repository)
    result = update_entity(
        repository,
        SCHEMA,
        path="people/bea.md",
        expected_id="person-bea",
        set_metadata={"aliases": ["Bea", "B"]},
        actor="updater",
        now="2026-08-18T11:00:00+02:00",
    )

    assert result.operation is PersistenceOperation.UPDATED
    assert result.revision == 2
    raw = repository.read_text("people/bea.md")
    assert 'aliases: ["Bea", "B"]' in raw
    assert 'created_at: "2026-08-18T10:00:00+02:00"' in raw
    assert 'created_by: {"app": "phase12-test", "human": null}' in raw
    assert 'updated_by: {"app": "updater", "human": null}' in raw
    assert "revision: 2" in raw


def test_update_replaces_and_removes_tags(repository: VaultRepository) -> None:
    """Allow explicit tag replacement and removal with normal revisioning."""
    create_person(repository, metadata={"type": "person", "tags": ["idea"]})
    result = update_entity(
        repository,
        SCHEMA,
        path="people/bea.md",
        expected_id="person-bea",
        set_metadata={"tags": ["decision", "review"]},
        actor="updater",
        now=NOW,
    )
    assert result.operation is PersistenceOperation.UPDATED
    assert result.revision == 2
    assert 'tags: ["decision", "review"]' in repository.read_text("people/bea.md")
    removed = update_entity(
        repository,
        SCHEMA,
        path="people/bea.md",
        expected_id="person-bea",
        set_metadata={},
        remove_metadata=("tags",),
        actor="updater",
        now=NOW,
    )
    assert removed.operation is PersistenceOperation.UPDATED
    assert "tags:" not in repository.read_text("people/bea.md")


def test_update_invalid_tags_fails_closed_and_identical_tags_are_no_change(
    repository: VaultRepository, monkeypatch
) -> None:
    """Reject invalid tag patches before writing and preserve no-op semantics."""
    create_person(repository, metadata={"type": "person", "tags": ["idea"]})
    before = repository.read_text("people/bea.md")
    with pytest.raises(NoteValidationError):
        update_entity(
            repository,
            SCHEMA,
            path="people/bea.md",
            expected_id="person-bea",
            set_metadata={"tags": [" bad"]},
            actor="updater",
            now=NOW,
        )
    assert repository.read_text("people/bea.md") == before
    monkeypatch.setattr(repository, "replace_text", lambda *args: pytest.fail("must not write"))
    result = update_entity(
        repository,
        SCHEMA,
        path="people/bea.md",
        expected_id="person-bea",
        set_metadata={"tags": ["idea"]},
        actor="updater",
        now=NOW,
    )
    assert result.operation is PersistenceOperation.NO_CHANGE


def test_update_removes_property_and_replaces_body_exactly(repository: VaultRepository) -> None:
    """Explicit removal and body replacement never invoke a text merge."""
    create_person(repository, metadata={"type": "person", "aliases": ["Bea"]})
    update_entity(
        repository,
        SCHEMA,
        path="people/bea.md",
        expected_id="person-bea",
        set_metadata={},
        remove_metadata=("aliases",),
        content="A caller-decided replacement.\n",
        actor="updater",
        now="2026-08-18T11:00:00+02:00",
    )
    raw = repository.read_text("people/bea.md")
    assert "aliases:" not in raw
    assert raw.endswith("A caller-decided replacement.\n")


def test_update_rejects_scalar_remove_metadata_before_write(repository: VaultRepository) -> None:
    """A scalar removal name cannot be interpreted as a character sequence."""
    create_person(repository, metadata={"type": "person", "aliases": ["Bea"]})
    before = repository.read_text("people/bea.md")
    with pytest.raises(TypeError, match="sequence of strings"):
        update_entity(
            repository,
            SCHEMA,
            path="people/bea.md",
            expected_id="person-bea",
            set_metadata={},
            remove_metadata="aliases",
            actor="updater",
            now=NOW,
        )
    assert repository.read_text("people/bea.md") == before


def test_update_rejects_non_string_remove_metadata_element(repository: VaultRepository) -> None:
    """Removal fields must all be explicit property names."""
    create_person(repository)
    with pytest.raises(TypeError, match="only strings"):
        update_entity(
            repository,
            SCHEMA,
            path="people/bea.md",
            expected_id="person-bea",
            set_metadata={},
            remove_metadata=("aliases", 7),
            actor="updater",
            now=NOW,
        )


def test_update_accepts_valid_remove_metadata_sequence(repository: VaultRepository) -> None:
    """A sequence of string property names removes the requested property."""
    create_person(repository, metadata={"type": "person", "aliases": ["Bea"]})
    update_entity(
        repository,
        SCHEMA,
        path="people/bea.md",
        expected_id="person-bea",
        set_metadata={},
        remove_metadata=("aliases",),
        actor="updater",
        now=NOW,
    )
    assert "aliases:" not in repository.read_text("people/bea.md")


def test_update_content_none_preserves_body(repository: VaultRepository) -> None:
    """A metadata-only update keeps the exact existing body."""
    create_person(repository, content="Body with *Markdown*.\r\n")
    update_entity(
        repository,
        SCHEMA,
        path="people/bea.md",
        expected_id="person-bea",
        set_metadata={"aliases": ["Bea"]},
        actor="updater",
        now="2026-08-18T11:00:00+02:00",
    )
    assert repository.read_text("people/bea.md").endswith("Body with *Markdown*.\r\n")


def test_update_no_change_does_not_write_or_bump_revision(
    repository: VaultRepository, monkeypatch
) -> None:
    """Identical explicit mutations return NO_CHANGE and avoid replacement."""
    create_person(repository, metadata={"type": "person", "aliases": ["Bea"]})

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise AssertionError("no-op update must not write")

    monkeypatch.setattr(repository, "replace_text", fail_replace)
    result = update_entity(
        repository,
        SCHEMA,
        path="people/bea.md",
        expected_id="person-bea",
        set_metadata={"aliases": ["Bea"]},
        actor="different-actor",
        now="2026-08-18T12:00:00+02:00",
    )
    assert result.operation is PersistenceOperation.NO_CHANGE
    assert result.revision == 1


def test_update_fails_closed_for_wrong_id_and_invalid_mutations(
    repository: VaultRepository,
) -> None:
    """Identity mismatch and invalid patches leave the existing note unchanged."""
    create_person(repository)
    before = repository.read_text("people/bea.md")
    with pytest.raises(EntityIdentityMismatchError):
        update_entity(
            repository,
            SCHEMA,
            path="people/bea.md",
            expected_id="wrong-id",
            set_metadata={"relationship_to_user": "partner"},
            actor="updater",
            now=NOW,
        )
    assert repository.read_text("people/bea.md") == before
    with pytest.raises(NoteValidationError):
        update_entity(
            repository,
            SCHEMA,
            path="people/bea.md",
            expected_id="person-bea",
            set_metadata={"birth_date": "not-a-date"},
            actor="updater",
            now=NOW,
        )
    assert repository.read_text("people/bea.md") == before
    with pytest.raises(ProtectedMetadataError):
        update_entity(
            repository,
            SCHEMA,
            path="people/bea.md",
            expected_id="person-bea",
            set_metadata={"id": "other"},
            actor="updater",
            now=NOW,
        )


def test_update_rejects_required_property_removal_and_bad_existing_note(
    repository: VaultRepository,
) -> None:
    """Required fields and malformed existing Markdown fail before replacement."""
    create_entity(
        repository,
        SCHEMA,
        path="people/journal.md",
        entity_id="journal-1",
        metadata={"name": "Journal", "type": "journal_entry", "entry_date": "2026-08-18"},
        content="entry",
        actor="test",
        now=NOW,
    )
    before = repository.read_text("people/journal.md")
    with pytest.raises(NoteValidationError):
        update_entity(
            repository,
            SCHEMA,
            path="people/journal.md",
            expected_id="journal-1",
            set_metadata={},
            remove_metadata=("entry_date",),
            actor="updater",
            now=NOW,
        )
    assert repository.read_text("people/journal.md") == before

    repository.replace_text("people/journal.md", "not markdown")
    with pytest.raises(NoteFormatError):
        update_entity(
            repository,
            SCHEMA,
            path="people/journal.md",
            expected_id="journal-1",
            set_metadata={},
            actor="updater",
            now=NOW,
        )


def test_update_rejects_schema_invalid_existing_note_without_modification(
    repository: VaultRepository,
) -> None:
    """A syntactically valid but non-canonical existing note is not updateable."""
    create_person(repository)
    repository.replace_text(
        "people/bea.md",
        repository.read_text("people/bea.md").replace('type: "person"', 'type: "unknown"'),
    )
    before = repository.read_text("people/bea.md")

    with pytest.raises(NoteValidationError):
        update_entity(
            repository,
            SCHEMA,
            path="people/bea.md",
            expected_id="person-bea",
            set_metadata={"relationship_to_user": "partner"},
            actor="updater",
            now=NOW,
        )

    assert repository.read_text("people/bea.md") == before


def test_update_invalid_path_is_rejected(repository: VaultRepository) -> None:
    """Persistence delegates unsafe path handling to the repository boundary."""
    with pytest.raises(InvalidNotePath):
        update_entity(
            repository,
            SCHEMA,
            path="../outside.md",
            expected_id="person-bea",
            set_metadata={},
            actor="updater",
            now=NOW,
        )
