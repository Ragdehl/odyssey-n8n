"""Durable replay records for completed logical mutation deliveries."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_MAX_RECORD_BYTES = 2 * 1024 * 1024
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


class DeliveryResultError(RuntimeError):
    """Report a corrupt, conflicting, or unavailable delivery-result record."""


class LocalDeliveryResultStore:
    """Persist bounded completed mutation results outside canonical Markdown.

    Records contain a hash binding instead of the user's request text. They are operational replay
    state: Markdown remains the knowledge authority, while a lost HTTP response can be recovered
    without planning or mutating the same logical delivery again.
    """

    def __init__(self, root: Path) -> None:
        """Bind this store to one already actor-isolated durable state root."""
        if not isinstance(root, Path):
            raise TypeError("delivery result root must be a pathlib.Path")
        self._root = root

    @staticmethod
    def fingerprint(request: str, conversation_id: str) -> str:
        """Return a non-reversible binding for one request and conversation pair."""
        if not isinstance(request, str) or not request.strip():
            raise DeliveryResultError("delivery request is invalid")
        if not isinstance(conversation_id, str) or not conversation_id:
            raise DeliveryResultError("delivery conversation is invalid")
        encoded = json.dumps(
            {"conversation_id": conversation_id, "request": request},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def load(self, request_id: str, fingerprint: str) -> dict[str, Any] | None:
        """Load a completed result or reject reuse/corruption of its request identity."""
        path = self._path(request_id)
        if not path.exists():
            return None
        record = self._read(path)
        if record["request_fingerprint"] != fingerprint:
            raise DeliveryResultError("request ID is already bound to another delivery")
        return dict(record["response"])

    def save(
        self, request_id: str, fingerprint: str, response: Mapping[str, Any], completed_at: str
    ) -> None:
        """Atomically create one immutable completed mutation result."""
        self._validate_request_id(request_id)
        if not isinstance(fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
            raise DeliveryResultError("delivery fingerprint is invalid")
        if not isinstance(response, Mapping) or response.get("request_id") != request_id:
            raise DeliveryResultError("delivery response is invalid")
        if not isinstance(completed_at, str) or not completed_at:
            raise DeliveryResultError("delivery completion time is invalid")
        response_value = dict(response)
        response_digest = self._response_digest(response_value)
        record = {
            "version": 1,
            "request_id": request_id,
            "request_fingerprint": fingerprint,
            "completed_at": completed_at,
            "response_sha256": response_digest,
            "response": response_value,
        }
        path = self._path(request_id)
        if path.exists():
            existing = self._read(path)
            if existing != record:
                raise DeliveryResultError("completed delivery result is immutable")
            return
        encoded = self._encode(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            # The execution coordinator is the single writer. Refuse an unexpected race rather
            # than replacing another process's completed result.
            if path.exists():
                raise DeliveryResultError("completed delivery result already exists")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            raw = path.read_bytes()
            if len(raw) > _MAX_RECORD_BYTES:
                raise DeliveryResultError("delivery result is too large")
            record = json.loads(raw)
        except (OSError, json.JSONDecodeError) as error:
            raise DeliveryResultError("delivery result is unavailable") from error
        if not isinstance(record, dict) or set(record) != {
            "version",
            "request_id",
            "request_fingerprint",
            "completed_at",
            "response_sha256",
            "response",
        }:
            raise DeliveryResultError("delivery result is invalid")
        request_id = record.get("request_id")
        self._validate_request_id(request_id)
        if (
            record.get("version") != 1
            or not isinstance(record.get("request_fingerprint"), str)
            or re.fullmatch(r"[0-9a-f]{64}", record["request_fingerprint"]) is None
            or not isinstance(record.get("completed_at"), str)
            or not record["completed_at"]
            or not isinstance(record.get("response"), dict)
            or record["response"].get("request_id") != request_id
            or record.get("response_sha256") != self._response_digest(record["response"])
        ):
            raise DeliveryResultError("delivery result is invalid")
        return record

    def _path(self, request_id: str) -> Path:
        self._validate_request_id(request_id)
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        return self._root / f"{digest}.json"

    @staticmethod
    def _response_digest(response: Mapping[str, Any]) -> str:
        try:
            encoded = json.dumps(
                response, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise DeliveryResultError("delivery response is not JSON-compatible") from error
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _encode(record: Mapping[str, Any]) -> bytes:
        try:
            encoded = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        except (TypeError, ValueError) as error:
            raise DeliveryResultError("delivery result is not JSON-compatible") from error
        if len(encoded) > _MAX_RECORD_BYTES:
            raise DeliveryResultError("delivery result is too large")
        return encoded

    @staticmethod
    def _validate_request_id(request_id: object) -> None:
        if not isinstance(request_id, str) or _REQUEST_ID_PATTERN.fullmatch(request_id) is None:
            raise DeliveryResultError("delivery request ID is invalid")
