"""Actor-local at-most-once optional C4 advice; never an E3 write authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .delivery_results import DeliveryResultError, LocalDeliveryResultStore

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BYTES = 8192


class DeferredDiagnosticStore:
    """One durable intent and at most one response bound to immutable E3 bytes."""

    def __init__(self, root: Path):
        self.root = root

    @staticmethod
    def _binding(request_id: str, fingerprint: str, digest: str) -> dict[str, object]:
        LocalDeliveryResultStore._validate_request_id(request_id)
        if not isinstance(fingerprint, str) or not _HEX.fullmatch(fingerprint):
            raise DeliveryResultError("invalid diagnostic fingerprint")
        if not isinstance(digest, str) or not _HEX.fullmatch(digest):
            raise DeliveryResultError("invalid diagnostic receipt digest")
        return {
            "version": 1,
            "request_id": request_id,
            "fingerprint": fingerprint,
            "response_sha256": digest,
        }

    def _paths(self, request_id: str) -> tuple[Path, Path]:
        LocalDeliveryResultStore._validate_request_id(request_id)
        name = hashlib.sha256(request_id.encode()).hexdigest()
        return self.root / (name + ".claim"), self.root / (name + ".json")

    @staticmethod
    def _check(path: Path, expected: Mapping[str, object]) -> None:
        try:
            raw = path.read_bytes()
            if len(raw) > 1024 or json.loads(raw) != expected:
                raise DeliveryResultError("diagnostic receipt mismatch")
        except (OSError, ValueError) as exc:
            raise DeliveryResultError("diagnostic claim unavailable") from exc

    def _fsync_directory(self) -> None:
        """Persist linked claim/result names before their state is relied upon."""
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def claim(self, request_id: str, fingerprint: str, digest: str) -> bool:
        """Reserve at most once BEFORE a network call; crash means no retry."""
        identity = self._binding(request_id, fingerprint, digest)
        claim, _ = self._paths(request_id)
        claim.parent.mkdir(parents=True, exist_ok=True)
        # Publish a fully fsynced claim in one directory operation. A competing
        # worker must never observe a newly created, still-empty claim file.
        fd, tmp = tempfile.mkstemp(prefix=".c4claim.", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(json.dumps(identity, sort_keys=True).encode())
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(tmp, claim)
            except FileExistsError:
                self._check(claim, identity)
                return False
            self._fsync_directory()
            return True
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def finish(
        self,
        request_id: str,
        fingerprint: str,
        digest: str,
        diagnosis: Mapping[str, Any] | None,
    ) -> None:
        """Persist an immutable terminal advice, without modifying E3 response."""
        identity = self._binding(request_id, fingerprint, digest)
        claim, target = self._paths(request_id)
        self._check(claim, identity)
        if diagnosis is not None and (
            not isinstance(diagnosis, Mapping) or "request_id" in diagnosis
        ):
            raise DeliveryResultError("invalid diagnostic result")
        record = {
            **identity,
            "status": "completed" if diagnosis is not None else "unavailable",
            "diagnosis": dict(diagnosis) if diagnosis is not None else None,
        }
        data = json.dumps(record, ensure_ascii=False, sort_keys=True).encode()
        if len(data) > _MAX_BYTES:
            raise DeliveryResultError("diagnostic record too large")
        if target.exists():
            if target.read_bytes() != data:
                raise DeliveryResultError("diagnostic result cannot be replaced")
            return
        fd, tmp = tempfile.mkstemp(prefix=".c4.", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(tmp, target)
            except FileExistsError as exc:
                raise DeliveryResultError("diagnostic record already exists") from exc
            self._fsync_directory()
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def read(self, request_id: str, fingerprint: str, digest: str) -> dict[str, Any]:
        """A request from another actor or changed base receipt has no authority."""
        identity = self._binding(request_id, fingerprint, digest)
        claim, target = self._paths(request_id)
        if not claim.exists():
            return {"status": "unavailable"}
        self._check(claim, identity)
        if not target.exists():
            return {"status": "pending"}
        try:
            raw = target.read_bytes()
            if len(raw) > _MAX_BYTES:
                raise DeliveryResultError("diagnostic result too large")
            result = json.loads(raw)
        except (OSError, ValueError) as exc:
            raise DeliveryResultError("diagnostic result unreadable") from exc
        if (
            not isinstance(result, dict)
            or set(result) != {*identity, "status", "diagnosis"}
            or any(result[key] != value for key, value in identity.items())
            or result["status"] not in ("completed", "unavailable")
            or (result["status"] == "unavailable") != (result["diagnosis"] is None)
            or (result["diagnosis"] is not None and not isinstance(result["diagnosis"], dict))
        ):
            raise DeliveryResultError("diagnostic result invalid")
        if result["diagnosis"] is None:
            return {"status": "unavailable"}
        return {"status": "completed", "diagnosis": result["diagnosis"]}


def project_receipt_diagnostic_evidence(response: Mapping[str, Any]) -> dict[str, Any] | None:
    """Project only receipt-proven diagnosis facts; never publish note IDs or source.

    The caller must load an actor's immutable, SHA-verified E3 delivery.
    A missing or malformed E2 ledger cannot be replaced with model claims.
    """
    if not isinstance(response, Mapping):
        return None
    ledger = response.get("execution_ledger")
    status = response.get("status")
    if (
        not isinstance(ledger, dict)
        or ledger.get("version") != 1
        or ledger.get("request_id") != response.get("request_id")
        or status not in ("failed", "partial", "needs_attention")
        or ledger.get("status") != status
        or not isinstance(ledger.get("stages"), list)
        or len(ledger["stages"]) > 64
        or not isinstance(ledger.get("affected_stable_note_ids"), list)
        or len(ledger["affected_stable_note_ids"]) > 64
        or ledger["affected_stable_note_ids"] != response.get("affected_stable_note_ids")
    ):
        return None
    reason = (
        response.get("product_reason") or response.get("clarification_code") or "UNKNOWN_FAILURE"
    )
    if not isinstance(reason, str) or not 1 <= len(reason) <= 120:
        return None
    stages = []
    icons = {"router", "temporal", "planner", "tasks", "core", "git", "index", "pending", "result"}
    for item in ledger["stages"]:
        if not isinstance(item, dict) or item.get("outcome") not in ("failed", "unavailable"):
            continue
        stage = item.get("name")
        route = item.get("route_index")
        parent = item.get("parent_stage")
        view = item.get("stage_view")
        if (
            not isinstance(stage, str)
            or not 1 <= len(stage) <= 80
            or not isinstance(view, dict)
            or set(view) != {"version", "label", "icon"}
            or view["version"] != 1
            or not isinstance(view["label"], str)
            or not 1 <= len(view["label"]) <= 80
            or any(ch in view["label"] for ch in "\r\n<>")
            or not isinstance(view["icon"], str)
            or view["icon"] not in icons
            or not (route is None or type(route) is int and 0 <= route <= 31)
            or not (parent is None or isinstance(parent, str) and 1 <= len(parent) <= 80)
        ):
            return None
        stages.append(
            {
                "name": stage,
                "outcome": item["outcome"],
                "route_index": route,
                "parent_stage": parent,
                "stage_view": view,
            }
        )
    if not stages:
        return None
    return {
        "version": 1,
        "status": status,
        "reason_code": reason,
        "write_evidence": "SOME" if ledger["affected_stable_note_ids"] else "UNKNOWN",
        "stages": stages,
    }
