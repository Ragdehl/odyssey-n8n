"""Deterministic tests for Odyssey-owned user to canonical person bindings."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from odyssey_core.identity_boundary import (
    OdysseyUser,
    SelfBindingConflictError,
    SelfBindingError,
    SelfBindingRepository,
)
from odyssey_core.notes import Note, serialize_note
from odyssey_core.storage import VaultRepository

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "config" / "note-schema.json").read_text(
        encoding="utf-8"
    )
)


def _note(
    vault: VaultRepository,
    path: str,
    note_id: str,
    note_type: str = "person",
    deleted: bool = False,
) -> None:
    """Write one schema-valid synthetic note fixture."""
    metadata = {
        "id": note_id,
        "name": Path(path).stem,
        "type": note_type,
        "created_at": "2026-09-12T10:00:00+02:00",
        "updated_at": "2026-09-12T10:00:00+02:00",
        "created_by": {"human": None, "app": "test"},
        "updated_by": {"human": None, "app": "test"},
        "revision": 1,
        "schema_version": 3,
    }
    if deleted:
        metadata["deleted"] = True
    vault.create_text(path, serialize_note(Note(metadata=metadata, content="# Synthetic")))


@pytest.fixture
def binding_setup(tmp_path: Path) -> tuple[SelfBindingRepository, VaultRepository, Path]:
    """Provide isolated state and a synthetic canonical vault."""
    vault_path = tmp_path / "vault"
    state_path = tmp_path / "state"
    vault_path.mkdir()
    state_path.mkdir()
    (vault_path / "people").mkdir()
    (vault_path / "other").mkdir()
    vault = VaultRepository(vault_path)
    _note(vault, "people/alpha.md", "person-alpha")
    _note(vault, "people/beta.md", "person-beta")
    return SelfBindingRepository(state_path, vault, SCHEMA), vault, state_path


def test_create_and_repeat_binding_is_idempotent(
    binding_setup: tuple[SelfBindingRepository, VaultRepository, Path],
) -> None:
    """Create one binding and accept an exact repeated bind without changing state."""
    repository, _, state = binding_setup
    user = OdysseyUser.new().stable_user_id

    first = repository.bind(user, "person-alpha")
    second = repository.bind(user, "person-alpha")

    assert first == second == repository.resolve(user)
    assert set(json.loads((state / "self-bindings.json").read_text())["bindings"][0]) == {
        "odyssey_user_id",
        "person_note_id",
    }
    assert (state / "self-bindings.json").stat().st_mode & 0o077 == 0


def test_conflict_requires_compare_and_swap_rebind(
    binding_setup: tuple[SelfBindingRepository, VaultRepository, Path],
) -> None:
    """Never silently replace a user binding and require the exact previous target to rebind."""
    repository, _, _ = binding_setup
    user = OdysseyUser.new().stable_user_id
    repository.bind(user, "person-alpha")

    with pytest.raises(SelfBindingConflictError):
        repository.bind(user, "person-beta")
    with pytest.raises(SelfBindingError, match="compare-and-swap"):
        repository.rebind(user, "wrong-person", "person-beta")
    assert repository.rebind(user, "person-alpha", "person-beta").person_note_id == "person-beta"


def test_two_users_and_renamed_note_keep_distinct_stable_bindings(
    binding_setup: tuple[SelfBindingRepository, VaultRepository, Path],
) -> None:
    """Use stable IDs rather than similar names or filenames for independent users."""
    repository, vault, _ = binding_setup
    first = OdysseyUser.new().stable_user_id
    second = OdysseyUser.new().stable_user_id
    repository.bind(first, "person-alpha")
    repository.bind(second, "person-beta")

    os.rename(vault.root / "people/alpha.md", vault.root / "people/Renamed Alpha.md")

    assert repository.resolve(first).person_note_id == "person-alpha"
    assert repository.resolve(second).person_note_id == "person-beta"


@pytest.mark.parametrize(
    ("note_id", "note_type", "deleted"),
    [("missing", "person", False), ("person-deleted", "person", True), ("store", "store", False)],
)
def test_invalid_person_targets_fail_closed(
    binding_setup: tuple[SelfBindingRepository, VaultRepository, Path],
    note_id: str,
    note_type: str,
    deleted: bool,
) -> None:
    """Reject missing, deleted, and non-person target notes."""
    repository, vault, _ = binding_setup
    if note_id != "missing":
        _note(vault, f"other/{note_id}.md", note_id, note_type, deleted)

    with pytest.raises(SelfBindingError):
        repository.bind(OdysseyUser.new().stable_user_id, note_id)


def test_malformed_and_duplicate_state_fail_closed(
    binding_setup: tuple[SelfBindingRepository, VaultRepository, Path],
) -> None:
    """Reject malformed records and duplicate users rather than repairing identity state."""
    repository, _, state = binding_setup
    user = OdysseyUser.new().stable_user_id
    path = state / "self-bindings.json"
    path.write_text(
        json.dumps(
            {
                "format": "odyssey_self_bindings",
                "format_version": 1,
                "bindings": [
                    {"odyssey_user_id": user, "person_note_id": "person-alpha"},
                    {"odyssey_user_id": user, "person_note_id": "person-beta"},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SelfBindingError):
        repository.resolve(user)


def test_provider_identity_is_not_present_in_self_binding_state(
    binding_setup: tuple[SelfBindingRepository, VaultRepository, Path],
) -> None:
    """Keep provider identity in the separate principal map, never in self-binding state."""
    repository, _, state = binding_setup
    user = OdysseyUser.new().stable_user_id
    repository.bind(user, "person-alpha")

    serialized = (state / "self-bindings.json").read_text(encoding="utf-8")
    assert "issuer" not in serialized
    assert "subject" not in serialized
    assert "email" not in serialized
