"""Optional, root-bound diagnostic checkpoints for in-flight product deliveries."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

_MAX_RECORD_BYTES = 16 * 1024
_MAX_EVENTS = 64
_MAX_RECORDS = 500
_RETENTION = timedelta(days=30)
_MAX_SCAN_ENTRIES = 2_048
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_RECORD_FILENAME_PATTERN = re.compile(r"[0-9a-f]{64}\.json\Z")
_STAGES = frozenset(
    {
        "starting",
        "routing.started",
        "routing.ready",
        "temporal.started",
        "temporal.ready",
        "planner.started",
        "planner.ready",
        "action.retrieve.started",
        "action.delegate.started",
        "action.write.started",
        "finalizing",
        "delivery.result_persisted",
        "processing.returned",
        "failed_or_unknown",
    }
)


class ExecutionCheckpointError(RuntimeError):
    """Report an invalid, corrupt, or unavailable diagnostic checkpoint."""


class CheckpointOutcome(StrEnum):
    """Describe what one checkpoint milestone can safely claim."""

    MILESTONE_OBSERVED = "milestone_observed"
    RESULT_PERSISTED = "result_persisted"
    PROCESSING_RETURNED = "processing_returned"
    FAILED_OR_UNKNOWN = "failed_or_unknown"


class LocalExecutionCheckpointStore:
    """Persist bounded source-free diagnostic milestones per request under one actor root.

    The store is intentionally non-authoritative: it never resumes work, proves a mutation, or
    substitutes for ``LocalDeliveryResultStore``. Retention is deliberately limited to validated
    checkpoint files below this one actor root; it never inspects or cleans general user state.
    """

    def __init__(
        self,
        root: Path,
        *,
        max_records: int = _MAX_RECORDS,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """Bind diagnostics to one actor root with bounded retention and an injectable UTC clock.

        Args:
            root: Actor-selected directory used only for execution checkpoints.
            max_records: Maximum validated request histories retained below ``root``.
            now: Trusted aware clock used solely to decide checkpoint expiry.

        Raises:
            ValueError: If the record bound is invalid.
        """
        if not isinstance(root, Path):
            raise TypeError("checkpoint root must be a pathlib.Path")
        if not isinstance(max_records, int) or isinstance(max_records, bool) or max_records < 1:
            raise ValueError("checkpoint max_records must be positive")
        if now is not None and not callable(now):
            raise TypeError("checkpoint clock must be callable")
        self._root = root
        self._max_records = max_records
        self._now = now or (lambda: datetime.now(UTC))

    def record(
        self,
        request_id: str,
        stage: str,
        outcome: CheckpointOutcome,
        observed_at: str,
    ) -> dict[str, Any]:
        """Atomically append one safe milestone to a bounded rolling diagnostic history.

        Raises:
            ExecutionCheckpointError: If input, prior state, capacity, or storage is invalid.
        """
        self._validate_request_id(request_id)
        self._validate_stage(stage)
        if not isinstance(outcome, CheckpointOutcome):
            raise ExecutionCheckpointError("checkpoint outcome is invalid")
        self._validate_time(observed_at)
        with self._locked_root():
            path = self._path(request_id)
            previous = self._read(path, request_id) if self._exists(path) else None
            # One request emits many milestones; a full scan at each stage scales
            # poorly as retained diagnostic requests accumulate.
            if previous is None:
                self._prune(exclude=path, need_slot=True)
            if previous is None:
                sequence = 1
            else:
                sequence = previous["sequence"] + 1
            self._validate_stage_outcome(stage, outcome)
            event = {
                "sequence": sequence,
                "stage": stage,
                "outcome": outcome.value,
                "observed_at": observed_at,
            }
            history = ([] if previous is None else previous["events"]) + [event]
            truncated = bool(previous and previous["truncated"]) or len(history) > _MAX_EVENTS
            record = {
                "version": 1,
                "request_id": request_id,
                "stage": stage,
                "outcome": outcome.value,
                "sequence": sequence,
                "observed_at": observed_at,
                "events": history[-_MAX_EVENTS:],
                "truncated": truncated,
            }
            self._atomic_write(path, record)
            return dict(record)

    def load(self, request_id: str) -> dict[str, Any] | None:
        """Return the bounded validated milestone history, or ``None`` if absent."""
        self._validate_request_id(request_id)
        with self._locked_root(create=False):
            path = self._path(request_id)
            if not self._exists(path):
                return None
            record = self._read(path, request_id)
            if self._expired(record):
                self._unlink_validated(path, record)
                return None
            return record

    @contextmanager
    def _locked_root(self, *, create: bool = True) -> Iterator[None]:
        """Serialize cooperating checkpoint writers without touching other diagnostic state."""
        if self._root.exists() and self._root.is_symlink():
            raise ExecutionCheckpointError("checkpoint root is unsafe")
        if not self._root.exists() and not create:
            yield
            return
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            if self._root.is_symlink() or not self._root.is_dir():
                raise ExecutionCheckpointError("checkpoint root is unsafe")
            lock_path = self._root / ".retention.lock"
            descriptor = os.open(
                lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
            )
        except OSError as error:
            raise ExecutionCheckpointError("checkpoint store is unavailable") from error
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        except OSError as error:
            raise ExecutionCheckpointError("checkpoint store is unavailable") from error
        finally:
            os.close(descriptor)

    def _prune(self, *, exclude: Path, need_slot: bool) -> None:
        """Remove only expired or lowest-priority validated checkpoint records in this root."""
        # Scan once per new request, reusing validated records for eviction.
        records = []
        for path, record in self._validated_records():
            if path == exclude:
                continue
            if self._expired(record):
                self._unlink_validated(path, record)
            else:
                records.append((path, record))
        allowed = self._max_records - (1 if need_slot else 0)
        if allowed < 0:
            raise ExecutionCheckpointError("checkpoint store capacity is exhausted")
        if len(records) <= allowed:
            return
        records.sort(
            key=lambda item: (self._eviction_priority(item[1]), self._record_time(item[1]))
        )
        for path, record in records[: len(records) - allowed]:
            self._unlink_validated(path, record)

    def _validated_records(self) -> Iterator[tuple[Path, dict[str, Any]]]:
        """Yield only regular internally named records that fully validate and bind to their hash."""
        try:
            entries = self._root.iterdir()
            for count, path in enumerate(entries, start=1):
                if count > _MAX_SCAN_ENTRIES:
                    raise ExecutionCheckpointError("checkpoint store scan is unsafe")
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or _RECORD_FILENAME_PATTERN.fullmatch(path.name) is None
                ):
                    continue
                try:
                    raw = path.read_bytes()
                    if len(raw) > _MAX_RECORD_BYTES:
                        continue
                    value = json.loads(raw)
                    request_id = value.get("request_id") if isinstance(value, dict) else None
                    if not isinstance(request_id, str) or path != self._path(request_id):
                        continue
                    record = self._read(path, request_id)
                except (ExecutionCheckpointError, OSError, json.JSONDecodeError):
                    continue
                yield path, record
        except OSError as error:
            raise ExecutionCheckpointError("checkpoint store is unavailable") from error

    def _unlink_validated(self, path: Path, record: dict[str, Any]) -> None:
        """Unlink one just-validated internally issued checkpoint, failing closed if it changed."""
        if path.parent != self._root or path != self._path(record["request_id"]):
            raise ExecutionCheckpointError("checkpoint deletion is unsafe")
        if (
            path.is_symlink()
            or not path.is_file()
            or self._read(path, record["request_id"]) != record
        ):
            raise ExecutionCheckpointError("checkpoint deletion is unsafe")
        try:
            path.unlink()
        except OSError as error:
            raise ExecutionCheckpointError("checkpoint store is unavailable") from error

    def _read(self, path: Path, request_id: str) -> dict[str, Any]:
        try:
            if path.is_symlink() or not path.is_file():
                raise ExecutionCheckpointError("checkpoint is unsafe")
            raw = path.read_bytes()
            if len(raw) > _MAX_RECORD_BYTES:
                raise ExecutionCheckpointError("checkpoint is too large")
            value = json.loads(raw)
        except (OSError, json.JSONDecodeError) as error:
            raise ExecutionCheckpointError("checkpoint is unavailable") from error
        if not isinstance(value, dict) or set(value) != {
            "version",
            "request_id",
            "stage",
            "outcome",
            "sequence",
            "observed_at",
            "events",
            "truncated",
        }:
            raise ExecutionCheckpointError("checkpoint is invalid")
        try:
            self._validate_request_id(value["request_id"])
            self._validate_stage(value["stage"])
            CheckpointOutcome(value["outcome"])
            if type(value["sequence"]) is not int or not 1 <= value["sequence"] <= 2**31 - 1:
                raise ExecutionCheckpointError("checkpoint is invalid")
            self._validate_time(value["observed_at"])
            self._validate_stage_outcome(value["stage"], CheckpointOutcome(value["outcome"]))
            if value["request_id"] != request_id or type(value["truncated"]) is not bool:
                raise ExecutionCheckpointError("checkpoint is invalid")
            events = value["events"]
            if not isinstance(events, list) or not 1 <= len(events) <= _MAX_EVENTS:
                raise ExecutionCheckpointError("checkpoint is invalid")
            for ordinal, event in enumerate(events):
                if not isinstance(event, dict) or set(event) != {
                    "sequence",
                    "stage",
                    "outcome",
                    "observed_at",
                }:
                    raise ExecutionCheckpointError("checkpoint is invalid")
                if type(event["sequence"]) is not int or event["sequence"] != (
                    value["sequence"] - len(events) + ordinal + 1
                ):
                    raise ExecutionCheckpointError("checkpoint is invalid")
                self._validate_stage(event["stage"])
                self._validate_stage_outcome(event["stage"], CheckpointOutcome(event["outcome"]))
                self._validate_time(event["observed_at"])
            if events[-1] != {
                "sequence": value["sequence"],
                "stage": value["stage"],
                "outcome": value["outcome"],
                "observed_at": value["observed_at"],
            }:
                raise ExecutionCheckpointError("checkpoint is invalid")
            if value["truncated"] != (value["sequence"] > len(events)):
                raise ExecutionCheckpointError("checkpoint is invalid")
        except (KeyError, TypeError, ValueError) as error:
            raise ExecutionCheckpointError("checkpoint is invalid") from error
        if value["version"] != 1:
            raise ExecutionCheckpointError("checkpoint is invalid")
        return value

    def _atomic_write(self, path: Path, record: dict[str, Any]) -> None:
        try:
            encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ExecutionCheckpointError("checkpoint is invalid") from error
        if len(encoded) > _MAX_RECORD_BYTES:
            raise ExecutionCheckpointError("checkpoint is too large")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as error:
            raise ExecutionCheckpointError("checkpoint store is unavailable") from error
        finally:
            if "temporary" in locals() and os.path.exists(temporary):
                os.unlink(temporary)

    def _path(self, request_id: str) -> Path:
        return self._root / f"{hashlib.sha256(request_id.encode('utf-8')).hexdigest()}.json"

    @staticmethod
    def _exists(path: Path) -> bool:
        """Return whether a regular checkpoint path exists without following symlinks."""
        return path.exists() or path.is_symlink()

    def _record_time(self, record: dict[str, Any]) -> datetime:
        """Parse one validated checkpoint timestamp into UTC for retention comparisons."""
        return datetime.fromisoformat(record["observed_at"]).astimezone(UTC)

    def _expired(self, record: dict[str, Any]) -> bool:
        """Return whether the trusted UTC clock is strictly beyond the 30-day retention boundary."""
        now = self._now()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ExecutionCheckpointError("checkpoint clock is invalid")
        return now.astimezone(UTC) - self._record_time(record) > _RETENTION

    @staticmethod
    def _eviction_priority(record: dict[str, Any]) -> int:
        """Prefer evicting terminal returned histories before unknown or incomplete diagnostics."""
        return (
            0
            if record["outcome"]
            in {
                CheckpointOutcome.RESULT_PERSISTED.value,
                CheckpointOutcome.PROCESSING_RETURNED.value,
            }
            else 1
        )

    @staticmethod
    def _validate_request_id(request_id: object) -> None:
        if not isinstance(request_id, str) or _REQUEST_ID_PATTERN.fullmatch(request_id) is None:
            raise ExecutionCheckpointError("checkpoint request ID is invalid")

    @staticmethod
    def _validate_stage(stage: object) -> None:
        if not isinstance(stage, str) or stage not in _STAGES:
            raise ExecutionCheckpointError("checkpoint stage is invalid")

    @staticmethod
    def _validate_time(value: object) -> None:
        if not isinstance(value, str):
            raise ExecutionCheckpointError("checkpoint time is invalid")
        try:
            if datetime.fromisoformat(value).tzinfo is None:
                raise ValueError
        except ValueError as error:
            raise ExecutionCheckpointError("checkpoint time is invalid") from error

    @staticmethod
    def _validate_stage_outcome(stage: str, outcome: CheckpointOutcome) -> None:
        """Prevent diagnostic status labels from claiming unsupported completion."""
        claimed = {
            "delivery.result_persisted": CheckpointOutcome.RESULT_PERSISTED,
            "processing.returned": CheckpointOutcome.PROCESSING_RETURNED,
            "failed_or_unknown": CheckpointOutcome.FAILED_OR_UNKNOWN,
        }
        required = claimed.get(stage, CheckpointOutcome.MILESTONE_OBSERVED)
        if outcome != required:
            raise ExecutionCheckpointError("checkpoint stage and outcome disagree")
