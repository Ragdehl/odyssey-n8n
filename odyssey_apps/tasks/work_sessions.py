"""Tasks-owned canonical Work Session lifecycle and projections."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from odyssey_core.git_history import GitHistoryResult, HistoryRecorder, HistoryStatus
from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.persistence import ActorInput, create_entity, soft_delete_entity, update_entity
from odyssey_core.storage import NoteUnavailableError, VaultRepository

from .schema import TASK_TYPE, WORK_SESSION_TYPE

_WORK_SESSION_PATH_PREFIX = "Work session - "
_ACTIVITY_HEADING = "## Actividad"
_ACTIVITY_LINE = re.compile(
    r"^- (?P<text>.+?) <!-- odyssey-work-session-entry:(?P<id>[A-Za-z0-9_-]{1,128}):(?P<created_at>[^>]+) -->$"
)
_MAX_ACTIVITY_TEXT = 2_000


class WorkSessionError(ValueError):
    """Reject unavailable, stale, ambiguous, or invalid Work Session mutations."""

    def __init__(self, code: str, *, active_task_id: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.active_task_id = active_task_id


@dataclass(frozen=True, slots=True)
class WorkSessionActivity:
    """One stable user-authored activity entry inside a Work Session."""

    id: str
    created_at: str
    text: str


@dataclass(frozen=True, slots=True)
class WorkSessionSnapshot:
    """Expose one bounded Work Session projection with stale-state mutation tokens."""

    id: str
    task_id: str
    started_at: str
    ended_at: str | None
    activity: tuple[WorkSessionActivity, ...]
    revision: int
    source_hash: str


@dataclass(frozen=True, slots=True)
class WorkSessionMutationResult:
    """Return one completed Work Session mutation and its authoritative task owner."""

    operation: str
    task_id: str
    session: WorkSessionSnapshot
    history: GitHistoryResult
    path: str
    previous_source_hash: str | None


class TaskWorkSessionService:
    """Own deterministic Work Session creation, stopping, editing, and task projections."""

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        history: HistoryRecorder | None,
        *,
        id_allocator: Callable[[], str] = lambda: str(uuid4()),
        activity_id_allocator: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self.repository = repository
        self.schema = schema
        self.history = history
        self.id_allocator = id_allocator
        self.activity_id_allocator = activity_id_allocator

    def list_for_task(self, task_id: str) -> tuple[WorkSessionSnapshot, ...]:
        """Return current sessions for one canonical Task, newest first."""
        if not isinstance(task_id, str) or not task_id:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE")
        sessions = [item for item in self._sessions() if item[1].metadata.get("task_id") == task_id]
        snapshots = [self._snapshot(raw, note) for _path, note, raw in sessions]
        snapshots.sort(key=lambda item: (item.started_at, item.id), reverse=True)
        return tuple(snapshots)

    def start(
        self,
        *,
        task_id: str,
        started_at: str,
        request_id: str,
        actor: ActorInput,
        now: str,
        expected_task_revision: int | None = None,
        expected_task_source_hash: str | None = None,
    ) -> WorkSessionMutationResult:
        """Start one globally unique active Work Session without changing Task lifecycle state."""
        _task_path, task, _task_raw = self._load_task(
            task_id,
            expected_revision=expected_task_revision,
            expected_source_hash=expected_task_source_hash,
        )
        if task.metadata.get("status") not in {"pending", "in_progress"}:
            raise WorkSessionError("WORK_SESSION_TASK_CLOSED")
        self._validate_datetime(started_at, "WORK_SESSION_START_INVALID")
        self._validate_datetime(now, "WORK_SESSION_TIME_INVALID")
        active = self._active_sessions()
        if active:
            active_task = str(active[0][1].metadata["task_id"])
            raise WorkSessionError("WORK_SESSION_ALREADY_ACTIVE", active_task_id=active_task)
        session_id = self.id_allocator()
        if (
            not isinstance(session_id, str)
            or not session_id.strip()
            or "/" in session_id
            or "\\" in session_id
        ):
            raise WorkSessionError("WORK_SESSION_ID_INVALID")
        name = f"Work session · {task.metadata['name']} · {started_at}"
        path = f"{_WORK_SESSION_PATH_PREFIX}{session_id}.md"
        snapshot = self._begin_history(request_id)
        try:
            create_entity(
                self.repository,
                self.schema,
                path=path,
                entity_id=session_id,
                metadata={
                    "name": name,
                    "type": WORK_SESSION_TYPE,
                    "task_id": task_id,
                    "started_at": started_at,
                },
                content="",
                actor=actor,
                now=now,
            )
            raw = self.repository.read_text(path)
            note = parse_note(raw)
            validate_note(note, self.schema)
        except (ValueError, OSError, NoteFormatError, NoteValidationError) as error:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE") from error
        session = self._snapshot(raw, note)
        return WorkSessionMutationResult(
            "work_session_started",
            task_id,
            session,
            self._record_history(request_id, snapshot, session_id),
            path,
            None,
        )

    def stop(
        self,
        *,
        session_id: str,
        ended_at: str,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        """Stop one exact active session through current stale-state evidence."""
        path, note, raw = self._load_session(
            session_id,
            expected_revision=expected_revision,
            expected_source_hash=expected_source_hash,
        )
        if note.metadata.get("ended_at") is not None:
            raise WorkSessionError("WORK_SESSION_NOT_ACTIVE")
        self._validate_interval(str(note.metadata["started_at"]), ended_at)
        snapshot = self._begin_history(request_id)
        try:
            update_entity(
                self.repository,
                self.schema,
                path=path,
                expected_id=session_id,
                expected_revision=expected_revision,
                set_metadata={"ended_at": ended_at},
                remove_metadata=(),
                content=note.content,
                actor=actor,
                now=now,
            )
            updated_raw = self.repository.read_text(path)
            updated = parse_note(updated_raw)
            validate_note(updated, self.schema)
        except (ValueError, OSError, NoteFormatError, NoteValidationError) as error:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE") from error
        task_id = str(updated.metadata["task_id"])
        return WorkSessionMutationResult(
            "work_session_stopped",
            task_id,
            self._snapshot(updated_raw, updated),
            self._record_history(request_id, snapshot, session_id),
            path,
            hashlib.sha256(raw.encode()).hexdigest(),
        )

    def stop_for_task(
        self,
        *,
        task_id: str,
        ended_at: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        """Stop the single active session owned by one resolved Task."""
        self._load_task(task_id)
        matches = [
            item for item in self._active_sessions() if item[1].metadata.get("task_id") == task_id
        ]
        if not matches:
            raise WorkSessionError("WORK_SESSION_NOT_ACTIVE")
        if len(matches) != 1:
            raise WorkSessionError("WORK_SESSION_STATE_INVALID")
        path, note, raw = matches[0]
        return self.stop(
            session_id=str(note.metadata["id"]),
            ended_at=ended_at,
            expected_revision=int(note.metadata["revision"]),
            expected_source_hash=hashlib.sha256(raw.encode()).hexdigest(),
            request_id=request_id,
            actor=actor,
            now=now,
        )

    def edit(
        self,
        *,
        session_id: str,
        started_at: str,
        ended_at: str | None,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        """Replace one session's user-correctable temporal interval without changing its Task."""
        path, note, raw = self._load_session(
            session_id,
            expected_revision=expected_revision,
            expected_source_hash=expected_source_hash,
        )
        self._validate_datetime(started_at, "WORK_SESSION_START_INVALID")
        if ended_at is not None:
            self._validate_interval(started_at, ended_at)
        else:
            active_others = [
                item for item in self._active_sessions() if item[1].metadata.get("id") != session_id
            ]
            if active_others:
                raise WorkSessionError(
                    "WORK_SESSION_ALREADY_ACTIVE",
                    active_task_id=str(active_others[0][1].metadata["task_id"]),
                )
        set_metadata: dict[str, Any] = {"started_at": started_at}
        remove_metadata: tuple[str, ...] = ()
        if ended_at is None:
            remove_metadata = ("ended_at",)
        else:
            set_metadata["ended_at"] = ended_at
        snapshot = self._begin_history(request_id)
        try:
            update_entity(
                self.repository,
                self.schema,
                path=path,
                expected_id=session_id,
                expected_revision=expected_revision,
                set_metadata=set_metadata,
                remove_metadata=remove_metadata,
                content=note.content,
                actor=actor,
                now=now,
            )
            updated_raw = self.repository.read_text(path)
            updated = parse_note(updated_raw)
            validate_note(updated, self.schema)
        except (ValueError, OSError, NoteFormatError, NoteValidationError) as error:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE") from error
        task_id = str(updated.metadata["task_id"])
        return WorkSessionMutationResult(
            "work_session_edited",
            task_id,
            self._snapshot(updated_raw, updated),
            self._record_history(request_id, snapshot, session_id),
            path,
            hashlib.sha256(raw.encode()).hexdigest(),
        )

    def edit_for_task(
        self,
        *,
        task_id: str,
        started_at: str | None,
        ended_at: str | None,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        """Edit the unique session for a Task on the corrected timestamp's local calendar date."""
        self._load_task(task_id)
        if started_at is None and ended_at is None:
            raise WorkSessionError("WORK_SESSION_EDIT_INVALID")
        hint = started_at or ended_at
        assert hint is not None
        hint_dt = self._validate_datetime(hint, "WORK_SESSION_TIME_INVALID")
        sessions = self.list_for_task(task_id)
        candidates = [
            item
            for item in sessions
            if self._validate_datetime(item.started_at, "WORK_SESSION_TIME_INVALID").date()
            == hint_dt.date()
        ]
        if not candidates:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE")
        if len(candidates) != 1:
            raise WorkSessionError("WORK_SESSION_AMBIGUOUS")
        current = candidates[0]
        return self.edit(
            session_id=current.id,
            started_at=started_at or current.started_at,
            ended_at=ended_at if ended_at is not None else current.ended_at,
            expected_revision=current.revision,
            expected_source_hash=current.source_hash,
            request_id=request_id,
            actor=actor,
            now=now,
        )

    def delete(
        self,
        *,
        session_id: str,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        """Soft-delete one exact Work Session through current stale-state evidence."""
        path, note, raw = self._load_session(
            session_id,
            expected_revision=expected_revision,
            expected_source_hash=expected_source_hash,
        )
        task_id = str(note.metadata["task_id"])
        prior = self._snapshot(raw, note)
        history = self._begin_history(request_id)
        try:
            soft_delete_entity(
                self.repository,
                self.schema,
                path=path,
                expected_id=session_id,
                expected_revision=expected_revision,
                actor=actor,
                now=now,
            )
        except (ValueError, OSError, NoteFormatError, NoteValidationError) as error:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE") from error
        return WorkSessionMutationResult(
            "work_session_deleted",
            task_id,
            prior,
            self._record_history(request_id, history, session_id),
            path,
            hashlib.sha256(raw.encode()).hexdigest(),
        )

    def add_activity(
        self,
        *,
        session_id: str,
        text: str,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        """Append one stable timestamped activity entry to an existing Work Session."""
        path, note, raw = self._load_session(
            session_id,
            expected_revision=expected_revision,
            expected_source_hash=expected_source_hash,
        )
        normalized = self._normalize_activity_text(text)
        self._validate_datetime(now, "WORK_SESSION_TIME_INVALID")
        entry_id = self.activity_id_allocator()
        if (
            not isinstance(entry_id, str)
            or not entry_id.strip()
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", entry_id)
        ):
            raise WorkSessionError("WORK_SESSION_ACTIVITY_ID_INVALID")
        entries = list(self._parse_activity(note.content))
        if any(item.id == entry_id for item in entries):
            raise WorkSessionError("WORK_SESSION_ACTIVITY_ID_INVALID")
        entries.append(WorkSessionActivity(entry_id, now, normalized))
        return self._replace_activity(
            path=path,
            note=note,
            raw=raw,
            entries=tuple(entries),
            operation="work_session_activity_added",
            request_id=request_id,
            actor=actor,
            now=now,
        )

    def edit_activity(
        self,
        *,
        session_id: str,
        activity_id: str,
        text: str,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        """Correct one exact activity entry while preserving its original trace timestamp."""
        path, note, raw = self._load_session(
            session_id,
            expected_revision=expected_revision,
            expected_source_hash=expected_source_hash,
        )
        normalized = self._normalize_activity_text(text)
        entries = list(self._parse_activity(note.content))
        matches = [index for index, item in enumerate(entries) if item.id == activity_id]
        if len(matches) != 1:
            raise WorkSessionError("WORK_SESSION_ACTIVITY_UNAVAILABLE")
        index = matches[0]
        current = entries[index]
        entries[index] = WorkSessionActivity(current.id, current.created_at, normalized)
        return self._replace_activity(
            path=path,
            note=note,
            raw=raw,
            entries=tuple(entries),
            operation="work_session_activity_edited",
            request_id=request_id,
            actor=actor,
            now=now,
        )

    def delete_activity(
        self,
        *,
        session_id: str,
        activity_id: str,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        """Remove one exact activity entry from a Work Session."""
        path, note, raw = self._load_session(
            session_id,
            expected_revision=expected_revision,
            expected_source_hash=expected_source_hash,
        )
        entries = list(self._parse_activity(note.content))
        filtered = [item for item in entries if item.id != activity_id]
        if len(filtered) != len(entries) - 1:
            raise WorkSessionError("WORK_SESSION_ACTIVITY_UNAVAILABLE")
        return self._replace_activity(
            path=path,
            note=note,
            raw=raw,
            entries=tuple(filtered),
            operation="work_session_activity_deleted",
            request_id=request_id,
            actor=actor,
            now=now,
        )

    def add_activity_for_task(
        self,
        *,
        task_id: str | None,
        text: str,
        session_date: str | None,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        """Append activity to one safely selected active or date-scoped Work Session."""
        if task_id is not None:
            self._load_task(task_id)
            sessions = list(self.list_for_task(task_id))
        else:
            sessions = [self._snapshot(raw, note) for _path, note, raw in self._active_sessions()]
        if session_date is not None:
            try:
                wanted_date = datetime.fromisoformat(session_date).date()
            except ValueError as error:
                raise WorkSessionError("WORK_SESSION_TEMPORAL_INVALID") from error
            sessions = [
                item
                for item in sessions
                if self._validate_datetime(item.started_at, "WORK_SESSION_TIME_INVALID").date()
                == wanted_date
            ]
        else:
            sessions = [item for item in sessions if item.ended_at is None]
        if not sessions:
            raise WorkSessionError(
                "WORK_SESSION_NOT_ACTIVE" if session_date is None else "WORK_SESSION_UNAVAILABLE"
            )
        if len(sessions) != 1:
            raise WorkSessionError("WORK_SESSION_AMBIGUOUS")
        current = sessions[0]
        return self.add_activity(
            session_id=current.id,
            text=text,
            expected_revision=current.revision,
            expected_source_hash=current.source_hash,
            request_id=request_id,
            actor=actor,
            now=now,
        )

    def _replace_activity(
        self,
        *,
        path: str,
        note: Any,
        raw: str,
        entries: tuple[WorkSessionActivity, ...],
        operation: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> WorkSessionMutationResult:
        session_id = str(note.metadata["id"])
        snapshot = self._begin_history(request_id)
        try:
            update_entity(
                self.repository,
                self.schema,
                path=path,
                expected_id=session_id,
                expected_revision=int(note.metadata["revision"]),
                set_metadata={},
                remove_metadata=(),
                content=self._render_activity(entries),
                actor=actor,
                now=now,
            )
            updated_raw = self.repository.read_text(path)
            updated = parse_note(updated_raw)
            validate_note(updated, self.schema)
        except (ValueError, OSError, NoteFormatError, NoteValidationError) as error:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE") from error
        task_id = str(updated.metadata["task_id"])
        return WorkSessionMutationResult(
            operation,
            task_id,
            self._snapshot(updated_raw, updated),
            self._record_history(request_id, snapshot, session_id),
            path,
            hashlib.sha256(raw.encode()).hexdigest(),
        )

    def _load_task(
        self,
        task_id: str,
        *,
        expected_revision: int | None = None,
        expected_source_hash: str | None = None,
    ) -> tuple[str, Any, str]:
        path, note, raw = self._load_unique(task_id, TASK_TYPE)
        if expected_revision is not None or expected_source_hash is not None:
            if (
                expected_revision is None
                or expected_source_hash is None
                or note.metadata.get("revision") != expected_revision
                or not hmac.compare_digest(
                    hashlib.sha256(raw.encode()).hexdigest(), expected_source_hash
                )
            ):
                raise WorkSessionError("STALE_NOTE")
        return path, note, raw

    def _load_session(
        self,
        session_id: str,
        *,
        expected_revision: int,
        expected_source_hash: str,
    ) -> tuple[str, Any, str]:
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE")
        path = f"{_WORK_SESSION_PATH_PREFIX}{session_id}.md"
        try:
            raw = self.repository.read_text(path)
            note = parse_note(raw)
            validate_note(note, self.schema)
        except (NoteUnavailableError, NoteFormatError, NoteValidationError, ValueError) as error:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE") from error
        if note.metadata.get("id") != session_id or note.metadata.get("type") != WORK_SESSION_TYPE:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE")
        if (
            not isinstance(expected_revision, int)
            or isinstance(expected_revision, bool)
            or expected_revision < 1
            or not isinstance(expected_source_hash, str)
            or len(expected_source_hash) != 64
            or note.metadata.get("revision") != expected_revision
            or not hmac.compare_digest(
                hashlib.sha256(raw.encode()).hexdigest(), expected_source_hash
            )
        ):
            raise WorkSessionError("STALE_NOTE")
        return path, note, raw

    def _load_unique(self, note_id: str, expected_type: str) -> tuple[str, Any, str]:
        if not isinstance(note_id, str) or not note_id:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE")
        matches: list[tuple[str, Any, str]] = []
        for path in self.repository.list_markdown_paths():
            try:
                raw = self.repository.read_text(path)
                note = parse_note(raw)
                validate_note(note, self.schema)
            except (
                NoteUnavailableError,
                NoteFormatError,
                NoteValidationError,
                ValueError,
            ) as error:
                raise WorkSessionError("WORK_SESSION_UNAVAILABLE") from error
            if note.metadata.get("id") == note_id and note.metadata.get("deleted") is not True:
                matches.append((path, note, raw))
        if len(matches) != 1 or matches[0][1].metadata.get("type") != expected_type:
            raise WorkSessionError("WORK_SESSION_UNAVAILABLE")
        return matches[0]

    def _sessions(self) -> list[tuple[str, Any, str]]:
        result: list[tuple[str, Any, str]] = []
        for path in self.repository.list_markdown_paths():
            if not path.startswith(_WORK_SESSION_PATH_PREFIX):
                continue
            try:
                raw = self.repository.read_text(path)
                note = parse_note(raw)
                validate_note(note, self.schema)
            except (
                NoteUnavailableError,
                NoteFormatError,
                NoteValidationError,
                ValueError,
            ) as error:
                raise WorkSessionError("WORK_SESSION_UNAVAILABLE") from error
            if (
                note.metadata.get("deleted") is not True
                and note.metadata.get("type") == WORK_SESSION_TYPE
            ):
                result.append((path, note, raw))
        return result

    def _active_sessions(self) -> list[tuple[str, Any, str]]:
        active = [item for item in self._sessions() if item[1].metadata.get("ended_at") is None]
        if len(active) > 1:
            raise WorkSessionError("WORK_SESSION_STATE_INVALID")
        return active

    @staticmethod
    def _validate_datetime(value: str, code: str) -> datetime:
        if not isinstance(value, str):
            raise WorkSessionError(code)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise WorkSessionError(code) from error
        if parsed.tzinfo is None:
            raise WorkSessionError(code)
        return parsed

    @classmethod
    def _validate_interval(cls, started_at: str, ended_at: str) -> None:
        start = cls._validate_datetime(started_at, "WORK_SESSION_START_INVALID")
        end = cls._validate_datetime(ended_at, "WORK_SESSION_END_INVALID")
        if end < start:
            raise WorkSessionError("WORK_SESSION_END_BEFORE_START")

    @staticmethod
    def _snapshot(raw: str, note: Any) -> WorkSessionSnapshot:
        metadata = note.metadata
        return WorkSessionSnapshot(
            id=str(metadata["id"]),
            task_id=str(metadata["task_id"]),
            started_at=str(metadata["started_at"]),
            ended_at=(str(metadata["ended_at"]) if metadata.get("ended_at") is not None else None),
            activity=TaskWorkSessionService._parse_activity(note.content),
            revision=int(metadata["revision"]),
            source_hash=hashlib.sha256(raw.encode()).hexdigest(),
        )

    @staticmethod
    def _normalize_activity_text(value: str) -> str:
        if not isinstance(value, str):
            raise WorkSessionError("WORK_SESSION_ACTIVITY_INVALID")
        normalized = " ".join(value.split())
        if (
            not normalized
            or len(normalized) > _MAX_ACTIVITY_TEXT
            or "<!--" in normalized
            or "-->" in normalized
        ):
            raise WorkSessionError("WORK_SESSION_ACTIVITY_INVALID")
        return normalized

    @staticmethod
    def _parse_activity(content: str) -> tuple[WorkSessionActivity, ...]:
        if not isinstance(content, str):
            raise WorkSessionError("WORK_SESSION_ACTIVITY_INVALID")
        if not content.strip():
            return ()
        lines = content.rstrip().splitlines()
        if not lines or lines[0] != _ACTIVITY_HEADING:
            raise WorkSessionError("WORK_SESSION_ACTIVITY_INVALID")
        entries: list[WorkSessionActivity] = []
        seen_ids: set[str] = set()
        for line in lines[1:]:
            if not line.strip():
                continue
            match = _ACTIVITY_LINE.fullmatch(line)
            if match is None:
                raise WorkSessionError("WORK_SESSION_ACTIVITY_INVALID")
            entry_id = match.group("id")
            if entry_id in seen_ids:
                raise WorkSessionError("WORK_SESSION_ACTIVITY_INVALID")
            created_at = match.group("created_at")
            TaskWorkSessionService._validate_datetime(created_at, "WORK_SESSION_ACTIVITY_INVALID")
            text = TaskWorkSessionService._normalize_activity_text(match.group("text"))
            entries.append(WorkSessionActivity(entry_id, created_at, text))
            seen_ids.add(entry_id)
        return tuple(entries)

    @staticmethod
    def _render_activity(entries: tuple[WorkSessionActivity, ...]) -> str:
        if not entries:
            return ""
        lines = [_ACTIVITY_HEADING, ""]
        for entry in entries:
            text = TaskWorkSessionService._normalize_activity_text(entry.text)
            TaskWorkSessionService._validate_datetime(
                entry.created_at, "WORK_SESSION_ACTIVITY_INVALID"
            )
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", entry.id):
                raise WorkSessionError("WORK_SESSION_ACTIVITY_INVALID")
            lines.append(
                f"- {text} <!-- odyssey-work-session-entry:{entry.id}:{entry.created_at} -->"
            )
        return "\n".join(lines) + "\n"

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
