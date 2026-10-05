"""Deterministic direct lifecycle mutations for explicit Tasks UI controls."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from odyssey_core.git_history import GitHistoryResult, HistoryRecorder, HistoryStatus
from odyssey_core.materialization import MaterializationError, materialize_update
from odyssey_core.notes import NoteFormatError, parse_note, validate_note
from odyssey_core.persistence import ActorInput, PersistenceOperation
from odyssey_core.request_planning import KnowledgeUnit, PropertyChange, SelectionCriteria
from odyssey_core.storage import NoteUnavailableError, VaultRepository
from odyssey_core.write_target import WriteTargetDecision, WriteTargetOutcome

from .schema import TASK_TYPE


class TaskDirectMutationError(ValueError):
    """Reject a stale, invalid, or unsupported direct Task lifecycle mutation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TaskDirectMutationResult:
    operation: str
    note_id: str
    history: GitHistoryResult
    path: str
    revision: int
    source_hash: str
    status: str
    completed_at: str | None


class TaskDirectMutationService:
    """Toggle completion from an explicit stable-ID UI action without model involvement."""

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        history: HistoryRecorder | None,
    ) -> None:
        self.repository = repository
        self.schema = schema
        self.history = history

    def set_completed(
        self,
        *,
        note_id: str,
        completed: bool,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> TaskDirectMutationResult:
        _path, note, _source_hash = self._load_current(
            note_id, expected_revision, expected_source_hash
        )
        if note.metadata.get("type") != TASK_TYPE:
            raise TaskDirectMutationError("TASK_UNAVAILABLE")
        status = note.metadata.get("status")
        if completed:
            if status not in {"pending", "in_progress"}:
                raise TaskDirectMutationError("TASK_INVALID_TRANSITION")
            changes = (
                PropertyChange("status", "set", "completed"),
                PropertyChange("completed_at", "set", now),
            )
            operation = "task_completed"
        else:
            if status != "completed":
                raise TaskDirectMutationError("TASK_INVALID_TRANSITION")
            changes = (
                PropertyChange("status", "set", "pending"),
                PropertyChange("completed_at", "remove", None),
            )
            operation = "task_reopened"
        unit = KnowledgeUnit(
            SelectionCriteria(note.metadata["name"], note.metadata["name"], TASK_TYPE, (), None),
            "amend",
            changes,
            (),
            (),
            (),
            "one",
        )
        snapshot = self._begin_history(request_id)
        try:
            result = materialize_update(
                unit,
                WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id=note_id),
                repository=self.repository,
                schema=self.schema,
                actor=actor,
                now=now,
                request_id=request_id,
                fact_ordinals=(),
            )
        except (MaterializationError, ValueError) as error:
            raise TaskDirectMutationError("TASK_UNAVAILABLE") from error
        if result.operation is not PersistenceOperation.UPDATED:
            raise TaskDirectMutationError("TASK_UNAVAILABLE")
        updated_raw = self.repository.read_text(_path)
        try:
            updated_note = parse_note(updated_raw)
            validate_note(updated_note, self.schema)
        except (NoteFormatError, ValueError) as error:
            raise TaskDirectMutationError("TASK_UNAVAILABLE") from error
        revision = updated_note.metadata.get("revision")
        updated_status = updated_note.metadata.get("status")
        completed_at = updated_note.metadata.get("completed_at")
        if (
            not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
            or not isinstance(updated_status, str)
            or (completed_at is not None and not isinstance(completed_at, str))
        ):
            raise TaskDirectMutationError("TASK_UNAVAILABLE")
        return TaskDirectMutationResult(
            operation,
            note_id,
            self._record_history(request_id, snapshot, note_id),
            _path,
            revision,
            hashlib.sha256(updated_raw.encode()).hexdigest(),
            updated_status,
            completed_at,
        )

    def _load_current(
        self, note_id: str, expected_revision: int, expected_source_hash: str
    ) -> tuple[str, Any, str]:
        if (
            not isinstance(note_id, str)
            or not note_id
            or not isinstance(expected_revision, int)
            or isinstance(expected_revision, bool)
            or expected_revision < 1
            or not isinstance(expected_source_hash, str)
            or len(expected_source_hash) != 64
            or any(character not in "0123456789abcdef" for character in expected_source_hash)
        ):
            raise TaskDirectMutationError("STALE_NOTE")
        matches: list[tuple[str, Any, str]] = []
        for path in self.repository.list_markdown_paths():
            try:
                raw = self.repository.read_text(path)
                note = parse_note(raw)
                validate_note(note, self.schema)
            except (NoteUnavailableError, NoteFormatError, ValueError) as error:
                raise TaskDirectMutationError("TASK_UNAVAILABLE") from error
            if note.metadata.get("id") == note_id:
                matches.append((path, note, hashlib.sha256(raw.encode()).hexdigest()))
        if len(matches) != 1:
            raise TaskDirectMutationError("TASK_UNAVAILABLE")
        path, note, source_hash = matches[0]
        if note.metadata.get("deleted") is True:
            raise TaskDirectMutationError("TASK_UNAVAILABLE")
        if note.metadata.get("revision") != expected_revision or not hmac.compare_digest(
            source_hash, expected_source_hash
        ):
            raise TaskDirectMutationError("STALE_NOTE")
        return path, note, source_hash

    def _begin_history(self, request_id: str) -> object | None:
        if self.history is None:
            return None
        try:
            return self.history.begin(request_id)
        except Exception:
            return None

    def _record_history(
        self, request_id: str, snapshot: object | None, note_id: str
    ) -> GitHistoryResult:
        if self.history is None:
            return GitHistoryResult.disabled()
        if snapshot is None:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history snapshot failed")
        try:
            return self.history.record(
                request_id=request_id,
                snapshot=snapshot,
                affected_stable_note_ids=(note_id,),
                repository=self.repository,
                schema=self.schema,
            )
        except Exception:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history record failed")
