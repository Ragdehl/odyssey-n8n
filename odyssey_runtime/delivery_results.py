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

    @staticmethod
    def mutation_fingerprint(
        operation: str, payload: Mapping[str, Any], actor_state_root: Path
    ) -> str:
        """Bind a direct UI command to its canonical operation, payload and actor root.

        This deliberately stores a digest only.  The root is already the store
        namespace, but including it in the immutable binding makes a copied
        record unusable across actor roots as well.
        """
        if not isinstance(operation, str) or not operation:
            raise DeliveryResultError("mutation operation is invalid")
        if not isinstance(payload, Mapping):
            raise DeliveryResultError("mutation payload is invalid")
        if not isinstance(actor_state_root, Path):
            raise DeliveryResultError("mutation actor root is invalid")
        try:
            encoded = json.dumps(
                {
                    "actor_state_root": str(actor_state_root.resolve()),
                    "operation": operation,
                    "payload": dict(payload),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OSError) as error:
            raise DeliveryResultError("mutation payload is invalid") from error
        return hashlib.sha256(encoded).hexdigest()

    def claim_mutation(self, request_id: str, fingerprint: str) -> None:
        """Atomically reserve a direct mutation ID before any physical effects.

        When a worker dies after writing Markdown but before its final result
        is persisted, the durable claim remains. The next worker must NOT
        execute that delivery again: it needs explicit reconciliation. This
        uses the same actor-local delivery state, not another knowledge store.
        """
        self._validate_request_id(request_id)
        if not isinstance(fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
            raise DeliveryResultError("mutation fingerprint is invalid")
        claim_path = self._path(request_id).with_suffix(".claim")
        claim_path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(
            {"version": 1, "request_id": request_id, "fingerprint": fingerprint},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            descriptor = os.open(claim_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            # Even an identical pending request cannot be replayed until the
            # authoritative final receipt has been found or reconciled.
            raise DeliveryResultError(
                "mutation delivery has an unresolved prior attempt"
            ) from error
        except OSError as error:
            raise DeliveryResultError("mutation reservation is unavailable") from error
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            # Retain the claim on uncertain write/fsync, fail closed.
            raise DeliveryResultError("mutation reservation is unavailable") from error

    def inspect_mutation_claim(self, request_id: str, fingerprint: str) -> dict[str, object]:
        """Read-only E3 forensic status: never replay, release or repair a claim.

        A claim without a result cannot prove if a worker died before or after
        writing Markdown. It must remain blocked pending external reconciliation.
        No personal request, fingerprint or Note contents are returned.
        """
        self._validate_request_id(request_id)
        if not isinstance(fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
            raise DeliveryResultError("mutation fingerprint is invalid")
        result_path = self._path(request_id)
        claim_path = result_path.with_suffix(".claim")
        receipt = self.load(request_id, fingerprint)  # validate immutable receipt
        if not claim_path.exists():
            return {
                "state": "receipt_confirmed" if receipt is not None else "unseen",
                "receipt_verified": receipt is not None,
                "claim_pending": False,
                "replay_permitted": receipt is not None,
            }
        try:
            raw = claim_path.read_bytes()
            if len(raw) > 4096:
                raise ValueError("claim exceeds budget")
            claim = json.loads(raw)
        except (OSError, ValueError, TypeError) as error:
            raise DeliveryResultError("mutation claim is unavailable or invalid") from error
        if (
            not isinstance(claim, dict)
            or set(claim) != {"version", "request_id", "fingerprint"}
            or claim.get("version") != 1
            or claim.get("request_id") != request_id
            or claim.get("fingerprint") != fingerprint
        ):
            raise DeliveryResultError("mutation claim is conflicting or invalid")
        return {
            "state": "receipt_confirmed_with_stale_claim"
            if receipt is not None
            else "unresolved_attempt",
            "receipt_verified": receipt is not None,
            "claim_pending": True,
            "replay_permitted": receipt is not None,
        }

    def finish_mutation_claim(self, request_id: str) -> None:
        """Best-effort cleanup only after the immutable receipt exists."""
        if not self._path(request_id).exists():
            raise DeliveryResultError("mutation cannot finish before receipt")
        try:
            self._path(request_id).with_suffix(".claim").unlink(missing_ok=True)
        except OSError:
            # Completed receipt takes precedence on all later replay checks.
            pass

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
            # ``replace`` is unsafe here: two processes can both observe an absent path and the
            # later one would silently replace the first semantic outcome.  A hard link creates
            # the destination atomically on this same state filesystem and therefore refuses the
            # loser without changing the authoritative first result.
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                raise DeliveryResultError("completed delivery result already exists") from error
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
