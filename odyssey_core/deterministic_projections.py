"""Rebuildable, non-authoritative SQLite rows derived from canonical Markdown.

One note stays one Markdown file. Atomic facts are independently addressable
inside the derived index, without becoming independent files or writers.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from odyssey_core.atomic_facts import AtomicFactError, parse_atomic_facts
from odyssey_core.notes import Note


class DeterministicProjectionError(ValueError):
    """Canonical fact structure cannot be safely indexed."""


def note_attribute_rows(note_id: str, note: Note) -> list[tuple[str, str, str]]:
    """Preserve EVERY schema-valid frontmatter field, including future properties.

    JSON arrays/objects remain complete field values rather than losing their
    structure via list flattening. These are read projections, not metadata authority.
    """
    return [
        (note_id, key, json.dumps(value, sort_keys=True, ensure_ascii=False))
        for key, value in sorted(note.metadata.items())
    ]


def note_alias_rows(note_id: str, note: Note) -> list[tuple[str, str, str]]:
    """Keep original aliases and their deterministic exact-lookup search key."""
    return [
        (note_id, alias, " ".join(unicodedata.normalize("NFC", alias).casefold().split()))
        for alias in note.metadata.get("aliases", [])
    ]


def note_fact_rows(note_id: str, note: Note) -> list[tuple[Any, ...]]:
    """Project fact ID, text, capture date and temporal anchors without rewriting."""
    try:
        facts = parse_atomic_facts(note.content)
    except AtomicFactError as error:
        raise DeterministicProjectionError("Canonical atomic facts are malformed") from error
    return [
        (
            note_id,
            fact.locator,
            fact.request_id,
            fact.ordinal,
            fact.text,
            fact.recorded_at,
            json.dumps([anchor.value for anchor in fact.temporal_anchors]),
            fact.start,
            fact.end,
        )
        for fact in facts
    ]
