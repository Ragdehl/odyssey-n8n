"""Deterministic canonical Task queries owned by the Tasks application."""

from __future__ import annotations

from datetime import date, datetime

from odyssey_core.context import ContextItem, ContextPackage
from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.storage import NoteUnavailableError, VaultRepository

from .interpretation import TaskQueryScope
from .schema import TASK_TYPE


class TaskQueryError(ValueError):
    """Reject unavailable or malformed canonical task query state."""


class TaskQueryService:
    """Project task lifecycle collections directly from authoritative Markdown."""

    def __init__(self, repository: VaultRepository, schema: dict) -> None:
        self.repository = repository
        self.schema = schema

    def query(
        self,
        source_text: str,
        scope: TaskQueryScope,
        *,
        now: str,
        limit: int = 40,
    ) -> ContextPackage:
        if not isinstance(source_text, str) or not source_text.strip():
            raise TaskQueryError("Task query source is invalid")
        if not isinstance(scope, TaskQueryScope):
            raise TaskQueryError("Task query scope is invalid")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 40:
            raise TaskQueryError("Task query limit is invalid")
        try:
            current = datetime.fromisoformat(now)
        except (TypeError, ValueError) as error:
            raise TaskQueryError("Task query current time is invalid") from error
        if current.tzinfo is None:
            raise TaskQueryError("Task query current time must be offset-aware")

        selected: list[tuple[tuple[object, ...], ContextItem]] = []
        for path in self.repository.list_markdown_paths():
            try:
                note = parse_note(self.repository.read_text(path))
                validate_note(note, self.schema)
            except (
                NoteUnavailableError,
                NoteFormatError,
                NoteValidationError,
                ValueError,
            ) as error:
                raise TaskQueryError("Task query cannot validate canonical Markdown") from error
            if note.metadata.get("deleted") is True or note.metadata.get("type") != TASK_TYPE:
                continue
            if not _matches_scope(note.metadata, scope, current):
                continue
            note_id = note.metadata.get("id")
            name = note.metadata.get("name")
            tags = note.metadata.get("tags", [])
            if (
                not isinstance(note_id, str)
                or not isinstance(name, str)
                or not isinstance(tags, list)
                or any(not isinstance(tag, str) for tag in tags)
            ):
                raise TaskQueryError("Task note identity is invalid")
            item = ContextItem(
                note_id,
                path,
                name,
                TASK_TYPE,
                tuple(tags),
                dict(note.metadata),
                note.content,
                1.0,
            )
            selected.append((_task_sort_key(note.metadata, name), item))
        selected.sort(key=lambda pair: pair[0])
        return ContextPackage(source_text, tuple(item for _key, item in selected[:limit]))


def _matches_scope(metadata: dict, scope: TaskQueryScope, current: datetime) -> bool:
    status = metadata.get("status")
    if scope is TaskQueryScope.ALL:
        return status in {"pending", "in_progress", "completed", "cancelled"}
    if scope is TaskQueryScope.OPEN:
        return status in {"pending", "in_progress"}
    if scope is TaskQueryScope.PENDING:
        return status == "pending"
    if scope is TaskQueryScope.IN_PROGRESS:
        return status == "in_progress"
    if scope is TaskQueryScope.COMPLETED:
        return status == "completed"
    if scope is TaskQueryScope.CANCELLED:
        return status == "cancelled"
    if scope is TaskQueryScope.OVERDUE:
        return status in {"pending", "in_progress"} and _deadline_is_overdue(
            metadata.get("deadline_at"), current
        )
    return False


def _deadline_is_overdue(value: object, current: datetime) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) == 10:
        try:
            deadline = date.fromisoformat(value)
        except ValueError:
            return False
        return deadline < current.date()
    try:
        deadline_at = datetime.fromisoformat(value)
    except ValueError:
        return False
    return deadline_at.tzinfo is not None and deadline_at < current


def _task_sort_key(metadata: dict, name: str) -> tuple[object, ...]:
    status_order = {"in_progress": 0, "pending": 1, "completed": 2, "cancelled": 3}
    temporal = (
        metadata.get("deadline_at")
        or metadata.get("target_date")
        or metadata.get("planned_start_at")
        or "9999-12-31"
    )
    return (status_order.get(metadata.get("status"), 9), str(temporal), name.casefold())
