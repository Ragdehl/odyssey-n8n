"""Private, restartable 10k–50k source scan with a bounded SQLite *progress* manifest.

Operational checkpoint only: SQLite is NOT note/identity authority and is never
used to authorize a canonical write. Every completed receipt is independently
verified against physical Markdown and the frozen filesystem inventory.
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from odyssey_core.schema_retrospection import (
    _MAX_STAGED_ID_BYTES,
    _MAX_STAGED_SCAN_IDS,
    RetrospectionCursor,
    RetrospectionProgress,
    ScanKind,
    SchemaRetrospectionError,
    _scan_schema_sources_page,
    _staged_scan_inventory,
    _StagedScanPage,
)
from odyssey_core.storage import VaultRepository

_MAX_DATABASE_BYTES = 48_000_000
_LARGE_THRESHOLD = 10_000


def _connection(path: Path) -> sqlite3.Connection:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_size > _MAX_DATABASE_BYTES
    ):
        raise SchemaRetrospectionError("Unsafe large scan checkpoint")
    conn = sqlite3.connect(f"file:{path}?mode=rw", uri=True, timeout=5)
    conn.execute("PRAGMA trusted_schema=OFF")
    conn.execute("PRAGMA synchronous=FULL")
    return conn


def _progress(meta: dict[str, Any]) -> RetrospectionProgress:
    cursor = (
        RetrospectionCursor(meta["inventory_hash"], meta["scanned_paths"], meta["context_hash"])
        if meta["scanned_paths"] < meta["total_paths"]
        else None
    )
    return RetrospectionProgress(
        kind=meta["kind"],
        target_type_id=meta["target_type_id"],
        property_id=meta["property_id"],
        inventory_hash=meta["inventory_hash"],
        context_hash=meta["context_hash"],
        scanned_paths=meta["scanned_paths"],
        eligible_notes=meta["eligible_notes"],
        skipped_existing_values=meta["skipped_existing_values"],
        legacy_sources=meta["legacy_sources"],
        # Never materialize the entire set of source IDs into a 2 MB JSON.
        # Its exact membership is protected by the UNIQUE SQLite progress
        # table and fully reproved from canonical Markdown on completion.
        seen_note_ids=frozenset(),
        next_cursor=cursor,
        identity_proof="external",
    )


def _read_meta(conn: sqlite3.Connection, *, scope: str, job_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT payload FROM scan_meta WHERE id=1").fetchone()
    if row is None:
        raise SchemaRetrospectionError("Large scan metadata missing")
    meta = json.loads(row[0])
    required = {
        "version",
        "scope",
        "job_id",
        "kind",
        "target_type_id",
        "property_id",
        "inventory_hash",
        "context_hash",
        "total_paths",
        "scanned_paths",
        "eligible_notes",
        "skipped_existing_values",
        "legacy_sources",
        "seen_id_bytes",
    }
    if (
        not isinstance(meta, dict)
        or set(meta) != required
        or meta["version"] != 2
        or meta["scope"] != scope
        or meta["job_id"] != job_id
        or meta["kind"] not in ("discover_type", "backfill_property")
        or not isinstance(meta["target_type_id"], str)
        or (meta["property_id"] is not None and not isinstance(meta["property_id"], str))
        or any(
            not isinstance(meta[key], str) or len(meta[key]) != 64
            for key in ("inventory_hash", "context_hash")
        )
        or any(
            type(meta[key]) is not int or meta[key] < 0
            for key in (
                "total_paths",
                "scanned_paths",
                "eligible_notes",
                "skipped_existing_values",
                "legacy_sources",
                "seen_id_bytes",
            )
        )
        or not _LARGE_THRESHOLD < meta["total_paths"] <= _MAX_STAGED_SCAN_IDS
        or meta["scanned_paths"] > meta["total_paths"]
        or meta["eligible_notes"] + meta["skipped_existing_values"] > meta["scanned_paths"]
        or meta["legacy_sources"] > meta["eligible_notes"]
        or meta["seen_id_bytes"] > _MAX_STAGED_ID_BYTES
    ):
        raise SchemaRetrospectionError("Invalid large scan metadata")
    return meta


def create(
    path: Path,
    *,
    repository: VaultRepository,
    scope: str,
    job_id: str,
    max_notes: int = _MAX_STAGED_SCAN_IDS,
    schema: dict[str, Any],
    kind: ScanKind,
    target_type_id: str,
    property_id: str | None,
) -> bool:
    """Freeze N path/physical-version pairs once. Return false for small vaults."""
    snapshot = _staged_scan_inventory(repository)
    if len(snapshot.paths) <= _LARGE_THRESHOLD:
        return False
    if len(snapshot.paths) > max_notes:
        raise SchemaRetrospectionError("Physical scan capacity exceeded")
    if sum(len(item.encode("utf-8")) for item in snapshot.paths) > _MAX_STAGED_ID_BYTES:
        raise SchemaRetrospectionError("Physical path inventory exceeds memory budget")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".scan-large-", suffix=".sqlite3", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
        with closing(_connection(temporary)) as conn, conn:
            conn.execute(
                "CREATE TABLE manifest (seq INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, "
                "version_json TEXT NOT NULL)"
            )
            conn.execute("CREATE TABLE seen (note_id TEXT PRIMARY KEY)")
            conn.execute("CREATE TABLE scan_meta (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            conn.executemany(
                "INSERT INTO manifest(seq,path,version_json) VALUES(?,?,?)",
                (
                    (i, item, json.dumps(snapshot.versions[item], separators=(",", ":")))
                    for i, item in enumerate(snapshot.paths)
                ),
            )
            first_manifest = _StagedScanPage(
                offset=0,
                total_paths=len(snapshot.paths),
                files=tuple((p, snapshot.versions[p]) for p in snapshot.paths[:1]),
                inventory_hash=snapshot.inventory_hash,
            )
            first = _scan_schema_sources_page(
                repository=repository,
                schema=schema,
                kind=kind,
                target_type_id=target_type_id,
                property_id=property_id,
                limit=1,
                _staged_inventory=first_manifest,
            )
            meta = {
                "version": 2,
                "scope": scope,
                "job_id": job_id,
                "kind": kind,
                "target_type_id": target_type_id,
                "property_id": property_id,
                "inventory_hash": snapshot.inventory_hash,
                "context_hash": first.context_hash,
                "total_paths": len(snapshot.paths),
                "scanned_paths": 0,
                "eligible_notes": 0,
                "skipped_existing_values": 0,
                "legacy_sources": 0,
                "seen_id_bytes": 0,
            }
            conn.execute("INSERT INTO scan_meta(id,payload) VALUES(1,?)", (json.dumps(meta),))
            conn.commit()
        if repository.note_version_snapshot() != snapshot.versions:
            raise SchemaRetrospectionError("Vault changed during large scan initialization")
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _manifest_page(conn: sqlite3.Connection, offset: int, count: int) -> _StagedScanPage:
    meta = json.loads(conn.execute("SELECT payload FROM scan_meta WHERE id=1").fetchone()[0])
    rows = conn.execute(
        "SELECT path,version_json FROM manifest WHERE seq>=? ORDER BY seq LIMIT ?",
        (offset, count),
    ).fetchall()
    return _StagedScanPage(
        offset=offset,
        total_paths=meta["total_paths"],
        files=tuple((path, tuple(json.loads(version))) for path, version in rows),
        inventory_hash=meta["inventory_hash"],
    )


def _verify_final(
    conn: sqlite3.Connection,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    meta: dict[str, Any],
) -> None:
    """Reparse every canonical ID and fact; reject missing/forged progress.

    One O(N) read and two physical version snapshots at completion, not 2N
    snapshots across 50k/25 individual page calls. SQLite progress can never
    certify success alone.
    """
    frozen = _staged_scan_inventory(repository)
    if frozen.inventory_hash != meta["inventory_hash"] or len(frozen.paths) != meta["total_paths"]:
        raise SchemaRetrospectionError("Large scan physical inventory changed")
    seen: set[str] = set()
    eligible = skipped = legacy = scanned = 0
    cursor = None
    while True:
        page = _scan_schema_sources_page(
            repository=repository,
            schema=schema,
            kind=meta["kind"],
            target_type_id=meta["target_type_id"],
            property_id=meta["property_id"],
            limit=25,
            cursor=cursor,
            _staged_inventory=frozen,
        )
        if (
            page.context_hash != meta["context_hash"]
            or page.inventory_hash != meta["inventory_hash"]
        ):
            raise SchemaRetrospectionError("Large scan schema or inventory changed")
        if seen.intersection(page.source_note_ids):
            raise SchemaRetrospectionError("Duplicate canonical identity across pages")
        seen.update(page.source_note_ids)
        scanned += page.scanned_paths
        eligible += len(page.eligible_notes)
        skipped += page.skipped_existing_values
        legacy += sum(source.legacy_coverage_unverified for source in page.eligible_notes)
        cursor = page.next_cursor
        if cursor is None:
            break
    if repository.note_version_snapshot() != frozen.versions or (
        scanned,
        eligible,
        skipped,
        legacy,
        conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0],
    ) != (
        meta["scanned_paths"],
        meta["eligible_notes"],
        meta["skipped_existing_values"],
        meta["legacy_sources"],
        len(seen),
    ):
        raise SchemaRetrospectionError("Large scan progress disagrees with canonical Markdown")
    # SQLite identity membership is a work-progress cache, not authority. The
    # exact set is independently reparsed and checked at final publication.
    indexed_ids = (row[0] for row in conn.execute("SELECT note_id FROM seen"))
    if any(id_ not in seen for id_ in indexed_ids):
        raise SchemaRetrospectionError("Large scan cached identities disagree")


def advance(
    path: Path,
    *,
    repository: VaultRepository,
    scope: str,
    job_id: str,
    schema: dict[str, Any],
    kind: ScanKind,
    target_type_id: str,
    property_id: str | None,
    limit: int,
) -> RetrospectionProgress:
    """Advance one physical page atomically; zero canonical writes."""
    with closing(_connection(path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        # An operational receipt with a missing/modified metadata row is not
        # a new job. NEVER silently initialize it from live Markdown.
        meta = _read_meta(conn, scope=scope, job_id=job_id)
        if (meta["kind"], meta["target_type_id"], meta["property_id"]) != (
            kind,
            target_type_id,
            property_id,
        ):
            raise SchemaRetrospectionError("Large scan target changed")
        if meta["scanned_paths"] == meta["total_paths"]:
            # Recheck this completed receipt against the current physical vault.
            _verify_final(conn, repository=repository, schema=schema, meta=meta)
            return _progress(meta)

        offset = meta["scanned_paths"]
        page_manifest = _manifest_page(conn, offset, limit)
        page = _scan_schema_sources_page(
            repository=repository,
            schema=schema,
            kind=kind,
            target_type_id=target_type_id,
            property_id=property_id,
            cursor=(
                RetrospectionCursor(meta["inventory_hash"], offset, meta["context_hash"])
                if offset
                else None
            ),
            limit=limit,
            _staged_inventory=page_manifest,
        )
        if page.context_hash != meta["context_hash"]:
            raise SchemaRetrospectionError("Large scan schema changed")
        if len(page.source_note_ids) != len(set(page.source_note_ids)) or page.scanned_paths != len(
            page_manifest.files
        ):
            raise SchemaRetrospectionError("Invalid large scan page")
        if any(
            not isinstance(note_id, str) or not 1 <= len(note_id) <= 4096
            for note_id in page.source_note_ids
        ):
            raise SchemaRetrospectionError("Large scan identity exceeds bounded budget")
        meta["seen_id_bytes"] += sum(
            len(note_id.encode("utf-8")) for note_id in page.source_note_ids
        )
        if meta["seen_id_bytes"] > _MAX_STAGED_ID_BYTES:
            raise SchemaRetrospectionError("Large scan identity bytes exceed memory budget")
        try:
            conn.executemany(
                "INSERT INTO seen(note_id) VALUES(?)",
                ((item,) for item in page.source_note_ids),
            )
        except sqlite3.IntegrityError as error:
            raise SchemaRetrospectionError("Duplicate canonical source identity") from error
        meta["scanned_paths"] += page.scanned_paths
        meta["eligible_notes"] += len(page.eligible_notes)
        meta["skipped_existing_values"] += page.skipped_existing_values
        meta["legacy_sources"] += sum(x.legacy_coverage_unverified for x in page.eligible_notes)
        if meta["scanned_paths"] == meta["total_paths"]:
            _verify_final(conn, repository=repository, schema=schema, meta=meta)
        conn.execute("UPDATE scan_meta SET payload=? WHERE id=1", (json.dumps(meta),))
        conn.commit()
        return _progress(meta)


def read(path: Path, *, scope: str, job_id: str) -> RetrospectionProgress:
    with closing(_connection(path)) as conn:
        meta = _read_meta(conn, scope=scope, job_id=job_id)
        return _progress(meta)
