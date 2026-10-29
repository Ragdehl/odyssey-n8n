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
_MANIFEST_CAPABILITY_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_DEFAULT_MANIFEST_CAPABILITIES = frozenset({"core", "tasks"})


class DeliveryResultError(RuntimeError):
    """Report a corrupt, conflicting, or unavailable delivery-result record."""


class LocalDeliveryResultStore:
    """Persist bounded completed mutation results outside canonical Markdown.

    Records contain a hash binding instead of the user's request text. They are operational replay
    state: Markdown remains the knowledge authority, while a lost HTTP response can be recovered
    without planning or mutating the same logical delivery again.
    """

    def __init__(
        self,
        root: Path,
        *,
        manifest_capabilities: frozenset[str] = _DEFAULT_MANIFEST_CAPABILITIES,
    ) -> None:
        """Bind actor-local state and a trusted list of registered Apps.

        The manifest is forensic, never write authorization. The default
        retains the historical Core+Tasks contract; only application
        composition may explicitly extend the accepted vocabulary.
        """
        if not isinstance(root, Path):
            raise TypeError("delivery result root must be a pathlib.Path")
        if (
            not isinstance(manifest_capabilities, frozenset)
            or not 1 <= len(manifest_capabilities) <= 64
            or any(
                not isinstance(name, str) or _MANIFEST_CAPABILITY_PATTERN.fullmatch(name) is None
                for name in manifest_capabilities
            )
        ):
            raise DeliveryResultError("registered manifest capability set is invalid")
        self._root = root
        self._manifest_capabilities = manifest_capabilities

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

    def begin_operation_manifest(
        self,
        request_id: str,
        fingerprint: str,
        source: str,
        groups: tuple[tuple[str, str, tuple[int, ...]], ...],
    ) -> None:
        """Persist immutable source-hash-only N-group topology BEFORE any WRITE.

        A manifest is operational forensic evidence, NEVER mutation authority.
        It cannot permit resumption of an unresolved E3 claim.
        """
        if (
            not isinstance(source, str)
            or not source.strip()
            or len(source) > 4096
            or not isinstance(groups, tuple)
            or not 2 <= len(groups) <= 16
        ):
            raise DeliveryResultError("operation source or group budget is invalid")
        if self.inspect_mutation_claim(request_id, fingerprint)["state"] != "unresolved_attempt":
            raise DeliveryResultError("operation manifest requires a pending E3 claim")
        normalized = []
        for ordinal, group in enumerate(groups):
            if (
                not isinstance(group, tuple)
                or len(group) != 3
                or group[0] not in self._manifest_capabilities
                or not isinstance(group[1], str)
                or not group[1].strip()
                or not isinstance(group[2], tuple)
                or any(
                    not isinstance(index, int)
                    or isinstance(index, bool)
                    or not 0 <= index < ordinal
                    for index in group[2]
                )
                or len(set(group[2])) != len(group[2])
            ):
                raise DeliveryResultError("operation group or dependency is invalid")
            normalized.append(
                {
                    "ordinal": ordinal,
                    "capability": group[0],
                    "source_sha256": hashlib.sha256(group[1].encode("utf-8")).hexdigest(),
                    "predecessors": list(group[2]),
                }
            )
        if "".join(part[1] for part in groups) != source:
            raise DeliveryResultError("operation manifest does not cover original source")
        self._atomic_operation_record(
            self._operation_path(request_id, "plan"),
            {
                "version": 1,
                "request_id": request_id,
                "fingerprint": fingerprint,
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "groups": normalized,
            },
        )

    def observe_operation_manifest(
        self,
        request_id: str,
        fingerprint: str,
        ordinal: int,
        capability: str,
        status: str,
        affected_ids: tuple[str, ...],
    ) -> None:
        """Durably observe a *returned* App result, not a provable WRITE receipt.

        This does NOT certify absent writes after a crash between persistence
        and this observation. All uncertain E3 claims remain non-replayable.
        """
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
            raise DeliveryResultError("operation ordinal is invalid")
        if status not in ("completed", "partial", "needs_attention", "failed"):
            raise DeliveryResultError("operation status is invalid")
        if status == "failed" and affected_ids:
            # Failure observations must not advertise successful mutations.
            raise DeliveryResultError("failed operation cannot claim affected IDs")
        if (
            not isinstance(affected_ids, tuple)
            or len(affected_ids) > 64
            or any(
                not isinstance(value, str) or not value or len(value) > 256
                for value in affected_ids
            )
            or len(set(affected_ids)) != len(affected_ids)
        ):
            raise DeliveryResultError("operation affected IDs are invalid")
        manifest = self._read_operation_record(self._operation_path(request_id, "plan"))
        if (
            manifest.get("request_id") != request_id
            or manifest.get("fingerprint") != fingerprint
            or manifest.get("version") != 1
        ):
            raise DeliveryResultError("operation manifest identity differs from E3 claim")
        groups = manifest.get("groups")
        if (
            not isinstance(groups, list)
            or ordinal >= len(groups)
            or groups[ordinal].get("ordinal") != ordinal
            or groups[ordinal].get("capability") != capability
        ):
            raise DeliveryResultError("operation does not match prepared scope")
        if self.inspect_mutation_claim(request_id, fingerprint)["state"] != "unresolved_attempt":
            raise DeliveryResultError("operation observation requires a pending E3 claim")
        for prior in range(ordinal):
            record = self._read_operation_record(self._operation_path(request_id, str(prior)))
            if record.get("status") != "completed":
                raise DeliveryResultError("prior operation was not completed")
        self._atomic_operation_record(
            self._operation_path(request_id, str(ordinal)),
            {
                "version": 1,
                "request_id": request_id,
                "fingerprint": fingerprint,
                "ordinal": ordinal,
                "capability": capability,
                "status": status,
                "affected_ids": list(affected_ids),
                "proof_level": "application_result_observed_not_physical_recovery_authority",
            },
        )

    def inspect_operation_manifest(self, request_id: str, fingerprint: str) -> dict[str, object]:
        """Source-free E3 diagnostic; never considers operations recoverable."""
        claim = self.inspect_mutation_claim(request_id, fingerprint)
        path = self._operation_path(request_id, "plan")
        if not path.exists() and not path.is_symlink():
            return {
                "manifest_present": False,
                "observed_operations": 0,
                "claim_state": claim["state"],
                "recovery_authorized": False,
            }
        manifest = self._read_operation_record(path)
        if manifest.get("fingerprint") != fingerprint or manifest.get("request_id") != request_id:
            raise DeliveryResultError("operation manifest fingerprint differs")
        groups = manifest.get("groups")
        if not isinstance(groups, list) or not 2 <= len(groups) <= 16:
            raise DeliveryResultError("operation manifest groups are invalid")
        observed = 0
        for ordinal in range(len(groups)):
            step = self._operation_path(request_id, str(ordinal))
            if not step.exists() and not step.is_symlink():
                break
            record = self._read_operation_record(step)
            if (
                record.get("request_id") != request_id
                or record.get("fingerprint") != fingerprint
                or record.get("ordinal") != ordinal
                or record.get("capability") != groups[ordinal].get("capability")
                or record.get("proof_level")
                != "application_result_observed_not_physical_recovery_authority"
            ):
                raise DeliveryResultError("operation observation identity is invalid")
            observed += 1
        return {
            "manifest_present": True,
            "planned_operations": len(groups),
            "observed_operations": observed,
            "claim_state": claim["state"],
            "recovery_authorized": False,
        }

    def _operation_path(self, request_id: str, suffix: str) -> Path:
        self._validate_request_id(request_id)
        if suffix != "plan" and (not suffix.isascii() or not suffix.isdecimal() or len(suffix) > 2):
            raise DeliveryResultError("operation path suffix is invalid")
        return self._path(request_id).with_suffix(f".operation-{suffix}.json")

    @staticmethod
    def _read_operation_record(path: Path) -> dict[str, Any]:
        try:
            if path.is_symlink() or not path.is_file():
                raise DeliveryResultError("operation record is unavailable or unsafe")
            data = path.read_bytes()
            if len(data) > 8192:
                raise DeliveryResultError("operation record exceeds budget")
            result = json.loads(data)
        except (OSError, ValueError, TypeError) as error:
            raise DeliveryResultError("operation record is invalid") from error
        if not isinstance(result, dict):
            raise DeliveryResultError("operation record is malformed")
        return result

    @staticmethod
    def _atomic_operation_record(path: Path, record: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.is_symlink():
            raise DeliveryResultError("operation record root is unsafe")
        encoded = json.dumps(
            dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded) > 8192:
            raise DeliveryResultError("operation record exceeds budget")
        if path.exists() or path.is_symlink():
            existing = LocalDeliveryResultStore._read_operation_record(path)
            if existing != dict(record):
                raise DeliveryResultError("operation receipt is immutable")
            return
        descriptor, temporary = tempfile.mkstemp(prefix=".odyssey-operation-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                raise DeliveryResultError(
                    "concurrent operation record was already written"
                ) from error
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

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
        if claim_path.is_symlink():
            raise DeliveryResultError("mutation claim is unsafe")
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

    def reconcile_confirmed_claim(self, request_id: str, fingerprint: str) -> dict[str, object]:
        """Reconcile ONLY an orphan reservation with a verified immutable result.

        This never examines or changes Markdown and never guesses whether a
        receipt-less attempt wrote zero, one or multiple Notes. Such attempts
        are reported unresolved and MUST NOT be resumed or re-executed.
        """
        prior = self.inspect_mutation_claim(request_id, fingerprint)
        if prior["state"] == "receipt_confirmed_with_stale_claim":
            self.finish_mutation_claim(request_id)
            current = self.inspect_mutation_claim(request_id, fingerprint)
            if current["receipt_verified"] is not True:
                raise DeliveryResultError("confirmed receipt disappeared during reconciliation")
            return {**current, "reconciled_confirmed_claim": True}
        return {**prior, "reconciled_confirmed_claim": False}

    def finish_mutation_claim(self, request_id: str) -> None:
        """Cleanup only a matching claim after verifying its complete durable receipt.

        A mere existing filename must not authorize deletion: the actual
        result checksum, request identity and original claim fingerprint must
        agree. A lost or tampered claim cannot be silently made replayable.
        """
        receipt_path = self._path(request_id)
        if not receipt_path.exists() or receipt_path.is_symlink():
            raise DeliveryResultError("mutation cannot finish before receipt")
        receipt = self._read(receipt_path)
        if receipt["request_id"] != request_id:
            raise DeliveryResultError("mutation result identity is invalid")
        claim_path = receipt_path.with_suffix(".claim")
        if not claim_path.exists() and not claim_path.is_symlink():
            return
        try:
            if claim_path.is_symlink() or not claim_path.is_file():
                raise DeliveryResultError("mutation claim is unsafe")
            raw = claim_path.read_bytes()
            if len(raw) > 4096:
                raise DeliveryResultError("mutation claim exceeds budget")
            claim = json.loads(raw)
        except (OSError, ValueError, TypeError) as error:
            raise DeliveryResultError("mutation claim is unavailable") from error
        if (
            not isinstance(claim, dict)
            or set(claim) != {"version", "request_id", "fingerprint"}
            or claim["version"] != 1
            or claim["request_id"] != request_id
            or claim["fingerprint"] != receipt["request_fingerprint"]
        ):
            raise DeliveryResultError("mutation claim does not match completed receipt")
        try:
            claim_path.unlink()
        except OSError:
            # Immutable completed receipt still wins even if cleanup fails.
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

    def read_diagnostic_binding(self, request_id: str) -> tuple[str, str] | None:
        """Read a validated immutable receipt's fingerprint and digest.

        Only an authenticated actor-local store is allowed to call this.
        """
        path = self._path(request_id)
        if not path.exists():
            return None
        record = self._read(path)
        return record["request_fingerprint"], record["response_sha256"]

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
