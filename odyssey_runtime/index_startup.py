"""Safely reuse existing derived indexes on P4 restart when nothing changed.

Read-only validation; if any source/index/model/schema mismatch exists, factory
still performs the legacy full rebuild. No Markdown or credentials mutated.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from odyssey_core.context import _INDEX_MARKERS as CONTEXT_MARKERS
from odyssey_core.context import ContextIndex
from odyssey_core.semantic import _INDEX_MARKERS as SEMANTIC_MARKERS
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.semantic import _canonical_types as semantic_types
from odyssey_core.storage import VaultRepository
from odyssey_core.verified_metadata_catalog import _from_complete_index


def _indexed_rows(index: Path, markers: Mapping[str, str], embedder: Any):
    with sqlite3.connect(f"file:{index}?mode=ro", uri=True) as connection:
        observed = dict(connection.execute("SELECT key,value FROM metadata"))
        if any(observed.get(key) != value for key, value in markers.items()):
            return None
        if (
            observed.get("model_name") != embedder.model_name
            or observed.get("model_version") != embedder.model_version
        ):
            return None
        values = {
            row[0]: tuple(row[1:])
            for row in connection.execute("SELECT id,path,type,primary_name,source_hash FROM notes")
        }
        return observed, values


def p4_indexes_reusable(
    repo: VaultRepository,
    schema: dict[str, Any],
    embedder: Any,
    context: ContextIndex,
    semantic: SemanticEntityIndex,
    applications: Mapping[str, tuple[SemanticEntityIndex, dict[str, Any]]],
) -> bool:
    """Prove all physical sources/index schemas/model rows before reuse.

    The manifest includes soft-deleted IDs so an unrelated new/deleted
    Markdown can never slip past a source-negative check. Every normal query
    still rechecks versions and positive source bytes; boot is not authority.
    """
    try:
        paths = tuple(repo.list_markdown_paths())
        snapshot = _from_complete_index(repo, schema, str(context.path), paths)
        if snapshot is None:
            return False
        primary = _indexed_rows(context.path, CONTEXT_MARKERS, embedder)
        if primary is None:
            return False
        _meta, current = primary
        with sqlite3.connect(f"file:{context.path}?mode=ro", uri=True) as connection:
            inventory = {
                r[0]: (r[1], r[2])
                for r in connection.execute(
                    "SELECT note_id,source_hash,metadata_json FROM vault_inventory"
                )
            }
        expected = {
            row.id: (row.path, row.type, row.name, inventory[row.id][0])
            for row in snapshot.rows
            if not row.deleted
        }
        if current != expected:
            return False
        for index, custom_schema in ((semantic, schema), *applications.values()):
            read = _indexed_rows(index.path, SEMANTIC_MARKERS, embedder)
            if read is None:
                return False
            meta, indexed = read
            types = set(semantic_types(custom_schema))
            if set(json.loads(meta["canonical_types"])) != types:
                return False
            allowed = {key: value for key, value in expected.items() if value[1] in types}
            if indexed != allowed:
                return False
        return True
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return False
