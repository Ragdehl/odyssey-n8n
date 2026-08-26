"""Deterministic Phase 16.5B identity preflight coverage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from odyssey_core import (
    KnowledgeReference,
    KnowledgeUnit,
    SelectionCriteria,
    WriteAction,
    WriteTargetOutcome,
    find_exact_entity_candidates,
    preflight_write_action,
)
from odyssey_core.notes import Note, serialize_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]


class EmptyIndex:
    """Provide no semantic candidates without loading a model."""

    def find_candidates(self, *args: object, **kwargs: object) -> tuple[object, ...]:
        """Return an empty deterministic candidate set."""
        return ()


class EmptyEmbedder:
    """Satisfy the injected resolver boundary for CREATE-only tests."""

    model_name = "test"
    model_version = "1"


class NoReasoner:
    """Fail if preflight unexpectedly reaches contextual model reasoning."""

    def resolve(self, request: object) -> object:
        """Reject an unexpected contextual call."""
        raise AssertionError("preflight test unexpectedly called a reasoner")


def unit(query: str, *, entity: str | None = None, note_type: str = "person", refs=()):
    """Build the validated-shaped unit used by deterministic preflight cases."""
    return KnowledgeUnit(
        SelectionCriteria(entity, query, note_type, (), None),
        "record",
        (),
        (),
        ("fact",),
        tuple(refs),
    )


def action(*units: KnowledgeUnit) -> WriteAction:
    """Build an ordered write action from its units."""
    return WriteAction(tuple(units))


def run(vault: Path, schema: dict[str, Any], value: WriteAction, *, ids=None):
    """Run preflight with local no-op dependencies and an optional deterministic allocator."""
    kwargs = {}
    if ids is not None:
        kwargs["id_allocator"] = iter(ids).__next__
    return preflight_write_action(
        value,
        repository=VaultRepository(vault),
        schema=schema,
        semantic_index=EmptyIndex(),
        embedder=EmptyEmbedder(),
        contextual_reasoner=NoReasoner(),
        semantic_limit=5,
        **kwargs,
    )


@pytest.fixture
def schema() -> dict[str, Any]:
    """Load the canonical schema."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def write_existing(vault: Path, path: str, name: str = "Marta") -> None:
    """Write one valid existing note fixture without exposing personal vault data."""
    value = Note(
        {
            "id": "existing-marta",
            "name": name,
            "type": "person",
            "created_at": "2026-08-25T10:00:00Z",
            "updated_at": "2026-08-25T10:00:00Z",
            "created_by": "test",
            "updated_by": "test",
            "revision": 1,
            "schema_version": 2,
        },
        "fact",
    )
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialize_note(value), encoding="utf-8")


def test_create_preallocates_full_uuid_and_entity_name(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Use target.entity and preserve every UUID character in the creation path."""
    result = run(
        tmp_path,
        schema,
        action(unit("Marta query", entity="Marta García")),
        ids=["550e8400-e29b-41d4-a716-446655440000"],
    )
    assert result[0].outcome is WriteTargetOutcome.CREATE
    assert result[0].canonical_name == "Marta García"
    assert result[0].stable_id == "550e8400-e29b-41d4-a716-446655440000"
    assert result[0].path == "Marta García - 550e8400-e29b-41d4-a716-446655440000.md"


def test_create_without_entity_uses_query_and_same_names_do_not_suffix(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Use the human query and distinguish identical names solely by full allocated IDs."""
    result = run(
        tmp_path,
        schema,
        action(unit("Marta García"), unit("Marta García")),
        ids=["id-one", "id-two"],
    )
    assert [item.stable_id for item in result] == ["id-one", "id-two"]
    assert [item.path for item in result] == [
        "Marta García - id-one.md",
        "Marta García - id-two.md",
    ]


def test_existing_target_reuses_id_path_and_metadata_name(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Return authoritative existing physical and canonical identities for UPDATE."""
    write_existing(tmp_path, "people/Marta García - old.md", "Marta García López")
    result = run(tmp_path, schema, action(unit("Marta García López", entity="Marta García López")))
    assert result[0].outcome is WriteTargetOutcome.UPDATE
    assert (result[0].stable_id, result[0].path, result[0].canonical_name) == (
        "existing-marta",
        "people/Marta García - old.md",
        "Marta García López",
    )


def test_create_reference_target_is_preflighted_once_before_any_write(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Preflight reference-only targets and leave all markers/source files untouched."""
    target = unit("Leche Pascual")
    purchase = unit(
        "purchase",
        note_type="purchase",
        refs=(KnowledgeReference(0, "product", "Leche Pascual"),),
    )
    result = run(tmp_path, schema, action(target, purchase), ids=["product-id", "purchase-id"])
    assert [item.outcome for item in result] == [
        WriteTargetOutcome.CREATE,
        WriteTargetOutcome.CREATE,
    ]
    assert result[1].stable_id == "purchase-id"
    assert list(tmp_path.rglob("*.md")) == []


def test_exact_identity_uses_current_name_not_stale_creation_label(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    """Resolve the current metadata name even when the creation filename is stale."""
    write_existing(tmp_path, "people/Marta García - old-id.md", "Marta García López")
    repository = VaultRepository(tmp_path)
    candidates = find_exact_entity_candidates(
        repository, schema, "Marta García López", type="person"
    )
    assert len(candidates) == 1
    assert candidates[0].primary_name == "Marta García López"
    assert find_exact_entity_candidates(repository, schema, "Marta García", type="person") == ()
