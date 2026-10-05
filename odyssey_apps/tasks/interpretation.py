"""Bounded Tasks lifecycle interpretation without Core mutation authority."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.temporal_interpretation import TemporalInterpretation
from odyssey_core.temporal_resolution import TemporalResolutionKind

TASK_INTERPRETER_MODEL = "gpt-6-luna"
TASK_INTERPRETER_REASONING_EFFORT = "low"
TASK_INTERPRETER_MAX_OUTPUT_TOKENS = 512
TASK_INTERPRETER_TIMEOUT_SECONDS = 30.0
_TASK_TEMPORAL_FIELDS = {
    "TARGET_DATE": "target_date",
    "PLANNED_START_AT": "planned_start_at",
    "PLANNED_END_AT": "planned_end_at",
    "DEADLINE_AT": "deadline_at",
}
_TASK_CLEARABLE_FIELDS = frozenset(_TASK_TEMPORAL_FIELDS.values())
_WORK_SESSION_OPERATIONS = frozenset(
    {
        "START_WORK_SESSION",
        "STOP_WORK_SESSION",
        "EDIT_WORK_SESSION",
        "ADD_WORK_SESSION_ACTIVITY",
    }
)
_WORK_SESSION_TEMPORAL_ROLES = frozenset(
    {"WORK_SESSION_START_AT", "WORK_SESSION_END_AT", "WORK_SESSION_AT"}
)


class TaskInterpretationError(ValueError):
    """Reject malformed, unsupported, or unsafe Tasks semantics."""


class TaskOperation(StrEnum):
    CREATE = "CREATE"
    START = "START"
    COMPLETE = "COMPLETE"
    REOPEN = "REOPEN"
    CANCEL = "CANCEL"
    UPDATE = "UPDATE"
    QUERY = "QUERY"
    START_WORK_SESSION = "START_WORK_SESSION"
    STOP_WORK_SESSION = "STOP_WORK_SESSION"
    EDIT_WORK_SESSION = "EDIT_WORK_SESSION"
    ADD_WORK_SESSION_ACTIVITY = "ADD_WORK_SESSION_ACTIVITY"


class TaskQueryScope(StrEnum):
    ALL = "ALL"
    OPEN = "OPEN"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    OVERDUE = "OVERDUE"


class TaskActivityTarget(StrEnum):
    NONE = "NONE"
    ACTIVE = "ACTIVE"
    TASK = "TASK"


class TaskTemporalRole(StrEnum):
    TARGET_DATE = "TARGET_DATE"
    PLANNED_START_AT = "PLANNED_START_AT"
    PLANNED_END_AT = "PLANNED_END_AT"
    DEADLINE_AT = "DEADLINE_AT"
    WORK_SESSION_START_AT = "WORK_SESSION_START_AT"
    WORK_SESSION_END_AT = "WORK_SESSION_END_AT"
    WORK_SESSION_AT = "WORK_SESSION_AT"


class TaskRelationshipRole(StrEnum):
    ASSIGNEE = "ASSIGNEE"
    PARENT_TASK = "PARENT_TASK"


class ResponsesClient(Protocol):
    responses: Any


@dataclass(frozen=True, slots=True)
class TaskTemporalMention:
    """Assign one exact source temporal phrase to one Tasks-owned property meaning."""

    text: str
    role: TaskTemporalRole

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise TaskInterpretationError("Task temporal wording is invalid")
        if not isinstance(self.role, TaskTemporalRole):
            raise TaskInterpretationError("Task temporal role is invalid")


@dataclass(frozen=True, slots=True)
class TaskRelationshipMention:
    """Assign exact source wording to one Tasks-owned relationship role without resolving it."""

    text: str
    role: TaskRelationshipRole

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise TaskInterpretationError("Task relationship wording is invalid")
        if not isinstance(self.role, TaskRelationshipRole):
            raise TaskInterpretationError("Task relationship role is invalid")


@dataclass(frozen=True, slots=True)
class TaskInterpretation:
    """Carry only Tasks lifecycle meaning and temporal-role assignments."""

    source_text: str
    operation: TaskOperation
    temporal_mentions: tuple[TaskTemporalMention, ...] = ()
    clear_fields: tuple[str, ...] = ()
    query_scope: TaskQueryScope | None = None
    relationship_mentions: tuple[TaskRelationshipMention, ...] = ()
    task_reference: str | None = None
    activity_text: str | None = None
    activity_target: TaskActivityTarget = TaskActivityTarget.NONE

    def __post_init__(self) -> None:
        if not isinstance(self.source_text, str) or not self.source_text.strip():
            raise TaskInterpretationError("Task source is invalid")
        if not isinstance(self.operation, TaskOperation):
            raise TaskInterpretationError("Task operation is invalid")
        if not isinstance(self.activity_target, TaskActivityTarget):
            raise TaskInterpretationError("Task activity target is invalid")
        if not isinstance(self.temporal_mentions, tuple) or not all(
            isinstance(item, TaskTemporalMention) for item in self.temporal_mentions
        ):
            raise TaskInterpretationError("Task temporal mentions are invalid")
        if len(self.temporal_mentions) > 4:
            raise TaskInterpretationError("Task temporal mentions are too large")
        if not isinstance(self.relationship_mentions, tuple) or not all(
            isinstance(item, TaskRelationshipMention) for item in self.relationship_mentions
        ):
            raise TaskInterpretationError("Task relationship mentions are invalid")
        if len(self.relationship_mentions) > 2:
            raise TaskInterpretationError("Task relationship mentions are too large")
        relationship_roles: set[TaskRelationshipRole] = set()
        for mention in self.relationship_mentions:
            if self.source_text.count(mention.text) != 1:
                raise TaskInterpretationError(
                    "Task relationship wording must identify one source occurrence"
                )
            if mention.role in relationship_roles:
                raise TaskInterpretationError("Task relationship roles must be unique")
            relationship_roles.add(mention.role)
        work_session_operation = self.operation.value in _WORK_SESSION_OPERATIONS
        roles: set[TaskTemporalRole] = set()
        if work_session_operation:
            role_cursors: dict[TaskTemporalRole, int] = {}
            for mention in self.temporal_mentions:
                cursor = role_cursors.get(mention.role, 0)
                position = self.source_text.find(mention.text, cursor)
                if position < 0:
                    raise TaskInterpretationError(
                        "Work Session temporal wording is not grounded in source order for its role"
                    )
                role_cursors[mention.role] = position + len(mention.text)
                roles.add(mention.role)
        else:
            cursor = 0
            for mention in self.temporal_mentions:
                position = self.source_text.find(mention.text, cursor)
                if position < 0:
                    raise TaskInterpretationError(
                        "Task temporal wording is not grounded in source order"
                    )
                cursor = position + len(mention.text)
                if mention.role in roles:
                    raise TaskInterpretationError("Task temporal roles must be unique")
                roles.add(mention.role)
        if (
            not isinstance(self.clear_fields, tuple)
            or len(set(self.clear_fields)) != len(self.clear_fields)
            or any(field not in _TASK_CLEARABLE_FIELDS for field in self.clear_fields)
        ):
            raise TaskInterpretationError("Task clear fields are invalid")
        if roles & {
            TaskTemporalRole(role)
            for role, field in _TASK_TEMPORAL_FIELDS.items()
            if field in self.clear_fields
        }:
            raise TaskInterpretationError("Task cannot set and clear the same temporal property")

        session_roles = {role for role in roles if role.value in _WORK_SESSION_TEMPORAL_ROLES}
        if work_session_operation:
            activity_operation = self.operation is TaskOperation.ADD_WORK_SESSION_ACTIVITY
            if activity_operation:
                if self.activity_target is TaskActivityTarget.TASK:
                    if (
                        not isinstance(self.task_reference, str)
                        or not self.task_reference.strip()
                        or self.source_text.count(self.task_reference) != 1
                    ):
                        raise TaskInterpretationError(
                            "Task-targeted Work Session activity requires one grounded Task reference"
                        )
                elif self.activity_target is TaskActivityTarget.ACTIVE:
                    if self.task_reference is not None or self.temporal_mentions:
                        raise TaskInterpretationError(
                            "Active Work Session activity cannot carry Task or date selection"
                        )
                else:
                    raise TaskInterpretationError(
                        "Work Session activity requires ACTIVE or TASK selection"
                    )
                if (
                    not isinstance(self.activity_text, str)
                    or not self.activity_text.strip()
                    or len(self.activity_text) > 2_000
                    or self.source_text.count(self.activity_text) != 1
                ):
                    raise TaskInterpretationError(
                        "Work Session activity requires one grounded activity span"
                    )
            else:
                if self.activity_target is not TaskActivityTarget.NONE:
                    raise TaskInterpretationError(
                        "Only Work Session activity may carry an activity target"
                    )
                if (
                    not isinstance(self.task_reference, str)
                    or not self.task_reference.strip()
                    or self.source_text.count(self.task_reference) != 1
                ):
                    raise TaskInterpretationError(
                        "Work Session operation requires one grounded Task reference"
                    )
                if self.activity_text is not None:
                    raise TaskInterpretationError(
                        "Only Work Session activity may carry activity text"
                    )
            if self.query_scope is not None or self.clear_fields or self.relationship_mentions:
                raise TaskInterpretationError(
                    "Work Session operation cannot carry Task query, clear, or relationship semantics"
                )
            if len(session_roles) != len(roles):
                raise TaskInterpretationError(
                    "Work Session operation cannot carry Task scheduling temporal roles"
                )
            if self.operation is TaskOperation.START_WORK_SESSION and any(
                role is not TaskTemporalRole.WORK_SESSION_START_AT for role in roles
            ):
                raise TaskInterpretationError("Work Session start accepts only a start instant")
            if self.operation is TaskOperation.STOP_WORK_SESSION and any(
                role is not TaskTemporalRole.WORK_SESSION_END_AT for role in roles
            ):
                raise TaskInterpretationError("Work Session stop accepts only an end instant")
            if self.operation is TaskOperation.EDIT_WORK_SESSION and (
                not self.temporal_mentions
                or any(
                    role
                    not in {
                        TaskTemporalRole.WORK_SESSION_START_AT,
                        TaskTemporalRole.WORK_SESSION_END_AT,
                    }
                    for role in roles
                )
            ):
                raise TaskInterpretationError("Work Session edit requires corrected start/end time")
            if activity_operation and any(
                role is not TaskTemporalRole.WORK_SESSION_AT for role in roles
            ):
                raise TaskInterpretationError(
                    "Work Session activity accepts only a session-selection time"
                )
        else:
            if self.task_reference is not None:
                raise TaskInterpretationError(
                    "Only Work Session operations may carry a direct Task reference"
                )
            if self.activity_text is not None:
                raise TaskInterpretationError("Only Work Session activity may carry activity text")
            if session_roles:
                raise TaskInterpretationError(
                    "Task lifecycle/scheduling cannot carry Work Session temporal roles"
                )
            if self.operation is TaskOperation.QUERY:
                if (
                    self.query_scope is None
                    or self.clear_fields
                    or self.temporal_mentions
                    or self.relationship_mentions
                ):
                    raise TaskInterpretationError(
                        "Tasks v0 query requires one lifecycle scope without temporal range semantics"
                    )
            elif self.query_scope is not None:
                raise TaskInterpretationError("Task write cannot carry query scope")
            if self.operation not in {
                TaskOperation.CREATE,
                TaskOperation.UPDATE,
                TaskOperation.QUERY,
            } and (self.temporal_mentions or self.clear_fields or self.relationship_mentions):
                raise TaskInterpretationError(
                    "Lifecycle transition cannot also change task scheduling or relationships"
                )
            if self.operation is TaskOperation.CREATE and self.clear_fields:
                raise TaskInterpretationError("Task create cannot clear scheduling properties")
            if self.operation is TaskOperation.UPDATE and not (
                self.temporal_mentions or self.clear_fields or self.relationship_mentions
            ):
                raise TaskInterpretationError(
                    "Task update has no scheduling or relationship change"
                )
            if self.temporal_mentions and self.clear_fields:
                # Core cannot yet atomically mix property set/remove in one generic unit. Keep the app
                # fail-closed instead of allowing a partial schedule transition.
                raise TaskInterpretationError(
                    "Mixed task schedule set/remove is not supported atomically"
                )

    def requires_temporal(self) -> bool:
        return bool(self.temporal_mentions)


_STATUS_FOR_OPERATION = {
    TaskOperation.CREATE: "pending",
    TaskOperation.START: "in_progress",
    TaskOperation.COMPLETE: "completed",
    TaskOperation.REOPEN: "pending",
    TaskOperation.CANCEL: "cancelled",
}


def _property_evidence(field: str, source_text: str, value: str) -> DomainEvidence:
    return DomainEvidence(f"property.{field}", source_text, value)


def _remove_evidence(field: str, source_text: str) -> DomainEvidence:
    return DomainEvidence(f"property_remove.{field}", source_text, "null")


def compose_work_session_times(
    task: TaskInterpretation,
    temporal: TemporalInterpretation | None,
    *,
    now: str,
) -> tuple[str | None, str | None]:
    """Normalize Tasks-owned Work Session start/end instants from Temporal evidence."""
    if not isinstance(task, TaskInterpretation) or task.operation not in {
        TaskOperation.START_WORK_SESSION,
        TaskOperation.STOP_WORK_SESSION,
        TaskOperation.EDIT_WORK_SESSION,
    }:
        raise TaskInterpretationError("Work Session interpretation is invalid")
    if task.requires_temporal() != (temporal is not None):
        raise TaskInterpretationError("Work Session temporal dependency is inconsistent")
    if temporal is not None and temporal.source_text != task.source_text:
        raise TaskInterpretationError("Tasks and Temporal sources differ")
    try:
        current = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise TaskInterpretationError("Work Session current time is invalid") from error
    if current.tzinfo is None:
        raise TaskInterpretationError("Work Session current time must be offset-aware")

    start_at: str | None = None
    end_at: str | None = None
    if temporal is not None:
        temporal_positions = _temporal_positions(temporal)
        grouped: dict[TaskTemporalRole, list[object]] = {}
        for task_mention in task.temporal_mentions:
            task_position = _unique_source_position(task.source_text, task_mention.text)
            matches = [
                item
                for item in temporal_positions
                if _spans_overlap(
                    task_position,
                    task_position + len(task_mention.text),
                    item[0],
                    item[1],
                )
            ]
            if not matches:
                raise TaskInterpretationError(
                    "Work Session temporal role does not map to Temporal evidence"
                )
            grouped.setdefault(task_mention.role, []).extend(item[2].resolution for item in matches)
        for role, resolutions in grouped.items():
            value = _merge_work_session_datetime(resolutions)
            if role is TaskTemporalRole.WORK_SESSION_START_AT:
                start_at = value
            elif role is TaskTemporalRole.WORK_SESSION_END_AT:
                end_at = value
            else:
                raise TaskInterpretationError("Work Session temporal role is invalid")

    if task.operation is TaskOperation.START_WORK_SESSION and start_at is None:
        start_at = now
    if task.operation is TaskOperation.STOP_WORK_SESSION and end_at is None:
        end_at = now
    return start_at, end_at


def compose_work_session_activity_date(
    task: TaskInterpretation, temporal: TemporalInterpretation | None
) -> str | None:
    """Resolve an optional exact local calendar date used only to select a Work Session."""
    if (
        not isinstance(task, TaskInterpretation)
        or task.operation is not TaskOperation.ADD_WORK_SESSION_ACTIVITY
    ):
        raise TaskInterpretationError("Work Session activity interpretation is invalid")
    if task.requires_temporal() != (temporal is not None):
        raise TaskInterpretationError("Work Session activity temporal dependency is inconsistent")
    if temporal is None:
        return None
    if temporal.source_text != task.source_text:
        raise TaskInterpretationError("Tasks and Temporal sources differ")
    temporal_positions = _temporal_positions(temporal)
    dates: set[str] = set()
    for mention in task.temporal_mentions:
        if mention.role is not TaskTemporalRole.WORK_SESSION_AT:
            raise TaskInterpretationError("Work Session activity temporal role is invalid")
        position = _unique_source_position(task.source_text, mention.text)
        matches = [
            item
            for item in temporal_positions
            if _spans_overlap(position, position + len(mention.text), item[0], item[1])
        ]
        if not matches:
            raise TaskInterpretationError("Work Session activity time is not grounded")
        for _start, _end, temporal_mention in matches:
            resolution = temporal_mention.resolution
            if resolution.kind is TemporalResolutionKind.EXACT_DATE:
                if resolution.exact_date is None:
                    raise TaskInterpretationError("Work Session activity date is unavailable")
                dates.add(resolution.exact_date)
            elif resolution.kind is TemporalResolutionKind.EXACT_DATETIME:
                if resolution.exact_datetime is None:
                    raise TaskInterpretationError("Work Session activity time is unavailable")
                try:
                    dates.add(
                        datetime.fromisoformat(resolution.exact_datetime.replace("Z", "+00:00"))
                        .date()
                        .isoformat()
                    )
                except ValueError as error:
                    raise TaskInterpretationError(
                        "Work Session activity time is invalid"
                    ) from error
            else:
                raise TaskInterpretationError(
                    "Work Session activity selection requires an exact date or date-time"
                )
    if len(dates) != 1:
        raise TaskInterpretationError("Work Session activity selection is ambiguous")
    return next(iter(dates))


def _merge_work_session_datetime(resolutions: list[object]) -> str:
    """Collapse split date/time evidence only when it proves one exact Work Session instant."""
    datetimes: set[str] = set()
    dates: set[str] = set()
    for resolution in resolutions:
        kind = getattr(resolution, "kind", None)
        if kind is TemporalResolutionKind.EXACT_DATETIME:
            value = getattr(resolution, "exact_datetime", None)
            if not isinstance(value, str):
                raise TaskInterpretationError("Work Session temporal value is unavailable")
            datetimes.add(value)
        elif kind is TemporalResolutionKind.EXACT_DATE:
            value = getattr(resolution, "exact_date", None)
            if not isinstance(value, str):
                raise TaskInterpretationError("Work Session temporal value is unavailable")
            dates.add(value)
        else:
            raise TaskInterpretationError("Work Session times require exact temporal evidence")
    if len(datetimes) != 1 or len(dates) > 1:
        raise TaskInterpretationError("Work Session temporal evidence is not one exact date-time")
    value = next(iter(datetimes))
    if dates and value[:10] != next(iter(dates)):
        raise TaskInterpretationError("Work Session date and time evidence conflict")
    return value


def compose_task_domain_interpretation(
    task: TaskInterpretation,
    temporal: TemporalInterpretation | None,
    *,
    now: str,
) -> DomainInterpretation:
    """Combine Tasks role semantics with Temporal normalization into Core-safe property evidence."""
    if not isinstance(task, TaskInterpretation):
        raise TaskInterpretationError("Task interpretation is invalid")
    if task.operation.value in _WORK_SESSION_OPERATIONS:
        raise TaskInterpretationError(
            "Work Session operations do not mutate Task state through Core"
        )
    if task.requires_temporal() != (temporal is not None):
        raise TaskInterpretationError("Task temporal dependency is inconsistent")
    if temporal is not None and temporal.source_text != task.source_text:
        raise TaskInterpretationError("Task and Temporal sources differ")

    evidence: list[DomainEvidence] = []
    status = _STATUS_FOR_OPERATION.get(task.operation)
    if status is not None:
        evidence.append(_property_evidence("status", task.source_text, status))
    if task.operation is TaskOperation.COMPLETE:
        evidence.append(_property_evidence("completed_at", task.source_text, now))

    if temporal is not None:
        temporal_positions = _temporal_positions(temporal)
        for task_mention in task.temporal_mentions:
            task_position = _unique_source_position(task.source_text, task_mention.text)
            matches = [
                item
                for item in temporal_positions
                if _spans_overlap(
                    task_position,
                    task_position + len(task_mention.text),
                    item[0],
                    item[1],
                )
            ]
            if len(matches) != 1:
                raise TaskInterpretationError(
                    "Task temporal role does not map to one Temporal result"
                )
            _start, _end, mention = matches[0]
            resolution = mention.resolution
            field = _TASK_TEMPORAL_FIELDS[task_mention.role.value]
            if task_mention.role is TaskTemporalRole.TARGET_DATE:
                if resolution.kind is not TemporalResolutionKind.EXACT_DATE:
                    raise TaskInterpretationError("Task target_date requires an exact date")
                value = resolution.exact_date
            elif task_mention.role in {
                TaskTemporalRole.PLANNED_START_AT,
                TaskTemporalRole.PLANNED_END_AT,
            }:
                if resolution.kind is not TemporalResolutionKind.EXACT_DATETIME:
                    raise TaskInterpretationError("Task planned time requires an exact date-time")
                value = resolution.exact_datetime
            else:
                if resolution.kind is TemporalResolutionKind.EXACT_DATE:
                    value = resolution.exact_date
                elif resolution.kind is TemporalResolutionKind.EXACT_DATETIME:
                    value = resolution.exact_datetime
                else:
                    raise TaskInterpretationError(
                        "Task deadline requires an exact date or date-time"
                    )
            if value is None:
                raise TaskInterpretationError("Task temporal value is unavailable")
            evidence.append(_property_evidence(field, task_mention.text, value))

    for field in task.clear_fields:
        evidence.append(_remove_evidence(field, task.source_text))
    if task.operation is TaskOperation.QUERY:
        assert task.query_scope is not None
        evidence.append(
            DomainEvidence("task.query_scope", task.source_text, task.query_scope.value)
        )

    return DomainInterpretation("tasks", task.source_text, task.operation.value, tuple(evidence))


def _unique_source_position(source: str, text: str) -> int:
    first = source.find(text)
    if first < 0 or source.find(text, first + 1) >= 0:
        raise TaskInterpretationError("Task temporal wording must identify one source occurrence")
    return first


def _temporal_positions(temporal: TemporalInterpretation):
    cursor = 0
    result = []
    for mention in temporal.mentions:
        start = temporal.source_text.find(mention.temporal_text, cursor)
        if start < 0:
            raise TaskInterpretationError("Temporal evidence is not grounded")
        end = start + len(mention.temporal_text)
        result.append((start, end, mention))
        cursor = end
    return result


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def task_interpretation_json_schema() -> dict[str, Any]:
    """Return Tasks' closed lifecycle/role contract; dates remain unresolved strings."""
    temporal_item = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "role": {"type": "string", "enum": [item.value for item in TaskTemporalRole]},
        },
        "required": ["text", "role"],
        "additionalProperties": False,
    }
    relationship_item = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "role": {
                "type": "string",
                "enum": [item.value for item in TaskRelationshipRole],
            },
        },
        "required": ["text", "role"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": [item.value for item in TaskOperation]},
            "temporal_mentions": {
                "type": "array",
                "maxItems": 4,
                "items": temporal_item,
            },
            "relationship_mentions": {
                "type": "array",
                "maxItems": 2,
                "items": relationship_item,
            },
            "clear_fields": {
                "type": "array",
                "maxItems": len(_TASK_CLEARABLE_FIELDS),
                "items": {"type": "string", "enum": sorted(_TASK_CLEARABLE_FIELDS)},
            },
            "query_scope": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "enum": [item.value for item in TaskQueryScope]},
                ]
            },
            "task_reference": {
                "type": "string",
                "description": (
                    "Exact candidate task-reference span from the source. Copy named references "
                    "without deciding whether they resolve to a real Task."
                ),
            },
            "activity_text": {
                "type": "string",
                "maxLength": 2000,
                "description": "Exact source span containing only the activity to record.",
            },
            "activity_target": {
                "type": "string",
                "enum": [item.value for item in TaskActivityTarget],
                "description": (
                    "For ADD_WORK_SESSION_ACTIVITY: TASK whenever the session wording supplies "
                    "any named candidate reference; ACTIVE only for an explicitly current/active "
                    "session with no named candidate. NONE for every other operation."
                ),
            },
        },
        "required": [
            "operation",
            "temporal_mentions",
            "relationship_mentions",
            "clear_fields",
            "query_scope",
            "task_reference",
            "activity_text",
            "activity_target",
        ],
        "additionalProperties": False,
    }


def parse_task_interpretation(payload: Mapping[str, Any], source_text: str) -> TaskInterpretation:
    if not isinstance(payload, Mapping) or set(payload) != {
        "operation",
        "temporal_mentions",
        "relationship_mentions",
        "clear_fields",
        "query_scope",
        "task_reference",
        "activity_text",
        "activity_target",
    }:
        raise TaskInterpretationError("Task interpretation fields are invalid")
    try:
        operation = TaskOperation(payload["operation"])
        query_scope = (
            None if payload["query_scope"] is None else TaskQueryScope(payload["query_scope"])
        )
        activity_target = TaskActivityTarget(payload["activity_target"])
    except (TypeError, ValueError) as error:
        raise TaskInterpretationError("Task interpretation enum is invalid") from error
    raw_temporal = payload["temporal_mentions"]
    if not isinstance(raw_temporal, list):
        raise TaskInterpretationError("Task temporal mentions are invalid")
    mentions: list[TaskTemporalMention] = []
    for raw in raw_temporal:
        if not isinstance(raw, Mapping) or set(raw) != {"text", "role"}:
            raise TaskInterpretationError("Task temporal mention is invalid")
        try:
            mentions.append(TaskTemporalMention(raw["text"], TaskTemporalRole(raw["role"])))
        except (TypeError, ValueError) as error:
            raise TaskInterpretationError("Task temporal mention is invalid") from error
    raw_relationships = payload["relationship_mentions"]
    if not isinstance(raw_relationships, list):
        raise TaskInterpretationError("Task relationship mentions are invalid")
    relationships: list[TaskRelationshipMention] = []
    for raw in raw_relationships:
        if not isinstance(raw, Mapping) or set(raw) != {"text", "role"}:
            raise TaskInterpretationError("Task relationship mention is invalid")
        try:
            relationships.append(
                TaskRelationshipMention(raw["text"], TaskRelationshipRole(raw["role"]))
            )
        except (TypeError, ValueError) as error:
            raise TaskInterpretationError("Task relationship mention is invalid") from error
    clear_fields = payload["clear_fields"]
    if not isinstance(clear_fields, list) or any(
        not isinstance(item, str) for item in clear_fields
    ):
        raise TaskInterpretationError("Task clear fields are invalid")
    return TaskInterpretation(
        source_text=source_text,
        operation=operation,
        temporal_mentions=tuple(mentions),
        clear_fields=tuple(clear_fields),
        query_scope=query_scope,
        relationship_mentions=tuple(relationships),
        task_reference=payload["task_reference"] or None,
        activity_text=payload["activity_text"] or None,
        activity_target=activity_target,
    )


def render_task_prompt() -> str:
    """Render the single closed Tasks interpretation contract."""
    return (
        "You are Odyssey Tasks. Interpret only Tasks-owned semantics in the exact routed user source. "
        "Never resolve note identities, invent identities, normalize time, emit Markdown, or perform mutations. "
        "CREATE creates an actionable commitment. START is only an explicit lifecycle transition to in_progress; "
        "it never means that actual work has started. COMPLETE, REOPEN, and CANCEL are lifecycle transitions. "
        "UPDATE changes task scheduling without changing lifecycle. QUERY inspects tasks. START_WORK_SESSION begins "
        "actual work on one existing task, STOP_WORK_SESSION ends actual work, and EDIT_WORK_SESSION corrects its "
        "recorded start/end time. ADD_WORK_SESSION_ACTIVITY records user-authored information about work performed "
        "inside one existing Work Session; activity_text must be the smallest exact contiguous source substring "
        "containing only the information to record. For ADD_WORK_SESSION_ACTIVITY, do not decide whether a named "
        "reference is truly a Task: when the Work Session wording supplies any named candidate reference, set "
        "activity_target TASK and copy that exact candidate into task_reference so Core can resolve it later. Use "
        "activity_target ACTIVE only for an explicitly current/active Work Session with no named candidate reference. "
        "All other operations use activity_target NONE. For start, stop, and edit, task_reference must be the smallest "
        "exact non-empty source substring naming the task. For ADD_WORK_SESSION_ACTIVITY, copy that exact task span "
        "when the user names a task; return an empty task_reference only when the user explicitly targets the "
        "current/active Work Session without naming a task. For every non-Work-Session operation, task_reference "
        "and activity_text must be exact empty strings. For Work Session operations other than activity logging, "
        "activity_text must also be empty. Task scheduling uses TARGET_DATE, PLANNED_START_AT, PLANNED_END_AT, or "
        "DEADLINE_AT only outside Work Sessions. Work Session start/end corrections use WORK_SESSION_START_AT and "
        "WORK_SESSION_END_AT. A date or time used only to select which session receives activity uses WORK_SESSION_AT. "
        "Every temporal_mentions.text must be an exact contiguous source substring. If date and clock wording are "
        "separate, emit separate mentions with the same role; Odyssey combines them only when Temporal proves they "
        "are coherent. Work Session start/stop with no explicit time uses the current instant later and emits no "
        "invented temporal mention. EDIT_WORK_SESSION requires at least one corrected start/end mention. Activity "
        "logging may omit temporal mentions when it targets the active session. relationship_mentions may assign "
        "exact source wording to ASSIGNEE or PARENT_TASK only. clear_fields removes task scheduling values only. "
        "Do not combine ordinary lifecycle transitions with schedule changes. QUERY must choose the narrow scope. "
        "Return only the strict JSON object."
    )


class OpenAITaskInterpreter:
    """Interpret one Tasks route with one bounded provider call and zero retries."""

    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self.model = TASK_INTERPRETER_MODEL
        self.reasoning_effort = TASK_INTERPRETER_REASONING_EFFORT
        self.last_call = False
        self.last_usage = None
        self.last_response_id = None
        self.last_provider_status = None
        self.last_error_category = None

    @classmethod
    def from_environment(cls) -> OpenAITaskInterpreter:
        if not os.environ.get("OPENAI_API_KEY"):
            raise TaskInterpretationError("OPENAI_API_KEY is required for Tasks interpretation")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise TaskInterpretationError(
                "Install the OpenAI SDK for Tasks interpretation"
            ) from error
        return cls(OpenAI(max_retries=0, timeout=TASK_INTERPRETER_TIMEOUT_SECONDS))

    def interpret(
        self, source_text: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> TaskInterpretation:
        del conversation_context
        if not isinstance(source_text, str) or not source_text.strip():
            raise TaskInterpretationError("Task source must be non-empty")
        self.last_call = True
        try:
            response = self._client.responses.create(
                model=self.model,
                reasoning={"effort": self.reasoning_effort},
                store=False,
                max_output_tokens=TASK_INTERPRETER_MAX_OUTPUT_TOKENS,
                input=[
                    {"role": "system", "content": render_task_prompt()},
                    {"role": "user", "content": source_text},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_task_interpretation",
                        "strict": True,
                        "schema": task_interpretation_json_schema(),
                    }
                },
            )
        except Exception as error:
            self.last_error_category = type(error).__name__[:120]
            raise TaskInterpretationError("Tasks provider call failed") from error
        self.last_usage = getattr(response, "usage", None)
        self.last_response_id = getattr(response, "id", None)
        self.last_provider_status = getattr(response, "status", None)
        if self.last_provider_status != "completed":
            self.last_error_category = "IncompleteProviderResponse"
            raise TaskInterpretationError("Tasks provider response was not completed")
        try:
            payload = json.loads(response.output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            self.last_error_category = "MalformedTaskJSON"
            raise TaskInterpretationError("Tasks provider returned malformed output") from error
        try:
            return parse_task_interpretation(payload, source_text)
        except TaskInterpretationError:
            self.last_error_category = "LocalTaskValidationError"
            raise
