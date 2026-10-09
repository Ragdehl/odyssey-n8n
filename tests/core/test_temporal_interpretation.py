from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from odyssey_core.temporal_interpretation import (
    TEMPORAL_INTERPRETER_MAX_ITEMS,
    OpenAITemporalInterpreter,
    TemporalInterpreterError,
    parse_temporal_interpretation,
    render_temporal_prompt,
    temporal_interpretation_json_schema,
)
from odyssey_core.temporal_resolution import TemporalResolutionKind

CURRENT = {"date": "2026-10-04", "time": "10:00:00", "timezone": "Europe/Paris"}


def mention(
    text: str,
    *,
    kind: str = "EXACT_DATE",
    exact_date: str | None = "2026-10-04",
    exact_datetime: str | None = None,
    range_start: str | None = None,
    range_end_exclusive: str | None = None,
) -> dict[str, object]:
    """Build one complete strict-output-shaped temporal mention."""
    return {
        "temporal_text": text,
        "temporal": {
            "kind": kind,
            "exact_date": exact_date,
            "exact_datetime": exact_datetime,
            "range_start": range_start,
            "range_end_exclusive": range_end_exclusive,
        },
    }


def test_exact_date_projects_only_bounded_temporal_evidence_to_core() -> None:
    source = "Hoy hemos vaciado el garaje con Bea y mis hijos."
    result = parse_temporal_interpretation(
        {"mentions": [mention("Hoy")]}, source, timezone="Europe/Paris"
    )

    assert result.mentions[0].resolution.kind is TemporalResolutionKind.EXACT_DATE
    evidence = result.core_domain_interpretation()
    assert evidence.capability_id == "temporal"
    assert evidence.source_text == source
    assert evidence.evidence[0].source_text == "Hoy"
    assert evidence.evidence[0].value == "2026-10-04"


def test_multiple_exact_dates_are_preserved_in_source_order_for_core() -> None:
    source = "Ayer vi a Ana y hoy vi a Luis."
    result = parse_temporal_interpretation(
        {
            "mentions": [
                mention("Ayer", exact_date="2026-10-03"),
                mention("hoy", exact_date="2026-10-04"),
            ]
        },
        source,
        timezone="Europe/Paris",
    )

    assert result.kinds() == (
        TemporalResolutionKind.EXACT_DATE,
        TemporalResolutionKind.EXACT_DATE,
    )
    evidence = result.core_domain_interpretation()
    assert [(item.source_text, item.value) for item in evidence.evidence] == [
        ("Ayer", "2026-10-03"),
        ("hoy", "2026-10-04"),
    ]


def test_exact_datetime_provider_wall_time_is_canonicalized_with_runtime_timezone() -> None:
    """Replay the live-gate shape where Luna omitted the UTC offset."""
    result = parse_temporal_interpretation(
        {
            "mentions": [
                mention(
                    "mañana a las 15:00",
                    kind="EXACT_DATETIME",
                    exact_date=None,
                    exact_datetime="2026-10-05T15:00:00",
                )
            ]
        },
        "Marta empieza mañana a las 15:00 en Airbus.",
        timezone="Europe/Paris",
    )
    assert result.mentions[0].resolution.exact_datetime == "2026-10-05T15:00:00+02:00"
    assert result.core_domain_interpretation().evidence[0].value == "2026-10-05T15:00:00+02:00"


def test_temporal_rejects_ungrounded_or_out_of_order_source_spans() -> None:
    with pytest.raises(TemporalInterpreterError, match="grounded"):
        parse_temporal_interpretation(
            {"mentions": [mention("mañana", exact_date="2026-10-05")]},
            "Marta empieza hoy.",
            timezone="Europe/Paris",
        )
    with pytest.raises(TemporalInterpreterError, match="source order"):
        parse_temporal_interpretation(
            {
                "mentions": [
                    mention("hoy", exact_date="2026-10-04"),
                    mention("Ayer", exact_date="2026-10-03"),
                ]
            },
            "Ayer vi a Ana y hoy vi a Luis.",
            timezone="Europe/Paris",
        )


def test_exact_datetime_projects_to_core_anchor_while_range_stays_unsupported() -> None:
    datetime_result = parse_temporal_interpretation(
        {
            "mentions": [
                mention(
                    "mañana a las 15:00",
                    kind="EXACT_DATETIME",
                    exact_date=None,
                    exact_datetime="2026-10-05T15:00:00+02:00",
                )
            ]
        },
        "Marta empieza mañana a las 15:00.",
        timezone="Europe/Paris",
    )
    range_result = parse_temporal_interpretation(
        {
            "mentions": [
                mention(
                    "del lunes al miércoles",
                    kind="DATE_RANGE",
                    exact_date=None,
                    range_start="2026-10-05",
                    range_end_exclusive="2026-10-08",
                )
            ]
        },
        "Estuve allí del lunes al miércoles.",
        timezone="Europe/Paris",
    )

    assert datetime_result.kinds() == (TemporalResolutionKind.EXACT_DATETIME,)
    assert range_result.kinds() == (TemporalResolutionKind.DATE_RANGE,)
    evidence = datetime_result.core_domain_interpretation()
    assert evidence.evidence[0].source_text == "mañana a las 15:00"
    assert evidence.evidence[0].value == "2026-10-05T15:00:00+02:00"
    with pytest.raises(TemporalInterpreterError, match="not an exact Core anchor"):
        range_result.core_domain_interpretation()


def test_prompt_and_schema_have_only_temporal_authority_and_ordered_mentions() -> None:
    prompt = render_temporal_prompt(CURRENT)
    assert "Never classify the user's domain" in prompt
    assert "choose a target" in prompt
    assert "resolve an entity" in prompt
    assert "emit a mutation" in prompt
    assert "every material temporal mention" in prompt
    assert "in source order" in prompt
    assert "Calendar" not in prompt
    assert "journal" not in prompt.casefold()

    schema = temporal_interpretation_json_schema()
    assert set(schema["properties"]) == {"mentions"}
    assert schema["properties"]["mentions"]["minItems"] == 1
    assert schema["properties"]["mentions"]["maxItems"] == TEMPORAL_INTERPRETER_MAX_ITEMS
    item = schema["properties"]["mentions"]["items"]
    assert set(item["properties"]) == {"temporal_text", "temporal"}
    assert item["additionalProperties"] is False


def test_parse_rejects_empty_open_or_overlarge_mentions() -> None:
    with pytest.raises(TemporalInterpreterError):
        parse_temporal_interpretation({"mentions": []}, "hoy", timezone="Europe/Paris")
    with pytest.raises(TemporalInterpreterError):
        parse_temporal_interpretation(
            {"mentions": [{**mention("hoy"), "extra": True}]},
            "hoy",
            timezone="Europe/Paris",
        )
    with pytest.raises(TemporalInterpreterError):
        parse_temporal_interpretation(
            {"mentions": [mention("hoy")] * (TEMPORAL_INTERPRETER_MAX_ITEMS + 1)},
            "hoy " * (TEMPORAL_INTERPRETER_MAX_ITEMS + 1),
            timezone="Europe/Paris",
        )


def test_provider_contract_makes_one_low_reasoning_call_without_retries() -> None:
    calls = []

    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"mentions": [mention("hoy")]}),
                usage=SimpleNamespace(input_tokens=90, output_tokens=20),
                id="resp-temporal",
            )

    interpreter = OpenAITemporalInterpreter(SimpleNamespace(responses=Responses()), CURRENT)
    result = interpreter.interpret("hoy fui al parque")

    assert result.mentions[0].resolution.exact_date == "2026-10-04"
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-6-luna"
    assert calls[0]["reasoning"] == {"effort": "low"}
    assert calls[0]["store"] is False
    assert calls[0]["text"]["format"]["strict"] is True
    assert interpreter.last_usage.input_tokens == 90


def test_from_environment_disables_sdk_retries_and_sets_timeout(monkeypatch) -> None:
    constructor_calls: list[dict[str, object]] = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            constructor_calls.append(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    interpreter = OpenAITemporalInterpreter.from_environment(CURRENT)

    assert isinstance(interpreter, OpenAITemporalInterpreter)
    assert constructor_calls == [{"max_retries": 0, "timeout": 30.0}]


@pytest.mark.parametrize(
    ("response", "expected_category"),
    [
        (RuntimeError("network"), "RuntimeError"),
        (SimpleNamespace(status="incomplete", output_text="{}"), "IncompleteProviderResponse"),
        (SimpleNamespace(status="completed", output_text="not json"), "MalformedTemporalJSON"),
        (
            SimpleNamespace(
                status="completed",
                output_text=json.dumps({"mentions": [mention("mañana", exact_date="2026-10-05")]}),
            ),
            "LocalTemporalValidationError",
        ),
    ],
)
def test_provider_and_local_failures_make_one_call_then_fail_closed(
    response: object, expected_category: str
) -> None:
    calls = 0

    class Responses:
        def create(self, **_kwargs):
            nonlocal calls
            calls += 1
            if isinstance(response, Exception):
                raise response
            return response

    interpreter = OpenAITemporalInterpreter(SimpleNamespace(responses=Responses()), CURRENT)
    with pytest.raises(TemporalInterpreterError):
        interpreter.interpret("hoy fui al parque")

    assert calls == 1
    assert interpreter.last_error_category == expected_category


def test_repeated_same_temporal_wording_preserves_occurrence_multiplicity() -> None:
    source = "hoy fui al parque y hoy cené con Ana"
    result = parse_temporal_interpretation(
        {"mentions": [mention("hoy"), mention("hoy")]},
        source,
        timezone="Europe/Paris",
    )

    evidence = result.core_domain_interpretation()
    assert len(evidence.evidence) == 2
    assert [(item.source_text, item.value) for item in evidence.evidence] == [
        ("hoy", "2026-10-04"),
        ("hoy", "2026-10-04"),
    ]


def test_exact_temporal_explicit_year_cannot_be_reinterpreted_by_luna() -> None:
    """A 2026 date in source must never become a plausible but wrong 2025 note."""
    with pytest.raises(TemporalInterpreterError, match="Explicit year"):
        parse_temporal_interpretation(
            {"mentions": [mention("el 20 de octubre de 2026", exact_date="2025-10-20")]},
            "Vi a Ana el 20 de octubre de 2026.",
            timezone="Europe/Paris",
        )
    resolved = parse_temporal_interpretation(
        {"mentions": [mention("el 20 de octubre de 2026", exact_date="2026-10-20")]},
        "Vi a Ana el 20 de octubre de 2026.",
        timezone="Europe/Paris",
    )
    assert resolved.mentions[0].resolution.exact_date == "2026-10-20"
