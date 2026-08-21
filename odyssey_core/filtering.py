"""Shared deterministic filter capabilities for Odyssey retrieval boundaries."""

from __future__ import annotations

from collections.abc import Mapping


def supported_filter_operators(definition: Mapping[str, object]) -> tuple[str, ...]:
    """Return the Core-supported operators for one canonical filter definition.

    Args:
        definition: Canonical metadata or type-property field definition.

    Returns:
        The closed operator sequence accepted by deterministic context retrieval.

    Raises:
        ValueError: If the field has no retrieval-supported value type.

    Example:
        A ``relationship_to_user`` string field returns ``("eq", "in")``.
    """
    value_type = definition.get("value_type")
    constraints = definition.get("constraints", {})
    if value_type == "array[string]":
        return ("contains",)
    if value_type == "string":
        return (
            ("eq", "in", "gt", "gte", "lt", "lte")
            if isinstance(constraints, Mapping) and constraints.get("format") == "date-time"
            else ("eq", "in")
        )
    if value_type in {"integer", "date"}:
        return ("eq", "in", "gt", "gte", "lt", "lte")
    raise ValueError(f"Unsupported filter field value type: {value_type!r}")
