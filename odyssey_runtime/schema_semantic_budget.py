"""Durable pre-call reservations for one actor-bound property campaign.

A reservation may be charged even if the provider fails before responding.
The receipt contains IDs and counters only, never note text or model output.
This limits outbound SDK calls, NOT actual dollars/tokens or provider billing.
"""

from __future__ import annotations

import fcntl
import hmac
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .schema_backfill_interpreter import SemanticPropertyInterpreter
from .schema_backfill_jobs import LocalBackfillJob, LocalBackfillJobError, SemanticBudgetStopped


class SemanticCallLedger:
    """Private HMAC checkpoint shared across every child journal of a campaign."""

    def __init__(self, *, worker: LocalBackfillJob, campaign_id: str, limit: int):
        if (
            not isinstance(worker, LocalBackfillJob)
            or type(limit) is not int
            or not 1 <= limit <= 36
        ):
            raise LocalBackfillJobError("Invalid approved semantic call cap")
        self.worker = worker
        self.campaign_id = campaign_id
        self.limit = limit
        self.path = worker._path(campaign_id).with_suffix(".semantic-budget.json")

    @contextmanager
    def _lock(self) -> Iterator[None]:
        root = self.worker.root
        path = root / ".semantic-budget.lock"
        if root.is_symlink() or path.is_symlink():
            raise LocalBackfillJobError("Unsafe semantic budget lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise LocalBackfillJobError("Unsafe semantic budget lock")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _read(self) -> dict[str, Any]:
        fresh = {
            "version": 1,
            "scope": self.worker.scope,
            "schema_hash": self.worker.schema_hash,
            "campaign_id": self.campaign_id,
            "limit": self.limit,
            "calls": 0,
            "notes": {},
        }
        if self.path.is_symlink():
            raise LocalBackfillJobError("Unsafe semantic budget link")
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return fresh
        try:
            with os.fdopen(fd, "rb") as stream:
                meta = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(meta.st_mode)
                    or meta.st_uid != os.getuid()
                    or meta.st_nlink != 1
                    or stat.S_IMODE(meta.st_mode) != 0o600
                    or meta.st_size > 200_000
                ):
                    raise LocalBackfillJobError("Unsafe semantic budget receipt")
                stored = json.load(stream)
        except (OSError, ValueError, UnicodeError, RecursionError) as error:
            raise LocalBackfillJobError("Unreadable semantic budget receipt") from error
        if not isinstance(stored, dict):
            raise LocalBackfillJobError("Invalid semantic budget receipt")
        digest = stored.pop("_integrity", None)
        if not isinstance(digest, str) or not hmac.compare_digest(
            digest, self.worker._integrity(stored)
        ):
            raise LocalBackfillJobError("Semantic budget HMAC mismatch")
        if (
            set(stored) != set(fresh)
            or any(
                stored[k] != fresh[k]
                for k in ("version", "scope", "schema_hash", "campaign_id", "limit")
            )
            or type(stored["calls"]) is not int
            or not 0 <= stored["calls"] <= self.limit
            or not isinstance(stored["notes"], dict)
            or len(stored["notes"]) > self.limit
            or any(
                not isinstance(k, str)
                or not 1 <= len(k) <= 4096
                or type(n) is not int
                or not 1 <= n <= 2
                for k, n in stored["notes"].items()
            )
            or sum(stored["notes"].values()) != stored["calls"]
        ):
            raise LocalBackfillJobError("Invalid semantic budget counters or scope")
        return stored

    def can_attempt(self, note_id: str) -> bool:
        with self._lock():
            record = self._read()
            return note_id not in record["notes"] and record["calls"] < self.limit

    def reserve(self, note_id: str, expected_previous_calls: int) -> None:
        """Fsync signed reservation BEFORE dispatching each real SDK request."""
        with self._lock():
            record = self._read()
            if (
                not isinstance(note_id, str)
                or not 1 <= len(note_id) <= 4096
                or record["calls"] >= self.limit
                or record["notes"].get(note_id, 0) != expected_previous_calls
                or not 0 <= expected_previous_calls < 2
            ):
                raise SemanticBudgetStopped(
                    "Semantic campaign call budget exhausted or already attempted"
                )
            record["calls"] += 1
            record["notes"][note_id] = expected_previous_calls + 1
            self.worker._write(self.path, record)

    def status(self) -> dict[str, int]:
        with self._lock():
            record = self._read()
            return {"reserved_calls": record["calls"], "call_limit": self.limit}


class BudgetedSemanticInterpreter:
    """Use existing two-pass interpreter, with durable reservations per call."""

    def __init__(self, *, interpreter: SemanticPropertyInterpreter, ledger: SemanticCallLedger):
        if not isinstance(interpreter, SemanticPropertyInterpreter):
            raise LocalBackfillJobError("Invalid semantic interpreter")
        self.interpreter = interpreter
        self.ledger = ledger

    def can_attempt(self, note_id: str) -> bool:
        return self.ledger.can_attempt(note_id)

    def propose_and_review(self, *, source: Any, type_id: str, property_definition: dict[str, Any]):
        if not self.can_attempt(source.note_id):
            raise SemanticBudgetStopped("Semantic source already attempted or budget exhausted")
        ledger = self.ledger
        gateway = self.interpreter.gateway

        class _ReservedGateway:
            calls = 0

            def _complete(self, **kwargs):
                ledger.reserve(source.note_id, self.calls)
                self.calls += 1
                return gateway._complete(**kwargs)

        return SemanticPropertyInterpreter(_ReservedGateway()).propose_and_review(
            source=source, type_id=type_id, property_definition=property_definition
        )
