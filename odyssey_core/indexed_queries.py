"""A narrow Core read port over version-proven derived SQLite projections.

Never hands out an authoritative Note solely from SQL. The complete inventory
must match current physical Markdown versions; every positive is then grounded
in its exact source bytes and hash. Negative read results are safe only within
that best-effort filesystem-version proof; mutations still use canonical CAS.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odyssey_core.atomic_facts import AtomicFactError, parse_atomic_facts
from odyssey_core.context import extract_wikilink_targets
from odyssey_core.notes import Note, parse_note, validate_note
from odyssey_core.storage import VaultRepository
from odyssey_core.verified_metadata_catalog import _from_complete_index


class IndexedQueryUnavailable(RuntimeError):
    """A derived query could not be safely grounded in current canonical Markdown."""


@dataclass(frozen=True, slots=True)
class IndexedNoteHit:
    path: str
    note: Note
    source_hash: str


class CoreIndexedQueries:
    """Generic type/alias/property/fact/link read interface, no write authority."""

    def __init__(self, repository: VaultRepository, schema: dict[str, Any], index_path: Path):
        self.repository = repository
        self.schema = schema
        self.index_path = index_path

    def _complete(self):
        paths = tuple(self.repository.list_markdown_paths())
        snapshot = _from_complete_index(self.repository, self.schema, str(self.index_path), paths)
        if snapshot is None:
            raise IndexedQueryUnavailable("Canonical inventory is missing, stale, or incomplete")
        return snapshot

    def _ground(self, path: str, indexed_id: str, indexed_sha: str) -> IndexedNoteHit:
        try:
            source = self.repository.read_text(path)
            if hashlib.sha256(source.encode("utf-8")).hexdigest() != indexed_sha:
                raise IndexedQueryUnavailable("Indexed source hash differs from Markdown")
            note = parse_note(source)
            validate_note(note, self.schema)
            if note.metadata["id"] != indexed_id:
                raise IndexedQueryUnavailable("Indexed identity differs from Markdown")
            return IndexedNoteHit(path, note, indexed_sha)
        except IndexedQueryUnavailable:
            raise
        except (ValueError, OSError, TypeError, KeyError) as error:
            raise IndexedQueryUnavailable("Cannot ground indexed Note") from error

    def by_id(self, note_id: str) -> IndexedNoteHit | None:
        self._complete()
        with sqlite3.connect(f"file:{self.index_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT path,note_id,source_hash FROM vault_inventory WHERE note_id=?",
                (note_id,),
            ).fetchall()
        if len(rows) > 1:
            raise IndexedQueryUnavailable("Ambiguous indexed ID")
        return self._ground(*rows[0]) if rows else None

    def exact_names(
        self,
        name: str,
        *,
        type: str | None = None,
        include_deleted: bool = False,
        maximum: int = 24,
    ) -> tuple[IndexedNoteHit, ...]:
        from odyssey_core.identity import _normalize_reference

        self._complete()
        normalized = _normalize_reference(name)
        if not normalized or maximum < 1:
            raise ValueError("An exact name and a positive budget are required")
        with sqlite3.connect(f"file:{self.index_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT i.path,i.note_id,i.source_hash,i.metadata_json "
                "FROM vault_inventory i WHERE i.normalized_name=? OR EXISTS( "
                "SELECT 1 FROM vault_aliases a WHERE a.note_id=i.note_id AND a.normalized=?) "
                "ORDER BY i.path",
                (normalized, normalized),
            ).fetchall()
        selected = []
        for path, note_id, source_hash, metadata_json in rows:
            metadata = json.loads(metadata_json)
            if type is not None and metadata.get("type") != type:
                continue
            if not include_deleted and metadata.get("deleted") is True:
                continue
            selected.append((path, note_id, source_hash))
            if len(selected) > maximum:
                raise IndexedQueryUnavailable("Exact results exceed bounded budget")
        hits = tuple(self._ground(*item) for item in selected)
        if any(
            (type is not None and hit.note.metadata["type"] != type)
            or (not include_deleted and hit.note.metadata.get("deleted") is True)
            or not any(
                _normalize_reference(alias) == normalized
                for alias in (hit.note.metadata["name"], *hit.note.metadata.get("aliases", []))
            )
            for hit in hits
        ):
            raise IndexedQueryUnavailable("Index name/alias evidence is not canonical")
        return hits

    def by_attribute(
        self, field: str, value: Any, *, maximum: int = 24
    ) -> tuple[IndexedNoteHit, ...]:
        self._complete()
        if not field or maximum < 1:
            raise ValueError("Invalid field or budget")
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
        with sqlite3.connect(f"file:{self.index_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT i.path,i.note_id,i.source_hash FROM note_attributes a "
                "JOIN vault_inventory i ON i.note_id=a.note_id "
                "WHERE a.field=? AND a.value_json=? ORDER BY i.path",
                (field, encoded),
            ).fetchall()
        if len(rows) > maximum:
            raise IndexedQueryUnavailable("Attribute matches exceed budget")
        hits = tuple(self._ground(*row) for row in rows)
        if any(hit.note.metadata.get(field) != value for hit in hits):
            raise IndexedQueryUnavailable("Indexed attribute does not match canonical Note")
        return hits

    def facts(self, note_id: str) -> tuple[tuple[str, str], ...]:
        hit = self.by_id(note_id)
        if hit is None or hit.note.metadata.get("deleted") is True:
            return ()
        try:
            actual = {fact.locator: fact.text for fact in parse_atomic_facts(hit.note.content)}
        except AtomicFactError as error:
            raise IndexedQueryUnavailable("Canonical facts cannot be parsed") from error
        with sqlite3.connect(f"file:{self.index_path}?mode=ro", uri=True) as conn:
            state = conn.execute(
                "SELECT status FROM note_fact_integrity WHERE note_id=?", (note_id,)
            ).fetchone()
            rows = conn.execute(
                "SELECT locator,fact_text FROM note_facts WHERE note_id=? ORDER BY start_offset",
                (note_id,),
            ).fetchall()
        if state != ("valid",) or actual != dict(rows):
            raise IndexedQueryUnavailable("Derived facts do not match canonical facts")
        return tuple(rows)

    def links(self, note_id: str, *, incoming: bool = False) -> tuple[tuple[str, str, str], ...]:
        snapshot = self._complete()
        col = "target_id" if incoming else "source_id"
        with sqlite3.connect(f"file:{self.index_path}?mode=ro", uri=True) as conn:
            data = conn.execute(
                f"SELECT source_id,target_id,target_text FROM note_links WHERE {col}=? ORDER BY source_id,target_id,target_text",
                (note_id,),
            ).fetchall()
        for source_id, target_id, target_text in data:
            source = self.by_id(source_id)
            target = self.by_id(target_id)
            stem = target_text.removesuffix(".md").casefold()
            resolved = [
                row.id
                for row in snapshot.rows
                if not row.deleted
                and (
                    row.path.removesuffix(".md").casefold() == stem
                    or (
                        "/" not in stem
                        and row.path.removesuffix(".md").rsplit("/", 1)[-1].casefold() == stem
                    )
                )
            ]
            if (
                source is None
                or target is None
                or len(resolved) != 1
                or resolved[0] != target_id
                or not any(
                    literal == target_text
                    for literal, _label in extract_wikilink_targets(source.note.content)
                )
            ):
                raise IndexedQueryUnavailable("Graph link lacks canonical source evidence")
        return tuple(data)
