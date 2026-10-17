"""Request-scoped, physically verified metadata for repeated Core uniqueness checks.

This is NEVER a durable Note authority, nor an index-completeness claim. It
validates every Markdown Note on first use; each later use rechecks the whole
path set and physical versions. If any source changed, revalidate the vault.
Only the P4 runtime opts in; unrelated callers retain their existing paths.
"""

from __future__ import annotations

import json
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


_ACTIVE: ContextVar[_Scope | None] = ContextVar("odyssey_p4_verified_catalog", default=None)


@contextmanager
def scoped_verified_metadata_catalog() -> Iterator[None]:
    """Use per-delivery, never across users/requests, and opt-in only."""
    token = _ACTIVE.set(_Scope())
    try:
        yield
    finally:
        _ACTIVE.reset(token)


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
            if paths == snapshot.paths and all(
                repository.file_version(path) == version
                for path, version in zip(paths, snapshot.versions, strict=True)
            ):
                return snapshot
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
