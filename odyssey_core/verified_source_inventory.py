"""Verified, complete canonical inventory shared by independent derived indexes.

Every entry originates from the context index after its successful write. This
is only a performance hint: filesystem versions must still match before and
after each consumer's SQLite publication; changed notes are parsed anew.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odyssey_core.source_inventory import schema_digest, source_inventory_unchanged
from odyssey_core.storage import VaultRepository


@dataclass(frozen=True, slots=True)
class VerifiedSourceRecord:
    path: str
    id: str
    type: str
    name: str
    source_hash: str
    deleted: bool
    version: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class VerifiedSourceInventory:
    records: tuple[VerifiedSourceRecord, ...]
    versions: dict[str, tuple[object, ...]]

    def assert_unchanged(self, repository: VaultRepository) -> None:
        if not source_inventory_unchanged(repository, self.versions):
            raise ValueError("Verified canonical inventory changed before index publication")


def verified_context_source_inventory(
    repository: VaultRepository, schema: dict[str, Any], context_index_path: Path
) -> VerifiedSourceInventory:
    """Verify all on-disk versions against the fresh complete context inventory.

    Unlike a semantic full scan, only filesystem fingerprints and validated
    context SQL metadata are loaded. Any drift forces fail-closed fallback.
    """
    try:
        with sqlite3.connect(f"file:{context_index_path}?mode=ro", uri=True) as db:
            metadata = dict(db.execute("SELECT key,value FROM metadata"))
            if (
                metadata.get("format") != "context-index"
                or metadata.get("format_version") != "6"
                or metadata.get("schema_digest") != schema_digest(schema)
            ):
                raise ValueError("Context inventory contract is incompatible")
            stored = db.execute(
                "SELECT path,note_id,version_json,source_hash,metadata_json FROM vault_inventory"
            ).fetchall()
    except sqlite3.Error as error:
        raise ValueError("Context inventory is unavailable") from error
    records = []
    versions = {}
    ids = set()
    for path, note_id, version_json, source_hash, metadata_json in stored:
        try:
            version = tuple(json.loads(version_json))
            note = json.loads(metadata_json)
            if (
                not isinstance(path, str)
                or not isinstance(note_id, str)
                or not isinstance(source_hash, str)
                or len(source_hash) != 64
                or note.get("id") != note_id
                or not isinstance(note.get("name"), str)
                or not isinstance(note.get("type"), str)
                or note_id in ids
                or path in versions
                or len(version) != 6
            ):
                raise ValueError("Invalid context inventory entry")
            deleted = note.get("deleted") is True
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("Context inventory row is not valid") from error
        ids.add(note_id)
        versions[path] = version
        records.append(
            VerifiedSourceRecord(
                path, note_id, note["type"], note["name"], source_hash, deleted, version
            )
        )
    snapshot = VerifiedSourceInventory(tuple(records), versions)
    snapshot.assert_unchanged(repository)
    return snapshot
