"""An exact dated arrival may be an Event without an imperative or noun title.

These are frozen typed-provider contracts, not fresh production-model results.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from odyssey_apps.events import EventMutationService, EventOccurrence
from odyssey_apps.events.interpretation import EventOperation
from odyssey_apps.events.provider import (
    EVENTS_PROMPT,
    EVENTS_PROMPT_V4,
    EVENTS_PROMPT_V5_EXTENSION,
    OpenAIEventInterpreter,
    validate_event_candidate,
)
from odyssey_core.temporal import TemporalAnchor
from tests.apps.events.test_event_calendar_vertical import CLOCK, calendar, setup


@pytest.mark.parametrize(
    ("source", "title", "date_quote"),
    [
        (
            "Mi prima vendrá a Lyon el 16 de noviembre de 2026",
            "Mi prima vendrá a Lyon",
            "16 de noviembre de 2026",
        ),
        (
            "La vecina llegará a casa el 20 de noviembre de 2026",
            "La vecina llegará a casa",
            "20 de noviembre de 2026",
        ),
        (
            "Ma cousine viendra à Lyon le 16 novembre 2026",
            "Ma cousine viendra à Lyon",
            "16 novembre 2026",
        ),
        (
            "My cousin arrives in Lyon on November 16, 2026",
            "My cousin arrives in Lyon",
            "November 16, 2026",
        ),
    ],
)
def test_future_visit_has_source_bound_verbal_event_title(source, title, date_quote):
    candidate = validate_event_candidate(
        source,
        {
            "operation": "CREATE",
            "temporal_mentions": [{"quote": date_quote, "role": "DATE"}],
            "event_reference": None,
            "title_quote": title,
            "query_quote": None,
        },
    )
    assert candidate.interpretation.operation is EventOperation.CREATE
    assert candidate.title_quote == title
    assert candidate.interpretation.source_text == source
    assert candidate.interpretation.temporal_mentions[0].quote == date_quote


@pytest.mark.parametrize(
    "source",
    [
        "Quizá mi prima venga a Lyon el 16 de noviembre de 2026",
        "Si mi prima viene a Lyon el 16 de noviembre de 2026, saldremos",
        "Mi prima no vendrá a Lyon el 16 de noviembre de 2026",
        "Mi prima vino a Lyon el 16 de noviembre de 2025",
        "Mi prima tiene 30 años el 16 de noviembre de 2026",
        "Tengo que llamar a mi prima el 16 de noviembre de 2026",
    ],
)
def test_nonconfirmed_arrival_and_dated_non_event_keep_abstention(source):
    candidate = validate_event_candidate(
        source,
        {
            "operation": "ABSTAIN",
            "temporal_mentions": [],
            "event_reference": None,
            "title_quote": None,
            "query_quote": None,
        },
    )
    assert candidate.interpretation.operation is EventOperation.ABSTAIN


def test_additive_prompt_revision_retains_source_and_refusal_guards():
    assert EVENTS_PROMPT == EVENTS_PROMPT_V4 + EVENTS_PROMPT_V5_EXTENSION
    for instruction in (
        "ABSTAIN: all mentions empty",
        "Never resolve dates, time zones, participants, or note IDs",
        "For mixed Tasks+Events in the SAME",
    ):
        assert instruction in EVENTS_PROMPT_V4
    assert "future arrival or visit" in EVENTS_PROMPT_V5_EXTENSION
    assert "hypothetical/conditional visits" in EVENTS_PROMPT_V5_EXTENSION


def test_current_interpreter_uses_v5_with_one_closed_model_call():
    source = "Mi prima vendrá a Lyon el 16 de noviembre de 2026"
    payload = {
        "operation": "CREATE",
        "temporal_mentions": [{"quote": "16 de noviembre de 2026", "role": "DATE"}],
        "event_reference": None,
        "title_quote": "Mi prima vendrá a Lyon",
        "query_quote": None,
    }
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(payload), usage=None)

    candidate = OpenAIEventInterpreter(
        SimpleNamespace(responses=SimpleNamespace(create=create))
    ).interpret(source)
    assert candidate.title_quote == payload["title_quote"]
    assert len(calls) == 1
    assert calls[0]["text"]["format"]["name"] == "e5_event_intent_v5"
    assert calls[0]["input"][0]["content"] == EVENTS_PROMPT
    assert calls[0]["input"][1]["content"] == source


def test_synthetic_arrival_event_persists_in_core_and_calendar(tmp_path):
    schema, repo = setup(tmp_path)
    source = "Mi prima vendrá a Lyon el 16 de noviembre de 2026"
    candidate = validate_event_candidate(
        source,
        {
            "operation": "CREATE",
            "temporal_mentions": [{"quote": "16 de noviembre de 2026", "role": "DATE"}],
            "event_reference": None,
            "title_quote": "Mi prima vendrá a Lyon",
            "query_quote": None,
        },
    )
    service = EventMutationService(repo, schema)
    receipt = service.create(
        name=candidate.title_quote,
        source_text=candidate.interpretation.source_text,
        occurrence=EventOccurrence(TemporalAnchor("2026-11-16")),
        request_id="synthetic-arrival-20261116",
        actor="fixture",
        now=CLOCK,
    )
    assert receipt.readback.metadata["name"] == "Mi prima vendrá a Lyon"
    assert receipt.readback.metadata["start_date"] == "2026-11-16"
    assert source in receipt.readback.content
    assert (
        calendar(tmp_path, repo, schema).day("2026-11-16").events[0].source.id == receipt.target_id
    )
