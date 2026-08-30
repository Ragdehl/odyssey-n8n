#!/usr/bin/env python3
"""Deterministically validate Odyssey's canonical note schema."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
TOP_LEVEL_KEYS = {"schema_version", "metadata_fields", "types"}
REQUIRED_TYPE_FIELDS = {"id", "name", "description", "examples", "properties"}
REQUIRED_FIELD_DEFINITION_FIELDS = {"id", "value_type", "required", "description"}
REQUIRED_TAG_FIELDS = {"id", "description"}


def _validate_optional_filterable(definition: dict[str, Any], location: str) -> None:
    """Validate the optional schema flag that exposes a field to deterministic retrieval."""
    if "filterable" in definition and not isinstance(definition["filterable"], bool):
        raise SchemaValidationError(f"{location} filterable must be boolean")


class SchemaValidationError(ValueError):
    """Raised when the canonical note schema violates its contract."""


def _require_non_empty_string(value: Any, location: str) -> None:
    """Require a meaningful text value in an Odyssey schema definition."""
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{location} must be a non-empty string")


def _validate_subtypes(subtypes: Any, type_id: str) -> None:
    """Validate the controlled subtype definitions belonging to a note type."""
    if not isinstance(subtypes, list):
        raise SchemaValidationError(f"type {type_id!r} subtypes must be an array")
    seen: set[str] = set()
    for index, subtype in enumerate(subtypes):
        location = f"type {type_id!r} subtype at index {index}"
        if not isinstance(subtype, dict):
            raise SchemaValidationError(f"{location} must be an object")
        missing = {"id", "name", "description"} - subtype.keys()
        if missing:
            raise SchemaValidationError(f"{location} missing required fields: {sorted(missing)}")
        subtype_id = subtype["id"]
        if not isinstance(subtype_id, str) or not ID_PATTERN.fullmatch(subtype_id):
            raise SchemaValidationError(f"{location} has invalid id {subtype_id!r}")
        if subtype_id in seen:
            raise SchemaValidationError(f"duplicate subtype id {subtype_id!r} in type {type_id!r}")
        seen.add(subtype_id)
        _require_non_empty_string(subtype["name"], f"{location} name")
        _require_non_empty_string(subtype["description"], f"{location} description")


def _validate_properties(properties: Any, type_id: str) -> None:
    """Validate deterministic domain properties declared for a note type."""
    if not isinstance(properties, list):
        raise SchemaValidationError(f"type {type_id!r} properties must be an array")
    seen: set[str] = set()
    for index, property_definition in enumerate(properties):
        location = f"type {type_id!r} property at index {index}"
        if not isinstance(property_definition, dict):
            raise SchemaValidationError(f"{location} must be an object")
        missing = REQUIRED_FIELD_DEFINITION_FIELDS - property_definition.keys()
        if missing:
            raise SchemaValidationError(f"{location} missing required fields: {sorted(missing)}")
        property_id = property_definition["id"]
        if not isinstance(property_id, str) or not ID_PATTERN.fullmatch(property_id):
            raise SchemaValidationError(f"{location} has invalid id {property_id!r}")
        if property_id in seen:
            raise SchemaValidationError(
                f"duplicate property id {property_id!r} in type {type_id!r}"
            )
        seen.add(property_id)
        _require_non_empty_string(
            property_definition["value_type"], f"property {property_id!r} value_type"
        )
        if not isinstance(property_definition["required"], bool):
            raise SchemaValidationError(f"property {property_id!r} required must be boolean")
        _require_non_empty_string(
            property_definition["description"], f"property {property_id!r} description"
        )
        _validate_optional_filterable(property_definition, location)


def _validate_types(types: Any) -> None:
    """Validate the canonical registry of Odyssey note type definitions."""
    if not isinstance(types, list):
        raise SchemaValidationError("types must be an array")
    seen: set[str] = set()
    for index, note_type in enumerate(types):
        location = f"type at index {index}"
        if not isinstance(note_type, dict):
            raise SchemaValidationError(f"{location} must be an object")
        missing = REQUIRED_TYPE_FIELDS - note_type.keys()
        if missing:
            raise SchemaValidationError(f"{location} missing required fields: {sorted(missing)}")
        type_id = note_type["id"]
        if not isinstance(type_id, str) or not ID_PATTERN.fullmatch(type_id):
            raise SchemaValidationError(f"{location} has invalid id {type_id!r}")
        if type_id in seen:
            raise SchemaValidationError(f"duplicate type id {type_id!r}")
        seen.add(type_id)
        _require_non_empty_string(note_type["name"], f"type {type_id!r} name")
        _require_non_empty_string(note_type["description"], f"type {type_id!r} description")
        examples = note_type["examples"]
        if not isinstance(examples, list) or any(not isinstance(item, str) for item in examples):
            raise SchemaValidationError(f"type {type_id!r} examples must be an array of strings")
        _validate_properties(note_type["properties"], type_id)


def _validate_tags(tags: Any) -> None:
    """Validate the optional top-level tag registry.

    Phase 17E intentionally leaves this registry empty in Core. Keeping the structural hook here
    lets a later explicit extension contract reuse validation without giving Core a built-in
    vocabulary.
    """
    if not isinstance(tags, list):
        raise SchemaValidationError("tags must be an array")
    seen: set[str] = set()
    for index, tag in enumerate(tags):
        location = f"tag at index {index}"
        if not isinstance(tag, dict):
            raise SchemaValidationError(f"{location} must be an object")
        missing = REQUIRED_TAG_FIELDS - tag.keys()
        if missing:
            raise SchemaValidationError(f"{location} missing required fields: {sorted(missing)}")
        tag_id = tag["id"]
        if not isinstance(tag_id, str) or not ID_PATTERN.fullmatch(tag_id):
            raise SchemaValidationError(f"{location} has invalid id {tag_id!r}")
        if tag_id in seen:
            raise SchemaValidationError(f"duplicate tag id {tag_id!r}")
        seen.add(tag_id)
        _require_non_empty_string(tag["description"], f"tag {tag_id!r} description")


def _validate_metadata_fields(metadata_fields: Any) -> None:
    """Validate Odyssey's canonical universal metadata definitions."""
    if not isinstance(metadata_fields, list):
        raise SchemaValidationError("metadata_fields must be an array")
    definitions: dict[str, dict[str, Any]] = {}
    for index, field in enumerate(metadata_fields):
        location = f"metadata field at index {index}"
        if not isinstance(field, dict):
            raise SchemaValidationError(f"{location} must be an object")
        missing = REQUIRED_FIELD_DEFINITION_FIELDS - field.keys()
        if missing:
            raise SchemaValidationError(f"{location} missing required fields: {sorted(missing)}")
        field_id = field["id"]
        if not isinstance(field_id, str) or not ID_PATTERN.fullmatch(field_id):
            raise SchemaValidationError(f"{location} has invalid id {field_id!r}")
        if field_id in definitions:
            raise SchemaValidationError(f"duplicate metadata field id {field_id!r}")
        _require_non_empty_string(field["value_type"], f"metadata field {field_id!r} value_type")
        if not isinstance(field["required"], bool):
            raise SchemaValidationError(f"metadata field {field_id!r} required must be boolean")
        _require_non_empty_string(field["description"], f"metadata field {field_id!r} description")
        _validate_optional_filterable(field, location)
        definitions[field_id] = field

    _validate_architectural_metadata_invariants(definitions)


def _validate_architectural_metadata_invariants(
    definitions: dict[str, dict[str, Any]],
) -> None:
    """Protect the minimum metadata invariants required by Odyssey's Core note model."""
    identity = definitions.get("id")
    if identity is None:
        raise SchemaValidationError("Odyssey metadata must define the id field")
    if identity["required"] is not True:
        raise SchemaValidationError("Odyssey metadata field 'id' must be required")

    note_type = definitions.get("type")
    if note_type is None:
        raise SchemaValidationError("Odyssey metadata must define the type field")
    if note_type["required"] is not True:
        raise SchemaValidationError("Odyssey metadata field 'type' must be required")
    type_constraints = note_type.get("constraints")
    if not isinstance(type_constraints, dict) or not (
        type_constraints.get("registry") == "types" and type_constraints.get("controlled") is True
    ):
        raise SchemaValidationError("type must be controlled by the canonical types registry")

    for field_id in ("created_by", "updated_by"):
        provenance = definitions.get(field_id)
        if provenance is None:
            raise SchemaValidationError(f"Odyssey metadata must define the {field_id} field")
        if provenance["required"] is not True or provenance["value_type"] != "object":
            raise SchemaValidationError(f"{field_id} must be a required object provenance field")

    # Phase 17E deliberately removes `subtype` and `tags` from the active universal metadata.
    # Their registries remain schema-definition hooks only; Core does not require or expose those
    # fields until a real extension use case reintroduces them.


def validate_schema(schema: Any) -> None:
    """Validate that data follows the canonical Odyssey schema-definition contract."""
    if not isinstance(schema, dict):
        raise SchemaValidationError("schema root must be an object")
    missing = TOP_LEVEL_KEYS - schema.keys()
    if missing:
        raise SchemaValidationError(f"missing required top-level keys: {sorted(missing)}")
    unexpected = schema.keys() - TOP_LEVEL_KEYS
    if unexpected:
        raise SchemaValidationError(f"unexpected top-level keys: {sorted(unexpected)}")
    version = schema["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SchemaValidationError("schema_version must be a positive integer")
    _validate_metadata_fields(schema["metadata_fields"])
    _validate_types(schema["types"])


def load_schema(path: Path) -> Any:
    """Load an Odyssey note schema from a JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SchemaValidationError(f"cannot read valid JSON from {path}: {error}") from error


def main() -> int:
    """Validate a requested schema file and report a command-line pass or failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "schema",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "note-schema.json",
    )
    args = parser.parse_args()
    try:
        validate_schema(load_schema(args.schema))
    except SchemaValidationError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {args.schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
