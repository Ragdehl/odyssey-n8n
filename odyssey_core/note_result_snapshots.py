"""Bounded durable historical Notes result-set snapshots for conversation turns."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_QUERY_BYTES = 512
MAX_FILTERS = 16
MAX_NOTE_IDS = 64
MAX_ENCODED_BYTES = 16 * 1024


class NoteResultSnapshotError(ValueError):
    """Indicate an unsafe or malformed durable result-set snapshot."""


@dataclass(frozen=True, slots=True)
class NoteResultSnapshot:
    """Represent the versioned, body-free historical membership of one Notes result."""

    query: str
    filters: tuple[Mapping[str, Any], ...]
    sort: str
    ranking_version: str
    executed_at: str
    note_ids: tuple[str, ...]
    total: int
    truncated: bool
    version: int = 1

    def to_payload(self) -> dict[str, Any]:
        """Serialize the closed, browser-safe snapshot representation."""
        return {
            "version": self.version,
            "query": self.query,
            "filters": [dict(item) for item in self.filters],
            "sort": self.sort,
            "ranking_version": self.ranking_version,
            "executed_at": self.executed_at,
            "note_ids": list(self.note_ids),
            "total": self.total,
            "truncated": self.truncated,
        }


def validate_note_result_snapshot(value: object) -> NoteResultSnapshot | None:
    """Validate one optional snapshot before durable persistence or public projection."""
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "version",
        "query",
        "filters",
        "sort",
        "ranking_version",
        "executed_at",
        "note_ids",
        "total",
        "truncated",
    }:
        raise NoteResultSnapshotError("Note result snapshot is invalid")
    query, filters, ids = value["query"], value["filters"], value["note_ids"]
    if (
        value["version"] != 1
        or not isinstance(query, str)
        or not query.strip()
        or len(query.encode()) > MAX_QUERY_BYTES
        or not isinstance(filters, list)
        or len(filters) > MAX_FILTERS
        or not all(
            isinstance(item, Mapping)
            and set(item) == {"field", "op", "value"}
            and isinstance(item["field"], str)
            and isinstance(item["op"], str)
            for item in filters
        )
        or not isinstance(ids, list)
        or len(ids) > MAX_NOTE_IDS
        or len(ids) != len(set(ids))
        or not all(isinstance(item, str) and item and len(item) <= 128 for item in ids)
        or not isinstance(value["sort"], str)
        or not isinstance(value["ranking_version"], str)
        or not isinstance(value["executed_at"], str)
        or not isinstance(value["total"], int)
        or value["total"] < len(ids)
        or not isinstance(value["truncated"], bool)
        or value["truncated"] != (value["total"] > len(ids))
    ):
        raise NoteResultSnapshotError("Note result snapshot is invalid")
    snapshot = NoteResultSnapshot(
        query,
        tuple(dict(item) for item in filters),
        value["sort"],
        value["ranking_version"],
        value["executed_at"],
        tuple(ids),
        value["total"],
        value["truncated"],
    )
    if (
        len(json.dumps(snapshot.to_payload(), ensure_ascii=False, separators=(",", ":")).encode())
        > MAX_ENCODED_BYTES
    ):
        raise NoteResultSnapshotError("Note result snapshot is too large")
    return snapshot
