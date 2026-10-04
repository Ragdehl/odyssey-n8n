"""Bounded Tasks lifecycle interpretation without Core mutation authority."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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


class TaskQueryScope(StrEnum):
    ALL = "ALL"
    OPEN = "OPEN"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    OVERDUE = "OVERDUE"


class TaskTemporalRole(StrEnum):
    TARGET_DATE = "TARGET_DATE"
    PLANNED_START_AT = "PLANNED_START_AT"
    PLANNED_END_AT = "PLANNED_END_AT"
    DEADLINE_AT = "DEADLINE_AT"


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
class TaskInterpretation:
    """Carry only Tasks lifecycle meaning and temporal-role assignments."""

    source_text: str
    operation: TaskOperation
    temporal_mentions: tuple[TaskTemporalMention, ...] = ()
    clear_fields: tuple[str, ...] = ()
    query_scope: TaskQueryScope | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_text, str) or not self.source_text.strip():
            raise TaskInterpretationError("Task source is invalid")
        if not isinstance(self.operation, TaskOperation):
            raise TaskInterpretationError("Task operation is invalid")
        if not isinstance(self.temporal_mentions, tuple) or not all(
            isinstance(item, TaskTemporalMention) for item in self.temporal_mentions
        ):
            raise TaskInterpretationError("Task temporal mentions are invalid")
        if len(self.temporal_mentions) > 4:
            raise TaskInterpretationError("Task temporal mentions are too large")
        cursor = 0
        roles: set[TaskTemporalRole] = set()
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
        if self.operation is TaskOperation.QUERY:
            if self.query_scope is None or self.clear_fields or self.temporal_mentions:
                raise TaskInterpretationError(
                    "Tasks v0 query requires one lifecycle scope without temporal range semantics"
                )
        elif self.query_scope is not None:
            raise TaskInterpretationError("Task write cannot carry query scope")
        if self.operation not in {
            TaskOperation.CREATE,
            TaskOperation.UPDATE,
            TaskOperation.QUERY,
        } and (self.temporal_mentions or self.clear_fields):
            raise TaskInterpretationError("Lifecycle transition cannot also reschedule in Tasks v0")
        if self.operation is TaskOperation.CREATE and self.clear_fields:
            raise TaskInterpretationError("Task create cannot clear scheduling properties")
        if self.operation is TaskOperation.UPDATE and not (
            self.temporal_mentions or self.clear_fields
        ):
            raise TaskInterpretationError("Task update has no scheduling change")
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


def compose_task_domain_interpretation(
    task: TaskInterpretation,
    temporal: TemporalInterpretation | None,
    *,
    now: str,
) -> DomainInterpretation:
    """Combine Tasks role semantics with Temporal normalization into Core-safe property evidence."""
    if not isinstance(task, TaskInterpretation):
        raise TaskInterpretationError("Task interpretation is invalid")
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
    return {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": [item.value for item in TaskOperation]},
            "temporal_mentions": {
                "type": "array",
                "maxItems": 4,
                "items": temporal_item,
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
        },
        "required": ["operation", "temporal_mentions", "clear_fields", "query_scope"],
        "additionalProperties": False,
    }


def parse_task_interpretation(payload: Mapping[str, Any], source_text: str) -> TaskInterpretation:
    if not isinstance(payload, Mapping) or set(payload) != {
        "operation",
        "temporal_mentions",
        "clear_fields",
        "query_scope",
    }:
        raise TaskInterpretationError("Task interpretation fields are invalid")
    try:
        operation = TaskOperation(payload["operation"])
        query_scope = (
            None if payload["query_scope"] is None else TaskQueryScope(payload["query_scope"])
        )
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
    clear_fields = payload["clear_fields"]
    if not isinstance(clear_fields, list) or any(
        not isinstance(item, str) for item in clear_fields
    ):
        raise TaskInterpretationError("Task clear fields are invalid")
    return TaskInterpretation(
        source_text,
        operation,
        tuple(mentions),
        tuple(clear_fields),
        query_scope,
    )


def render_task_prompt() -> str:
    """Render only Tasks lifecycle classification and temporal-role assignment instructions."""
    return (
        "You are Odyssey Tasks. Interpret only task lifecycle semantics in the exact routed user "
        "source. Never choose a Core note target, invent a task identity, normalize a date/time, emit "
        "facts, references, filters, Markdown, or mutation instructions. CREATE means the user is "
        "creating an actionable commitment, not merely describing a future or past occurrence. START "
        "means move an existing task into active work. COMPLETE, REOPEN, and CANCEL are explicit "
        "lifecycle transitions. UPDATE changes task scheduling without changing lifecycle state. QUERY "
        "asks to inspect tasks. Assign every scheduling/deadline temporal phrase material to Tasks to "
        "exact source text and exactly one role: TARGET_DATE is the day the user intends to address the "
        "task and is not a hard deadline; PLANNED_START_AT and PLANNED_END_AT are exact planned clock "
        "instants; DEADLINE_AT is the hard latest date/time. Do not use DEADLINE_AT merely because a "
        "task is associated with a date. Do not infer task lifecycle from words like task, future tense, "
        "or a clock time alone. clear_fields is only for an explicit request to remove an existing "
        "scheduling value. Do not combine lifecycle transitions with schedule changes in v0. QUERY must "
        "choose the narrow query_scope that matches the request. Return only the strict JSON object."
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
