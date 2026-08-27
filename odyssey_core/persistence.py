"""Deterministic persistence of caller-decided canonical Odyssey entities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .notes import Note, parse_note, serialize_note, validate_note
from .storage import VaultRepository

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


def _check_protected_fields(fields: Sequence[str], operation: str) -> None:
    """Reject caller mutations of lifecycle fields.

    Args:
        fields: Metadata keys supplied for a domain mutation.
        operation: Human-readable operation name used in the error.

    Raises:
        ProtectedMetadataError: If any key belongs to Core-managed metadata.
    """
    protected = sorted(set(fields) & _PROTECTED_FIELDS)
    if protected:
        raise ProtectedMetadataError(
            f"{operation} cannot mutate Core-managed metadata: {protected}"
        )


def _validated_existing_note(
    repository: VaultRepository, schema: dict[str, Any], path: str
) -> Note:
    """Read, parse, and validate one existing canonical note before using it.

    Args:
        repository: Authoritative vault repository.
        schema: Parsed canonical note schema.
        path: Vault-relative path to read.

    Returns:
        The validated note represented by the stored Markdown.

    Raises:
        NoteFormatError: If stored Markdown is malformed.
        NoteValidationError: If stored metadata is not canonical.
        VaultRepository errors: If the target cannot be safely read.
    """
    return _parse_and_validate(repository.read_text(path), schema)


def _parse_and_validate(markdown: str, schema: dict[str, Any]) -> Note:
    """Parse and validate Markdown at a persistence boundary."""
    note = parse_note(markdown)
    validate_note(note, schema)
    return note


def _find_duplicate_id(
    repository: VaultRepository, schema: dict[str, Any], entity_id: str
) -> str | None:
    """Find a validated canonical note carrying a stable ID, if one exists.

    Every encountered Markdown note is parsed and validated. Malformed or schema-invalid
    Markdown aborts duplicate inspection; storage errors also propagate rather than weakening
    the check.
    """
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
    actor: str,
    now: str,
) -> EntityPersistenceResult:
    """Create one caller-decided entity as a validated canonical Markdown note.

    Args:
        repository: Authoritative vault repository used for all filesystem access.
        schema: Parsed canonical note schema.
        path: Intended vault-relative Markdown path.
        entity_id: Explicit stable logical entity ID.
        metadata: Domain metadata already decided by the caller.
        content: Exact caller-decided Markdown body.
        actor: Application or process responsible for the operation.
        now: Explicit lifecycle timestamp in canonical date-time form.

    Returns:
        A ``CREATED`` result with the stable ID, path, and revision ``1``.

    Raises:
        EntityAlreadyExistsError: If the stable ID exists in another canonical note.
        ProtectedMetadataError: If metadata attempts to supply lifecycle fields.
        NoteFormatError or NoteValidationError: If the resulting note is invalid.
        VaultRepository errors: If the path or storage operation is unsafe or unavailable.
    """
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    _check_protected_fields(metadata.keys(), "create_entity")
    if _find_duplicate_id(repository, schema, entity_id) is not None:
        raise EntityAlreadyExistsError(f"Entity ID already exists: {entity_id}")

    complete_metadata = dict(metadata)
    complete_metadata.update(
        {
            "id": entity_id,
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
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
    actor: str,
    now: str,
) -> EntityPersistenceResult:
    """Apply an explicit metadata/body mutation to one expected canonical entity.

    ``content=None`` preserves the existing body exactly; a string replaces it exactly. No
    semantic Markdown merge or inferred property change occurs.

    Args:
        repository: Authoritative vault repository used for all filesystem access.
        schema: Parsed canonical note schema.
        path: Physical vault-relative Markdown path to update.
        expected_id: Stable ID required in the existing note at ``path``.
        expected_revision: Optional authoritative revision observed by the caller before planning.
            A different current revision fails closed before any replacement is attempted.
        set_metadata: Explicit domain properties to add or replace.
        remove_metadata: Explicit domain properties to remove.
        content: Optional exact replacement body.
        actor: Application or process responsible for the update.
        now: Explicit lifecycle timestamp in canonical date-time form.

    Returns:
        ``UPDATED`` with the incremented revision, or ``NO_CHANGE`` without writing.

    Raises:
        EntityIdentityMismatchError: If the loaded note ID differs from ``expected_id``.
        EntityRevisionMismatchError: If ``expected_revision`` differs from the current note revision.
        ProtectedMetadataError: If the mutation attempts to alter lifecycle fields.
        NoteFormatError or NoteValidationError: If existing or resulting Markdown is invalid.
        VaultRepository errors: If the target cannot be safely read or replaced.
    """
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
            "updated_by": actor,
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
    actor: str,
    now: str,
) -> EntityPersistenceResult:
    """Persist a complete active-note type migration at the same path and stable identity.

    Args:
        repository: Authoritative Markdown repository.
        schema: Active canonical schema.
        path: Existing vault-relative Markdown path retained by the migration.
        expected_id: Stable source and destination identity.
        expected_revision: Revision observed while staging the destination.
        destination: Complete validated destination representation before update lifecycle fields.
        actor: Lifecycle updater identity.
        now: Canonical update timestamp.

    Returns:
        A ``MIGRATED`` result with exactly one incremented revision.

    Raises:
        EntityIdentityMismatchError: If source/destination identities differ.
        EntityRevisionMismatchError: If source revision changed.
        ProtectedMetadataError: If protected identity or creation lifecycle changed.
    """
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
    metadata.update({"updated_at": now, "updated_by": actor, "revision": expected_revision + 1})
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
    actor: str,
    now: str,
) -> EntityPersistenceResult:
    """Retire one active entity while preserving its canonical Markdown and identity.

    Args:
        repository: Authoritative vault repository used for all filesystem access.
        schema: Parsed canonical note schema.
        path: Physical vault-relative Markdown path to retire without moving it.
        expected_id: Stable ID required in the existing note at ``path``.
        expected_revision: Authoritative revision observed before the delete decision.
        actor: Application identity recorded as the lifecycle updater.
        now: Explicit lifecycle timestamp in canonical date-time form.

    Returns:
        A ``DELETED`` result with the same stable ID and path and an incremented revision.

    Raises:
        EntityIdentityMismatchError: If the path no longer contains ``expected_id``.
        EntityRevisionMismatchError: If the note changed after target resolution.
        NoteValidationError: If the existing or resulting note is not canonical.
        VaultRepository errors: If the target cannot be safely read or replaced.
    """
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
        {"deleted": True, "updated_at": now, "updated_by": actor, "revision": expected_revision + 1}
    )
    updated = Note(metadata=metadata, content=existing.content)
    validate_note(updated, schema)
    repository.replace_text(path, serialize_note(updated))
    return EntityPersistenceResult(
        PersistenceOperation.DELETED, expected_id, path, expected_revision + 1
    )
