"""Private device-local journal for autonomous property-enrichment writes.

Stage all source identities while the Markdown inventory is stable. Each
advance re-reads one canonical Note and records intent BEFORE a physical edit.
No model output or source body is persisted in the journal.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from odyssey_core.notes import parse_note, validate_note
from odyssey_core.schema_auto_backfill import AutomaticPropertyBackfill, choose_explicit_backfill
from odyssey_core.schema_retrospection import (
    SchemaRetrospectionError,
    accumulate_schema_scan,
    reload_staged_backfill_source,
    scan_schema_sources,
)
from odyssey_core.storage import VaultRepository
from odyssey_runtime.schema_backfill_interpreter import SemanticPropertyInterpreter

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_GIT_SHA = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})\Z")
_REQ = re.compile(r"schema-[a-f0-9]{16}-[0-9]{5}\Z")
_DONE = {"updated", "no_evidence", "ambiguous", "stale", "deferred", "already_present"}
_LIMIT = 10000
_BYTES = 8000000


class LocalBackfillJobError(RuntimeError):
    """A local progress state cannot be trusted or safely resumed."""


class LocalBackfillJob:
    """Actor/vault-bound writer. Requires an explicit foreground advance."""

    def __init__(
        self,
        *,
        state_root: Path,
        repository: VaultRepository,
        writer: AutomaticPropertyBackfill,
        actor_id: str,
    ) -> None:
        if (
            not isinstance(state_root, Path)
            or not state_root.is_dir()
            or state_root.is_symlink()
            or not isinstance(repository, VaultRepository)
            or not isinstance(writer, AutomaticPropertyBackfill)
            or writer.repository.root != repository.root
            or not isinstance(actor_id, str)
            or not 1 <= len(actor_id) <= 256
        ):
            raise LocalBackfillJobError("Trusted local profile unavailable")
        root = state_root.resolve(strict=True)
        vault = repository.root
        if root.is_relative_to(vault) or vault.is_relative_to(root):
            raise LocalBackfillJobError("Progress must be outside Markdown vault")
        self.root = root / "schema-backfill-jobs"
        if self.root.is_symlink():
            raise LocalBackfillJobError("Unsafe job directory")
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.root.chmod(0o700)
        self.repository = repository
        self.writer = writer
        self.scope = hashlib.sha256(
            json.dumps([actor_id, str(vault), vault.stat().st_dev, vault.stat().st_ino]).encode()
        ).hexdigest()
        self.schema_hash = hashlib.sha256(
            json.dumps(writer.schema, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def stage(self, *, job_id: str, type_id: str, property_id: str) -> dict[str, Any]:
        """Finish a consistent source scan before any mutation (max 2000)."""
        # Do not publish a plan that can never write because the property
        # is not optional. The canonical scanner independently checks IDs.
        definitions = [
            prop
            for note_type in self.writer.schema["types"]
            if note_type["id"] == type_id
            for prop in note_type["properties"]
            if prop["id"] == property_id
        ]
        if len(definitions) != 1 or definitions[0].get("required", False):
            raise LocalBackfillJobError("Only registered optional properties can be enriched")
        path = self._path(job_id)
        with self._lock():
            existing = self._read(path, job_id)
            if existing is not None:
                self._target(existing, type_id, property_id)
                return self._summary(existing)
            cursor = None
            progress = None
            rows: list[dict[str, Any]] = []
            while True:
                page = scan_schema_sources(
                    repository=self.repository,
                    schema=self.writer.schema,
                    kind="backfill_property",
                    target_type_id=type_id,
                    property_id=property_id,
                    cursor=cursor,
                    limit=25,
                )
                progress = accumulate_schema_scan(page, progress)
                rows.extend(
                    {
                        "id": note.note_id,
                        "path": note.path,
                        "hash": note.source_hash,
                        "revision": note.revision,
                        "status": "pending",
                        "request": None,
                        "digest": None,
                        "undo": None,
                    }
                    for note in page.eligible_notes
                )
                if len(rows) > _LIMIT:
                    raise LocalBackfillJobError("Local plan source capacity exceeded")
                cursor = page.next_cursor
                if cursor is None:
                    break
            record = {
                "version": 1,
                "scope": self.scope,
                "schema_hash": self.schema_hash,
                "job_id": job_id,
                "type_id": type_id,
                "property_id": property_id,
                "inventory_hash": progress.inventory_hash,
                "rows": rows,
            }
            self._write(path, record)
            return self._summary(record)

    def status(self, job_id: str) -> dict[str, Any] | None:
        path = self._path(job_id)
        with self._lock():
            data = self._read(path, job_id)
            return None if data is None else self._summary(data)

    def advance(
        self,
        *,
        job_id: str,
        type_id: str,
        property_id: str,
        actor: dict[str, str | None],
        now: str,
        interpreter: SemanticPropertyInterpreter | None = None,
    ) -> dict[str, Any]:
        """Apply at most one source; safely stop on unknown write outcome."""
        path = self._path(job_id)
        with self._lock():
            record = self._required(path, job_id)
            self._target(record, type_id, property_id)
            index = next(
                (
                    i
                    for i, row in enumerate(record["rows"])
                    if row["status"] not in _DONE
                    or (interpreter is not None and row["status"] == "deferred")
                ),
                None,
            )
            if index is None:
                return self._summary(record)
            row = record["rows"][index]
            if row["status"] == "writing":
                # If evidence fully proves a commit or absence of a write,
                # recover autonomously. Only unresolved ambiguity needs attention.
                self._reconcile_locked(record, row, path, type_id, property_id)
                return self._summary(record)
            if row["status"] not in {"pending", "deferred"}:
                raise LocalBackfillJobError("Unexpected progress status")
            row["status"] = "interpreting"
            self._write(path, record)
            try:
                source = reload_staged_backfill_source(
                    repository=self.repository,
                    schema=self.writer.schema,
                    path=row["path"],
                    note_id=row["id"],
                    source_hash=row["hash"],
                    revision=row["revision"],
                    type_id=type_id,
                    property_id=property_id,
                )
                definition = next(
                    prop
                    for kind in self.writer.schema["types"]
                    if kind["id"] == type_id
                    for prop in kind["properties"]
                    if prop["id"] == property_id
                )
                choice = choose_explicit_backfill(source, type_id=type_id, definition=definition)
                reviewed = None
                if choice.status != "auto":
                    if interpreter is not None:
                        reviewed = interpreter.propose_and_review(
                            source=source, type_id=type_id, property_definition=definition
                        )
                    if reviewed is None:
                        row["status"] = (
                            "deferred"
                            if interpreter is None
                            else "ambiguous"
                            if choice.status == "ambiguous"
                            else "no_evidence"
                        )
                        self._write(path, record)
                        return self._summary(record)
                value = reviewed.value if reviewed is not None else choice.value
                if value is None:
                    raise LocalBackfillJobError("Missing grounded value")
                row["digest"] = self._digest(value)
                row["request"] = (
                    f"schema-{hashlib.sha256(f'{self.scope}:{job_id}'.encode()).hexdigest()[:16]}-{index:05d}"
                )
                row["status"] = "writing"
                self._write(path, record)
                receipt = self.writer.apply(
                    source=source,
                    type_id=type_id,
                    property_id=property_id,
                    actor=actor,
                    now=now,
                    request_id=row["request"],
                    reviewed_semantic=reviewed,
                )
                if receipt.status not in _DONE:
                    raise LocalBackfillJobError("Unexpected write receipt")
                if receipt.status == "updated" and not receipt.undo_commit:
                    raise LocalBackfillJobError("Write lacks recovery evidence")
                row["status"] = receipt.status
                row["undo"] = receipt.undo_commit
                if receipt.status != "updated":
                    # Non-write receipts must not retain a misleading
                    # in-flight intention after their CAS rejection.
                    row["request"] = None
                    row["digest"] = None
                self._write(path, record)
                return self._summary(record)
            except SchemaRetrospectionError:
                row["status"] = "stale"
                self._write(path, record)
                return self._summary(record)
            except Exception:
                if row["status"] == "interpreting":
                    # Only model/read operations have happened, no physical write.
                    row["status"] = "pending"
                    self._write(path, record)
                # For status=writing never retry an unknown physical outcome.
                raise

    def reconcile(self, *, job_id: str, type_id: str, property_id: str) -> dict[str, Any]:
        """Resume only if Git+canonical Note prove the write or prove no write."""
        path = self._path(job_id)
        with self._lock():
            record = self._required(path, job_id)
            self._target(record, type_id, property_id)
            inflight = [row for row in record["rows"] if row["status"] == "writing"]
            if len(inflight) != 1:
                raise LocalBackfillJobError("No unique in-flight write")
            row = inflight[0]
            return self._reconcile_locked(record, row, path, type_id, property_id)

    def _reconcile_locked(
        self,
        record: dict[str, Any],
        row: dict[str, Any],
        path: Path,
        type_id: str,
        property_id: str,
    ) -> dict[str, Any]:
        commit = self._git_receipt(row["request"], row["path"])
        try:
            raw = self.repository.read_text(row["path"])
            note = parse_note(raw)
            validate_note(note, self.writer.schema)
        except (OSError, ValueError) as error:
            raise LocalBackfillJobError("Cannot reconcile canonical Note") from error
        if note.metadata.get("id") != row["id"] or note.metadata.get("type") != type_id:
            raise LocalBackfillJobError("Source identity changed")
        if (
            commit is None
            and note.metadata["revision"] == row["revision"]
            and hashlib.sha256(raw.encode("utf-8")).hexdigest() == row["hash"]
        ):
            row.update(status="pending", request=None, digest=None)
            self._write(path, record)
            return self._summary(record)
        if (
            commit is not None
            and note.metadata["revision"] == row["revision"] + 1
            and property_id in note.metadata
            and self._digest(note.metadata[property_id]) == row["digest"]
            and self._git_content(commit, row["path"]) == raw
        ):
            row.update(status="updated", undo=commit)
            self._write(path, record)
            return self._summary(record)
        raise LocalBackfillJobError("Ambiguous physical write; do not replay")

    def _git_receipt(self, request: str, path: str) -> str | None:
        if not isinstance(request, str) or _REQ.fullmatch(request) is None:
            raise LocalBackfillJobError("Invalid request receipt")
        result = subprocess.run(
            ["git", "log", "-n", "100", "--format=%H%x00%B%x00", "--", path],
            cwd=self.repository.root,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        parts = result.stdout.split("\x00")
        found = [
            parts[i].strip()
            for i in range(0, len(parts) - 1, 2)
            if f"Odyssey-Request: {request}" in parts[i + 1].splitlines()
        ]
        if len(found) > 1:
            raise LocalBackfillJobError("Repeated Git write receipt")
        return found[0] if found else None

    def _git_content(self, sha: str, path: str) -> str:
        result = subprocess.run(
            ["git", "show", f"{sha}:{path}"],
            cwd=self.repository.root,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        return result.stdout

    @staticmethod
    def _digest(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        statuses = [row["status"] for row in record["rows"]]
        counts = {
            key: statuses.count(key)
            for key in (
                "pending",
                "interpreting",
                "writing",
                "updated",
                "no_evidence",
                "ambiguous",
                "stale",
                "already_present",
                "deferred",
            )
        }
        phase = (
            "attention"
            if counts["writing"]
            else "in_progress"
            if counts["pending"] or counts["interpreting"]
            else "awaiting_ai"
            if counts["deferred"]
            else "complete"
        )
        return {"status": phase, "total": len(statuses), **counts}

    @staticmethod
    def _target(record: dict[str, Any], type_id: str, property_id: str) -> None:
        if record["type_id"] != type_id or record["property_id"] != property_id:
            raise LocalBackfillJobError("Job target changed")

    def _path(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or _ID.fullmatch(job_id) is None:
            raise LocalBackfillJobError("Invalid job ID")
        return self.root / f"{self.scope[:24]}-{job_id}.json"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        if self.root.is_symlink() or not self.root.is_dir():
            raise LocalBackfillJobError("Unsafe write journal root")
        fd = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise LocalBackfillJobError("Unsafe write lock")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _required(self, path: Path, job_id: str) -> dict[str, Any]:
        record = self._read(path, job_id)
        if record is None:
            raise LocalBackfillJobError("No staged local plan")
        return record

    def _read(self, path: Path, job_id: str) -> dict[str, Any] | None:
        if path.is_symlink():
            raise LocalBackfillJobError("Unsafe checkpoint link")
        if not path.exists():
            return None
        try:
            if not path.is_file() or path.stat().st_size > _BYTES:
                raise LocalBackfillJobError("Oversized checkpoint")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    data = json.load(handle)
            finally:
                os.close(fd)
        except (OSError, ValueError, RecursionError, UnicodeError) as error:
            raise LocalBackfillJobError("Unreadable journal") from error
        if (
            not isinstance(data, dict)
            or set(data)
            != {
                "version",
                "scope",
                "schema_hash",
                "job_id",
                "type_id",
                "property_id",
                "inventory_hash",
                "rows",
            }
            or type(data["version"]) is not int
            or data["version"] != 1
            or data["scope"] != self.scope
            or data["schema_hash"] != self.schema_hash
            or data["job_id"] != job_id
            or not isinstance(data["rows"], list)
            or len(data["rows"]) > _LIMIT
            or not isinstance(data["inventory_hash"], str)
            or _SHA.fullmatch(data["inventory_hash"]) is None
            or not isinstance(data["type_id"], str)
            or not isinstance(data["property_id"], str)
        ):
            raise LocalBackfillJobError("Journal does not match actor/schema")
        ids, paths = [], []
        for index, row in enumerate(data["rows"]):
            if (
                not isinstance(row, dict)
                or set(row)
                != {"id", "path", "hash", "revision", "status", "request", "digest", "undo"}
                or not isinstance(row["id"], str)
                or not 1 <= len(row["id"]) <= 4096
                or not isinstance(row["path"], str)
                or not 1 <= len(row["path"]) <= 4096
                or not isinstance(row["hash"], str)
                or _SHA.fullmatch(row["hash"]) is None
                or type(row["revision"]) is not int
                or row["revision"] < 1
                or row["status"] not in (_DONE | {"pending", "interpreting", "writing"})
                or (
                    row["request"] is not None
                    and (
                        not isinstance(row["request"], str)
                        or _REQ.fullmatch(row["request"]) is None
                    )
                )
                or (
                    row["digest"] is not None
                    and (
                        not isinstance(row["digest"], str) or _SHA.fullmatch(row["digest"]) is None
                    )
                )
                or (
                    row["undo"] is not None
                    and (
                        not isinstance(row["undo"], str) or _GIT_SHA.fullmatch(row["undo"]) is None
                    )
                )
                or (
                    row["status"] == "writing" and (row["request"] is None or row["digest"] is None)
                )
                or (
                    row["status"]
                    in {"pending", "interpreting", "no_evidence", "ambiguous", "stale", "deferred"}
                    and (
                        row["request"] is not None
                        or row["digest"] is not None
                        or row["undo"] is not None
                    )
                )
                or (
                    row["status"] == "updated"
                    and (row["request"] is None or row["digest"] is None or row["undo"] is None)
                )
            ):
                raise LocalBackfillJobError("Invalid journal row")
            if row["request"] is not None and row["request"] != (
                f"schema-{hashlib.sha256(f'{self.scope}:{job_id}'.encode()).hexdigest()[:16]}-{index:05d}"
            ):
                raise LocalBackfillJobError("Journal request is not bound to its row")
            ids.append(row["id"])
            paths.append(row["path"])
        if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
            raise LocalBackfillJobError("Duplicate candidate identity")
        if sum(row["status"] == "writing" for row in data["rows"]) > 1:
            raise LocalBackfillJobError("Multiple ambiguous writes")
        # Safe recovery after a crash during interpretation, BEFORE write intent.
        for row in data["rows"]:
            if row["status"] == "interpreting":
                row["status"] = "pending"
        return data

    def _write(self, path: Path, record: dict[str, Any]) -> None:
        if path.is_symlink():
            raise LocalBackfillJobError("Unsafe journal destination")
        temporary = None
        try:
            payload = json.dumps(
                record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if len(payload) > _BYTES:
                raise LocalBackfillJobError("Checkpoint capacity exceeded")
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.root,
                prefix=".write-",
                delete=False,
            ) as out:
                temporary = Path(out.name)
                os.fchmod(out.fileno(), 0o600)
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
            fd = os.open(self.root, os.O_DIRECTORY | os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as error:
            raise LocalBackfillJobError("Cannot persist progress") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
