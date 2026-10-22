"""E5 QUERY and finite natural-language weekly recurrence through typed contracts."""

from __future__ import annotations

from odyssey_apps.events.execution import bound_occurrence, execute_event_candidate
from odyssey_apps.events.mutations import EventMutationService
from odyssey_apps.events.provider import validate_event_candidate
from odyssey_apps.events.queries import event_note_snapshot
from odyssey_core import create_entity
from odyssey_core.notes import parse_note
from odyssey_core.temporal import DateRange
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from tests.apps.events.test_event_calendar_vertical import CLOCK, calendar, setup


def query(source, quote=None, times=()):
    return validate_event_candidate(
        source,
        {
            "operation": "QUERY",
            "event_reference": None,
            "title_quote": None,
            "query_quote": quote,
            "temporal_mentions": times,
        },
    )


def test_query_notes_is_actual_grounded_filtered_snapshot(tmp_path):
    schema, repo = setup(tmp_path)
    create_entity(
        repo,
        schema,
        path="photo.md",
        entity_id="photo-id",
        metadata={
            "type": "event",
            "name": "Foto del colegio",
            "event_status": "scheduled",
            "start_date": "2026-11-22",
        },
        content="",
        actor="fixture",
        now=CLOCK,
    )
    create_entity(
        repo,
        schema,
        path="cancelled.md",
        entity_id="c-id",
        metadata={
            "type": "event",
            "name": "Teatro del colegio",
            "event_status": "cancelled",
            "start_date": "2026-11-20",
        },
        content="",
        actor="fixture",
        now=CLOCK,
    )
    create_entity(
        repo,
        schema,
        path="another.md",
        entity_id="a-id",
        metadata={
            "type": "event",
            "name": "Teatro municipal",
            "event_status": "scheduled",
            "start_date": "2026-11-20",
        },
        content="",
        actor="fixture",
        now=CLOCK,
    )
    source = "¿Qué eventos del colegio hay en noviembre de 2026?"
    c = query(source, "colegio", [{"quote": "noviembre de 2026", "role": "DATE"}])
    resolution = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "noviembre de 2026",
                TemporalResolution(
                    TemporalResolutionKind.DATE_RANGE,
                    date_range=DateRange("2026-11-01", "2026-12-01"),
                ),
            ),
        ),
    )
    snapshot = event_note_snapshot(
        candidate=c, temporal=resolution, repository=repo, schema=schema, now=CLOCK
    )
    assert snapshot.note_ids == ("photo-id",)
    result = execute_event_candidate(
        candidate=c,
        temporal=resolution,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-q",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
        query_handler=lambda _c, _t: snapshot,
    )
    assert result.status.value == "completed"
    assert result.affected_stable_note_ids == ()
    assert result.note_result_snapshot["note_ids"] == ["photo-id"]
    assert result.presentation_intent == "show_notes"


def test_recurrence_weekday_derived_from_exact_source_only(tmp_path):
    source = "Piscina todos los lunes del 5 de abril al 28 de junio de 2027."
    c = validate_event_candidate(
        source,
        {
            "operation": "CREATE",
            "title_quote": "Piscina",
            "event_reference": None,
            "query_quote": None,
            "temporal_mentions": [
                {"quote": "todos los lunes", "role": "RECURRING_WEEKDAY"},
                {"quote": "del 5 de abril al 28 de junio de 2027", "role": "RECURRENCE_RANGE"},
            ],
        },
    )
    interpretation = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "del 5 de abril al 28 de junio de 2027",
                TemporalResolution(
                    TemporalResolutionKind.DATE_RANGE,
                    date_range=DateRange("2027-04-05", "2027-06-29"),
                ),
            ),
        ),
    )
    occurrence = bound_occurrence(c, interpretation)
    assert occurrence.start.date == "2027-04-05"
    assert occurrence.end.date == "2027-06-28"
    assert occurrence.recurrence_weekday == 0
    schema, repo = setup(tmp_path)
    result = execute_event_candidate(
        candidate=c,
        temporal=interpretation,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-weekly",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "completed"
    day = calendar(tmp_path, repo, schema).month("2027-04")
    assert [x.date for x in day.days if x.event_count] == [
        "2027-04-05",
        "2027-04-12",
        "2027-04-19",
        "2027-04-26",
    ]
    assert (
        sum(
            parse_note(repo.read_text(path)).metadata.get("type") == "event"
            for path in repo.list_markdown_paths()
        )
        == 1
    )
