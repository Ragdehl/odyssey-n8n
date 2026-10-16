"""Contract tests for the E3 shared canonical mutation boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from odyssey_core.mutation_gate import (
    CanonicalMutationError,
    CanonicalMutationGate,
    CreateMutationCommand,
    MutationCommand,
)
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.persistence import create_entity, update_entity
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-16T10:00:00Z"


def _build(tmp_path: Path) -> tuple[VaultRepository, dict, str]:
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    repository = VaultRepository(tmp_path)
    raw = serialize_note(
        Note(
            {
                "id": "person-a",
                "name": "Person A",
                "type": "person",
                "created_at": NOW,
                "updated_at": NOW,
                "created_by": {"human": None, "app": "test"},
                "updated_by": {"human": None, "app": "test"},
                "revision": 1,
                "schema_version": 3,
                "aliases": [],
                "tags": [],
            },
            "Original.",
        )
    )
    repository.create_text("person.md", raw)
    return repository, schema, raw


def _command(raw: str, **changes: object) -> MutationCommand:
    values: dict[str, object] = {
        "operation": "person_amended",
        "target_id": "person-a",
        "expected_revision": 1,
        "expected_source_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "request_id": "request-1",
        "actor": "test",
        "now": NOW,
        "expected_type": "person",
    }
    values.update(changes)
    return MutationCommand(**values)  # type: ignore[arg-type]


def test_gate_rejects_stale_wrong_type_and_duplicate_identity(tmp_path: Path) -> None:
    repository, schema, raw = _build(tmp_path)
    gate = CanonicalMutationGate(repository, schema, None)
    with pytest.raises(CanonicalMutationError, match="STALE_TARGET"):
        gate.prepare(_command(raw, expected_revision=2))
    with pytest.raises(CanonicalMutationError, match="TARGET_TYPE_MISMATCH"):
        gate.prepare(_command(raw, expected_type="project"))
    repository.create_text("duplicate.md", repository.read_text("person.md"))
    with pytest.raises(CanonicalMutationError, match="TARGET_UNAVAILABLE"):
        gate.prepare(_command(raw))


@pytest.mark.parametrize("invalid", [None, "", "a" * 63, "A" * 64, 24, object()])
def test_gate_rejects_malformed_hash_before_execution(tmp_path: Path, invalid: object) -> None:
    repository, schema, raw = _build(tmp_path)
    gate = CanonicalMutationGate(repository, schema, None)
    with pytest.raises(CanonicalMutationError, match="STALE_TARGET"):
        gate.prepare(_command(raw, expected_source_hash=invalid))
    assert repository.read_text("person.md") == raw


def test_gate_returns_physical_readback_receipt_without_second_writer(tmp_path: Path) -> None:
    repository, schema, raw = _build(tmp_path)
    gate = CanonicalMutationGate(repository, schema, None)
    command = _command(raw)
    receipt = gate.execute(
        command,
        lambda target: update_entity(
            repository,
            schema,
            path=target.path,
            expected_id=target.id,
            expected_revision=target.note.metadata["revision"],
            set_metadata={},
            content="Changed.",
            actor=command.actor,
            now=command.now,
        ),
    )
    assert receipt.before_revision == 1
    assert receipt.after_revision == 2
    assert receipt.readback.content == "Changed."
    assert parse_note(repository.read_text("person.md")).content == "Changed."


def test_gate_can_recover_a_readback_receipt_after_a_known_write(tmp_path: Path) -> None:
    repository, schema, raw = _build(tmp_path)
    gate = CanonicalMutationGate(repository, schema, None)
    target = gate.prepare(_command(raw))
    result = update_entity(
        repository,
        schema,
        path=target.path,
        expected_id=target.id,
        expected_revision=1,
        set_metadata={},
        content="Written before later failure.",
        actor="test",
        now=NOW,
    )
    receipt = gate.receipt_after_write(_command(raw), target, result)
    assert receipt.readback.content == "Written before later failure."


def test_gate_create_rechecks_parent_and_returns_a_physical_receipt(tmp_path: Path) -> None:
    repository, schema, raw = _build(tmp_path)
    gate = CanonicalMutationGate(repository, schema, None)
    parent = _command(raw)
    created = gate.execute_create(
        CreateMutationCommand(
            "fake_adapter_created",
            "project-b",
            "project.md",
            "project",
            "request-create",
            "test",
            NOW,
            parent,
        ),
        lambda _parent: create_entity(
            repository,
            schema,
            path="project.md",
            entity_id="project-b",
            metadata={"name": "Project B", "type": "project"},
            content="Created by a generic adapter.",
            actor="test",
            now=NOW,
        ),
    )
    assert created.readback.metadata["id"] == "project-b"
    assert created.readback.metadata["type"] == "project"
    assert created.affected_ids == ("project-b",)


def test_gate_create_rejects_a_stale_parent_before_the_executor(tmp_path: Path) -> None:
    repository, schema, raw = _build(tmp_path)
    gate = CanonicalMutationGate(repository, schema, None)
    parent = _command(raw, expected_revision=2)
    called = False

    def should_not_run(_parent: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("stale parent reached create executor")

    with pytest.raises(CanonicalMutationError, match="STALE_TARGET"):
        gate.execute_create(
            CreateMutationCommand(
                "fake_adapter_created",
                "project-b",
                "project.md",
                "project",
                "request-create",
                "test",
                NOW,
                parent,
            ),
            should_not_run,  # type: ignore[arg-type]
        )
    assert not called
