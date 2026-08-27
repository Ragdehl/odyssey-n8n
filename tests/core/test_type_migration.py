"""Focused Phase 16.7C identity-preserving type-migration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core import (
    MaterializationError,
    PersistenceOperation,
    WriteTargetDecision,
    WriteTargetOutcome,
    create_entity,
    materialize_type_migration,
)
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeUnit,
    PropertyChange,
    RequestPlanningError,
    SelectionCriteria,
    validate_request_plan,
)
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-08-28T10:00:00+02:00"


@pytest.fixture
def schema() -> dict:
    """Load the checked-in canonical schema."""
    return json.loads((ROOT / "config/note-schema.json").read_text())


@pytest.fixture
def repository(tmp_path: Path, schema: dict) -> VaultRepository:
    """Create one source note and an unchanged inbound-link source file."""
    (tmp_path / "notes").mkdir()
    repo = VaultRepository(tmp_path)
    create_entity(
        repo,
        schema,
        path="notes/odyssey.md",
        entity_id="odyssey",
        metadata={"name": "Odyssey", "type": "concept", "aliases": ["Ody"], "tags": ["idea"]},
        content="Original body with [[Other]].\n",
        actor="creator",
        now=NOW,
    )
    create_entity(
        repo,
        schema,
        path="notes/today.md",
        entity_id="today",
        metadata={"name": "Today", "type": "journal_entry", "entry_date": "2026-08-28"},
        content="Worked on [[Odyssey]].\n",
        actor="creator",
        now=NOW,
    )
    return repo


def unit(
    destination: str, properties: tuple[PropertyChange, ...] = (), *, cardinality: str = "one"
) -> KnowledgeUnit:
    """Build a migration-shaped unit without invoking a planner."""
    return KnowledgeUnit(
        SelectionCriteria("Odyssey", "Odyssey", "concept", (), None),
        "amend",
        properties,
        (),
        (),
        (),
        cardinality,
        destination,
    )


def decision() -> WriteTargetDecision:
    """Return the resolved source identity used by migration tests."""
    return WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id="odyssey")


def test_migration_preserves_identity_body_links_and_creation_lifecycle(
    repository: VaultRepository, schema: dict
) -> None:
    """One concept becomes a project at the same file and stable identity."""
    before = parse_note(repository.read_text("notes/odyssey.md"))
    inbound = repository.read_text("notes/today.md")
    result = materialize_type_migration(
        unit("project"),
        decision(),
        repository=repository,
        schema=schema,
        actor="migrator",
        now="2026-08-28T11:00:00+02:00",
    )
    after = parse_note(repository.read_text("notes/odyssey.md"))
    assert (
        result.operation is PersistenceOperation.MIGRATED
        and result.id == "odyssey"
        and result.path == "notes/odyssey.md"
    )
    assert after.content == before.content and repository.read_text("notes/today.md") == inbound
    assert after.metadata["name"] == before.metadata["name"]
    assert (
        after.metadata["created_at"] == before.metadata["created_at"]
        and after.metadata["created_by"] == before.metadata["created_by"]
    )
    assert after.metadata["aliases"] == ["Ody"] and after.metadata["tags"] == ["idea"]
    assert (
        after.metadata["type"] == "project"
        and after.metadata["revision"] == 2
        and after.metadata["updated_by"] == "migrator"
    )


def test_migration_fails_closed_for_source_property_or_missing_required_destination(
    repository: VaultRepository, schema: dict
) -> None:
    """Lossy person fields and absent journal dates never write a partial destination."""
    before = repository.read_text("notes/odyssey.md")
    with pytest.raises(MaterializationError):
        materialize_type_migration(
            unit("journal_entry"),
            decision(),
            repository=repository,
            schema=schema,
            actor="x",
            now=NOW,
        )
    assert repository.read_text("notes/odyssey.md") == before
    # A source-only person field cannot silently disappear during person -> project.
    note = parse_note(before)
    note.metadata.update({"type": "person", "birth_date": "1990-01-01"})
    repository.replace_text(
        "notes/odyssey.md",
        __import__("odyssey_core.notes", fromlist=["serialize_note"]).serialize_note(note),
    )
    before = repository.read_text("notes/odyssey.md")
    with pytest.raises(MaterializationError):
        materialize_type_migration(
            unit("project"), decision(), repository=repository, schema=schema, actor="x", now=NOW
        )
    assert repository.read_text("notes/odyssey.md") == before


def test_destination_property_makes_journal_migration_valid(
    repository: VaultRepository, schema: dict
) -> None:
    """An explicit destination-compatible required field completes the destination note."""
    result = materialize_type_migration(
        unit("journal_entry", (PropertyChange("entry_date", "set", "2026-08-27"),)),
        decision(),
        repository=repository,
        schema=schema,
        actor="x",
        now=NOW,
    )
    assert result.operation is PersistenceOperation.MIGRATED
    assert (
        parse_note(repository.read_text("notes/odyssey.md")).metadata["entry_date"] == "2026-08-27"
    )


def test_planner_destination_validation_and_type_property_protection(schema: dict) -> None:
    """Validate migration destination scope while retaining forbidden ordinary type mutations."""
    payload = {
        "actions": [
            {
                "kind": "write",
                "units": [
                    {
                        "target": {
                            "entity": "Odyssey",
                            "query": "Odyssey",
                            "type": "concept",
                            "filters": [],
                            "link_scope": None,
                        },
                        "cardinality": "one",
                        "destination_type": "project",
                        "intent": "amend",
                        "properties": [],
                        "tag_changes": [],
                        "facts": [],
                        "references": [],
                    }
                ],
            }
        ],
        "limitations": [],
    }
    plan = validate_request_plan(payload, schema)
    assert plan.actions[0].units[0].destination_type == "project"  # type: ignore[union-attr]
    payload["actions"][0]["units"][0]["destination_type"] = "unknown"
    with pytest.raises(RequestPlanningError):
        validate_request_plan(payload, schema)
    payload["actions"][0]["units"][0].update(
        {"destination_type": "project", "cardinality": "all_matching"}
    )
    with pytest.raises(RequestPlanningError):
        validate_request_plan(payload, schema)
