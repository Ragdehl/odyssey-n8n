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
_EXCLUDED_FIELDS = {"subtype", "tags"}


def build_planner_capabilities(
    schema: Mapping[str, Any], *, current_context: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Project canonical note-schema data into planner-safe capabilities.

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
            filters[field["id"]] = _filter_capability(field, type_ids)
    for note_type in types:
        for field in note_type["properties"]:
            if field.get("filterable"):
                filters[field["id"]] = _filter_capability(field, [note_type["id"]])
    if current_context is not None:
        if set(current_context) != {"date", "time", "timezone"}:
            raise ValueError("Planner current context must contain date, time, and timezone")
        capabilities["current_context"] = dict(current_context)
    return capabilities


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
