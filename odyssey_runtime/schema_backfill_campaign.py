"""Bounded signed multi-journal campaign atop existing E3/Git backfill jobs.

Operational scope: a campaign is NOT a new canonical writer, permission
grant, model decision or standalone scheduler. The authenticated host checks
the existing actor/property approval on every public invocation.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from odyssey_runtime.schema_backfill_jobs import LocalBackfillJob, LocalBackfillJobError

_MAX_SEGMENTS = 50002
_DEFAULT_SEGMENT_SIZE = 1000
_COUNTERS = ("updated", "no_evidence", "ambiguous", "stale", "already_present", "deferred")


class LocalBackfillCampaign:
    """One actor/schema/approved property, sequential bounded signed journals."""

    def __init__(self, *, worker: LocalBackfillJob, segment_size: int = _DEFAULT_SEGMENT_SIZE):
        if (
            not isinstance(worker, LocalBackfillJob)
            or type(segment_size) is not int
            or not 1 <= segment_size <= 10000
        ):
            raise LocalBackfillJobError("Invalid bounded campaign configuration")
        self.worker = worker
        self.segment_size = segment_size

    def _path(self, campaign_id: str) -> Path:
        # Reuse the existing strict job ID, vault/actor scope and integrity key.
        path = self.worker._path(campaign_id)
        return path.with_suffix(".campaign.json")

    @staticmethod
    def _child_id(scope: str, campaign_id: str, index: int) -> str:
        return hashlib.sha256(
            f"schema-campaign:{scope}:{campaign_id}:{index}".encode()
        ).hexdigest()[:48]

    @contextmanager
    def _locked(self) -> Iterator[None]:
        path = self.worker.root / ".campaign.lock"
        if path.is_symlink() or self.worker.root.is_symlink():
            raise LocalBackfillJobError("Unsafe campaign lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            attrs = os.fstat(fd)
            if (
                not stat.S_ISREG(attrs.st_mode)
                or attrs.st_nlink != 1
                or attrs.st_uid != os.getuid()
                or stat.S_IMODE(attrs.st_mode) != 0o600
            ):
                raise LocalBackfillJobError("Unsafe campaign locking state")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _read(self, campaign_id: str) -> dict[str, Any] | None:
        path = self._path(campaign_id)
        if path.is_symlink():
            raise LocalBackfillJobError("Unsafe campaign checkpoint link")
        if not path.exists():
            return None
        try:
            # lstat and O_NONBLOCK both matter: even if a regular file is
            # replaced by a FIFO after lstat, opening it cannot hang.
            if not stat.S_ISREG(path.lstat().st_mode):
                raise LocalBackfillJobError("Unsafe campaign checkpoint type")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as source:
                attrs = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(attrs.st_mode)
                    or attrs.st_uid != os.getuid()
                    or attrs.st_nlink != 1
                    or stat.S_IMODE(attrs.st_mode) != 0o600
                    or attrs.st_size > 100_000
                ):
                    raise LocalBackfillJobError("Unsafe campaign checkpoint")
                record = json.load(source)
        except (OSError, ValueError, UnicodeError, RecursionError) as error:
            raise LocalBackfillJobError("Unreadable campaign checkpoint") from error
        if not isinstance(record, dict):
            raise LocalBackfillJobError("Campaign receipt invalid")
        integrity = record.pop("_integrity", None)
        if not isinstance(integrity, str) or not hmac.compare_digest(
            integrity, self.worker._integrity(record)
        ):
            raise LocalBackfillJobError("Campaign HMAC integrity mismatch")
        expected = {
            "version",
            "scope",
            "schema_hash",
            "campaign_id",
            "type_id",
            "property_id",
            "segment_size",
            "identity_hash",
            "eligibility_bitmap",
            "segment_index",
            "after_path",
            "active_segment",
            "active_frontier",
            "finished",
            "totals",
        }
        if (
            set(record) != expected
            or record["version"] != 1
            or record["scope"] != self.worker.scope
            or record["schema_hash"] != self.worker.schema_hash
            or record["campaign_id"] != campaign_id
            or type(record["segment_index"]) is not int
            or not 0 <= record["segment_index"] < _MAX_SEGMENTS
            or type(record["segment_size"]) is not int
            or not 1 <= record["segment_size"] <= 10000
            or record["segment_size"] != self.segment_size
            or type(record["finished"]) is not bool
            or not isinstance(record["type_id"], str)
            or not isinstance(record["property_id"], str)
            or (
                record["identity_hash"] is not None
                and (
                    not isinstance(record["identity_hash"], str)
                    or len(record["identity_hash"]) != 64
                )
            )
            or (
                record["eligibility_bitmap"] is not None
                and (
                    not isinstance(record["eligibility_bitmap"], str)
                    or len(record["eligibility_bitmap"]) > 8400
                )
            )
            or any(
                value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 4096)
                for value in (record["after_path"], record["active_frontier"])
            )
            or (
                record["active_segment"] is not None
                and record["active_segment"]
                != self._child_id(self.worker.scope, campaign_id, record["segment_index"])
            )
            or (record["active_segment"] is None and record["active_frontier"] is not None)
            or (record["finished"] and record["active_segment"] is not None)
            or not isinstance(record["totals"], dict)
            or set(record["totals"]) != {"total", *_COUNTERS}
            or any(
                type(count) is not int or count < 0 or count > _MAX_SEGMENTS * 10000
                for count in record["totals"].values()
            )
        ):
            raise LocalBackfillJobError("Invalid campaign state or owner")
        return record

    def _save(self, campaign_id: str, record: dict[str, Any]) -> None:
        self.worker._write(self._path(campaign_id), record)

    @staticmethod
    def _check_target(record: dict[str, Any], type_id: str, property_id: str) -> None:
        if (record["type_id"], record["property_id"]) != (type_id, property_id):
            raise LocalBackfillJobError("Campaign approved target changed")

    def _completed_write_paths(
        self,
        *,
        campaign_id: str,
        completed_segment_count: int,
        type_id: str,
        property_id: str,
    ) -> frozenset[str]:
        """Derive finished writes from authenticated child journals, not a new index.

        This is a bounded read of the already durable HMAC receipts (max 50k
        candidates). Missing, unfinished or altered evidence fails closed.
        """
        written: set[str] = set()
        with self.worker._lock():
            for index in range(completed_segment_count):
                child_id = self._child_id(self.worker.scope, campaign_id, index)
                receipt = self.worker._read(self.worker._path(child_id), child_id)
                if receipt is None:
                    raise LocalBackfillJobError("Campaign completed journal missing")
                self.worker._target(receipt, type_id, property_id)
                if any(
                    row["status"] in {"pending", "interpreting", "writing"}
                    for row in receipt["rows"]
                ):
                    raise LocalBackfillJobError("Campaign earlier journal is incomplete")
                for row in receipt["rows"]:
                    if row["status"] in {"updated", "already_present"}:
                        written.add(row["path"])
        return frozenset(written)

    def _summary(self, record: dict[str, Any]) -> dict[str, Any]:
        if record["finished"]:
            # Signed aggregate counts alone cannot certify completion if
            # an earlier child receipt has disappeared since the last call.
            self._completed_write_paths(
                campaign_id=record["campaign_id"],
                completed_segment_count=record["segment_index"],
                type_id=record["type_id"],
                property_id=record["property_id"],
            )
            # The final empty child proves that no further eligible sources
            # remained at the end; it too must remain an HMAC-authenticated
            # receipt rather than only a parent flag.
            final_id = self._child_id(
                self.worker.scope, record["campaign_id"], record["segment_index"]
            )
            with self.worker._lock():
                final_child = self.worker._read(self.worker._path(final_id), final_id)
                if final_child is None:
                    raise LocalBackfillJobError("Campaign terminal proof journal missing")
                self.worker._target(final_child, record["type_id"], record["property_id"])
                if final_child["rows"]:
                    raise LocalBackfillJobError("Campaign terminal proof contains pending sources")
        totals = dict(record["totals"])
        in_flight = {"pending": 0, "interpreting": 0, "writing": 0}
        active_id = record["active_segment"]
        if active_id is not None:
            current = self.worker.status(active_id)
            if current is None:
                raise LocalBackfillJobError("Campaign active journal is missing")
            for key in totals:
                totals[key] += current.get(key, 0)
            for key in in_flight:
                in_flight[key] = current.get(key, 0)
            status = current["status"]
        else:
            status = (
                "awaiting_ai"
                if totals["deferred"]
                else "complete"
                if record["finished"]
                else "in_progress"
            )
        if record["finished"]:
            status = "awaiting_ai" if totals["deferred"] else "complete"
        elif status in {"complete", "awaiting_ai"}:
            # A child is finished; the parent still owns more segments.
            status = "in_progress"
        return {
            "status": status,
            "segment": record["segment_index"],
            "finished": record["finished"],
            **totals,
            **in_flight,
        }

    def stage(self, *, campaign_id: str, type_id: str, property_id: str) -> dict[str, Any]:
        with self._locked():
            record = self._read(campaign_id)
            if record is None:
                record = {
                    "version": 1,
                    "scope": self.worker.scope,
                    "schema_hash": self.worker.schema_hash,
                    "campaign_id": campaign_id,
                    "type_id": type_id,
                    "property_id": property_id,
                    "segment_size": self.segment_size,
                    "identity_hash": None,
                    "eligibility_bitmap": None,
                    "segment_index": 0,
                    "after_path": None,
                    "active_segment": None,
                    "active_frontier": None,
                    "finished": False,
                    "totals": {"total": 0, **{key: 0 for key in _COUNTERS}},
                }
                self._save(campaign_id, record)
            self._check_target(record, type_id, property_id)
            if (
                not record["finished"]
                and record["segment_index"] == 0
                and record["active_segment"] is None
                and record["identity_hash"] is None
            ):
                # Preserve the historical stage() contract: prepare the first
                # bounded plan but NEVER perform an E3/Git write in stage().
                child_id = self._child_id(self.worker.scope, campaign_id, 0)
                child, frontier, identity, eligibility = self.worker._stage_segment(
                    job_id=child_id,
                    type_id=type_id,
                    property_id=property_id,
                    after_path=None,
                    max_candidates=self.segment_size,
                    expected_identity_hash=None,
                )
                record["identity_hash"] = identity
                record["eligibility_bitmap"] = eligibility
                if child["total"] == 0:
                    record["finished"] = True
                else:
                    if frontier is None:
                        raise LocalBackfillJobError("Campaign first frontier missing")
                    record["active_segment"] = child_id
                    record["active_frontier"] = frontier
                self._save(campaign_id, record)
            return self._summary(record)

    def status(self, campaign_id: str) -> dict[str, Any] | None:
        with self._locked():
            record = self._read(campaign_id)
            return None if record is None else self._summary(record)

    def advance(
        self,
        *,
        campaign_id: str,
        type_id: str,
        property_id: str,
        actor: dict[str, str | None],
        now: str,
        interpreter: Any = None,
    ) -> dict[str, Any]:
        """Advance at most one E3/Git write; stage a new segment only at boundary."""
        with self._locked():
            record = self._read(campaign_id)
            if record is None:
                raise LocalBackfillJobError("No staged campaign")
            self._check_target(record, type_id, property_id)
            if record["finished"]:
                return self._summary(record)
            if record["active_segment"] is not None:
                current = self.worker.status(record["active_segment"])
                if current is None:
                    raise LocalBackfillJobError("Campaign journal missing")
                if current["status"] in {"complete", "awaiting_ai"} and current["pending"] == 0:
                    for key in record["totals"]:
                        record["totals"][key] += current.get(key, 0)
                    record["after_path"] = record["active_frontier"]
                    record["segment_index"] += 1
                    record["active_segment"] = None
                    record["active_frontier"] = None
                    self._save(campaign_id, record)
                # An in-flight Git intent is handled by the existing child's
                # advance() reconciliation. If the outcome is ambiguous, that
                # primitive fails closed rather than reapplying the source.

            if record["active_segment"] is None:
                if record["segment_index"] >= _MAX_SEGMENTS:
                    raise LocalBackfillJobError("Campaign segment capacity exceeded")
                child_id = self._child_id(self.worker.scope, campaign_id, record["segment_index"])
                verified_completed_paths = self._completed_write_paths(
                    campaign_id=campaign_id,
                    completed_segment_count=record["segment_index"],
                    type_id=type_id,
                    property_id=property_id,
                )
                child, frontier, physical_identity, eligibility = self.worker._stage_segment(
                    job_id=child_id,
                    type_id=type_id,
                    property_id=property_id,
                    after_path=record["after_path"],
                    max_candidates=self.segment_size,
                    expected_identity_hash=record["identity_hash"],
                    expected_eligibility_bitmap=record["eligibility_bitmap"],
                    verified_completed_paths=verified_completed_paths,
                )
                if record["identity_hash"] is None:
                    record["identity_hash"] = physical_identity
                    record["eligibility_bitmap"] = eligibility
                if child["total"] == 0:
                    record["finished"] = True
                    self._save(campaign_id, record)
                    return self._summary(record)
                if frontier is None or frontier == record["after_path"]:
                    raise LocalBackfillJobError("Campaign frontier failed to advance")
                record["active_segment"] = child_id
                record["active_frontier"] = frontier
                self._save(campaign_id, record)

            self.worker.advance(
                job_id=record["active_segment"],
                type_id=type_id,
                property_id=property_id,
                actor=actor,
                now=now,
                interpreter=interpreter,
            )
            return self._summary(record)
