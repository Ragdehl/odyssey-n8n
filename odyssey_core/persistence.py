"""Deterministic persistence of caller-decided canonical Odyssey entities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeAlias

from .notes import Note, parse_note, serialize_note, validate_note
from .storage import VaultRepository

ActorInput: TypeAlias = str | Sequence[str | None]

_PROTECTED_FIELDS = frozenset(
    {
        "id",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
        "revision",
        "schema_version",
        "deleted",
    }
)


class PersistenceOperation(StrEnum):
    """Operation outcomes returned by entity persistence."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    NO_CHANGE = "NO_CHANGE"
    DELETED = "DELETED"
    MIGRATED = "MIGRATED"


@dataclass(frozen=True, slots=True)
class EntityPersistenceResult:
    """Describe the deterministic result of one entity persistence operation."""

    operation: PersistenceOperation
    id: str
    path: str
    revision: int


class EntityAlreadyExistsError(OSError):
    """Indicate that a stable entity ID already exists in a canonical note."""


class ProtectedMetadataError(ValueError):
    """Indicate that a caller attempted to mutate Core-managed metadata."""


class EntityIdentityMismatchError(ValueError):
    """Indicate that an update path does not contain its expected stable ID."""


class EntityRevisionMismatchError(ValueError):
    """Indicate that an entity changed after a caller read its authoritative revision."""


def normalize_actor_provenance(actor: ActorInput) -> list[str | None]:
    """Normalize caller provenance to canonical ``[human, app]`` metadata.

    A legacy non-empty string is temporarily accepted as an app-only actor so existing internal
    callers can migrate incrementally. New callers should pass a two-item sequence where position 0
    is the stable human user ID (or ``None``) and position 1 is the stable app/capability ID (or
    ``None``). At least one position must be present.
    """
    if isinstance(actor, str):
        value = actor.strip()
        if not value:
            raise TypeError("actor string must be non-empty")
        return [None, value]
    if isinstance(actor, (bytes, bytearray, memoryview)) or not isinstance(actor, Sequence):
        raise TypeError("actor must be a non-empty app string or a [human, app] pair")
    values = list(actor)
    if len(values) != 2:
        raise TypeError("actor pair must contain exactly [human, app]")
    normalized: list[str | None] = []
    for value in values:
        if value is None:
            normalized.append(None)
        elif isinstance(value, str) and value.strip():
            normalized.append(value.strip())
        else:
            raise TypeError("actor pair values must be non-empty strings or None")
    if normalized == [None, None]:
        raise TypeError("actor pair must identify a human, an app, or both")
    return normalized


def _check_protected_fields(fields: Sequence[str], operation: str) -> None:
    """Reject caller mutations of lifecycle fields."""
    protected = sorted(set(fields) & _PROTECTED_FIELDS)
    if protected:
        raise ProtectedMetadataError(
            f"{operation} cannot mutate Core-managed metadata: {protected}"
        )


def _validated_existing_note(
    repository: VaultRepository, schema: dict[str, Any], path: str
) -> Note:
    """Read, parse, and validate one existing canonical note before using it."""
    return _parse_and_validate(repository.read_text(path), schema)


def _parse_and_validate(markdown: str, schema: dict[str, Any]) -> Note:
    """Parse and validate Markdown at a persistence boundary."""
    note = parse_note(markdown)
    validate_note(note, schema)
    return note


def _find_duplicate_id(
    repository: VaultRepository, schema: dict[str, Any], entity_id: str
) -> str | None:
    """Find a validated canonical note carrying a stable ID, if one exists."""
    for path in repository.list_markdown_paths():
        note = _parse_and_validate(repository.read_text(path), schema)
        if note.metadata.get("id") == entity_id:
            return path
    return None


def create_entity(
    repository: VaultRepository,
    schema: dict[str, Any],
    *,
    path: str,
    entity_id: str,
    metadata: Mapping[str, Any],
    content: str,
    actor: ActorInput,
    now: str,
) -> EntityPersistenceResult:
    """Create one caller-decided entity as a validated canonical Markdown note."""
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    _check_protected_fields(metadata.keys(), "create_entity")
    if _find_duplicate_id(repository, schema, entity_id) is not None:
        raise EntityAlreadyExistsError(f"Entity ID already exists: {entity_id}")

    provenance = normalize_actor_provenance(actor)
    complete_metadata = dict(metadata)
    complete_metadata.update(
        {
            "id": entity_id,
            "created_at": now,
            "updated_at": now,
            "created_by": provenance,
            "updated_by": provenance.copy(),
            "revision": 1,
            "schema_version": schema["schema_version"],
        }
    )
    note = Note(metadata=complete_metadata, content=content)
    validate_note(note, schema)
    repository.create_text(path, serialize_note(note))
    return EntityPersistenceResult(PersistenceOperation.CREATED, entity_id, path, 1)


def update_entity(
    repository: VaultRepository,
    schema: dict[str, Any],
    *,
    path: str,
    expected_id: str,
    expected_revision: int | None = None,
    set_metadata: Mapping[str, Any],
    remove_metadata: Sequence[str] = (),
    content: str | None = None,
    actor: ActorInput,
    now: str,
) -> EntityPersistenceResult:
    """Apply an explicit metadata/body mutation to one expected canonical entity."""
    if not isinstance(set_metadata, Mapping):
        raise TypeError("set_metadata must be a mapping")
    if expected_revision is not None and (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 1
    ):
        raise TypeError("expected_revision must be a positive integer or None")
    if isinstance(remove_metadata, (str, bytes, bytearray, memoryview)):
        raise TypeError("remove_metadata must be a sequence of strings")
    if any(not isinstance(field_id, str) for field_id in remove_metadata):
        raise TypeError("remove_metadata must contain only strings")
    remove_fields = tuple(remove_metadata)
    _check_protected_fields(set_metadata.keys(), "update_entity")
    _check_protected_fields(remove_fields, "update_entity")
    if "type" in set_metadata or "type" in remove_fields:
        raise ProtectedMetadataError("update_entity cannot mutate canonical type")
    if set(set_metadata) & set(remove_fields):
        raise ValueError("A metadata field cannot be both set and removed")

    existing = _validated_existing_note(repository, schema, path)
    if existing.metadata.get("id") != expected_id:
        raise EntityIdentityMismatchError(f"Expected entity ID at path {path!r}")
    if expected_revision is not None and existing.metadata.get("revision") != expected_revision:
        raise EntityRevisionMismatchError(f"Expected entity revision at path {path!r}")

    metadata = dict(existing.metadata)
    metadata.update(set_metadata)
    for field_id in remove_fields:
        metadata.pop(field_id, None)
    resulting_content = existing.content if content is None else content
    if metadata == existing.metadata and resulting_content == existing.content:
        return EntityPersistenceResult(
            PersistenceOperation.NO_CHANGE, expected_id, path, existing.metadata["revision"]
        )

    metadata.update(
        {
            "updated_at": now,
            "updated_by": normalize_actor_provenance(actor),
            "revision": existing.metadata["revision"] + 1,
        }
    )
    updated = Note(metadata=metadata, content=resulting_content)
    validate_note(updated, schema)
    repository.replace_text(path, serialize_note(updated))
    return EntityPersistenceResult(
        PersistenceOperation.UPDATED, expected_id, path, updated.metadata["revision"]
    )


def migrate_entity(
    repository: VaultRepository,
    schema: dict[str, Any],
    *,
    path: str,
    expected_id: str,
    expected_revision: int,
    destination: Note,
    actor: ActorInput,
    now: str,
) -> EntityPersistenceResult:
    """Persist a complete active-note type migration at the same path and stable identity."""
    if not isinstance(destination, Note):
        raise TypeError("destination must be a Note")
    existing = _validated_existing_note(repository, schema, path)
    if existing.metadata.get("id") != expected_id or destination.metadata.get("id") != expected_id:
        raise EntityIdentityMismatchError(f"Expected entity ID at path {path!r}")
    if existing.metadata.get("revision") != expected_revision:
        raise EntityRevisionMismatchError(f"Expected entity revision at path {path!r}")
    if existing.metadata.get("deleted") is True:
        raise ValueError("Cannot migrate a deleted entity")
    protected = ("id", "name", "created_at", "created_by", "schema_version", "deleted")
    if any(destination.metadata.get(key) != existing.metadata.get(key) for key in protected):
        raise ProtectedMetadataError("migrate_entity cannot alter identity or creation lifecycle")
    if destination.metadata.get("type") == existing.metadata.get("type"):
        raise ValueError("Migration requires a different canonical type")
    validate_note(destination, schema)
    metadata = dict(destination.metadata)
    metadata.update(
        {
            "updated_at": now,
            "updated_by": normalize_actor_provenance(actor),
            "revision": expected_revision + 1,
        }
    )
    updated = Note(metadata=metadata, content=destination.content)
    validate_note(updated, schema)
    repository.replace_text(path, serialize_note(updated))
    return EntityPersistenceResult(
        PersistenceOperation.MIGRATED, expected_id, path, expected_revision + 1
    )


def soft_delete_entity(
    repository: VaultRepository,
    schema: dict[str, Any],
    *,
    path: str,
    expected_id: str,
    expected_revision: int,
    actor: ActorInput,
    now: str,
) -> EntityPersistenceResult:
    """Retire one active entity while preserving its canonical Markdown and identity."""
    if (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 1
    ):
        raise TypeError("expected_revision must be a positive integer")
    existing = _validated_existing_note(repository, schema, path)
    if existing.metadata.get("id") != expected_id:
        raise EntityIdentityMismatchError(f"Expected entity ID at path {path!r}")
    if existing.metadata.get("revision") != expected_revision:
        raise EntityRevisionMismatchError(f"Expected entity revision at path {path!r}")
    if existing.metadata.get("deleted") is True:
        return EntityPersistenceResult(
            PersistenceOperation.NO_CHANGE, expected_id, path, expected_revision
        )
    metadata = dict(existing.metadata)
    metadata.update(
        {
            "deleted": True,
            "updated_at": now,
            "updated_by": normalize_actor_provenance(actor),
            "revision": expected_revision + 1,
        }
    )
    updated = Note(metadata=metadata, content=existing.content)
    validate_note(updated, schema)
    repository.replace_text(path, serialize_note(updated))
    return EntityPersistenceResult(
        PersistenceOperation.DELETED, expected_id, path, expected_revision + 1
    )
