"""Root-isolated durable admission for one logical two-fact Core request.

This is an opt-in orchestration guard, not a new semantic planner.
A stable client logical-operation key, NOT the per-attempt Core request ID
or message text, must remain identical across network retries. Cooperating
processes serialize on the root-local existing flock pattern. The journal
is recorded before any Core action and is never silently pruned/retried.

Crash after reservation but before a physical fact marker remains marked
unknown and requires human reconciliation; no automatic resume/rollback.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import VaultRepository

_MAX_RECORD_BYTES = 2048
_MAX_ACTIVE_RECORDS = 5000
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_:-]{0,127}\Z")
_STATES = {"reserved", "completed", "partial", "unknown"}
_VERSION = 1


class DependentOperationAdmissionError(ValueError):
    """Reject duplicate, unaudited or unsafe dependent-operation admission."""


@dataclass(frozen=True, slots=True)
class DependentOperationReceipt:
    """Describe durable admission state without revealing original user text."""

    operation_digest: str
    request_id: str
    source_digest: str
    plan_digest: str
    vault_digest: str
    state: str


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DependentOperationJournal:
    """One actor-root local durable ledger, independently isolated from Notes."""

    def __init__(self, state_root: Path, repository: VaultRepository):
        if not isinstance(state_root, Path) or not isinstance(repository, VaultRepository):
            raise DependentOperationAdmissionError("Trusted root-bound state is required")
        if not state_root.is_dir() or state_root.is_symlink():
            raise DependentOperationAdmissionError(
                "Dependent operation state root is missing/unsafe"
            )
        root = state_root.resolve(strict=True)
        if repository.contains_filesystem_path(root) or root == repository.root:
            raise DependentOperationAdmissionError(
                "Operational state may not live in canonical vault"
            )
        self._vault_digest = _digest(str(repository.root))
        path = root / "dependent-operations"
        if path.is_symlink():
            raise DependentOperationAdmissionError("Operation journal is not trusted")
        path.mkdir(mode=0o700, exist_ok=True)
        if not path.is_dir() or path.is_symlink():
            raise DependentOperationAdmissionError("Operation journal root is unsafe")
        self._root = path

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or _KEY.fullmatch(key) is None:
            raise DependentOperationAdmissionError("Stable operation key is missing/unsafe")
        return self._root / (_digest(key) + ".json")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Keep the lock across journal writes AND entire ordinary Core execution."""
        path = self._root / ".admission.lock"
        if path.is_symlink():
            raise DependentOperationAdmissionError("Operation lock cannot be a symlink")
        try:
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        except OSError as error:
            raise DependentOperationAdmissionError("Cannot open root-bound lock") from error
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self, path: Path) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise DependentOperationAdmissionError("Journal record is not a safe regular file")
        try:
            if path.stat().st_size > _MAX_RECORD_BYTES:
                raise DependentOperationAdmissionError("Oversize dependent journal")
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise DependentOperationAdmissionError(
                "Unreadable dependent operation journal"
            ) from error
        if (
            not isinstance(record, dict)
            or set(record)
            != {
                "version",
                "operation_digest",
                "request_id",
                "source_digest",
                "plan_digest",
                "vault_digest",
                "state",
            }
            or record["version"] != _VERSION
            or record["state"] not in _STATES
            or record["vault_digest"] != self._vault_digest
            or not isinstance(record["request_id"], str)
            or not record["request_id"]
            or any(
                not isinstance(record[k], str) or re.fullmatch(r"[0-9a-f]{64}", record[k]) is None
                for k in ("operation_digest", "source_digest", "plan_digest", "vault_digest")
            )
            or path.name != record["operation_digest"] + ".json"
        ):
            raise DependentOperationAdmissionError("Journal contents are untrusted or corrupt")
        return record

    def _persist(self, path: Path, record: dict[str, Any]) -> None:
        """Atomic fsynced replace while the root-wide advisory lock is held."""
        blob = json.dumps(record, separators=(",", ":"), sort_keys=True).encode()
        if len(blob) > _MAX_RECORD_BYTES or path.is_symlink():
            raise DependentOperationAdmissionError("Journal target is unsafe or too large")
        temp_path: Path | None = None
        try:
            fd, name = tempfile.mkstemp(prefix=".dependent-", suffix=".tmp", dir=self._root)
            temp_path = Path(name)
            with os.fdopen(fd, "wb") as file:
                file.write(blob)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, path)
            directory_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as error:
            raise DependentOperationAdmissionError(
                "Journal could not be persisted durably"
            ) from error
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def inspect(self, logical_operation_key: str) -> DependentOperationReceipt | None:
        """Return a complete previously reserved operation, never authorize replay."""
        path = self._path(logical_operation_key)
        with self._locked():
            if not path.exists() and not path.is_symlink():
                return None
            return DependentOperationReceipt(
                **{k: v for k, v in self._read(path).items() if k != "version"}
            )

    def execute_once(
        self,
        *,
        logical_operation_key: str,
        request_id: str,
        source: str,
        plan_repr: str,
        operation: Callable[[], Any],
        classify: Callable[[Any], str],
    ) -> Any:
        """Admit exactly one stable logical operation in this actor's state root.

        The record precedes the operation. If execution raises or process
        dies, the durable record stays reserved/unknown, and further attempts
        with the same key require manual state reconciliation.
        """
        path = self._path(logical_operation_key)
        if (
            not isinstance(request_id, str)
            or not request_id.strip()
            or not isinstance(source, str)
            or not source.strip()
            or not isinstance(plan_repr, str)
            or not plan_repr
            or not callable(operation)
            or not callable(classify)
        ):
            raise DependentOperationAdmissionError("Logical operation inputs invalid")
        with self._locked():
            if path.exists() or path.is_symlink():
                existing = self._read(path)
                raise DependentOperationAdmissionError(
                    f"Operation already admitted; status={existing['state']}"
                )
            if len(tuple(self._root.glob("*.json"))) >= _MAX_ACTIVE_RECORDS:
                raise DependentOperationAdmissionError("Dependent journal capacity exceeded")
            record: dict[str, Any] = {
                "version": _VERSION,
                "operation_digest": _digest(logical_operation_key),
                "request_id": request_id,
                "source_digest": _digest(source),
                "plan_digest": _digest(plan_repr),
                "vault_digest": self._vault_digest,
                "state": "reserved",
            }
            self._persist(path, record)
            try:
                result = operation()
                state = classify(result)
                if state not in {"completed", "partial", "unknown"}:
                    raise DependentOperationAdmissionError("Unsafe completion classifier")
            except BaseException:
                # Leave an already durable reservation, not a false success.
                record["state"] = "unknown"
                self._persist(path, record)
                raise
            record["state"] = state
            self._persist(path, record)
            return result


def execute_dependent_core_once(
    *,
    logical_operation_key: str,
    state_root: Path,
    source: str,
    context: Any,
    independent_plans: tuple[Any, Any],
    repository: VaultRepository,
    schema: dict[str, Any],
    context_index: Any,
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    actor: Any,
    now: str,
    context_limit: int,
    request_id_factory: Callable[[], str],
) -> Any:
    """Gate ONE original-source two-fact operation by a stable logical key.

    The existing Core planner has already independently compiled and
    source-validated the two plans. This thin facade only calls the
    original Core execute_request using that immutable combined plan,
    with the same original-source candidate coverage and canonical
    write guards. It does not invent a second semantic planner.

    The caller MUST reuse logical_operation_key across network retries
    even if it generates a new technical request ID. Passing a different
    key for the same logical event is not an authorized retry. No key
    can be inferred safely from natural-language text because users
    may intentionally send the same sentence again on another day.
    """
    from .application import ApplicationStatus, execute_request
    from .candidate_coverage import (
        CoreCandidateCoverageClaim,
        build_dependent_candidate_coverage_manifest,
        review_dependent_candidate_coverage,
    )

    if not callable(request_id_factory):
        raise DependentOperationAdmissionError("Core request ID factory is required")
    combined, coverage = build_dependent_candidate_coverage_manifest(
        source,
        context,
        independent_plans,
        tuple(
            CoreCandidateCoverageClaim(f"candidate-{ordinal + 1}", "planned_fact", ordinal)
            for ordinal in range(2)
        ),
    )
    request_id = request_id_factory()
    if not isinstance(request_id, str) or _KEY.fullmatch(request_id) is None:
        raise DependentOperationAdmissionError("New Core request ID is invalid")
    ledger = DependentOperationJournal(state_root, repository)

    class _AlreadyCompiledCorePlans:
        """Adapter for already compiled independent Core plans, no LLM calls."""

        is_local_replay = True

        def plan(self, request: str) -> Any:
            if request != source:
                raise DependentOperationAdmissionError("Original user request changed")
            return combined

    def run() -> Any:
        return execute_request(
            source,
            planner=_AlreadyCompiledCorePlans(),
            repository=repository,
            schema=schema,
            context_index=context_index,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            actor=actor,
            now=now,
            context_limit=context_limit,
            request_id_factory=lambda: request_id,
            candidate_context=context,
            candidate_coverage_factory=lambda *_: coverage,
        )

    def classify(result: Any) -> str:
        if result.status is ApplicationStatus.COMPLETED:
            verification = review_dependent_candidate_coverage(
                source, context, combined, coverage, result, repository, schema
            )
            return "completed" if verification.safe_to_report_all_candidates_complete else "unknown"
        if result.status is ApplicationStatus.PARTIAL:
            return "partial"
        return "unknown"

    return ledger.execute_once(
        logical_operation_key=logical_operation_key,
        request_id=request_id,
        source=source,
        plan_repr=repr(combined),
        operation=run,
        classify=classify,
    )
