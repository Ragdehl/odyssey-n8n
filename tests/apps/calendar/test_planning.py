"""Provider-free Calendar planner contract and GPT-6 Luna adapter coverage."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from odyssey_apps.calendar import (
    CALENDAR_PLANNER_MODEL,
    CALENDAR_PLANNER_REASONING_EFFORT,
    CalendarFailureCode,
    CalendarIntentKind,
    CalendarPlannerError,
    CalendarPlanOutcome,
    CalendarRouteExecutor,
    OpenAICalendarPlanner,
    TemporalResolutionKind,
    calendar_plan_json_schema,
    parse_calendar_plan,
    render_calendar_prompt,
    validate_calendar_plan_for_source,
)
from odyssey_apps.calendar.planning import CALENDAR_PLANNER_TIMEOUT_SECONDS
from odyssey_apps.catalog import ApplicationDescriptor, ApplicationRegistry
from odyssey_apps.router import Route, RouteOutcome, RoutePlan
from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
)
from odyssey_runtime.routing import execute_routed_request

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def schema() -> dict[str, Any]:
    """Load the canonical schema reused by Calendar's semantic-write branch."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def calendar_payload(
    *,
    outcome: str = "PLAN",
    intent: str | None = "DAY_LITERAL_CAPTURE",
    temporal_kind: str = "EXACT_DATE",
    exact_date: str | None = "2026-10-03",
    range_start: str | None = None,
    range_end_exclusive: str | None = None,
    semantic_write: dict[str, Any] | None = None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    """Build one complete strict-output-shaped Calendar payload."""
    return {
        "outcome": outcome,
        "intent": intent,
        "temporal_kind": temporal_kind,
        "exact_date": exact_date,
        "range_start": range_start,
        "range_end_exclusive": range_end_exclusive,
        "semantic_write": semantic_write,
        "failure_code": failure_code,
    }


def identity(description: str, direct_name: str | None, note_type: str | None) -> dict[str, Any]:
    """Build one complete semantic identity used by the Calendar Core-write branch."""
    return {
        "description": description,
        "binding": "described",
        "direct_name": direct_name,
        "note_type": note_type,
        "filters": [],
        "candidate_scope": None,
    }


def marta_write() -> dict[str, Any]:
    """Build a semantic write with one exact temporal reference and Airbus identity."""
    return {
        "kind": "write",
        "operations": [
            {
                "target": identity("Marta", "Marta", "person"),
                "apply_to": "one",
                "intent": "record",
                "facts": [
                    {
                        "parts": [
                            {"kind": "literal", "text": "Empieza "},
                            {"kind": "temporal_reference", "text": "mañana", "date": "2026-10-03"},
                            {"kind": "literal", "text": " a trabajar en "},
                            {
                                "kind": "identity",
                                "text": "Airbus",
                                "identity": identity("Airbus", "Airbus", None),
                            },
                            {"kind": "literal", "text": "."},
                        ]
                    }
                ],
                "properties": [],
                "tag_changes": [],
                "destination_type": None,
            }
        ],
    }


@pytest.mark.parametrize(
    ("payload", "kind", "start", "end", "failure"),
    [
        (calendar_payload(), TemporalResolutionKind.EXACT_DATE, None, None, None),
        (
            calendar_payload(
                outcome="FAIL_CLOSED",
                intent=None,
                temporal_kind="DATE_RANGE",
                exact_date=None,
                range_start="2026-10-05",
                range_end_exclusive="2026-10-12",
                failure_code="RANGE_REQUIRES_RANGE_AWARE_OPERATION",
            ),
            TemporalResolutionKind.DATE_RANGE,
            "2026-10-05",
            "2026-10-12",
            CalendarFailureCode.RANGE_REQUIRES_RANGE_AWARE_OPERATION,
        ),
        (
            calendar_payload(
                outcome="FAIL_CLOSED",
                intent=None,
                temporal_kind="DATE_RANGE",
                exact_date=None,
                range_start="2026-11-01",
                range_end_exclusive="2026-12-01",
                failure_code="RANGE_REQUIRES_RANGE_AWARE_OPERATION",
            ),
            TemporalResolutionKind.DATE_RANGE,
            "2026-11-01",
            "2026-12-01",
            CalendarFailureCode.RANGE_REQUIRES_RANGE_AWARE_OPERATION,
        ),
        (
            calendar_payload(
                outcome="FAIL_CLOSED",
                intent=None,
                temporal_kind="UNSPECIFIED",
                exact_date=None,
                failure_code="TEMPORAL_UNRESOLVED",
            ),
            TemporalResolutionKind.UNSPECIFIED,
            None,
            None,
            CalendarFailureCode.TEMPORAL_UNRESOLVED,
        ),
    ],
)
def test_temporal_shapes_preserve_exact_range_and_unresolved_without_fake_day(
    payload: dict[str, Any],
    kind: TemporalResolutionKind,
    start: str | None,
    end: str | None,
    failure: CalendarFailureCode | None,
) -> None:
    """Represent exact dates, week/month ranges, and vagueness without coercing one Day."""
    result = parse_calendar_plan(payload)
    assert result.temporal.kind is kind
    assert (result.temporal.date_range.start if result.temporal.date_range else None) == start
    assert (result.temporal.date_range.end_exclusive if result.temporal.date_range else None) == end
    assert result.failure_code is failure


def test_core_semantic_write_requires_one_correlated_source_grounded_temporal_reference() -> None:
    """Keep Calendar's interpretation exact while Core retains semantic-write authority."""
    result = parse_calendar_plan(
        calendar_payload(intent="CORE_SEMANTIC_WRITE", semantic_write=marta_write())
    )
    validated = validate_calendar_plan_for_source(
        result, "Marta empieza mañana a trabajar en Airbus."
    )
    assert validated.outcome is CalendarPlanOutcome.PLAN
    assert validated.intent is CalendarIntentKind.CORE_SEMANTIC_WRITE
    with pytest.raises(CalendarPlannerError, match="grounded"):
        validate_calendar_plan_for_source(result, "Marta empieza el viernes a trabajar en Airbus.")


@pytest.mark.parametrize(
    "payload",
    [
        {**calendar_payload(), "extra": True},
        calendar_payload(temporal_kind="DATE_RANGE"),
        calendar_payload(
            outcome="FAIL_CLOSED",
            intent=None,
            temporal_kind="EXACT_DATE",
            failure_code="RANGE_REQUIRES_RANGE_AWARE_OPERATION",
        ),
        calendar_payload(
            intent="CORE_SEMANTIC_WRITE", semantic_write=marta_write(), exact_date="2026-10-04"
        ),
    ],
)
def test_malformed_or_cross_correlated_calendar_payloads_fail_locally(
    payload: dict[str, Any],
) -> None:
    """Reject open objects, invalid temporal shapes, and mismatched write dates before execution."""
    with pytest.raises(CalendarPlannerError):
        parse_calendar_plan(payload)


def test_calendar_schema_adds_temporal_part_only_inside_calendar_contract(
    schema: dict[str, Any],
) -> None:
    """Expose the app-only temporal vocabulary without making it a generic Core planner field."""
    provider = calendar_plan_json_schema(schema)
    assert "semantic_temporal_reference_part" in provider["$defs"]
    temporal = provider["$defs"]["semantic_temporal_reference_part"]
    assert set(temporal["properties"]) == {"kind", "text", "date"}
    assert temporal["properties"]["kind"]["enum"] == ["temporal_reference"]


def test_prompt_uses_current_context_and_only_bounded_prior_turns() -> None:
    """Keep language interpretation in Calendar while prior conversation remains bounded evidence."""
    prompt = render_calendar_prompt(
        current_context={"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
        conversation_context=({"role": "user", "text": "previous"},) * 10,
    )
    assert "Resolve time using the supplied date/time/timezone" in prompt
    assert "Never turn a range or vague expression into one Day" in prompt
    assert prompt.count('"text":"previous"') == 8
    assert '"current_date":"2026-10-02"' in prompt
    with pytest.raises(CalendarPlannerError):
        render_calendar_prompt(
            current_context={"date": "02/10/2026", "time": "17:00", "timezone": "Europe/Paris"}
        )


class FakeResponses:
    """Return one local provider envelope while retaining the one-call payload."""

    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_fake_provider_uses_gpt6_luna_low_one_call_and_exact_current_source(
    schema: dict[str, Any],
) -> None:
    """Keep Calendar's provider boundary separate, bounded, and source-preserving."""
    fake = FakeResponses(
        SimpleNamespace(
            status="completed", output_text=json.dumps(calendar_payload(exact_date="2026-10-05"))
        )
    )
    planner = OpenAICalendarPlanner(
        SimpleNamespace(responses=fake),
        schema,
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
    )
    result = planner.plan(
        "Dentro de tres días viene el fontanero",
        ({"role": "assistant", "text": "prior"},),
    )
    assert result.temporal.exact_date == "2026-10-05"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == CALENDAR_PLANNER_MODEL == "gpt-6-luna"
    assert call["reasoning"] == {"effort": CALENDAR_PLANNER_REASONING_EFFORT} == {"effort": "low"}
    assert call["store"] is False
    assert call["text"]["format"]["strict"] is True
    assert call["input"][1] == {
        "role": "user",
        "content": "Dentro de tres días viene el fontanero",
    }
    assert '"text":"prior"' in call["input"][0]["content"]


@pytest.mark.parametrize(
    "response",
    [
        RuntimeError("network"),
        SimpleNamespace(status="incomplete", output_text=json.dumps(calendar_payload())),
        SimpleNamespace(status="completed", output_text="not json"),
        SimpleNamespace(
            status="completed", output_text=json.dumps({**calendar_payload(), "extra": 1})
        ),
    ],
)
def test_provider_or_local_validation_failure_makes_no_retry(
    schema: dict[str, Any], response: object
) -> None:
    """Fail closed after exactly one provider attempt and never produce executable intent."""
    fake = FakeResponses(response)
    planner = OpenAICalendarPlanner(
        SimpleNamespace(responses=fake),
        schema,
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
    )
    with pytest.raises(CalendarPlannerError):
        planner.plan("Mañana viene el fontanero")
    assert len(fake.calls) == 1


def test_from_environment_disables_retries_and_sets_timeout(
    schema: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configure the SDK transport without making a network request."""
    calls: list[dict[str, object]] = []

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    planner = OpenAICalendarPlanner.from_environment(
        schema, {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"}
    )
    assert isinstance(planner, OpenAICalendarPlanner)
    assert calls == [{"max_retries": 0, "timeout": CALENDAR_PLANNER_TIMEOUT_SECONDS}]


def test_calendar_executor_is_accepted_by_runtime_routing_contract(schema: dict[str, Any]) -> None:
    """Run one exact Day capture through the existing ApplicationExecutor adapter."""
    captured: list[str] = []
    executor = CalendarRouteExecutor(
        SimpleNamespace(plan=lambda *_args: parse_calendar_plan(calendar_payload())),
        schema=schema,
        capture_day_literal=lambda day, text, request_id, actor: (
            captured.append(text)
            or ApplicationResult(
                request_id,
                ApplicationStatus.COMPLETED,
                (ActionResult(0, "calendar", ActionStatus.COMPLETED),),
                (f"date:{day}",),
            )
        ),
        execute_core_write=lambda *_args: pytest.fail(
            "literal capture cannot call Core semantic write"
        ),
    )
    catalog = ApplicationRegistry.from_descriptors(
        (ApplicationDescriptor("calendar", "day/date-owned occurrences"),)
    ).catalog(enabled_ids=("calendar",))
    router = SimpleNamespace(
        route=lambda *_args: RoutePlan(
            RouteOutcome.ROUTE, (Route("calendar", "Mañana viene el fontanero"),)
        )
    )

    result = execute_routed_request(
        user_request="Mañana viene el fontanero",
        outer_request_id="outer",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail(
            "Calendar route cannot call Core planner"
        ),
        application_executors={"calendar": executor},
    )

    assert result.request_id == "outer"
    assert result.status is ApplicationStatus.COMPLETED
    assert captured == ["Mañana viene el fontanero"]


def test_frozen_calendar_live_gate_matrix_covers_temporal_and_ownership_boundaries() -> None:
    """Keep one compact provider-free oracle registry ready for the later authorized Luna gate."""
    matrix = json.loads(
        (ROOT / "benchmarks/calendar_planner/regression_v1.json").read_text(encoding="utf-8")
    )
    assert matrix["version"] == 1
    assert matrix["current_context"] == {
        "date": "2026-10-02",
        "time": "17:00",
        "timezone": "Europe/Paris",
    }
    cases = {item["id"]: item for item in matrix["cases"]}
    assert set(cases) == {
        "exact-tomorrow-literal",
        "exact-three-days-literal",
        "next-week-range",
        "next-month-range",
        "vague-end-of-month",
        "entity-owned-exact-date",
        "task-lifecycle-not-calendar-literal",
        "journal-not-calendar",
    }
    assert cases["next-week-range"]["expect"]["range_end_exclusive"] == "2026-10-12"
    assert cases["entity-owned-exact-date"]["expect"]["temporal_text"] == "mañana"
