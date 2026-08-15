"""Generic representation of one Odyssey note."""

from __future__ import annotations

from dataclasses import dataclass

type MetadataScalar = str | int | float | bool | None
type MetadataValue = MetadataScalar | list[MetadataScalar]


@dataclass(slots=True)
class Note:
    """Represent logical note metadata and Markdown content without a storage path.

    Attributes:
        metadata: Structured values serialized in the note's frontmatter.
        content: Uninterpreted Markdown body text.
    """

    metadata: dict[str, MetadataValue]
    content: str
