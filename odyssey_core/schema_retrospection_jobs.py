"""Local, actor/profile-scoped durable checkpoints for read-only schema scans.

The canonical vault stays on the caller's device.  This service does not use
n8n, the network, providers, a scheduler or a second knowledge database.
The trusted app must select a distinct private vault/state pair for each
local profile (or authenticated hosted actor) before constructing this store.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from odyssey_core import schema_large_scan_jobs as large_scans
from odyssey_core.schema_retrospection import (
    RetrospectionCursor,
    RetrospectionProgress,
    ScanKind,
    SchemaRetrospectionError,
    accumulate_schema_scan,
    scan_schema_sources,
)
from odyssey_core.storage import VaultRepository

_JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_MAX_RECORD_BYTES = 2_000_000
_MAX_IDS = 10_000
_MAX_NOTE_ID_CHARS = 4_096


class LocalSchemaScanError(SchemaRetrospectionError):
    """Unsafe or stale local scan checkpoint; never silently restart."""


class LocalSchemaScanJobs:
    """Checkpoint one bounded scan page per call in private local app storage.

    The file is *operational device state*, not a Markdown Note and not sync
    content. A future mobile foreground worker may call advance repeatedly,
    or resume on another launch, without requiring an internet connection.
    No scanning starts automatically on import or app startup.
    """

    def __init__(self, *, state_root: Path, repository: VaultRepository, actor_id: str) -> None:
        if (
            not isinstance(state_root, Path)
            or not isinstance(repository, VaultRepository)
            or not isinstance(actor_id, str)
            or not 1 <= len(actor_id) <= 256
            or state_root.is_symlink()
            or not state_root.is_dir()
        ):
            raise LocalSchemaScanError("Trusted local profile storage unavailable")
        root = state_root.resolve(strict=True)
        vault = repository.root
        if root.is_relative_to(vault) or vault.is_relative_to(root):
            raise LocalSchemaScanError("Scan state must be separate from Markdown vault")
        if (root / "schema-retrospection-jobs").is_symlink():
            raise LocalSchemaScanError("Local scan directory is unsafe")
        self._root = root / "schema-retrospection-jobs"
        self._root.mkdir(mode=0o700, exist_ok=True)
        self._root.chmod(0o700)
        self._repository = repository
        # Derived only from trusted local profile identity and physical vault
        # root. A job from another device/actor/vault cannot be resumed here.
        metadata = vault.stat()
        self._scope = hashlib.sha256(
            json.dumps(
                [actor_id, str(vault), metadata.st_dev, metadata.st_ino],
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self._actor_key = hashlib.sha256(actor_id.encode("utf-8")).hexdigest()

    def advance(
        self,
        *,
        job_id: str,
        schema: dict[str, Any],
        kind: ScanKind,
        target_type_id: str,
        property_id: str | None = None,
        limit: int = 20,
    ) -> RetrospectionProgress:
        """Read one page and persist only audited counts/cursor/seen source IDs.

        Repeated completion is idempotent. If a note or schema changes between
        pages, scan_schema_sources rejects the stale snapshot without advancing
        state. Caller must explicitly create a fresh job ID to restart.
        """
        if type(limit) is not int or not 1 <= limit <= 25:
            raise LocalSchemaScanError("Invalid scan page limit")
        path = self._path(job_id)
        large_path = path.with_suffix(".sqlite3")
        with self._locked():
            if large_path.is_symlink():
                raise LocalSchemaScanError("Unsafe large scan checkpoint")
            if large_path.exists():
                if path.exists():
                    raise LocalSchemaScanError("Conflicting scan receipt versions")
                try:
                    return large_scans.advance(
                        large_path,
                        repository=self._repository,
                        scope=self._scope,
                        job_id=job_id,
                        schema=schema,
                        kind=kind,
                        target_type_id=target_type_id,
                        property_id=property_id,
                        limit=limit,
                    )
                except (
                    SchemaRetrospectionError,
                    OSError,
                    ValueError,
                    sqlite3.DatabaseError,
                ) as error:
                    raise LocalSchemaScanError("Large scan receipt invalid or stale") from error
            previous = self._read(path, job_id)
            if previous is None:
                try:
                    if large_scans.create(
                        large_path,
                        repository=self._repository,
                        scope=self._scope,
                        job_id=job_id,
                        schema=schema,
                        kind=kind,
                        target_type_id=target_type_id,
                        property_id=property_id,
                    ):
                        return large_scans.advance(
                            large_path,
                            repository=self._repository,
                            scope=self._scope,
                            job_id=job_id,
                            schema=schema,
                            kind=kind,
                            target_type_id=target_type_id,
                            property_id=property_id,
                            limit=limit,
                        )
                except (
                    SchemaRetrospectionError,
                    OSError,
                    ValueError,
                    sqlite3.DatabaseError,
                ) as error:
                    raise LocalSchemaScanError("Large scan staging unavailable") from error
            if previous is not None:
                if (previous.kind, previous.target_type_id, previous.property_id) != (
                    kind,
                    target_type_id,
                    property_id,
                ):
                    raise LocalSchemaScanError("Scan job cannot change its target")
                if previous.complete:
                    # Re-check the physical inventory and schema on a completed
                    # retry: never present an old receipt as current evidence.
                    try:
                        first = scan_schema_sources(
                            repository=self._repository,
                            schema=schema,
                            kind=kind,
                            target_type_id=target_type_id,
                            property_id=property_id,
                            limit=1,
                        )
                    except SchemaRetrospectionError as error:
                        raise LocalSchemaScanError("Scan receipt cannot be revalidated") from error
                    if (
                        first.inventory_hash != previous.inventory_hash
                        or first.context_hash != previous.context_hash
                    ):
                        raise LocalSchemaScanError("Stale completed scan receipt")
                    return previous
            cursor = previous.next_cursor if previous else None
            try:
                page = scan_schema_sources(
                    repository=self._repository,
                    schema=schema,
                    kind=kind,
                    target_type_id=target_type_id,
                    property_id=property_id,
                    limit=limit,
                    cursor=cursor,
                )
            except SchemaRetrospectionError as error:
                raise LocalSchemaScanError("Stale or invalid scan evidence") from error
            result = accumulate_schema_scan(page, previous)
            self._write(path, job_id, result)
            return result

    def read(self, job_id: str) -> RetrospectionProgress | None:
        """Return historical local checkpoint metadata; no vault revalidation."""
        path = self._path(job_id)
        with self._locked():
            large_path = path.with_suffix(".sqlite3")
            if large_path.is_symlink():
                raise LocalSchemaScanError("Unsafe large scan checkpoint")
            if large_path.exists():
                if path.exists():
                    raise LocalSchemaScanError("Conflicting scan receipt versions")
                try:
                    return large_scans.read(large_path, scope=self._scope, job_id=job_id)
                except (
                    SchemaRetrospectionError,
                    OSError,
                    ValueError,
                    sqlite3.DatabaseError,
                ) as error:
                    raise LocalSchemaScanError("Large scan receipt unreadable") from error
            return self._read(path, job_id)

    def _path(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or _JOB_ID.fullmatch(job_id) is None:
            raise LocalSchemaScanError("Invalid scan job ID")
        return self._root / f"{self._actor_key}-{job_id}.json"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        if self._root.is_symlink() or not self._root.is_dir():
            raise LocalSchemaScanError("Scan directory changed")
        lock = self._root / ".scan.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise LocalSchemaScanError("Scan lock is unsafe")
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)
        except OSError as error:
            raise LocalSchemaScanError("Scan storage lock unavailable") from error

    def _read(self, path: Path, job_id: str) -> RetrospectionProgress | None:
        if path.is_symlink():
            raise LocalSchemaScanError("Scan record is unsafe")
        if not path.exists():
            return None
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                size = os.fstat(fd)
                if not stat.S_ISREG(size.st_mode) or size.st_size > _MAX_RECORD_BYTES:
                    raise LocalSchemaScanError("Scan record is unsafe or oversized")
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    data = json.load(handle)
            finally:
                os.close(fd)
        except (OSError, ValueError, UnicodeError, RecursionError) as error:
            raise LocalSchemaScanError("Scan record unreadable") from error
        if (
            not isinstance(data, dict)
            or set(data) != {"version", "job_id", "scope", "progress"}
            or type(data["version"]) is not int
            or data["version"] != 1
            or data["job_id"] != job_id
            or data["scope"] != self._scope
        ):
            raise LocalSchemaScanError("Scan record scope or version mismatch")
        p = data["progress"]
        required = {
            "kind",
            "target_type_id",
            "property_id",
            "inventory_hash",
            "context_hash",
            "scanned_paths",
            "eligible_notes",
            "skipped_existing_values",
            "legacy_sources",
            "seen_note_ids",
            "next_cursor",
        }
        if not isinstance(p, dict) or set(p) != required:
            raise LocalSchemaScanError("Scan progress malformed")
        counts = ("scanned_paths", "eligible_notes", "skipped_existing_values", "legacy_sources")
        ids = p["seen_note_ids"]
        if (
            p["kind"] not in ("discover_type", "backfill_property")
            or not isinstance(p["target_type_id"], str)
            or not p["target_type_id"]
            or (p["property_id"] is not None and not isinstance(p["property_id"], str))
            or any(
                not isinstance(p[key], str) or _SHA.fullmatch(p[key]) is None
                for key in ("inventory_hash", "context_hash")
            )
            or any(type(p[key]) is not int or p[key] < 0 for key in counts)
            or not isinstance(ids, list)
            or len(ids) > _MAX_IDS
            or any(
                not isinstance(value, str) or not value or len(value) > _MAX_NOTE_ID_CHARS
                for value in ids
            )
            or len(ids) != len(set(ids))
            or not 0 <= p["eligible_notes"] <= p["scanned_paths"] <= 20_000
            or p["legacy_sources"] > p["eligible_notes"]
            or p["skipped_existing_values"] + p["eligible_notes"] > p["scanned_paths"]
            or len(ids) < p["eligible_notes"] + p["skipped_existing_values"]
        ):
            raise LocalSchemaScanError("Scan progress invalid")
        saved_cursor = p["next_cursor"]
        if saved_cursor is not None:
            if (
                not isinstance(saved_cursor, dict)
                or set(saved_cursor) != {"inventory_hash", "context_hash", "offset"}
                or saved_cursor["inventory_hash"] != p["inventory_hash"]
                or saved_cursor["context_hash"] != p["context_hash"]
                or type(saved_cursor["offset"]) is not int
                or saved_cursor["offset"] != p["scanned_paths"]
            ):
                raise LocalSchemaScanError("Scan continuation invalid")
            cursor = RetrospectionCursor(**saved_cursor)
        else:
            cursor = None
        return RetrospectionProgress(
            kind=p["kind"],
            target_type_id=p["target_type_id"],
            property_id=p["property_id"],
            inventory_hash=p["inventory_hash"],
            context_hash=p["context_hash"],
            scanned_paths=p["scanned_paths"],
            eligible_notes=p["eligible_notes"],
            skipped_existing_values=p["skipped_existing_values"],
            legacy_sources=p["legacy_sources"],
            seen_note_ids=frozenset(ids),
            next_cursor=cursor,
        )

    def _write(self, path: Path, job_id: str, progress: RetrospectionProgress) -> None:
        if path.is_symlink():
            raise LocalSchemaScanError("Scan record is unsafe")
        if len(progress.seen_note_ids) > _MAX_IDS or any(
            not isinstance(value, str) or not value or len(value) > _MAX_NOTE_ID_CHARS
            for value in progress.seen_note_ids
        ):
            raise LocalSchemaScanError("Scan Note identity exceeds checkpoint budget")
        cursor = progress.next_cursor
        payload = {
            "version": 1,
            "job_id": job_id,
            "scope": self._scope,
            "progress": {
                "kind": progress.kind,
                "target_type_id": progress.target_type_id,
                "property_id": progress.property_id,
                "inventory_hash": progress.inventory_hash,
                "context_hash": progress.context_hash,
                "scanned_paths": progress.scanned_paths,
                "eligible_notes": progress.eligible_notes,
                "skipped_existing_values": progress.skipped_existing_values,
                "legacy_sources": progress.legacy_sources,
                "seen_note_ids": sorted(progress.seen_note_ids),
                "next_cursor": (
                    {
                        "inventory_hash": cursor.inventory_hash,
                        "context_hash": cursor.context_hash,
                        "offset": cursor.offset,
                    }
                    if cursor is not None
                    else None
                ),
            },
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_RECORD_BYTES:
            raise LocalSchemaScanError("Scan checkpoint exceeds local budget")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self._root, prefix=".scan-", delete=False
            ) as handle:
                temporary = Path(handle.name)
                os.fchmod(handle.fileno(), 0o600)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as error:
            raise LocalSchemaScanError("Scan checkpoint could not be published") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
