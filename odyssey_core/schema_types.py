"""Shared canonical note-type classification helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def canonical_type_definitions(schema: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return the canonical type registry or fail when the schema shape is unusable."""
    try:
        types = tuple(schema["types"])
    except (KeyError, TypeError) as error:
        raise ValueError("Canonical schema has unusable type data") from error
    if not types or any(not isinstance(item, Mapping) for item in types):
        raise ValueError("Canonical schema has unusable type data")
    return types


def ordinary_type_definitions(schema: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return canonical types owned by ordinary semantic Note behavior."""
    return tuple(item for item in canonical_type_definitions(schema) if "managed_by" not in item)


def ordinary_type_ids(schema: Mapping[str, Any]) -> frozenset[str]:
    """Return validated IDs for ordinary semantic types only."""
    values = tuple(item.get("id") for item in ordinary_type_definitions(schema))
    if not values or not all(isinstance(value, str) and value for value in values):
        raise ValueError("Canonical schema has unusable type data")
    return frozenset(values)


def is_application_managed_type(schema: Mapping[str, Any], type_id: str) -> bool:
    """Return whether one canonical type has an application-owned deterministic lifecycle."""
    return any(
        item.get("id") == type_id and "managed_by" in item
        for item in canonical_type_definitions(schema)
    )
