"""Deterministic direct lifecycle mutations for explicit Tasks UI controls."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from odyssey_core.git_history import GitHistoryResult, HistoryRecorder, HistoryStatus
from odyssey_core.materialization import (
    MaterializationError,
    materialize_create,
    materialize_update,
)
from odyssey_core.notes import NoteFormatError, parse_note, validate_note
from odyssey_core.persistence import ActorInput, PersistenceOperation
from odyssey_core.reference_binding import ReferenceBindingError, render_reference_facts
from odyssey_core.reference_preflight import (
    ReferencePreflightError,
    UnitTargetPreflight,
    preflight_write_action,
)
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    SelectionCriteria,
    WriteAction,
)
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


@dataclass(frozen=True, slots=True)
class TaskSubtaskCreateResult:
    """Return the newly materialized child Task through the bounded UI contract."""

    operation: str
    note_id: str
    name: str
    status: str
    history: GitHistoryResult
    path: str
    source_hash: str


class TaskDirectMutationService:
    """Toggle completion from an explicit stable-ID UI action without model involvement."""

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        history: HistoryRecorder | None,
        *,
        semantic_index: Any | None = None,
        embedder: Any | None = None,
        contextual_reasoner: Any | None = None,
        semantic_limit: int = 10,
    ) -> None:
        self.repository = repository
        self.schema = schema
        self.history = history
        self.semantic_index = semantic_index
        self.embedder = embedder
        self.contextual_reasoner = contextual_reasoner
        self.semantic_limit = semantic_limit

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

    def create_subtask(
        self,
        *,
        parent_note_id: str,
        title: str,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> TaskSubtaskCreateResult:
        """Create one pending child Task using Core target preflight and materialization.

        The parent is an already-selected stable UI target.  The child still passes through
        ordinary Core preflight so an ambiguous or existing target never silently becomes a
        duplicate note.
        """
        parent_path, parent, _parent_hash = self._load_current(
            parent_note_id, expected_revision, expected_source_hash
        )
        if parent.metadata.get("type") != TASK_TYPE:
            raise TaskDirectMutationError("TASK_UNAVAILABLE")
        if parent.metadata.get("status") not in {"pending", "in_progress"}:
            raise TaskDirectMutationError("TASK_PARENT_CLOSED")
        normalized_title = title.strip() if isinstance(title, str) else ""
        if not normalized_title or len(normalized_title) > 240:
            raise TaskDirectMutationError("TASK_SUBTASK_INVALID")
        if (
            self.semantic_index is None
            or self.embedder is None
            or self.contextual_reasoner is None
            or not isinstance(self.semantic_limit, int)
            or self.semantic_limit < 1
        ):
            raise TaskDirectMutationError("TASK_UNAVAILABLE")
        parent_name = parent.metadata.get("name")
        if not isinstance(parent_name, str) or not parent_name:
            raise TaskDirectMutationError("TASK_UNAVAILABLE")
        child_target = SelectionCriteria(normalized_title, normalized_title, TASK_TYPE, (), None)
        ordinary_child = KnowledgeUnit(
            child_target, "record", (PropertyChange("status", "set", "pending"),), (), (), ()
        )
        try:
            ordinary_preflight = preflight_write_action(
                WriteAction((ordinary_child,)),
                repository=self.repository,
                schema=self.schema,
                semantic_index=self.semantic_index,
                embedder=self.embedder,
                contextual_reasoner=self.contextual_reasoner,
                semantic_limit=self.semantic_limit,
            )[0]
        except (ReferencePreflightError, ValueError) as error:
            raise TaskDirectMutationError("TASK_SUBTASK_TARGET_UNAVAILABLE") from error
        if not (
            ordinary_preflight.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION
            and ordinary_preflight.reason == "managed_type_requires_application_create"
        ):
            raise TaskDirectMutationError("TASK_SUBTASK_TARGET_UNAVAILABLE")
        child = KnowledgeUnit(
            child_target,
            "record",
            (PropertyChange("status", "set", "pending"),),
            (),
            ("Tarea superior: {{ref:0}}.",),
            (KnowledgeReference(1, "parent_task", parent_name),),
            "one",
            force_create=True,
        )
        allocation_action = WriteAction((child,))
        parent_reference = KnowledgeUnit(
            SelectionCriteria(parent_name, parent_name, TASK_TYPE, (), None),
            "record",
            (),
            (),
            (),
            (),
            "one",
            reference_lookup_only=True,
        )
        render_action = WriteAction((child, parent_reference))
        parent_target = UnitTargetPreflight(
            1,
            WriteTargetOutcome.UPDATE,
            parent_note_id,
            parent_name,
            parent_path,
            reference_only=True,
        )
        try:
            preflight = preflight_write_action(
                allocation_action,
                repository=self.repository,
                schema=self.schema,
                semantic_index=self.semantic_index,
                embedder=self.embedder,
                contextual_reasoner=self.contextual_reasoner,
                semantic_limit=self.semantic_limit,
            )
            child_preflight = preflight[0]
            if child_preflight.outcome is not WriteTargetOutcome.CREATE:
                raise TaskDirectMutationError("TASK_SUBTASK_TARGET_UNAVAILABLE")
            rendered = render_reference_facts(render_action, (child_preflight, parent_target))
            if rendered.pending_references:
                raise TaskDirectMutationError("TASK_SUBTASK_TARGET_UNAVAILABLE")
        except (ReferencePreflightError, ReferenceBindingError, ValueError) as error:
            raise TaskDirectMutationError("TASK_SUBTASK_TARGET_UNAVAILABLE") from error
        snapshot = self._begin_history(request_id)
        try:
            result = materialize_create(
                child,
                child_preflight,
                unit_index=0,
                repository=self.repository,
                schema=self.schema,
                actor=actor,
                now=now,
                rendered_facts=rendered.rendered_facts[0],
                request_id=request_id,
                fact_ordinals=(0,),
            )
        except (MaterializationError, ValueError) as error:
            raise TaskDirectMutationError("TASK_SUBTASK_TARGET_UNAVAILABLE") from error
        if result.operation is not PersistenceOperation.CREATED:
            raise TaskDirectMutationError("TASK_SUBTASK_TARGET_UNAVAILABLE")
        child_id = child_preflight.stable_id
        child_path = child_preflight.path
        if not child_id or not child_path:
            raise TaskDirectMutationError("TASK_SUBTASK_TARGET_UNAVAILABLE")
        return TaskSubtaskCreateResult(
            "task_subtask_created",
            child_id,
            child_preflight.canonical_name or normalized_title,
            "pending",
            self._record_history(request_id, snapshot, child_id),
            child_path,
            hashlib.sha256(self.repository.read_text(child_path).encode()).hexdigest(),
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
