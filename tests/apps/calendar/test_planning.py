"""Provider-free Calendar domain-interpreter contract and GPT-6 Luna adapter coverage."""

from __future__ import annotations

import json
import sys
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
    OpenAICalendarPlanner,
    TemporalResolutionKind,
    calendar_plan_json_schema,
    parse_calendar_plan,
    render_calendar_prompt,
    validate_calendar_plan_for_source,
)
from odyssey_apps.calendar.planning import (
    CALENDAR_PLANNER_MAX_OUTPUT_TOKENS,
    CALENDAR_PLANNER_TIMEOUT_SECONDS,
)


def calendar_payload(
    *,
    outcome: str = "PLAN",
    intent: str | None = "DAY_LITERAL_CAPTURE",
    temporal_kind: str = "EXACT_DATE",
    exact_date: str | None = "2026-10-03",
    range_start: str | None = None,
    range_end_exclusive: str | None = None,
    temporal_text: str | None = "mañana",
    capture_text: str | None = None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    """Build one complete domain-only Calendar Structured Output payload."""
    if capture_text is None and outcome == "PLAN" and intent == "DAY_LITERAL_CAPTURE":
        capture_text = temporal_text
    return {
        "outcome": outcome,
        "intent": intent,
        "temporal_kind": temporal_kind,
        "exact_date": exact_date,
        "range_start": range_start,
        "range_end_exclusive": range_end_exclusive,
        "temporal_text": temporal_text,
        "capture_text": capture_text,
        "failure_code": failure_code,
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
def test_calendar_preserves_exact_range_and_unresolved_time_without_guessing(
    payload: dict[str, Any],
    kind: TemporalResolutionKind,
    start: str | None,
    end: str | None,
    failure: CalendarFailureCode | None,
) -> None:
    result = parse_calendar_plan(payload)
    assert result.temporal.kind is kind
    assert (result.temporal.date_range.start if result.temporal.date_range else None) == start
    assert (result.temporal.date_range.end_exclusive if result.temporal.date_range else None) == end
    assert result.failure_code is failure


def test_durable_statement_returns_only_grounded_temporal_evidence_for_core() -> None:
    payload = calendar_payload(intent="DELEGATE_TO_CORE", temporal_text="mañana")
    plan = parse_calendar_plan(payload)
    validated = validate_calendar_plan_for_source(
        plan, "Marta empieza mañana a trabajar en Airbus."
    )
    assert validated.intent is CalendarIntentKind.DELEGATE_TO_CORE
    assert validated.temporal.exact_date == "2026-10-03"
    assert validated.temporal_text == "mañana"
    with pytest.raises(CalendarPlannerError, match="grounded"):
        validate_calendar_plan_for_source(plan, "Marta empieza el viernes a trabajar en Airbus.")
    whole_source = parse_calendar_plan(
        calendar_payload(
            intent="DELEGATE_TO_CORE",
            temporal_text="Marta empieza mañana a trabajar en Airbus.",
        )
    )
    with pytest.raises(CalendarPlannerError, match="whole source"):
        validate_calendar_plan_for_source(
            whole_source, "Marta empieza mañana a trabajar en Airbus."
        )


def test_calendar_schema_contains_no_core_planning_or_mutation_vocabulary() -> None:
    provider = calendar_plan_json_schema()
    assert "$defs" not in provider
    assert set(provider["properties"]) == {
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
    assert provider["properties"]["intent"]["anyOf"][1]["enum"] == [
        "DAY_LITERAL_CAPTURE",
        "DELEGATE_TO_CORE",
    ]
    assert provider["properties"]["temporal_kind"]["enum"] == [
        "EXACT_DATE",
        "DATE_RANGE",
        "UNSPECIFIED",
    ]
    serialized = json.dumps(provider)
    for forbidden in (
        "semantic_write",
        "target",
        "identity",
        "candidate_scope",
        "facts",
        "references",
        "note_type",
        "tag_changes",
        "destination_type",
        "apply_to",
        "all_matching",
    ):
        assert forbidden not in serialized


def test_calendar_schema_is_closed_and_requires_every_domain_field() -> None:
    provider = calendar_plan_json_schema()
    assert provider["type"] == "object"
    assert provider["additionalProperties"] is False
    assert set(provider["required"]) == set(provider["properties"])


@pytest.mark.parametrize(
    "payload",
    [
        {**calendar_payload(), "target": "Marta"},
        {**calendar_payload(), "semantic_write": {}},
        calendar_payload(intent="DELEGATE_TO_CORE", temporal_text=None),
        calendar_payload(intent="DAY_LITERAL_CAPTURE", temporal_text=None),
        calendar_payload(temporal_kind="DATE_RANGE"),
        calendar_payload(temporal_kind="EXACT_DATETIME", exact_date=None),
        calendar_payload(
            outcome="FAIL_CLOSED",
            intent=None,
            temporal_kind="EXACT_DATE",
            failure_code="RANGE_REQUIRES_RANGE_AWARE_OPERATION",
        ),
    ],
)
def test_calendar_rejects_core_authority_and_cross_correlated_payloads(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(CalendarPlannerError):
        parse_calendar_plan(payload)


def test_fail_closed_discards_irrelevant_executable_fields() -> None:
    result = parse_calendar_plan(
        calendar_payload(
            outcome="FAIL_CLOSED",
            intent="DAY_LITERAL_CAPTURE",
            temporal_kind="UNSPECIFIED",
            exact_date=None,
            temporal_text="finales de mes",
            failure_code="TEMPORAL_UNRESOLVED",
        )
    )
    assert result.outcome is CalendarPlanOutcome.FAIL_CLOSED
    assert result.intent is None
    assert result.temporal_text is None
    assert result.failure_code is CalendarFailureCode.TEMPORAL_UNRESOLVED


def test_prompt_declares_minimal_app_authority_and_no_mini_core() -> None:
    prompt = render_calendar_prompt(
        current_context={"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
        conversation_context=({"role": "user", "text": "previous"},) * 10,
    )
    assert "authority is deliberately minimal" in prompt
    assert "DELEGATE_TO_CORE" in prompt
    assert "Core will independently decide semantic ownership" in prompt
    assert "Never collapse a range or vague phrase into one Day" in prompt
    assert "OUT_OF_SCOPE" in prompt
    assert prompt.count('"text":"previous"') == 8
    assert '"current_date":"2026-10-02"' in prompt
    for forbidden_instruction in (
        "direct_name",
        "candidate_scope",
        "identity parts",
        "SemanticWriteIntent",
        "CORE_SEMANTIC_WRITE",
    ):
        assert forbidden_instruction not in prompt
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


def test_diary_capture_without_explicit_date_uses_current_day_and_exact_content_span() -> None:
    source = "Escribe en mi diario que he tenido un día muy tranquilo."
    fake = FakeResponses(
        SimpleNamespace(
            status="completed",
            output_text=json.dumps(
                calendar_payload(
                    exact_date="2026-10-02",
                    temporal_text=None,
                    capture_text="he tenido un día muy tranquilo.",
                )
            ),
        )
    )
    planner = OpenAICalendarPlanner(
        SimpleNamespace(responses=fake),
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
    )

    result = planner.plan(source)

    assert result.intent is CalendarIntentKind.DAY_LITERAL_CAPTURE
    assert result.temporal.exact_date == "2026-10-02"
    assert result.temporal_text is None
    assert result.capture_text == "he tenido un día muy tranquilo."


def test_implicit_diary_date_cannot_escape_current_day_or_paraphrase_capture() -> None:
    current = {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"}
    source = "Escribe en mi diario que he tenido un día muy tranquilo."
    wrong_day = FakeResponses(
        SimpleNamespace(
            status="completed",
            output_text=json.dumps(
                calendar_payload(
                    exact_date="2026-10-03",
                    temporal_text=None,
                    capture_text="he tenido un día muy tranquilo.",
                )
            ),
        )
    )
    with pytest.raises(CalendarPlannerError, match="current date"):
        OpenAICalendarPlanner(SimpleNamespace(responses=wrong_day), current).plan(source)

    paraphrase = calendar_payload(
        exact_date="2026-10-02",
        temporal_text=None,
        capture_text="Fue un día tranquilo.",
    )
    with pytest.raises(CalendarPlannerError, match="grounded"):
        validate_calendar_plan_for_source(parse_calendar_plan(paraphrase), source)


def test_provider_uses_luna_low_once_without_receiving_core_schema() -> None:
    fake = FakeResponses(
        SimpleNamespace(
            status="completed",
            output_text=json.dumps(
                calendar_payload(exact_date="2026-10-05", temporal_text="Dentro de tres días")
            ),
        )
    )
    planner = OpenAICalendarPlanner(
        SimpleNamespace(responses=fake),
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
    )
    result = planner.plan(
        "Dentro de tres días viene el fontanero",
        ({"role": "assistant", "text": "prior"},),
    )
    assert result.temporal.exact_date == "2026-10-05"
    call = fake.calls[0]
    assert len(fake.calls) == 1
    assert call["model"] == CALENDAR_PLANNER_MODEL == "gpt-6-luna"
    assert call["reasoning"] == {"effort": CALENDAR_PLANNER_REASONING_EFFORT} == {"effort": "low"}
    assert call["max_output_tokens"] == CALENDAR_PLANNER_MAX_OUTPUT_TOKENS == 512
    assert call["store"] is False
    assert call["text"]["format"]["schema"] == calendar_plan_json_schema()
    assert call["input"][1] == {
        "role": "user",
        "content": "Dentro de tres días viene el fontanero",
    }


def test_calendar_planner_retains_safe_provider_metadata_for_runtime_telemetry() -> None:
    usage = {
        "input_tokens": 120,
        "output_tokens": 30,
        "input_tokens_details": {"cached_tokens": 20},
        "output_tokens_details": {"reasoning_tokens": 10},
    }
    fake = FakeResponses(
        SimpleNamespace(
            id="resp-calendar",
            status="completed",
            usage=usage,
            output_text=json.dumps(calendar_payload(temporal_text="Mañana")),
        )
    )
    planner = OpenAICalendarPlanner(
        SimpleNamespace(responses=fake),
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
    )
    planner.plan("Mañana viene el fontanero")
    assert planner.last_call is True
    assert planner.last_usage is usage
    assert planner.last_response_id == "resp-calendar"
    assert planner.last_provider_status == "completed"
    assert planner.last_error_category is None


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
def test_provider_or_local_validation_failure_makes_no_retry(response: object) -> None:
    fake = FakeResponses(response)
    planner = OpenAICalendarPlanner(
        SimpleNamespace(responses=fake),
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
    )
    with pytest.raises(CalendarPlannerError):
        planner.plan("Mañana viene el fontanero")
    assert len(fake.calls) == 1


def test_from_environment_disables_retries_and_sets_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    planner = OpenAICalendarPlanner.from_environment(
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"}
    )
    assert isinstance(planner, OpenAICalendarPlanner)
    assert calls == [{"max_retries": 0, "timeout": CALENDAR_PLANNER_TIMEOUT_SECONDS}]
