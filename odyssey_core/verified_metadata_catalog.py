"""Request-scoped, physically verified metadata for repeated Core uniqueness checks.

This is NEVER a durable Note authority, nor an index-completeness claim. It
validates every Markdown Note on first use; each later use rechecks the whole
path set and physical versions. If any source changed, revalidate the vault.
Only the P4 runtime opts in; unrelated callers retain their existing paths.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from odyssey_core.notes import parse_note, validate_note
from odyssey_core.storage import VaultRepository


class VerifiedCatalogError(RuntimeError):
    """A verified source snapshot could not be produced without ambiguity."""


@dataclass(frozen=True, slots=True)
class _MetadataRow:
    path: str
    id: str
    type: str
    name: str
    aliases: tuple[str, ...]
    content_excerpt: str
    date: str | None
    deleted: bool


@dataclass(frozen=True, slots=True)
class _VerifiedSnapshot:
    paths: tuple[str, ...]
    versions: tuple[tuple[object, ...], ...]
    rows: tuple[_MetadataRow, ...]

    def day_identity_collides(self, path: str, identity: str, date: str) -> bool:
        return any(
            item.path != path
            and (
                item.id == identity
                or (item.type == "calendar_day" and item.date == date and not item.deleted)
            )
            for item in self.rows
        )


@dataclass(slots=True)
class _Scope:
    repo: VaultRepository | None = None
    schema: dict[str, Any] | None = None
    schema_signature: str | None = None
    snapshot: _VerifiedSnapshot | None = None
    index_path: str | None = None


_ACTIVE: ContextVar[_Scope | None] = ContextVar("odyssey_p4_verified_catalog", default=None)


@contextmanager
def scoped_verified_metadata_catalog(*, index_path: str | None = None) -> Iterator[None]:
    """Use per-delivery, never across users/requests, and opt-in only."""
    token = _ACTIVE.set(_Scope(index_path=index_path))
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def _from_complete_index(
    repository: VaultRepository,
    schema: dict[str, Any],
    index_path: str,
    paths: tuple[str, ...],
) -> _VerifiedSnapshot | None:
    """Accept a derived source inventory ONLY if every physical version matches.

    This is a filesystem change-detector fast path, not a cryptographic
    guarantee against hostile same-inode timestamps or concurrent writers.
    Decisions involving a mutation are still protected by Core Writer/CAS.
    """
    from odyssey_core.source_inventory import schema_digest

    try:
        with sqlite3.connect(f"file:{index_path}?mode=ro", uri=True) as connection:
            markers = dict(connection.execute("SELECT key,value FROM metadata"))
            if (
                markers.get("format") != "context-index"
                or markers.get("format_version") != "6"
                or markers.get("schema_digest") != schema_digest(schema)
            ):
                return None
            indexed = list(
                connection.execute(
                    "SELECT path,note_id,version_json,metadata_json,body_excerpt,normalized_name "
                    "FROM vault_inventory ORDER BY path"
                )
            )
        if len(indexed) != len(paths) or any(
            item[0] != path for item, path in zip(indexed, paths, strict=True)
        ):
            return None
        versions_now = repository.note_version_snapshot()
        if tuple(sorted(versions_now)) != paths:
            return None
        verified_versions = []
        rows = []
        from odyssey_core.source_inventory import exact_key

        for path, note_id, version_json, metadata_json, excerpt, normalized_name in indexed:
            version = tuple(json.loads(version_json))
            if versions_now[path] != version:
                return None
            metadata = json.loads(metadata_json)
            if (
                metadata.get("id") != note_id
                or not isinstance(excerpt, str)
                or exact_key(metadata.get("name", "")) != normalized_name
            ):
                return None
            aliases = metadata.get("aliases", [])
            if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
                return None
            rows.append(
                _MetadataRow(
                    path=path,
                    id=note_id,
                    type=metadata["type"],
                    name=metadata["name"],
                    aliases=tuple(aliases),
                    content_excerpt=excerpt,
                    date=metadata.get("date"),
                    deleted=metadata.get("deleted") is True,
                )
            )
            verified_versions.append(version)
        if tuple(repository.list_markdown_paths()) != paths:
            return None
        # A change between initial stats and final proof cannot make a stale
        # negative look complete.
        if repository.note_version_snapshot() != versions_now:
            return None
        return _VerifiedSnapshot(paths, tuple(verified_versions), tuple(rows))
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, IndexError):
        return None


def verified_catalog_if_active(
    repository: VaultRepository, schema: dict[str, Any]
) -> _VerifiedSnapshot | None:
    scope = _ACTIVE.get()
    if scope is None:
        return None
    try:
        schema_signature = json.dumps(schema, sort_keys=True, ensure_ascii=False)
        paths = tuple(repository.list_markdown_paths())
        if (
            scope.repo is repository
            and scope.schema is schema
            and scope.schema_signature == schema_signature
            and scope.snapshot is not None
        ):
            snapshot = scope.snapshot
            if paths == snapshot.paths and repository.note_version_snapshot() == dict(
                zip(paths, snapshot.versions, strict=True)
            ):
                return snapshot
        if scope.index_path is not None:
            indexed = _from_complete_index(repository, schema, scope.index_path, paths)
            if indexed is not None:
                scope.repo = repository
                scope.schema = schema
                scope.schema_signature = schema_signature
                scope.snapshot = indexed
                return indexed
        if len(paths) > 20_000:
            # The catalogue is a bounded optimization, not a semantic limit.
            return None
        records: list[_MetadataRow] = []
        versions: list[tuple[object, ...]] = []
        for path in paths:
            before = repository.file_version(path)
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
            after = repository.file_version(path)
            if before != after:
                raise VerifiedCatalogError("Canonical source changed while building catalog")
            versions.append(after)
            records.append(
                _MetadataRow(
                    path=path,
                    id=note.metadata["id"],
                    type=note.metadata["type"],
                    name=note.metadata["name"],
                    aliases=tuple(note.metadata.get("aliases", [])),
                    content_excerpt=note.content.strip()[:320],
                    date=note.metadata.get("date"),
                    deleted=note.metadata.get("deleted") is True,
                )
            )
        if tuple(repository.list_markdown_paths()) != paths or any(
            repository.file_version(path) != version
            for path, version in zip(paths, versions, strict=True)
        ):
            raise VerifiedCatalogError("Canonical source changed while building catalog")
        snapshot = _VerifiedSnapshot(paths, tuple(versions), tuple(records))
        scope.repo = repository
        scope.schema = schema
        scope.schema_signature = schema_signature
        scope.snapshot = snapshot
        return snapshot
    except VerifiedCatalogError:
        scope.snapshot = None
        raise
    except (OSError, ValueError, TypeError, KeyError) as error:
        scope.snapshot = None
        raise VerifiedCatalogError("Cannot verify canonical metadata") from error
