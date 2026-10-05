"""Shared canonical note-type classification helpers."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
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


def notes_visible_type_definitions(schema: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return canonical types that the general Notes browser may expose.

    Ordinary Core types are visible by default. Application-managed types remain hidden unless
    their owning extension explicitly opts into Notes visibility. Visibility never grants generic
    creation or lifecycle mutation authority.
    """
    return tuple(
        item
        for item in canonical_type_definitions(schema)
        if "managed_by" not in item or item.get("notes_visible") is True
    )


def notes_visible_type_ids(schema: Mapping[str, Any]) -> frozenset[str]:
    values = tuple(item.get("id") for item in notes_visible_type_definitions(schema))
    if not values or not all(isinstance(value, str) and value for value in values):
        raise ValueError("Canonical schema has unusable type data")
    return frozenset(values)


def referenceable_type_definitions(schema: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return types that ordinary facts may reference as existing canonical identities only."""
    return tuple(
        item
        for item in canonical_type_definitions(schema)
        if "managed_by" not in item or item.get("referenceable") is True
    )


def referenceable_type_ids(schema: Mapping[str, Any]) -> frozenset[str]:
    values = tuple(item.get("id") for item in referenceable_type_definitions(schema))
    if not values or not all(isinstance(value, str) and value for value in values):
        raise ValueError("Canonical schema has unusable type data")
    return frozenset(values)


def content_writable_type_definitions(
    schema: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    """Return types that Core may amend with ordinary facts without owning their lifecycle."""
    return tuple(
        item
        for item in canonical_type_definitions(schema)
        if "managed_by" not in item or item.get("content_writable") is True
    )


def content_writable_type_ids(schema: Mapping[str, Any]) -> frozenset[str]:
    values = tuple(item.get("id") for item in content_writable_type_definitions(schema))
    if not values or not all(isinstance(value, str) and value for value in values):
        raise ValueError("Canonical schema has unusable type data")
    return frozenset(values)


def is_application_managed_type(schema: Mapping[str, Any], type_id: str) -> bool:
    """Return whether one canonical type has an application-owned deterministic lifecycle."""
    return any(
        item.get("id") == type_id and "managed_by" in item
        for item in canonical_type_definitions(schema)
    )


def planning_schema_for_capability(
    schema: Mapping[str, Any], capability_id: str | None
) -> dict[str, Any]:
    """Project app-owned canonical types into planner authority for one trusted app route only.

    Registered ``managed_by`` types remain excluded from ordinary Core planning.  A trusted
    application route may temporarily expose only the types it owns; persisted validation still uses
    the unchanged managed schema.
    """
    projected = deepcopy(dict(schema))
    if capability_id is None:
        return projected
    if not isinstance(capability_id, str) or not capability_id:
        raise ValueError("Planning capability id is invalid")
    raw_types = projected.get("types")
    if not isinstance(raw_types, list):
        raise ValueError("Canonical schema has unusable type data")
    for definition in raw_types:
        if isinstance(definition, dict) and definition.get("managed_by") == capability_id:
            definition.pop("managed_by")
    return projected
