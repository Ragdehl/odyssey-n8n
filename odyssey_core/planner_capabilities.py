"""Schema-derived capabilities supplied to an Odyssey request planner."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from odyssey_core.filtering import supported_filter_operators

LIMITATIONS = {
    "not_supported": "An exact exclusion / NOT condition cannot currently be represented deterministically.",
    "unsupported_domain_date": "The requested non-lifecycle/domain-event date has no canonical deterministic field.",
    "direct_link_not_filterable": "An exact direct wikilink relation cannot currently be filtered deterministically.",
}
_EXCLUDED_FIELDS = {"subtype"}
_SUPPORTED_WRITE_VALUE_TYPES = {"string", "integer", "array[string]", "date"}
_SUPPORTED_WRITE_CONSTRAINTS = {"non_empty", "minimum", "unique_items", "format"}
_SUPPORTED_WRITE_FORMATS = {"date-time"}


def build_planner_capabilities(
    schema: Mapping[str, Any], *, current_context: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Project canonical note-schema data into planner-safe retrieval capabilities.

    Args:
        schema: Parsed canonical Odyssey note schema.
        current_context: Optional runtime date, time, and timezone visible to the planner.

    Returns:
        Canonical types, filter capabilities, limitation meanings, and optional current context.

    Raises:
        ValueError: If required schema retrieval data is missing or malformed.

    Example:
        ``build_planner_capabilities(schema)["filters"]["created_at"]["value_type"]``
        returns ``"date-time"``.
    """
    try:
        types = list(schema["types"])
        metadata_fields = list(schema["metadata_fields"])
        type_field = next(field for field in metadata_fields if field["id"] == "type")
    except (KeyError, StopIteration, TypeError) as error:
        raise ValueError("Canonical schema has unusable planner capability data") from error

    type_ids = [item["id"] for item in types]
    capabilities: dict[str, Any] = {
        "types": {
            item["id"]: {
                "description": item["description"],
                "examples": item["examples"],
                "retrieval_guidance": type_field.get("retrieval_guidance", ""),
                "retrieval_examples": type_field.get("retrieval_examples", []),
            }
            for item in types
        },
        "filters": {
            "type": {
                "value_type": "string",
                "operators": ["eq", "in"],
                "controlled_values": type_ids,
                "applies_to": type_ids,
                "description": type_field["description"],
                "retrieval_guidance": type_field.get("retrieval_guidance", ""),
                "retrieval_examples": type_field.get("retrieval_examples", []),
            }
        },
        "limitations": LIMITATIONS,
    }
    filters = capabilities["filters"]
    for field in metadata_fields:
        if field.get("filterable") and field["id"] not in {"type", *_EXCLUDED_FIELDS}:
            capability = _filter_capability(field, type_ids)
            if field["id"] == "tags":
                capability["controlled_values"] = _controlled_tag_ids(schema)
            filters[field["id"]] = capability
    for note_type in types:
        for field in note_type["properties"]:
            if field.get("filterable"):
                _merge_filter_capability(filters, field, note_type["id"])
    if current_context is not None:
        if set(current_context) != {"date", "time", "timezone"}:
            raise ValueError("Planner current context must contain date, time, and timezone")
        capabilities["current_context"] = dict(current_context)
    return capabilities


def _controlled_tag_ids(schema: Mapping[str, Any]) -> list[str]:
    """Return the canonical controlled tag registry for planner restrictions.

    Args:
        schema: Parsed canonical Odyssey note schema.

    Returns:
        Deterministically ordered controlled tag IDs.

    Raises:
        ValueError: If the controlled tag registry is absent, malformed, or duplicated.
    """
    try:
        tag_ids = [tag["id"] for tag in schema["tags"]]
    except (KeyError, TypeError) as error:
        raise ValueError("Canonical schema has unusable controlled tags") from error
    if (
        not tag_ids
        or len(tag_ids) != len(set(tag_ids))
        or not all(isinstance(tag_id, str) and tag_id.strip() for tag_id in tag_ids)
    ):
        raise ValueError("Canonical schema has unusable controlled tags")
    return sorted(tag_ids)


def build_write_capabilities(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Project canonical note types and writable properties into a planner-safe contract.

    The projection is intentionally generic: production code must not name concrete note types or
    property IDs. New types/properties flow through automatically when their value-type and constraint
    semantics are already supported by Core.

    Args:
        schema: Parsed canonical Odyssey note schema.

    Returns:
        Canonical type descriptions/examples and their schema-declared writable properties.

    Raises:
        ValueError: If the schema is malformed or declares unsupported property semantics.
    """
    try:
        types = list(schema["types"])
    except (KeyError, TypeError) as error:
        raise ValueError("Canonical schema has unusable write capability data") from error

    projected: dict[str, Any] = {"types": {}}
    for note_type in types:
        try:
            type_id = note_type["id"]
            description = note_type["description"]
            examples = list(note_type["examples"])
            properties = list(note_type["properties"])
        except (KeyError, TypeError) as error:
            raise ValueError("Canonical schema has unusable write capability data") from error
        write_properties: dict[str, Any] = {}
        for field in properties:
            capability = _write_property_capability(field)
            field_id = field["id"]
            if field_id in write_properties:
                raise ValueError(f"Canonical type {type_id!r} duplicates property {field_id!r}")
            write_properties[field_id] = capability
        projected["types"][type_id] = {
            "description": description,
            "examples": examples,
            "properties": write_properties,
        }
    if not projected["types"]:
        raise ValueError("Canonical schema exposes no writable note types")
    return projected


def _merge_filter_capability(
    filters: dict[str, Any], field: Mapping[str, Any], note_type: str
) -> None:
    """Merge one type-specific filter field without silently overwriting another type."""
    field_id = field["id"]
    candidate = _filter_capability(field, [note_type])
    existing = filters.get(field_id)
    if existing is None:
        filters[field_id] = candidate
        return
    existing_semantics = {key: value for key, value in existing.items() if key != "applies_to"}
    candidate_semantics = {key: value for key, value in candidate.items() if key != "applies_to"}
    if existing_semantics != candidate_semantics:
        raise ValueError(f"Schema declares conflicting filter field: {field_id!r}")
    existing["applies_to"] = list(dict.fromkeys([*existing["applies_to"], note_type]))


def _filter_capability(field: Mapping[str, Any], applies_to: list[str]) -> dict[str, Any]:
    """Convert one filterable schema field into its deterministic planner contract."""
    value_type = field.get("constraints", {}).get("format", field["value_type"])
    return {
        "value_type": value_type,
        "operators": list(supported_filter_operators(field)),
        "controlled_values": [],
        "applies_to": applies_to,
        "description": field["description"],
        "retrieval_guidance": field.get("retrieval_guidance", ""),
        "retrieval_examples": field.get("retrieval_examples", []),
    }


def _write_property_capability(field: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one type-specific property into the generic write-planning contract."""
    try:
        field_id = field["id"]
        value_type = field["value_type"]
        required = field["required"]
        description = field["description"]
    except (KeyError, TypeError) as error:
        raise ValueError("Canonical schema has malformed writable property data") from error
    if value_type not in _SUPPORTED_WRITE_VALUE_TYPES:
        raise ValueError(f"Unsupported writable property value type: {value_type!r}")
    constraints = field.get("constraints", {})
    if not isinstance(constraints, Mapping):
        raise ValueError(f"Writable property {field_id!r} constraints must be an object")
    unsupported = set(constraints) - _SUPPORTED_WRITE_CONSTRAINTS
    if unsupported:
        raise ValueError(
            f"Writable property {field_id!r} declares unsupported constraints: {sorted(unsupported)}"
        )
    _validate_write_constraint_compatibility(field_id, value_type, constraints)
    return {
        "value_type": value_type,
        "required": required,
        "description": description,
        "constraints": dict(constraints),
    }


def _validate_write_constraint_compatibility(
    field_id: str, value_type: str, constraints: Mapping[str, Any]
) -> None:
    """Fail closed when a known constraint is attached to an unsupported value-type shape."""
    value_format = constraints.get("format")
    if value_format is not None:
        if value_format not in _SUPPORTED_WRITE_FORMATS or value_type != "string":
            raise ValueError(
                f"Writable property {field_id!r} declares unsupported format {value_format!r}"
            )
    if "minimum" in constraints and value_type != "integer":
        raise ValueError(f"Writable property {field_id!r} uses minimum on non-integer data")
    if constraints.get("unique_items") is True and value_type != "array[string]":
        raise ValueError(f"Writable property {field_id!r} uses unique_items on non-array data")
    if constraints.get("non_empty") is True and value_type != "string":
        raise ValueError(f"Writable property {field_id!r} uses non_empty on non-string data")
