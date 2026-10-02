"""Closed Calendar planner contract and routed executor for Calendar v0.

Calendar owns temporal interpretation after routing.  It never receives sibling current-message
text, and it delegates canonical writes back to injected Core boundaries.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
)
from odyssey_core.request_planning import RequestPlan
from odyssey_core.semantic_write import (
    ApplyTo,
    IdentityPart,
    SemanticWriteCompileError,
    SemanticWriteIntent,
    TemporalReferencePart,
    compile_semantic_write,
    decode_semantic_write_action,
)
from odyssey_core.temporal import DateRange, TemporalValueError, normalize_iso_date

CALENDAR_PLANNER_MODEL = "gpt-6-luna"
CALENDAR_PLANNER_REASONING_EFFORT = "low"
CALENDAR_PLANNER_MAX_OUTPUT_TOKENS = 1_024
CALENDAR_PLANNER_MAX_RECENT_TURNS = 8
CALENDAR_PLANNER_MAX_CONTEXT_CHARS = 1_000
CALENDAR_PLANNER_TIMEOUT_SECONDS = 30.0


class CalendarPlannerError(ValueError):
    """Report an invalid or unavailable Calendar planning result without executing it."""


class TemporalResolutionKind(StrEnum):
    """Name the only v0 temporal-resolution shapes preserved by Calendar."""

    EXACT_DATE = "EXACT_DATE"
    DATE_RANGE = "DATE_RANGE"
    UNSPECIFIED = "UNSPECIFIED"


class CalendarPlanOutcome(StrEnum):
    """Name whether Calendar has a complete executable intent or withheld it."""

    PLAN = "PLAN"
    FAIL_CLOSED = "FAIL_CLOSED"


class CalendarIntentKind(StrEnum):
    """Name Calendar's narrow Day capture and Core-owned semantic write choices."""

    DAY_LITERAL_CAPTURE = "DAY_LITERAL_CAPTURE"
    CORE_SEMANTIC_WRITE = "CORE_SEMANTIC_WRITE"


class CalendarFailureCode(StrEnum):
    """Keep non-executable Calendar reasons bounded and content-free."""

    RANGE_REQUIRES_RANGE_AWARE_OPERATION = "RANGE_REQUIRES_RANGE_AWARE_OPERATION"
    TEMPORAL_UNRESOLVED = "TEMPORAL_UNRESOLVED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True, slots=True)
class TemporalResolution:
    """Carry exact, range, or unresolved temporal evidence without guessing an exact Day."""

    kind: TemporalResolutionKind
    exact_date: str | None = None
    date_range: DateRange | None = None


@dataclass(frozen=True, slots=True)
class CalendarPlan:
    """Represent one validated Calendar result before any Core mutation is attempted."""

    outcome: CalendarPlanOutcome
    intent: CalendarIntentKind | None
    temporal: TemporalResolution
    semantic_write: SemanticWriteIntent | None = None
    failure_code: CalendarFailureCode | None = None


class ResponsesClient(Protocol):
    """Describe the injected Responses API subset required for one planner call."""

    responses: Any


def _bounded_context(conversation_context: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Validate and truncate only prior conversation evidence for Calendar interpretation."""
    if not isinstance(conversation_context, Sequence) or isinstance(conversation_context, str):
        raise CalendarPlannerError("Calendar context must be a sequence")
    result: list[dict[str, str]] = []
    for turn in conversation_context[-CALENDAR_PLANNER_MAX_RECENT_TURNS:]:
        if not isinstance(turn, Mapping):
            raise CalendarPlannerError("Calendar context turn is invalid")
        role, text = turn.get("role"), turn.get("text", turn.get("content"))
        if role not in {"user", "assistant"} or not isinstance(text, str):
            raise CalendarPlannerError("Calendar context turn is invalid")
        result.append({"role": role, "text": text[:CALENDAR_PLANNER_MAX_CONTEXT_CHARS]})
    return result


def _calendar_semantic_write_definitions() -> dict[str, Any]:
    """Build Calendar's app-native fact-write schema without generic Core mutation fields."""
    candidate_scope = {
        "type": "object",
        "properties": {
            "source": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {"kind": {"type": "string", "enum": ["SELF"]}},
                        "required": ["kind"],
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string", "enum": ["SOURCE_DESCRIPTION"]},
                            "description": {"type": "string"},
                        },
                        "required": ["kind", "description"],
                        "additionalProperties": False,
                    },
                ]
            },
            "member_query": {"type": "string"},
            "extent": {"type": "string", "enum": ["one_member"]},
        },
        "required": ["source", "member_query", "extent"],
        "additionalProperties": False,
    }
    identity = {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "binding": {"type": "string", "enum": ["self", "described"]},
            "direct_name": {"type": ["string", "null"]},
            "candidate_scope": {
                "anyOf": [
                    {"type": "null"},
                    {"$ref": "#/$defs/calendar_candidate_scope"},
                ]
            },
        },
        "required": ["description", "binding", "direct_name", "candidate_scope"],
        "additionalProperties": False,
    }
    literal_part = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["literal"]},
            "text": {"type": "string"},
        },
        "required": ["kind", "text"],
        "additionalProperties": False,
    }
    identity_part = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["identity"]},
            "text": {"type": "string"},
            "identity": {"$ref": "#/$defs/calendar_identity"},
        },
        "required": ["kind", "text", "identity"],
        "additionalProperties": False,
    }
    temporal_part = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["temporal_reference"]},
            "text": {"type": "string"},
            "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        },
        "required": ["kind", "text", "date"],
        "additionalProperties": False,
    }
    fact = {
        "type": "object",
        "properties": {
            "parts": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "anyOf": [
                        {"$ref": "#/$defs/calendar_literal_part"},
                        {"$ref": "#/$defs/calendar_identity_part"},
                        {"$ref": "#/$defs/calendar_temporal_reference_part"},
                    ]
                },
            }
        },
        "required": ["parts"],
        "additionalProperties": False,
    }
    operation = {
        "type": "object",
        "properties": {
            "target": {"$ref": "#/$defs/calendar_identity"},
            "facts": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/$defs/calendar_fact"},
            },
        },
        "required": ["target", "facts"],
        "additionalProperties": False,
    }
    write = {
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/$defs/calendar_operation"},
            }
        },
        "required": ["operations"],
        "additionalProperties": False,
    }
    return {
        "calendar_candidate_scope": candidate_scope,
        "calendar_identity": identity,
        "calendar_literal_part": literal_part,
        "calendar_identity_part": identity_part,
        "calendar_temporal_reference_part": temporal_part,
        "calendar_fact": fact,
        "calendar_operation": operation,
        "calendar_semantic_write": write,
    }


def calendar_plan_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Build Calendar's app-native strict schema without exposing generic Core mutation vocabulary."""
    del schema
    definitions = _calendar_semantic_write_definitions()
    root = {
        "type": "object",
        "properties": {
            "outcome": {"type": "string", "enum": [item.value for item in CalendarPlanOutcome]},
            "intent": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "enum": [item.value for item in CalendarIntentKind]},
                ]
            },
            "temporal_kind": {
                "type": "string",
                "enum": [item.value for item in TemporalResolutionKind],
            },
            "exact_date": {"type": ["string", "null"]},
            "range_start": {"type": ["string", "null"]},
            "range_end_exclusive": {"type": ["string", "null"]},
            "semantic_write": {
                "anyOf": [
                    {"type": "null"},
                    {"$ref": "#/$defs/calendar_semantic_write"},
                ]
            },
            "failure_code": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "enum": [item.value for item in CalendarFailureCode]},
                ]
            },
        },
        "required": [
            "outcome",
            "intent",
            "temporal_kind",
            "exact_date",
            "range_start",
            "range_end_exclusive",
            "semantic_write",
            "failure_code",
        ],
        "additionalProperties": False,
    }
    return {"$defs": definitions, **root}


def _expand_calendar_identity(raw: Any) -> dict[str, Any]:
    """Translate one app-local identity into the full shared Core semantic identity shape."""
    required = {"description", "binding", "direct_name", "candidate_scope"}
    if not isinstance(raw, Mapping) or set(raw) != required:
        raise SemanticWriteCompileError("Calendar semantic identity fields are invalid")
    scope = raw["candidate_scope"]
    if scope is not None:
        if not isinstance(scope, Mapping) or set(scope) != {"source", "member_query", "extent"}:
            raise SemanticWriteCompileError("Calendar candidate scope fields are invalid")
        if scope["extent"] != "one_member" or not isinstance(scope["member_query"], str):
            raise SemanticWriteCompileError("Calendar candidate scope is not singular")
        source = scope["source"]
        if not isinstance(source, Mapping):
            raise SemanticWriteCompileError("Calendar candidate source is invalid")
        if not (
            (set(source) == {"kind"} and source["kind"] == "SELF")
            or (
                set(source) == {"kind", "description"}
                and source["kind"] == "SOURCE_DESCRIPTION"
                and isinstance(source["description"], str)
            )
        ):
            raise SemanticWriteCompileError("Calendar candidate source fields are invalid")
    return {
        "description": raw["description"],
        "binding": raw["binding"],
        "direct_name": raw["direct_name"],
        "note_type": None,
        "filters": [],
        "candidate_scope": scope,
    }


def _expand_calendar_fact(raw: Any) -> dict[str, Any]:
    """Translate app-local fact parts while expanding only nested identities."""
    if not isinstance(raw, Mapping) or set(raw) != {"parts"} or not isinstance(raw["parts"], list):
        raise SemanticWriteCompileError("Calendar semantic fact fields are invalid")
    parts: list[dict[str, Any]] = []
    for part in raw["parts"]:
        if not isinstance(part, Mapping):
            raise SemanticWriteCompileError("Calendar semantic fact part is invalid")
        if set(part) == {"kind", "text"} and part["kind"] == "literal":
            parts.append(dict(part))
        elif set(part) == {"kind", "text", "date"} and part["kind"] == "temporal_reference":
            parts.append(dict(part))
        elif set(part) == {"kind", "text", "identity"} and part["kind"] == "identity":
            parts.append(
                {
                    "kind": "identity",
                    "text": part["text"],
                    "identity": _expand_calendar_identity(part["identity"]),
                }
            )
        else:
            raise SemanticWriteCompileError("Calendar semantic fact part fields are invalid")
    return {"parts": parts}


def _decode_calendar_semantic_write(raw: Any) -> SemanticWriteIntent:
    """Lower Calendar's minimal write contract into the existing full Core semantic-write contract."""
    if not isinstance(raw, Mapping) or set(raw) != {"operations"}:
        raise SemanticWriteCompileError("Calendar semantic write fields are invalid")
    operations = raw["operations"]
    if not isinstance(operations, list) or not operations:
        raise SemanticWriteCompileError("Calendar semantic write operations are invalid")
    expanded: list[dict[str, Any]] = []
    for operation in operations:
        if not isinstance(operation, Mapping) or set(operation) != {"target", "facts"}:
            raise SemanticWriteCompileError("Calendar semantic operation fields are invalid")
        facts = operation["facts"]
        if not isinstance(facts, list) or not facts:
            raise SemanticWriteCompileError("Calendar semantic operation facts are invalid")
        expanded.append(
            {
                "target": _expand_calendar_identity(operation["target"]),
                "apply_to": "one",
                "intent": "record",
                "facts": [_expand_calendar_fact(fact) for fact in facts],
                "properties": [],
                "tag_changes": [],
                "destination_type": None,
            }
        )
    return decode_semantic_write_action(
        {"kind": "write", "operations": expanded}, allow_temporal_reference=True
    )


def parse_calendar_plan(payload: Mapping[str, Any]) -> CalendarPlan:
    """Decode one closed provider payload and enforce cross-field Calendar safety invariants."""
    required = {
        "outcome",
        "intent",
        "temporal_kind",
        "exact_date",
        "range_start",
        "range_end_exclusive",
        "semantic_write",
        "failure_code",
    }
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise CalendarPlannerError("Calendar planner payload fields are invalid")
    try:
        outcome = CalendarPlanOutcome(payload["outcome"])
        temporal_kind = TemporalResolutionKind(payload["temporal_kind"])
    except (TypeError, ValueError) as error:
        raise CalendarPlannerError("Calendar planner enum is invalid") from error
    temporal = _parse_temporal(temporal_kind, payload)
    intent = _enum_or_none(CalendarIntentKind, payload["intent"], "Calendar intent")
    failure = _enum_or_none(CalendarFailureCode, payload["failure_code"], "Calendar failure")
    raw_semantic = payload["semantic_write"]
    if raw_semantic is None:
        semantic = None
    else:
        try:
            semantic = _decode_calendar_semantic_write(raw_semantic)
        except SemanticWriteCompileError as error:
            raise CalendarPlannerError("Calendar semantic write is invalid") from error
    plan = CalendarPlan(outcome, intent, temporal, semantic, failure)
    _validate_plan(plan)
    return plan


def _enum_or_none(enum_type: type[StrEnum], value: object, name: str) -> Any:
    """Decode one nullable closed enum with a bounded local error."""
    if value is None:
        return None
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise CalendarPlannerError(f"{name} is invalid") from error


def _parse_temporal(kind: TemporalResolutionKind, raw: Mapping[str, Any]) -> TemporalResolution:
    """Validate temporal-shape correlation without inventing an exact date from a range."""
    exact, start, end = raw["exact_date"], raw["range_start"], raw["range_end_exclusive"]
    if kind is TemporalResolutionKind.EXACT_DATE:
        if not isinstance(exact, str) or start is not None or end is not None:
            raise CalendarPlannerError("Exact Calendar date fields are invalid")
        try:
            return TemporalResolution(kind, exact_date=normalize_iso_date(exact))
        except TemporalValueError as error:
            raise CalendarPlannerError("Exact Calendar date is invalid") from error
    if kind is TemporalResolutionKind.DATE_RANGE:
        if exact is not None or not isinstance(start, str) or not isinstance(end, str):
            raise CalendarPlannerError("Calendar date range fields are invalid")
        try:
            return TemporalResolution(kind, date_range=DateRange(start, end))
        except TemporalValueError as error:
            raise CalendarPlannerError("Calendar date range is invalid") from error
    if exact is not None or start is not None or end is not None:
        raise CalendarPlannerError("Unspecified Calendar time must not carry dates")
    return TemporalResolution(kind)


def _validate_plan(plan: CalendarPlan) -> None:
    """Enforce executable temporal ownership and semantic-write correlation locally."""
    if plan.outcome is CalendarPlanOutcome.FAIL_CLOSED:
        if plan.intent is not None or plan.semantic_write is not None or plan.failure_code is None:
            raise CalendarPlannerError("Fail-closed Calendar plan correlation is invalid")
        if (
            plan.failure_code is CalendarFailureCode.RANGE_REQUIRES_RANGE_AWARE_OPERATION
            and plan.temporal.kind is not TemporalResolutionKind.DATE_RANGE
        ):
            raise CalendarPlannerError("Calendar range failure requires a date range")
        if (
            plan.failure_code is CalendarFailureCode.TEMPORAL_UNRESOLVED
            and plan.temporal.kind is not TemporalResolutionKind.UNSPECIFIED
        ):
            raise CalendarPlannerError("Calendar unresolved failure requires unspecified time")
        return
    if plan.failure_code is not None or plan.intent is None:
        raise CalendarPlannerError("Executable Calendar plan correlation is invalid")
    if plan.intent is CalendarIntentKind.DAY_LITERAL_CAPTURE:
        if (
            plan.temporal.kind is not TemporalResolutionKind.EXACT_DATE
            or plan.semantic_write is not None
        ):
            raise CalendarPlannerError("Calendar Day literal capture requires one exact date")
        return
    if plan.intent is CalendarIntentKind.CORE_SEMANTIC_WRITE:
        if (
            plan.temporal.kind is not TemporalResolutionKind.EXACT_DATE
            or plan.semantic_write is None
        ):
            raise CalendarPlannerError("Calendar Core write requires exact temporal reference")
        _validate_calendar_core_write(plan.semantic_write)
        dates = [
            part.date
            for operation in plan.semantic_write.operations
            for fact in operation.facts
            for part in fact.parts
            if isinstance(part, TemporalReferencePart)
        ]
        if dates != [plan.temporal.exact_date]:
            raise CalendarPlannerError(
                "Calendar temporal reference does not correlate to exact date"
            )
        return
    raise CalendarPlannerError("Calendar intent is unsupported")


def _validate_calendar_core_write(write: SemanticWriteIntent) -> None:
    """Keep Calendar's Core delegation to fact-only writes over generic identities."""
    if not write.operations:
        raise CalendarPlannerError("Calendar Core write requires at least one operation")
    for operation in write.operations:
        if (
            operation.apply_to is not ApplyTo.ONE
            or operation.intent != "record"
            or operation.properties
            or operation.tag_changes
            or operation.destination_type is not None
            or operation.target.note_type is not None
            or operation.target.filters
        ):
            raise CalendarPlannerError("Calendar Core write exceeds app-local authority")
        for fact in operation.facts:
            for part in fact.parts:
                if isinstance(part, IdentityPart) and (
                    part.identity.note_type is not None or part.identity.filters
                ):
                    raise CalendarPlannerError("Calendar identity exceeds app-local authority")


def validate_calendar_plan_for_source(plan: CalendarPlan, source_text: str) -> CalendarPlan:
    """Correlate model-owned temporal evidence to the exact routed current source."""
    if not isinstance(plan, CalendarPlan):
        raise CalendarPlannerError("Calendar plan is invalid")
    if not isinstance(source_text, str) or not source_text.strip():
        raise CalendarPlannerError("Calendar source text must be non-empty")
    if plan.intent is CalendarIntentKind.CORE_SEMANTIC_WRITE and plan.semantic_write is not None:
        parts = [
            part
            for operation in plan.semantic_write.operations
            for fact in operation.facts
            for part in fact.parts
            if isinstance(part, TemporalReferencePart)
        ]
        if len(parts) != 1 or parts[0].text not in source_text:
            raise CalendarPlannerError("Calendar temporal reference is not grounded in source")
    return plan


def render_calendar_prompt(
    *, current_context: Mapping[str, str], conversation_context: Sequence[Mapping[str, str]] = ()
) -> str:
    """Render Calendar-only instructions and bounded temporal/current-context evidence."""
    required = {"date", "time", "timezone"}
    if set(current_context) != required or not all(
        isinstance(current_context[key], str) and current_context[key].strip() for key in required
    ):
        raise CalendarPlannerError("Calendar current context is invalid")
    try:
        normalize_iso_date(current_context["date"])
    except TemporalValueError as error:
        raise CalendarPlannerError("Calendar current date is invalid") from error
    evidence = {
        "current_date": current_context["date"],
        "current_time": current_context["time"],
        "timezone": current_context["timezone"],
        "prior_conversation_only": _bounded_context(conversation_context),
    }
    return (
        "You are Odyssey Calendar's planner after routing. Interpret only the exact current routed "
        "source supplied as the user message; prior conversation is bounded continuity evidence, not "
        "a substitute current request. Preserve the source wording: DAY_LITERAL_CAPTURE carries no "
        "rewritten literal because execution records the exact routed source text. First decide whether "
        "the source is within Calendar's own supported semantics: a temporal occurrence, or a durable "
        "fact whose temporal wording qualifies a reusable subject identity. Instructions to create or "
        "write into another record/surface, obligations or intended work, and other foreign semantics "
        "are OUT_OF_SCOPE; do not identify which other capability owns them. Only for in-scope input, "
        "resolve the temporal shape from the supplied date/time/timezone: EXACT_DATE means one "
        "determinate date; DATE_RANGE means a bounded interval and uses a half-open "
        "range_end_exclusive; UNSPECIFIED means the wording is too vague to normalize safely. Never "
        "collapse a range or vague phrase into one Day. Tense or a future date alone never changes the "
        "semantic kind. For "
        "an entity-owned durable statement with EXACT_DATE, emit CORE_SEMANTIC_WRITE and include exactly "
        "one temporal_reference part using the original temporal mention and the same normalized date. "
        "Within that semantic write, preserve distinct logical participants as identity parts when they "
        "are safely selectable Odyssey identities; literal parts are for non-identity context or values, "
        "and ordinary context must not be promoted speculatively. Calendar Core writes are fact-only: "
        "never emit type constraints, filters, properties, tags, destination types, reclassification, "
        "or bulk selection. For remaining Day-owned occurrences, "
        "EXACT_DATE uses DAY_LITERAL_CAPTURE, DATE_RANGE uses "
        "FAIL_CLOSED/RANGE_REQUIRES_RANGE_AWARE_OPERATION, and UNSPECIFIED uses "
        "FAIL_CLOSED/TEMPORAL_UNRESOLVED. Core owns identity resolution, validation, Markdown, "
        "history, and mutation. Return only the strict JSON object.\n"
        + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    )


class OpenAICalendarPlanner:
    """Make exactly one bounded GPT-6 Luna Calendar planning call with no retries."""

    def __init__(
        self, client: ResponsesClient, schema: Mapping[str, Any], current_context: Mapping[str, str]
    ) -> None:
        """Bind injected transport, canonical Core schema, and explicit current temporal context."""
        self._client = client
        self._schema = schema
        self._current_context = dict(current_context)
        self.model = CALENDAR_PLANNER_MODEL
        self.reasoning_effort = CALENDAR_PLANNER_REASONING_EFFORT
        self.last_call = False

    @classmethod
    def from_environment(
        cls, schema: Mapping[str, Any], current_context: Mapping[str, str]
    ) -> OpenAICalendarPlanner:
        """Build the one-call adapter with SDK retries disabled when execution is configured."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise CalendarPlannerError("OPENAI_API_KEY is required for Calendar planning")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise CalendarPlannerError("Install the OpenAI SDK for Calendar planning") from error
        return cls(
            OpenAI(max_retries=0, timeout=CALENDAR_PLANNER_TIMEOUT_SECONDS), schema, current_context
        )

    def plan(
        self, source_text: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> CalendarPlan:
        """Interpret one exact routed source once, rejecting incomplete or malformed output locally."""
        if not isinstance(source_text, str) or not source_text.strip():
            raise CalendarPlannerError("Calendar source text must be non-empty")
        self.last_call = False
        prompt = render_calendar_prompt(
            current_context=self._current_context, conversation_context=conversation_context
        )
        self.last_call = True
        try:
            response = self._client.responses.create(
                model=CALENDAR_PLANNER_MODEL,
                reasoning={"effort": CALENDAR_PLANNER_REASONING_EFFORT},
                store=False,
                max_output_tokens=CALENDAR_PLANNER_MAX_OUTPUT_TOKENS,
                input=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": source_text},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_calendar_plan",
                        "strict": True,
                        "schema": calendar_plan_json_schema(self._schema),
                    }
                },
            )
        except Exception as error:
            raise CalendarPlannerError("Calendar planner provider call failed") from error
        if getattr(response, "status", None) != "completed":
            raise CalendarPlannerError("Calendar planner provider response was not completed")
        try:
            payload = json.loads(response.output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise CalendarPlannerError("Calendar planner returned malformed output") from error
        return validate_calendar_plan_for_source(parse_calendar_plan(payload), source_text)


class CalendarRouteExecutor:
    """Adapt validated Calendar plans to the existing routed application-result contract."""

    def __init__(
        self,
        planner: Any,
        *,
        schema: Mapping[str, Any],
        capture_day_literal: Callable[[str, str, str, object | None], ApplicationResult],
        execute_core_write: Callable[
            [RequestPlan, str, str, object | None, Sequence[Mapping[str, str]]], ApplicationResult
        ],
    ) -> None:
        """Bind Calendar planning to injected Core-owned execution services only."""
        self._planner = planner
        self._schema = schema
        self._capture_day_literal = capture_day_literal
        self._execute_core_write = execute_core_write

    def __call__(
        self,
        source_text: str,
        request_id: str,
        authenticated_actor: object | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
    ) -> ApplicationResult:
        """Execute one exact routed Calendar span or return bounded content-free failure evidence."""
        try:
            plan = self._planner.plan(source_text, conversation_context)
            if not isinstance(plan, CalendarPlan):
                raise CalendarPlannerError("Calendar planner returned an invalid plan")
            validate_calendar_plan_for_source(plan, source_text)
        except Exception:
            return _failure(request_id, "CALENDAR_PLANNER_INVALID")
        if plan.outcome is CalendarPlanOutcome.FAIL_CLOSED:
            return _fail_closed(request_id, plan.failure_code)
        try:
            if plan.intent is CalendarIntentKind.DAY_LITERAL_CAPTURE:
                return self._capture_day_literal(
                    plan.temporal.exact_date or "", source_text, request_id, authenticated_actor
                )
            if (
                plan.intent is CalendarIntentKind.CORE_SEMANTIC_WRITE
                and plan.semantic_write is not None
            ):
                write = compile_semantic_write(plan.semantic_write, self._schema)
                return self._execute_core_write(
                    RequestPlan((write,), ()),
                    source_text,
                    request_id,
                    authenticated_actor,
                    conversation_context,
                )
        except Exception:
            return _failure(request_id, "CALENDAR_EXECUTION_FAILED")
        return _failure(request_id, "CALENDAR_PLAN_INVALID")


def _fail_closed(request_id: str, failure_code: CalendarFailureCode | None) -> ApplicationResult:
    """Map understood but non-executable Calendar meaning to bounded product evidence."""
    if failure_code is None:
        return _failure(request_id, "CALENDAR_PLAN_INVALID")
    action = ActionResult(0, "calendar", ActionStatus.DEFERRED, reason=failure_code.value)
    if failure_code is CalendarFailureCode.TEMPORAL_UNRESOLVED:
        return ApplicationResult(
            request_id,
            ApplicationStatus.NEEDS_ATTENTION,
            (action,),
            (),
            clarification_code=failure_code.value,
        )
    return ApplicationResult(
        request_id,
        ApplicationStatus.NEEDS_ATTENTION,
        (action,),
        (),
        planning_error=failure_code.value,
    )


def _failure(request_id: str, reason: str) -> ApplicationResult:
    """Return one bounded Calendar route failure without leaking provider or vault details."""
    return ApplicationResult(
        request_id,
        ApplicationStatus.FAILED,
        (ActionResult(0, "calendar", ActionStatus.FAILED, reason=reason),),
        (),
        planning_error=reason,
    )
