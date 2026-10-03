"""Minimal Calendar interpretation and routed execution.

Calendar owns only temporal interpretation and the choice between a Day-owned occurrence and
a request that must return to the ordinary Core planner. It never plans Core identities, facts,
targets, references, or mutations.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from time import perf_counter
from typing import Any, Protocol

from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
)
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.observability import (
    OperationalEvidence,
    OperationalOutcome,
    OperationalStage,
    ProviderCallEvidence,
    normalize_provider_usage,
)
from odyssey_core.temporal import TemporalValueError, calendar_day_label, normalize_iso_date
from odyssey_core.temporal_resolution import (
    TemporalResolution,
    TemporalResolutionKind,
    parse_temporal_resolution,
)

CALENDAR_PLANNER_MODEL = "gpt-6-luna"
CALENDAR_PLANNER_REASONING_EFFORT = "low"
CALENDAR_PLANNER_MAX_OUTPUT_TOKENS = 512
CALENDAR_PLANNER_MAX_RECENT_TURNS = 8
CALENDAR_PLANNER_MAX_CONTEXT_CHARS = 1_000
CALENDAR_PLANNER_TIMEOUT_SECONDS = 30.0
CALENDAR_TEMPORAL_RESOLUTION_KINDS = (
    TemporalResolutionKind.EXACT_DATE,
    TemporalResolutionKind.DATE_RANGE,
    TemporalResolutionKind.UNSPECIFIED,
)


class CalendarPlannerError(ValueError):
    """Report an invalid or unavailable Calendar interpretation without executing it."""


class CalendarPlanOutcome(StrEnum):
    """Name whether Calendar has a safe domain interpretation or withholds execution."""

    PLAN = "PLAN"
    FAIL_CLOSED = "FAIL_CLOSED"


class CalendarIntentKind(StrEnum):
    """Choose only between Calendar-owned capture and ordinary Core planning."""

    DAY_LITERAL_CAPTURE = "DAY_LITERAL_CAPTURE"
    DELEGATE_TO_CORE = "DELEGATE_TO_CORE"


class CalendarFailureCode(StrEnum):
    """Keep non-executable Calendar reasons bounded and content-free."""

    RANGE_REQUIRES_RANGE_AWARE_OPERATION = "RANGE_REQUIRES_RANGE_AWARE_OPERATION"
    TEMPORAL_UNRESOLVED = "TEMPORAL_UNRESOLVED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True, slots=True)
class CalendarPlan:
    """Contain only Calendar-owned interpretation before Core or Day execution."""

    outcome: CalendarPlanOutcome
    intent: CalendarIntentKind | None
    temporal: TemporalResolution
    temporal_text: str | None = None
    failure_code: CalendarFailureCode | None = None
    capture_text: str | None = None


class ResponsesClient(Protocol):
    """Describe the injected Responses API subset required for one Calendar call."""

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


def calendar_plan_json_schema(_legacy_schema: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return Calendar's strict domain-only provider schema.

    The ignored optional argument keeps consumed historical benchmark modules importable; current
    production composition never supplies the canonical note schema to Calendar.
    """
    return {
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
                "enum": [item.value for item in CALENDAR_TEMPORAL_RESOLUTION_KINDS],
            },
            "exact_date": {"type": ["string", "null"]},
            "range_start": {"type": ["string", "null"]},
            "range_end_exclusive": {"type": ["string", "null"]},
            "temporal_text": {"type": ["string", "null"]},
            "capture_text": {"type": ["string", "null"]},
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
            "temporal_text",
            "capture_text",
            "failure_code",
        ],
        "additionalProperties": False,
    }


def parse_calendar_plan(payload: Mapping[str, Any]) -> CalendarPlan:
    """Decode one closed provider payload and enforce Calendar-only cross-field invariants."""
    required = {
        "outcome",
        "intent",
        "temporal_kind",
        "exact_date",
        "range_start",
        "range_end_exclusive",
        "temporal_text",
        "capture_text",
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
    temporal_text = payload["temporal_text"]
    if temporal_text is not None and (
        not isinstance(temporal_text, str) or not temporal_text.strip()
    ):
        raise CalendarPlannerError("Calendar temporal text is invalid")
    capture_text = payload["capture_text"]
    if capture_text is not None and (not isinstance(capture_text, str) or not capture_text.strip()):
        raise CalendarPlannerError("Calendar capture text is invalid")
    if outcome is CalendarPlanOutcome.FAIL_CLOSED and failure is not None:
        intent = None
        temporal_text = None
        capture_text = None
    plan = CalendarPlan(
        outcome,
        intent,
        temporal,
        temporal_text=temporal_text,
        failure_code=failure,
        capture_text=capture_text,
    )
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
    """Validate Calendar's date-only subset through the shared Temporal v1 contract."""
    try:
        return parse_temporal_resolution(
            {
                "kind": kind.value,
                "exact_date": raw["exact_date"],
                "exact_datetime": None,
                "range_start": raw["range_start"],
                "range_end_exclusive": raw["range_end_exclusive"],
            },
            allowed_kinds=CALENDAR_TEMPORAL_RESOLUTION_KINDS,
        )
    except TemporalValueError as error:
        raise CalendarPlannerError("Calendar temporal fields are invalid") from error


def _validate_plan(plan: CalendarPlan) -> None:
    """Reject any Calendar output that exceeds temporal/domain classification authority."""
    if plan.outcome is CalendarPlanOutcome.FAIL_CLOSED:
        if (
            plan.intent is not None
            or plan.temporal_text is not None
            or plan.capture_text is not None
            or plan.failure_code is None
        ):
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
    if plan.temporal.kind is not TemporalResolutionKind.EXACT_DATE:
        raise CalendarPlannerError("Executable Calendar interpretation requires one exact date")
    if plan.intent is CalendarIntentKind.DAY_LITERAL_CAPTURE:
        if plan.capture_text is None:
            raise CalendarPlannerError("Day capture requires exact source capture text")
        return
    if plan.intent is CalendarIntentKind.DELEGATE_TO_CORE:
        if plan.temporal_text is None or plan.capture_text is not None:
            raise CalendarPlannerError("Core delegation requires only exact temporal wording")
        return
    raise CalendarPlannerError("Calendar intent is unsupported")


def validate_calendar_plan_for_source(plan: CalendarPlan, source_text: str) -> CalendarPlan:
    """Correlate Calendar-owned evidence to the exact routed current source."""
    if not isinstance(plan, CalendarPlan):
        raise CalendarPlannerError("Calendar plan is invalid")
    if not isinstance(source_text, str) or not source_text.strip():
        raise CalendarPlannerError("Calendar source text must be non-empty")
    if plan.temporal_text is not None and plan.temporal_text not in source_text:
        raise CalendarPlannerError("Calendar temporal evidence is not grounded in source")
    if plan.capture_text is not None and plan.capture_text not in source_text:
        raise CalendarPlannerError("Calendar capture text is not grounded in source")
    if (
        plan.intent is CalendarIntentKind.DELEGATE_TO_CORE
        and plan.temporal_text is not None
        and plan.temporal_text.strip() == source_text.strip()
    ):
        raise CalendarPlannerError(
            "Delegated Calendar temporal evidence cannot consume the whole source"
        )
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
        "You are Odyssey Calendar's domain interpreter after routing. Interpret only the exact "
        "current routed source supplied as the user message; prior conversation is bounded continuity "
        "evidence, not a substitute current request. Your authority is deliberately minimal: resolve "
        "temporal wording and decide only whether the meaning is a Day-owned occurrence or must return "
        "to the ordinary Core planner. Never choose or describe Core targets, identities, candidate "
        "scopes, facts, references, note types, properties, tags, write intents, Markdown, or mutation "
        "structure. First decide whether the source is within Calendar's supported semantics: a temporal "
        "occurrence, everyday personal diary/journal capture, or a durable statement whose temporal "
        "wording changes or qualifies durable knowledge. A request to write in the user's personal diary "
        "means Day-owned Calendar content, not another record type. When that diary request names no date, "
        "use current_date as EXACT_DATE and set temporal_text to null; an explicit day/date phrase still "
        "uses the normal temporal resolution rules. Other instructions to create or write into another "
        "record/surface, obligations or intended work, and foreign semantics are OUT_OF_SCOPE; do not "
        "identify a sibling capability. Only "
        "for in-scope input, resolve the temporal shape from the supplied date/time/timezone: EXACT_DATE "
        "means one determinate date; DATE_RANGE means a bounded interval using a half-open "
        "range_end_exclusive; UNSPECIFIED means the wording is too vague to normalize safely. Never "
        "collapse a range or vague phrase into one Day. If a statement establishes, ends, or changes "
        "durable knowledge while also describing an occurrence on a date, durable knowledge takes "
        "precedence: emit DELEGATE_TO_CORE, preserve only the exact temporal wording in temporal_text, and "
        "supply only its normalized exact date; capture_text must be null. For executable exact-date "
        "results with explicit temporal wording, temporal_text must be that exact phrase from the routed "
        "source, never the whole durable statement. Core will independently decide semantic ownership, "
        "targets, identities, facts, references, and mutation semantics. Use DAY_LITERAL_CAPTURE only "
        "when the semantic content itself belongs to the Day. For every DAY_LITERAL_CAPTURE, capture_text "
        "must be the exact non-empty source substring that the user wants remembered, with command wrappers "
        "such as 'write in my diary that' excluded; never paraphrase, summarize, translate, or invent it. "
        "For an ordinary explicit-date Day occurrence, capture_text may be the whole routed source. Preserve "
        "explicit temporal wording in temporal_text so execution can canonicalize that occurrence when it "
        "appears inside capture_text. For a diary request with no explicit date, temporal_text is null and "
        "EXACT_DATE must be current_date. "
        "Remaining Day-owned EXACT_DATE uses "
        "DAY_LITERAL_CAPTURE, DATE_RANGE uses FAIL_CLOSED/RANGE_REQUIRES_RANGE_AWARE_OPERATION, and "
        "UNSPECIFIED uses FAIL_CLOSED/TEMPORAL_UNRESOLVED. Return only the strict JSON object.\n"
        + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    )


class OpenAICalendarPlanner:
    """Make exactly one bounded GPT-6 Luna Calendar interpretation call with no retries."""

    def __init__(self, client: ResponsesClient, current_context: Mapping[str, str]) -> None:
        self._client = client
        self._current_context = dict(current_context)
        self.model = CALENDAR_PLANNER_MODEL
        self.reasoning_effort = CALENDAR_PLANNER_REASONING_EFFORT
        self.last_call = False
        self.last_usage = None
        self.last_response_id = None
        self.last_provider_status = None
        self.last_error_category = None

    @classmethod
    def from_environment(cls, current_context: Mapping[str, str]) -> OpenAICalendarPlanner:
        """Build the one-call adapter with SDK retries disabled."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise CalendarPlannerError("OPENAI_API_KEY is required for Calendar planning")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise CalendarPlannerError("Install the OpenAI SDK for Calendar planning") from error
        return cls(OpenAI(max_retries=0, timeout=CALENDAR_PLANNER_TIMEOUT_SECONDS), current_context)

    def plan(
        self, source_text: str, conversation_context: Sequence[Mapping[str, str]] = ()
    ) -> CalendarPlan:
        """Interpret one exact routed source once, rejecting malformed output locally."""
        if not isinstance(source_text, str) or not source_text.strip():
            raise CalendarPlannerError("Calendar source text must be non-empty")
        self.last_call = False
        self.last_usage = None
        self.last_response_id = None
        self.last_provider_status = None
        self.last_error_category = None
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
                        "schema": calendar_plan_json_schema(),
                    }
                },
            )
        except Exception as error:
            self.last_error_category = type(error).__name__
            raise CalendarPlannerError("Calendar planner provider call failed") from error
        self.last_usage = getattr(response, "usage", None)
        self.last_response_id = getattr(response, "id", None)
        self.last_provider_status = getattr(response, "status", None)
        if self.last_provider_status != "completed":
            raise CalendarPlannerError("Calendar planner provider response was not completed")
        try:
            payload = json.loads(response.output_text)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise CalendarPlannerError("Calendar planner returned malformed output") from error
        plan = validate_calendar_plan_for_source(parse_calendar_plan(payload), source_text)
        if (
            plan.intent is CalendarIntentKind.DAY_LITERAL_CAPTURE
            and plan.temporal_text is None
            and plan.temporal.exact_date != self._current_context["date"]
        ):
            raise CalendarPlannerError("Implicit diary date must be the current date")
        return plan


class CalendarRouteExecutor:
    """Execute Calendar-owned Day capture or return specialized evidence to the Core planner."""

    def __init__(
        self,
        planner: Any,
        *,
        capture_day_literal: Callable[[str, str, str, object | None], ApplicationResult],
        execute_core: Callable[
            [
                str,
                str,
                object | None,
                Sequence[Mapping[str, str]],
                DomainInterpretation,
            ],
            ApplicationResult,
        ],
    ) -> None:
        self._planner = planner
        self._capture_day_literal = capture_day_literal
        self._execute_core = execute_core

    def __call__(
        self,
        source_text: str,
        request_id: str,
        authenticated_actor: object | None = None,
        conversation_context: Sequence[Mapping[str, str]] = (),
    ) -> ApplicationResult:
        """Interpret one routed Calendar span and retain bounded planner telemetry."""
        planner_started = perf_counter()
        try:
            plan = self._planner.plan(source_text, conversation_context)
            if not isinstance(plan, CalendarPlan):
                raise CalendarPlannerError("Calendar planner returned an invalid plan")
            validate_calendar_plan_for_source(plan, source_text)
        except Exception as error:
            stage = _calendar_planner_stage(self._planner, planner_started, error)
            return _prepend_operational_stage(
                _failure(request_id, "CALENDAR_PLANNER_INVALID"), stage
            )
        stage = _calendar_planner_stage(self._planner, planner_started)
        if plan.outcome is CalendarPlanOutcome.FAIL_CLOSED:
            return _prepend_operational_stage(_fail_closed(request_id, plan.failure_code), stage)
        try:
            if plan.intent is CalendarIntentKind.DAY_LITERAL_CAPTURE:
                exact_date = plan.temporal.exact_date or ""
                temporal_text = plan.temporal_text
                canonical_literal = plan.capture_text or ""
                if temporal_text and temporal_text in canonical_literal:
                    canonical_literal = canonical_literal.replace(
                        temporal_text, calendar_day_label(exact_date), 1
                    )
                result = self._capture_day_literal(
                    exact_date, canonical_literal, request_id, authenticated_actor
                )
                return _prepend_operational_stage(result, stage)
            if plan.intent is CalendarIntentKind.DELEGATE_TO_CORE:
                interpretation = DomainInterpretation(
                    capability_id="calendar",
                    source_text=source_text,
                    intent="TEMPORAL_ANNOTATION",
                    evidence=(
                        DomainEvidence(
                            TEMPORAL_REFERENCE_EVIDENCE,
                            plan.temporal_text or "",
                            plan.temporal.exact_date or "",
                        ),
                    ),
                )
                result = self._execute_core(
                    source_text,
                    request_id,
                    authenticated_actor,
                    conversation_context,
                    interpretation,
                )
                return _prepend_operational_stage(result, stage)
        except Exception:
            return _prepend_operational_stage(
                _failure(request_id, "CALENDAR_EXECUTION_FAILED"), stage
            )
        return _prepend_operational_stage(_failure(request_id, "CALENDAR_PLAN_INVALID"), stage)


def _calendar_planner_stage(
    planner: Any, started: float, error: Exception | None = None
) -> OperationalStage:
    """Expose one bounded Calendar provider call without retaining prompt or response content."""
    duration_ms = max(0.0, (perf_counter() - started) * 1000)
    usage = normalize_provider_usage(getattr(planner, "last_usage", None))
    provider_status = getattr(planner, "last_provider_status", None)
    attempted = bool(getattr(planner, "last_call", False))
    calls: tuple[ProviderCallEvidence, ...] = ()
    if attempted:
        call_outcome = (
            OperationalOutcome.COMPLETED
            if provider_status == "completed"
            else OperationalOutcome.FAILED
        )
        calls = (
            ProviderCallEvidence(
                name="calendar.planner",
                outcome=call_outcome,
                duration_ms=duration_ms,
                model=getattr(planner, "model", None),
                reasoning_effort=getattr(planner, "reasoning_effort", None),
                usage=usage,
                error_category=getattr(planner, "last_error_category", None),
                response_id=getattr(planner, "last_response_id", None),
                provider_status=provider_status,
                attempt_count=1,
                ordinal=1,
            ),
        )
    return OperationalStage(
        "calendar.planner",
        OperationalOutcome.FAILED if error is not None else OperationalOutcome.COMPLETED,
        duration_ms,
        model=getattr(planner, "model", None),
        reasoning_effort=getattr(planner, "reasoning_effort", None),
        usage=usage,
        error_category=type(error).__name__ if error is not None else None,
        provider_calls=calls,
        start_offset_ms=0.0,
    )


def _prepend_operational_stage(
    result: ApplicationResult, stage: OperationalStage
) -> ApplicationResult:
    """Prepend Calendar planning and shift existing route-local stages after it."""
    shift = stage.duration_ms or 0.0
    shifted = tuple(
        replace(
            item,
            start_offset_ms=(
                item.start_offset_ms + shift if item.start_offset_ms is not None else None
            ),
        )
        for item in result.operational.stages
    )
    total = result.operational.total_duration_ms
    return replace(
        result,
        operational=OperationalEvidence(
            total_duration_ms=(shift + total if total is not None else None),
            stages=(stage, *shifted),
        ),
    )


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
