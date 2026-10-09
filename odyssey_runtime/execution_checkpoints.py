"""Optional, root-bound diagnostic checkpoints for in-flight product deliveries."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

_MAX_RECORD_BYTES = 4 * 1024
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
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
        "completed",
        "failed_or_unknown",
    }
)


class ExecutionCheckpointError(RuntimeError):
    """Report an invalid, corrupt, or unavailable diagnostic checkpoint."""


class CheckpointOutcome(StrEnum):
    """Describe what the latest checkpoint can safely claim."""

    MILESTONE_OBSERVED = "milestone_observed"
    RESULT_PERSISTED = "result_persisted"
    COMPLETED = "completed"
    FAILED_OR_UNKNOWN = "failed_or_unknown"


class LocalExecutionCheckpointStore:
    """Persist one bounded latest-stage diagnostic record per request under one actor root.

    The store is intentionally non-authoritative: it never resumes work, proves a mutation, or
    substitutes for ``LocalDeliveryResultStore``. A full store fails closed for new request IDs;
    retention and deletion policy remain a product decision outside this opt-in boundary.
    """

    def __init__(self, root: Path, *, max_records: int = 64) -> None:
        """Bind the store to an actor-isolated root with a fixed non-retention count bound."""
        if not isinstance(root, Path):
            raise TypeError("checkpoint root must be a pathlib.Path")
        if not isinstance(max_records, int) or isinstance(max_records, bool) or max_records < 1:
            raise ValueError("checkpoint max_records must be positive")
        self._root = root
        self._max_records = max_records

    def record(
        self,
        request_id: str,
        stage: str,
        outcome: CheckpointOutcome,
        observed_at: str,
    ) -> dict[str, Any]:
        """Atomically replace one request's latest safe diagnostic milestone.

        Raises:
            ExecutionCheckpointError: If input, prior state, capacity, or storage is invalid.
        """
        self._validate_request_id(request_id)
        self._validate_stage(stage)
        if not isinstance(outcome, CheckpointOutcome):
            raise ExecutionCheckpointError("checkpoint outcome is invalid")
        self._validate_time(observed_at)
        path = self._path(request_id)
        previous = self._read(path) if path.exists() else None
        if previous is None:
            self._ensure_capacity()
            sequence = 1
        else:
            sequence = previous["sequence"] + 1
        record = {
            "version": 1,
            "request_id": request_id,
            "stage": stage,
            "outcome": outcome.value,
            "sequence": sequence,
            "observed_at": observed_at,
        }
        self._atomic_write(path, record)
        return dict(record)

    def load(self, request_id: str) -> dict[str, Any] | None:
        """Return a validated latest checkpoint, or ``None`` when no record exists."""
        self._validate_request_id(request_id)
        path = self._path(request_id)
        return self._read(path) if path.exists() else None

    def _ensure_capacity(self) -> None:
        """Refuse a new record once the no-retention capacity bound is reached."""
        if not self._root.exists():
            return
        try:
            count = sum(
                1 for item in self._root.iterdir() if item.is_file() and item.suffix == ".json"
            )
        except OSError as error:
            raise ExecutionCheckpointError("checkpoint store is unavailable") from error
        if count >= self._max_records:
            raise ExecutionCheckpointError("checkpoint store capacity is exhausted")

    def _read(self, path: Path) -> dict[str, Any]:
        try:
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
        }:
            raise ExecutionCheckpointError("checkpoint is invalid")
        try:
            self._validate_request_id(value["request_id"])
            self._validate_stage(value["stage"])
            CheckpointOutcome(value["outcome"])
            if not isinstance(value["sequence"], int) or value["sequence"] < 1:
                raise ExecutionCheckpointError("checkpoint is invalid")
            self._validate_time(value["observed_at"])
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
