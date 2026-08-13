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
REQUIRED_METADATA_FIELDS = {
    "id", "type", "created_at", "updated_at", "created_by", "updated_by",
    "revision", "schema_version",
}
OPTIONAL_METADATA_FIELDS = {"subtype", "aliases"}
REQUIRED_TYPE_FIELDS = {"id", "name", "description", "examples", "subtypes"}
REQUIRED_METADATA_DEFINITION_FIELDS = {"id", "value_type", "required", "description"}


class SchemaValidationError(ValueError):
    """Raised when the canonical note schema violates its contract."""


def _require_non_empty_string(value: Any, location: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{location} must be a non-empty string")


def _validate_subtypes(subtypes: Any, type_id: str) -> None:
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


def _validate_types(types: Any) -> None:
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
        _validate_subtypes(note_type["subtypes"], type_id)


def _validate_metadata_fields(metadata_fields: Any) -> None:
    if not isinstance(metadata_fields, list):
        raise SchemaValidationError("metadata_fields must be an array")
    definitions: dict[str, dict[str, Any]] = {}
    for index, field in enumerate(metadata_fields):
        location = f"metadata field at index {index}"
        if not isinstance(field, dict):
            raise SchemaValidationError(f"{location} must be an object")
        missing = REQUIRED_METADATA_DEFINITION_FIELDS - field.keys()
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
        definitions[field_id] = field

    missing = REQUIRED_METADATA_FIELDS - definitions.keys()
    if missing:
        raise SchemaValidationError(f"missing required canonical metadata fields: {sorted(missing)}")
    unexpected = definitions.keys() - REQUIRED_METADATA_FIELDS - OPTIONAL_METADATA_FIELDS
    if unexpected:
        raise SchemaValidationError(f"unexpected canonical metadata fields: {sorted(unexpected)}")
    for field_id in REQUIRED_METADATA_FIELDS:
        if definitions[field_id]["required"] is not True:
            raise SchemaValidationError(f"canonical metadata field {field_id!r} must be required")
    for field_id in OPTIONAL_METADATA_FIELDS:
        if field_id in definitions and definitions[field_id]["required"] is not False:
            raise SchemaValidationError(f"canonical metadata field {field_id!r} must be optional")

    type_constraints = definitions["type"].get("constraints")
    if not isinstance(type_constraints, dict) or not (
        type_constraints.get("registry") == "types" and type_constraints.get("controlled") is True
    ):
        raise SchemaValidationError("type must be controlled by the canonical types registry")

    subtype = definitions.get("subtype")
    if subtype is None:
        raise SchemaValidationError("controlled subtype policy requires the optional subtype field")
    subtype_constraints = subtype.get("constraints")
    expected = {
        "registry": "types[].subtypes", "parent_field": "type",
        "controlled": True, "allow_unregistered": False,
    }
    if not isinstance(subtype_constraints, dict) or any(
        subtype_constraints.get(key) != value for key, value in expected.items()
    ):
        raise SchemaValidationError(
            "subtype must be optional, controlled by its parent type registry, and disallow unregistered values"
        )


def validate_schema(schema: Any) -> None:
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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SchemaValidationError(f"cannot read valid JSON from {path}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "schema", nargs="?", type=Path,
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
