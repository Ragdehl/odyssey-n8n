"""Deterministic Phase 22D authenticated human provenance coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core import (
    AuthenticatedActorContext,
    PersistenceOperation,
    create_entity,
    migrate_entity,
    soft_delete_entity,
    update_entity,
)
from odyssey_core.notes import Note, parse_note
from odyssey_core.persistence import normalize_actor_provenance
from odyssey_core.storage import VaultRepository
from odyssey_runtime.composition import _persistence_actor

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
APP = "odyssey-runtime"
USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def repository(tmp_path: Path) -> VaultRepository:
    """Provide a disposable canonical vault for lifecycle provenance tests."""
    (tmp_path / "people").mkdir()
    return VaultRepository(tmp_path)


def actor(user_id: str) -> dict[str, str]:
    """Build the same named actor shape produced by the runtime composition."""
    return _persistence_actor(APP, AuthenticatedActorContext(user_id))  # type: ignore[return-value]


def create_person(
    repository: VaultRepository,
    *,
    entity_id: str = "person-edgar",
    path: str = "people/edgar.md",
    name: str = "Edgar",
    provenance: object = "legacy-test-app",
) -> None:
    """Create one synthetic person note with caller-selected provenance."""
    create_entity(
        repository,
        SCHEMA,
        path=path,
        entity_id=entity_id,
        metadata={"name": name, "type": "person"},
        content=f"# {name}\n",
        actor=provenance,  # type: ignore[arg-type]
        now="2026-09-12T10:00:00+02:00",
    )


def metadata(repository: VaultRepository, path: str = "people/edgar.md") -> dict:
    """Read parsed metadata from one synthetic note."""
    return parse_note(repository.read_text(path)).metadata


def test_authenticated_create_sets_human_and_app_provenance(
    repository: VaultRepository,
) -> None:
    """Authenticated CREATE records the Odyssey user without requiring a binding."""
    create_person(repository, provenance=actor(USER_A))
    note_metadata = metadata(repository)
    expected = {"human": USER_A, "app": APP}
    assert note_metadata["created_by"] == expected
    assert note_metadata["updated_by"] == expected


def test_authenticated_update_preserves_creation_and_updates_current_human(
    repository: VaultRepository,
) -> None:
    """UPDATE preserves the creator while attributing the current authenticated updater."""
    create_person(repository, provenance=actor(USER_A))
    result = update_entity(
        repository,
        SCHEMA,
        path="people/edgar.md",
        expected_id="person-edgar",
        set_metadata={"aliases": ["E"]},
        actor=actor(USER_B),
        now="2026-09-12T11:00:00+02:00",
    )
    assert result.operation is PersistenceOperation.UPDATED
    note_metadata = metadata(repository)
    assert note_metadata["created_by"] == {"human": USER_A, "app": APP}
    assert note_metadata["updated_by"] == {"human": USER_B, "app": APP}


def test_app_only_actor_keeps_human_null(repository: VaultRepository) -> None:
    """Legacy autonomous callers retain the app-only compatibility behavior."""
    create_person(repository)
    note_metadata = metadata(repository)
    assert note_metadata["created_by"] == {"human": None, "app": "legacy-test-app"}
    assert note_metadata["updated_by"] == {"human": None, "app": "legacy-test-app"}


def test_runtime_actor_construction_keeps_users_distinct_and_does_not_need_binding() -> None:
    """Only the Odyssey user ID enters human provenance; binding state is not consulted."""
    context_a = AuthenticatedActorContext(USER_A)
    context_b = AuthenticatedActorContext(USER_B)
    assert _persistence_actor(APP, context_a) == {"human": USER_A, "app": APP}
    assert _persistence_actor(APP, context_b) == {"human": USER_B, "app": APP}
    assert _persistence_actor(APP, None) == {"human": None, "app": APP}
    forbidden = {"person-note-id", "external-subject", "edgar@example.invalid"}
    assert not forbidden.intersection(_persistence_actor(APP, context_a).values())


def test_no_change_preserves_existing_provenance(repository: VaultRepository) -> None:
    """A semantic no-op does not create a provenance-only revision."""
    create_person(repository, provenance=actor(USER_A))
    before = repository.read_text("people/edgar.md")
    result = update_entity(
        repository,
        SCHEMA,
        path="people/edgar.md",
        expected_id="person-edgar",
        set_metadata={},
        actor=actor(USER_B),
        now="2026-09-12T12:00:00+02:00",
    )
    assert result.operation is PersistenceOperation.NO_CHANGE
    assert repository.read_text("people/edgar.md") == before


def test_delete_uses_authenticated_updated_provenance(repository: VaultRepository) -> None:
    """DELETE preserves creation attribution and records the current authenticated updater."""
    create_person(repository, provenance=actor(USER_A))
    result = soft_delete_entity(
        repository,
        SCHEMA,
        path="people/edgar.md",
        expected_id="person-edgar",
        expected_revision=1,
        actor=actor(USER_B),
        now="2026-09-12T13:00:00+02:00",
    )
    assert result.operation is PersistenceOperation.DELETED
    note_metadata = metadata(repository)
    assert note_metadata["created_by"] == {"human": USER_A, "app": APP}
    assert note_metadata["updated_by"] == {"human": USER_B, "app": APP}


def test_migration_uses_authenticated_updated_provenance(repository: VaultRepository) -> None:
    """TYPE migration follows the same creation/update provenance lifecycle."""
    create_person(repository, provenance=actor(USER_A))
    existing = parse_note(repository.read_text("people/edgar.md"))
    destination = Note(metadata={**existing.metadata, "type": "project"}, content=existing.content)
    result = migrate_entity(
        repository,
        SCHEMA,
        path="people/edgar.md",
        expected_id="person-edgar",
        expected_revision=1,
        destination=destination,
        actor=actor(USER_B),
        now="2026-09-12T14:00:00+02:00",
    )
    assert result.operation is PersistenceOperation.MIGRATED
    note_metadata = metadata(repository)
    assert note_metadata["created_by"] == {"human": USER_A, "app": APP}
    assert note_metadata["updated_by"] == {"human": USER_B, "app": APP}


def test_normalization_never_accepts_provider_or_person_identifiers_as_special_human_fields() -> (
    None
):
    """The existing named actor contract carries only normalized human/app values."""
    assert normalize_actor_provenance({"human": USER_A, "app": APP}) == {
        "human": USER_A,
        "app": APP,
    }
    with pytest.raises(TypeError):
        normalize_actor_provenance({"human": USER_A, "app": APP, "subject": "external"})
