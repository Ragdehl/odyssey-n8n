"""Validate generic Odyssey notes against an explicitly supplied canonical schema."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .model import Note


class NoteValidationError(ValueError):
    """Indicate that one note violates the supplied canonical schema contract."""


def validate_field_value(field_id: str, value: Any, definition: dict[str, Any]) -> None:
    """Validate one schema-declared value against its canonical field definition.

    This is shared by persisted-note validation and pre-persistence planner validation so Odyssey
    keeps one value-semantics implementation for supported metadata/property types.

    Args:
        field_id: Stable metadata/property field identifier used in errors.
        value: Candidate value to check.
        definition: Canonical field or type-property definition.

    Raises:
        NoteValidationError: If the value violates its declared type or constraints.
    """
    value_type = definition.get("value_type")
    if value_type == "string":
        valid_type = isinstance(value, str)
    elif value_type == "integer":
        valid_type = isinstance(value, int) and not isinstance(value, bool)
    elif value_type == "boolean":
        valid_type = isinstance(value, bool)
    elif value_type == "array[string]":
        valid_type = isinstance(value, list) and all(isinstance(item, str) for item in value)
    elif value_type == "date":
        valid_type = isinstance(value, str) and _is_date(value)
    elif value_type == "object":
        valid_type = (
            isinstance(value, dict)
            and set(value) == {"human", "app"}
            and all(
                item is None or (isinstance(item, str) and bool(item.strip()))
                for item in value.values()
            )
            and any(item is not None for item in value.values())
        ) or (isinstance(value, str) and bool(value.strip()))
    else:
        raise NoteValidationError(f"Schema declares unsupported value type for {field_id!r}")
    if not valid_type:
        raise NoteValidationError(f"Metadata field {field_id!r} must be {value_type}")

    constraints = definition.get("constraints", {})
    if constraints.get("non_empty") is True and isinstance(value, str) and not value.strip():
        raise NoteValidationError(f"Metadata field {field_id!r} must not be empty")
    minimum = constraints.get("minimum")
    if minimum is not None and value < minimum:
        raise NoteValidationError(f"Metadata field {field_id!r} must be at least {minimum}")
    if constraints.get("unique_items") is True and len(value) != len(set(value)):
        raise NoteValidationError(f"Metadata field {field_id!r} must contain unique items")
    if value_type == "array[string]" and field_id == "tags":
        if any(
            not item.strip() or "\n" in item or "\r" in item or item != item.strip()
            for item in value
        ):
            raise NoteValidationError(
                "Tags must be non-empty single-line strings without surrounding whitespace"
            )
    if constraints.get("format") == "date-time" and not _is_date_time(value):
        raise NoteValidationError(f"Metadata field {field_id!r} must be a date-time")


def _is_date(value: str) -> bool:
    """Return whether text is a strict ISO calendar date without a time component."""
    if len(value) != 10 or value[4:5] != "-" or value[7:8] != "-":
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _is_date_time(value: Any) -> bool:
    """Return whether text is an ISO date-time with an explicit UTC offset."""
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def validate_note(note: Note, schema: dict[str, Any]) -> None:
    """Validate one isolated note against an already parsed canonical schema.

    This checks only invariants visible in the current note. Historical guarantees,
    such as identity stability and revision progression, require lifecycle context and
    are deliberately outside this validator.
    """
    if not isinstance(note, Note):
        raise NoteValidationError("Expected an Odyssey Note")
    if not isinstance(note.metadata, dict):
        raise NoteValidationError("Note metadata must be a mapping")
    if not isinstance(note.content, str):
        raise NoteValidationError("Note content must be text")
    try:
        universal = {definition["id"]: definition for definition in schema["metadata_fields"]}
        types = {definition["id"]: definition for definition in schema["types"]}
        canonical_version = schema["schema_version"]
    except (KeyError, TypeError):
        raise NoteValidationError("Supplied schema is not a usable canonical schema") from None

    missing_universal = sorted(
        field_id
        for field_id, definition in universal.items()
        if definition.get("required") is True and field_id not in note.metadata
    )
    if missing_universal:
        raise NoteValidationError(f"Missing required metadata: {missing_universal}")

    if any(not isinstance(field_id, str) for field_id in note.metadata):
        raise NoteValidationError("Metadata field IDs must be strings")
    note_type_id = note.metadata.get("type")
    if not isinstance(note_type_id, str):
        raise NoteValidationError("Metadata field 'type' must be string")
    if note_type_id not in types:
        raise NoteValidationError(f"Unknown note type: {note_type_id!r}")
    note_type = types[note_type_id]
    properties = {definition["id"]: definition for definition in note_type["properties"]}
    allowed = universal | properties
    unknown = sorted(set(note.metadata) - set(allowed))
    if unknown:
        raise NoteValidationError(f"Unknown metadata fields for type {note_type_id!r}: {unknown}")
    missing_properties = sorted(
        field_id
        for field_id, definition in properties.items()
        if definition.get("required") is True and field_id not in note.metadata
    )
    if missing_properties:
        raise NoteValidationError(f"Missing required type properties: {missing_properties}")

    for field_id, value in note.metadata.items():
        validate_field_value(field_id, value, allowed[field_id])

    if note.metadata.get("schema_version") != canonical_version:
        raise NoteValidationError(
            "Note schema_version is incompatible with the supplied canonical schema"
        )
