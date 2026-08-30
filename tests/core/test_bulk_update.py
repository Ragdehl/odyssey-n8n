"""Deterministic Phase 16.7A bulk UPDATE execution tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core import (
    BulkUpdateResult,
    BulkUpdateSuccess,
    MaterializationError,
    SelectionCriteria,
    TagChange,
    execute_bulk_update,
)
from odyssey_core.notes import Note, serialize_note
from odyssey_core.request_planning import KnowledgeUnit, PropertyChange
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
NOW = "2026-08-27T10:00:00+02:00"


def put_note(
    vault: Path, note_id: str, name: str, note_type: str = "person", **metadata: object
) -> None:
    """Write one valid disposable Markdown note for a bulk selection fixture."""
    path = vault / f"{name.lower()}.md"
    value = Note(
        {
            "id": note_id,
            "name": name,
            "type": note_type,
            "created_at": "2026-08-24T12:00:00Z",
            "updated_at": "2026-08-24T12:00:00Z",
            "created_by": {"human": None, "app": "pytest"},
            "updated_by": {"human": None, "app": "pytest"},
            "revision": 1,
            "schema_version": 3,
            **metadata,
        },
        f"Synthetic knowledge for {note_id}.",
    )
    path.write_text(serialize_note(value), encoding="utf-8")


def bulk_unit(
    *, filters: tuple = (), intent: str = "amend", tags: tuple = (), facts: tuple = ()
) -> KnowledgeUnit:
    """Build a validated-shape all-matching unit with no singular identity evidence."""
    return KnowledgeUnit(
        SelectionCriteria(None, "all matching people", "person", filters, None),
        intent,
        (),
        tags,
        facts,
        (),
        "all_matching",
    )


@pytest.fixture
def repository(tmp_path: Path) -> VaultRepository:
    """Provide deterministic people with different birth years and tag states."""
    put_note(tmp_path, "z-person", "Zoe", tags=["idea"])
    put_note(tmp_path, "a-person", "Ana", tags=[])
    put_note(tmp_path, "other", "Other", tags=["idea"])
    return VaultRepository(tmp_path)


@pytest.mark.skip(reason="Retired Core tag bulk-update contract")
def test_type_selection_freezes_all_ids_in_deterministic_order(repository: VaultRepository) -> None:
    """Select every canonical person once, independent of filesystem discovery order."""
    result = execute_bulk_update(
        bulk_unit(tags=(TagChange("add", "review"),)),
        repository=repository,
        schema=SCHEMA,
        actor="pytest",
        now=NOW,
    )
    assert result.status == "SUCCESS"
    assert result.selected_note_ids == ("a-person", "other", "z-person")
    assert [item.stable_id for item in result.succeeded] == list(result.selected_note_ids)
    assert all(isinstance(item, BulkUpdateSuccess) for item in result.succeeded)
    assert all("review" in repository.read_text(path) for path in ("ana.md", "other.md", "zoe.md"))


def test_bulk_selection_excludes_deleted_notes(repository: VaultRepository) -> None:
    """Keep physically present deleted notes out of deterministic all-matching membership."""
    raw = repository.read_text("zoe.md").replace(
        "schema_version: 3", "schema_version: 3\ndeleted: true"
    )
    repository.replace_text("zoe.md", raw)
    result = execute_bulk_update(
        bulk_unit(tags=(TagChange("add", "review"),)),
        repository=repository,
        schema=SCHEMA,
        actor="pytest",
        now=NOW,
    )
    assert result.selected_note_ids == ("a-person", "other")
    assert "review" not in repository.read_text("zoe.md")


def test_filters_select_only_matching_notes_and_property_only_needs_no_writer(
    repository: VaultRepository,
) -> None:
    """Apply deterministic membership without invoking a semantic writer."""
    pytest.skip("Deferred person birth-date property")
    filters = (
        {"field": "birth_date", "op": "gte", "value": "1990-01-01"},
        {"field": "birth_date", "op": "lt", "value": "1991-01-01"},
    )
    result = execute_bulk_update(
        bulk_unit(filters=filters, tags=(TagChange("add", "review"),)),
        repository=repository,
        schema=SCHEMA,
        actor="pytest",
        now=NOW,
    )
    assert result.selected_note_ids == ("a-person", "z-person")
    assert len(result.succeeded) == 2
    assert "review" in repository.read_text("ana.md")
    assert "review" not in repository.read_text("other.md")


def test_property_only_bulk_update_uses_deterministic_materialization(
    repository: VaultRepository,
) -> None:
    """Apply one canonical property mutation per selected note without a writer."""
    pytest.skip("Deferred person relationship property")
    unit = KnowledgeUnit(
        SelectionCriteria(None, "all people", "person", (), None),
        "amend",
        (PropertyChange("relationship_to_user", "set", "friend"),),
        (),
        (),
        (),
        "all_matching",
    )
    result = execute_bulk_update(
        unit, repository=repository, schema=SCHEMA, actor="pytest", now=NOW
    )
    assert result.status == "SUCCESS" and len(result.succeeded) == 3
    for path in ("ana.md", "other.md", "zoe.md"):
        assert 'relationship_to_user: "friend"' in repository.read_text(path)


def test_free_text_bulk_update_uses_one_writer_request_per_note(
    repository: VaultRepository,
) -> None:
    """Keep free-text bulk reconciliation independent and bound to each current note."""

    class RecordingWriter:
        """Return one append operation while recording each independent writer context."""

        def __init__(self) -> None:
            self.requests = []

        def write(self, request: object) -> object:
            """Record one note-specific request and return a bounded append."""
            self.requests.append(request)
            return {"operations": [{"op": "APPEND", "text": "- Bulk fact."}]}

    writer = RecordingWriter()
    result = execute_bulk_update(
        bulk_unit(facts=("Each note gets this fact.",)),
        repository=repository,
        schema=SCHEMA,
        actor="pytest",
        now=NOW,
        writer=writer,  # type: ignore[arg-type]
    )
    assert result.status == "SUCCESS"
    assert [request.note_id for request in writer.requests] == ["a-person", "other", "z-person"]
    assert [request.current_body for request in writer.requests] == [
        "Synthetic knowledge for a-person.",
        "Synthetic knowledge for other.",
        "Synthetic knowledge for z-person.",
    ]
    assert len({request.current_body for request in writer.requests}) == 3


def test_empty_set_is_explicit_and_never_creates(repository: VaultRepository) -> None:
    """Treat no deterministic matches as EMPTY_SET with no persistence."""
    pytest.skip("Deferred person birth-date filter")
    result = execute_bulk_update(
        bulk_unit(filters=({"field": "birth_date", "op": "eq", "value": "2000-01-01"},)),
        repository=repository,
        schema=SCHEMA,
        actor="pytest",
        now=NOW,
    )
    assert result == BulkUpdateResult("all_matching", (), (), (), "EMPTY_SET")


@pytest.mark.parametrize("reason", ["semantic", "link"])
def test_unsupported_membership_is_fail_closed(repository: VaultRepository, reason: str) -> None:
    """Reject query-only or graph-derived bulk membership before any write."""
    target = SelectionCriteria(
        None,
        "related to Odyssey" if reason == "semantic" else "linked to Odyssey",
        None if reason == "semantic" else "person",
        (),
        object() if reason == "link" else None,  # type: ignore[arg-type]
    )
    unit = KnowledgeUnit(target, "amend", (), (TagChange("add", "review"),), (), (), "all_matching")
    result = execute_bulk_update(
        unit, repository=repository, schema=SCHEMA, actor="pytest", now=NOW
    )
    assert result.status == "UNSUPPORTED_BULK_SELECTION" and not result.selected_note_ids


def test_bulk_delete_returns_unsupported_without_writes(repository: VaultRepository) -> None:
    """Preserve delete intent in planning while Phase 16.7A rejects its execution."""
    result = execute_bulk_update(
        bulk_unit(intent="delete"),
        repository=repository,
        schema=SCHEMA,
        actor="pytest",
        now=NOW,
    )
    assert result.status == "UNSUPPORTED_BULK_DELETE" and result.selected_note_ids == ()


def test_partial_success_keeps_prior_write_and_associates_failure(
    repository: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Continue independent notes after one materialization failure without rollback."""
    from odyssey_core import bulk_update

    original = bulk_update.materialize_update

    def fail_one(unit: object, decision: object, **kwargs: object):
        """Fail one stable ID while delegating all other IDs to real materialization."""
        if decision.existing_note_id == "z-person":
            raise MaterializationError("stale revision")
        return original(unit, decision, **kwargs)

    monkeypatch.setattr(bulk_update, "materialize_update", fail_one)
    result = execute_bulk_update(
        bulk_unit(tags=(TagChange("add", "review"),)),
        repository=repository,
        schema=SCHEMA,
        actor="pytest",
        now=NOW,
    )
    assert result.status == "PARTIAL_SUCCESS"
    assert [item.stable_id for item in result.succeeded] == ["a-person", "other"]
    assert result.failed[0].stable_id == "z-person"
    assert "review" in repository.read_text("ana.md")
