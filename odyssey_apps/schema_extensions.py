"""Validated application-owned additions to Odyssey's canonical runtime schema."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


class ApplicationSchemaError(ValueError):
    """Reject unsafe or conflicting application schema registration."""


@dataclass(frozen=True, slots=True)
class ApplicationSchemaExtension:
    """Contribute canonical note types owned by one explicit application capability."""

    capability_id: str
    types: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capability_id, str)
            or not self.capability_id
            or self.capability_id.strip() != self.capability_id
        ):
            raise ApplicationSchemaError("Application schema capability id is invalid")
        if not isinstance(self.types, tuple) or not self.types:
            raise ApplicationSchemaError("Application schema extension must contribute types")
        seen: set[str] = set()
        for definition in self.types:
            if not isinstance(definition, Mapping):
                raise ApplicationSchemaError("Application schema type must be an object")
            type_id = definition.get("id")
            if not isinstance(type_id, str) or not type_id:
                raise ApplicationSchemaError("Application schema type id is invalid")
            if type_id in seen:
                raise ApplicationSchemaError(f"Duplicate application schema type: {type_id}")
            seen.add(type_id)
            if definition.get("managed_by") != self.capability_id:
                raise ApplicationSchemaError(
                    f"Application schema type {type_id!r} must be managed by {self.capability_id!r}"
                )


def compose_application_schema(
    base_schema: Mapping[str, Any], extensions: tuple[ApplicationSchemaExtension, ...]
) -> dict[str, Any]:
    """Return one runtime schema with app-owned types registered deterministically.

    The checked-in base schema remains Core-owned. Registration makes app notes valid canonical
    Markdown, while ``managed_by`` keeps those types out of ordinary Core planning authority.
    """
    if not isinstance(base_schema, Mapping):
        raise ApplicationSchemaError("Base schema is invalid")
    result = deepcopy(dict(base_schema))
    raw_types = result.get("types")
    if not isinstance(raw_types, list):
        raise ApplicationSchemaError("Base schema type registry is invalid")
    known = {
        item.get("id")
        for item in raw_types
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    capability_ids: set[str] = set()
    for extension in extensions:
        if not isinstance(extension, ApplicationSchemaExtension):
            raise ApplicationSchemaError("Application schema registration is invalid")
        if extension.capability_id in capability_ids:
            raise ApplicationSchemaError(
                f"Duplicate application schema capability: {extension.capability_id}"
            )
        capability_ids.add(extension.capability_id)
        for definition in extension.types:
            type_id = definition["id"]
            if type_id in known:
                raise ApplicationSchemaError(
                    f"Application schema type conflicts with base: {type_id}"
                )
            raw_types.append(deepcopy(dict(definition)))
            known.add(type_id)
    return result
