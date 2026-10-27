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
from dataclasses import dataclass, field
from threading import RLock
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
    _ids: dict[str, tuple[_MetadataRow, ...]] = field(init=False, compare=False, repr=False)
    _names: dict[str, tuple[_MetadataRow, ...]] = field(init=False, compare=False, repr=False)
    _days: dict[str, tuple[_MetadataRow, ...]] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        from odyssey_core.source_inventory import exact_key

        id_rows: dict[str, list[_MetadataRow]] = {}
        name_rows: dict[str, list[_MetadataRow]] = {}
        days: dict[str, list[_MetadataRow]] = {}
        for row in self.rows:
            id_rows.setdefault(row.id, []).append(row)
            if not row.deleted:
                unique_names = {exact_key(row.name), *(exact_key(alias) for alias in row.aliases)}
                for normalized in unique_names:
                    name_rows.setdefault(normalized, []).append(row)
                if row.type == "calendar_day" and row.date is not None:
                    days.setdefault(row.date, []).append(row)
        object.__setattr__(self, "_ids", {key: tuple(value) for key, value in id_rows.items()})
        object.__setattr__(self, "_names", {key: tuple(value) for key, value in name_rows.items()})
        object.__setattr__(self, "_days", {key: tuple(value) for key, value in days.items()})

    def id_candidates(self, stable_id: str) -> tuple[_MetadataRow, ...]:
        """Every claim on this ID, including deleted and misplaced Notes."""
        return self._ids.get(stable_id, ())

    def exact_name_candidates(
        self, normalized_name: str, *, include_deleted: bool = False
    ) -> tuple[_MetadataRow, ...]:
        """Candidates from physically verified names and aliases, with no guess."""
        matches = self._names.get(normalized_name, ())
        if include_deleted:
            # Deleted candidates deliberately omitted from ordinary lookups.
            from odyssey_core.source_inventory import exact_key

            deleted = (
                row
                for row in self.rows
                if row.deleted
                and (
                    exact_key(row.name) == normalized_name
                    or any(exact_key(alias) == normalized_name for alias in row.aliases)
                )
            )
            return (*matches, *deleted)
        return matches

    def day_identity_collides(self, path: str, identity: str, date: str) -> bool:
        return any(row.path != path for row in self.id_candidates(identity)) or any(
            row.path != path for row in self._days.get(date, ())
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


def verified_mutation_catalog_if_active(
    repository: VaultRepository, schema: dict[str, Any]
) -> _VerifiedSnapshot | None:
    """Mutation reuse requires metadata parsed from *canonical files*, never SQLite.

    The preexisting P4 read-only catalog can load a complete derived SQLite
    inventory; it is valuable for hints but cannot prove a negative identity
    claim for new Core writes if the derived metadata was tampered with.
    """
    scope = _ACTIVE.get()
    if scope is None or scope.index_path is not None:
        return None
    return verified_catalog_if_active(repository, schema)


def verified_history_paths_if_active(
    repository: VaultRepository,
    schema: dict[str, Any],
    affected_ids: tuple[str, ...],
) -> tuple[str, ...] | None:
    """Reattribute a write using prior canonical uniqueness proof, not stale IDs.

    This optional same-delivery optimization is usable only AFTER the mutation
    gate built/verified a complete snapshot. The exact affected paths may
    change; every *other* source must retain its physical version and path.
    Re-read and validate all affected Markdown, then check the entire inventory
    again. Drift or uncertainty falls back to Git's full canonical scan.
    """
    scope = _ACTIVE.get()
    if (
        scope is None
        or scope.index_path is not None
        or scope.repo is not repository
        or scope.schema is not schema
        or scope.snapshot is None
    ):
        return None
    snapshot = scope.snapshot
    mapping: dict[str, str] = {}
    for stable_id in affected_ids:
        matches = snapshot.id_candidates(stable_id)
        if len(matches) != 1:
            return None
        mapping[matches[0].path] = stable_id
    if len(mapping) != len(set(affected_ids)):
        return None
    try:
        original_versions = dict(zip(snapshot.paths, snapshot.versions, strict=True))
        current = repository.note_version_snapshot()
        if current.keys() != original_versions.keys():
            return None
        if any(
            current[path] != version
            for path, version in original_versions.items()
            if path not in mapping
        ):
            return None
        for path, stable_id in mapping.items():
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
            if note.metadata.get("id") != stable_id:
                return None
        if repository.note_version_snapshot() != current:
            return None
        return tuple(sorted(mapping))
    except (OSError, ValueError, TypeError, KeyError):
        return None


class CanonicalMutationInventoryCache:
    """In-process canonical proof reused by a trusted serial backfill writer.

    The first delivery parses the ENTIRE Markdown vault. Subsequent deliveries
    compare the full path/fingerprint inventory; a confirmed self-write can
    update one row only after verified canonical readback and full freshness
    checks. No SQLite/index input, durable cache, cross-vault or actor authority.
    Any unexpected drift discards the hint and forces a fresh full scan.
    """

    def __init__(self, repository: VaultRepository, schema: dict[str, Any]) -> None:
        self.repository = repository
        self.schema = schema
        self._schema_signature = json.dumps(schema, sort_keys=True, ensure_ascii=False)
        self._snapshot: _VerifiedSnapshot | None = None
        self._lock = RLock()

    @contextmanager
    def scoped(self) -> Iterator[CanonicalMutationInventoryCache]:
        """Lock cache access for one Core/E3/Git mutation and readback."""
        with self._lock:
            token = _ACTIVE.set(
                _Scope(
                    repo=self.repository,
                    schema=self.schema,
                    schema_signature=self._schema_signature,
                    snapshot=self._snapshot,
                    index_path=None,
                )
            )
            try:
                yield self
            finally:
                current = _ACTIVE.get()
                self._snapshot = current.snapshot if current is not None else None
                _ACTIVE.reset(token)

    def confirm_write(self, *, path: str, stable_id: str) -> None:
        """Refresh only an E3+Git-confirmed target; unknown outcome keeps old proof.

        Never raise on a cache failure after an actual commit: Core receipts
        already prove the write. A failed hint is simply discarded.
        """
        scope = _ACTIVE.get()
        if (
            scope is None
            or scope.repo is not self.repository
            or scope.schema is not self.schema
            or scope.index_path is not None
            or scope.snapshot is None
        ):
            return
        prior = scope.snapshot
        scope.snapshot = None
        try:
            matching = prior.id_candidates(stable_id)
            if len(matching) != 1 or matching[0].path != path:
                return
            old = dict(zip(prior.paths, prior.versions, strict=True))
            current = self.repository.note_version_snapshot()
            if current.keys() != old.keys() or any(
                current[item] != version for item, version in old.items() if item != path
            ):
                return
            before = self.repository.file_version(path)
            note = parse_note(self.repository.read_text(path))
            validate_note(note, self.schema)
            if note.metadata["id"] != stable_id or self.repository.file_version(path) != before:
                return
            if self.repository.note_version_snapshot() != current:
                return
            position = prior.paths.index(path)
            rows = list(prior.rows)
            rows[position] = _MetadataRow(
                path=path,
                id=stable_id,
                type=note.metadata["type"],
                name=note.metadata["name"],
                aliases=tuple(note.metadata.get("aliases", [])),
                content_excerpt=note.content.strip()[:320],
                date=note.metadata.get("date"),
                deleted=note.metadata.get("deleted") is True,
            )
            versions = list(prior.versions)
            versions[position] = current[path]
            scope.snapshot = _VerifiedSnapshot(prior.paths, tuple(versions), tuple(rows))
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            # Never resurrect a stale or half-updated source inventory.
            scope.snapshot = None
