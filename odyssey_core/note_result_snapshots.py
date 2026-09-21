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
    """Represent bounded body-free Notes membership retained on one assistant turn.

    Version 1 records a historical search. Version 2 records the exact stable identities affected
    by a mutation. Both forms deliberately contain membership evidence only; Markdown remains the
    source for current titles, types, and bodies when a user opens the set later.
    """

    query: str | None
    filters: tuple[Mapping[str, Any], ...]
    sort: str | None
    ranking_version: str | None
    executed_at: str
    note_ids: tuple[str, ...]
    total: int
    truncated: bool
    version: int = 1
    kind: str = "search"

    def to_payload(self) -> dict[str, Any]:
        """Serialize the closed, browser-safe snapshot representation."""
        if self.version == 2:
            return {
                "version": 2,
                "kind": "affected_notes",
                "executed_at": self.executed_at,
                "note_ids": list(self.note_ids),
                "total": self.total,
                "truncated": self.truncated,
            }
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
    if not isinstance(value, Mapping):
        raise NoteResultSnapshotError("Note result snapshot is invalid")
    if value.get("version") == 2:
        return _validate_affected_notes_snapshot(value)
    if set(value) != {
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
    _validate_encoded_size(snapshot)
    return snapshot


def affected_notes_snapshot(note_ids: object, executed_at: str) -> NoteResultSnapshot:
    """Create the exact bounded v2 membership set from Core mutation evidence.

    First-occurrence order is preserved while duplicates are collapsed before the fixed durable
    membership bound is applied. Invalid Core evidence fails closed rather than producing a
    browser affordance with guessed identities.
    """
    if not isinstance(note_ids, tuple) or not isinstance(executed_at, str):
        raise NoteResultSnapshotError("Note result snapshot is invalid")
    unique = tuple(dict.fromkeys(note_ids))
    if not unique or not all(
        isinstance(item, str) and item and len(item) <= 128 for item in unique
    ):
        raise NoteResultSnapshotError("Note result snapshot is invalid")
    snapshot = NoteResultSnapshot(
        None,
        (),
        None,
        None,
        executed_at,
        unique[:MAX_NOTE_IDS],
        len(unique),
        len(unique) > MAX_NOTE_IDS,
        version=2,
        kind="affected_notes",
    )
    _validate_encoded_size(snapshot)
    return snapshot


def _validate_affected_notes_snapshot(value: Mapping[str, Any]) -> NoteResultSnapshot:
    """Validate the closed v2 mutation-membership representation."""
    if set(value) != {"version", "kind", "executed_at", "note_ids", "total", "truncated"}:
        raise NoteResultSnapshotError("Note result snapshot is invalid")
    ids = value["note_ids"]
    if (
        value["kind"] != "affected_notes"
        or not isinstance(value["executed_at"], str)
        or not isinstance(ids, list)
        or len(ids) > MAX_NOTE_IDS
        or len(ids) != len(set(ids))
        or not all(isinstance(item, str) and item and len(item) <= 128 for item in ids)
        or not isinstance(value["total"], int)
        or value["total"] < 1
        or value["total"] < len(ids)
        or not isinstance(value["truncated"], bool)
        or value["truncated"] != (value["total"] > len(ids))
    ):
        raise NoteResultSnapshotError("Note result snapshot is invalid")
    snapshot = NoteResultSnapshot(
        None,
        (),
        None,
        None,
        value["executed_at"],
        tuple(ids),
        value["total"],
        value["truncated"],
        version=2,
        kind="affected_notes",
    )
    _validate_encoded_size(snapshot)
    return snapshot


def _validate_encoded_size(snapshot: NoteResultSnapshot) -> None:
    """Reject an otherwise-shaped snapshot that exceeds the durable size bound."""
    if (
        len(json.dumps(snapshot.to_payload(), ensure_ascii=False, separators=(",", ":")).encode())
        > MAX_ENCODED_BYTES
    ):
        raise NoteResultSnapshotError("Note result snapshot is too large")
