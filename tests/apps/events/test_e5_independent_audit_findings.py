"""Independent E5 audit FAIL reproductions, generated before repair.

Each case uses a real canonical Event Note and the deployed Events adapter,
not a mock successful mutation.
"""

from __future__ import annotations

from odyssey_apps.events.execution import execute_event_candidate
from odyssey_apps.events.mutations import EventMutationService
from odyssey_apps.events.provider import validate_event_candidate
from odyssey_core import create_entity
from odyssey_core.notes import parse_note
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from tests.apps.events.test_event_calendar_vertical import CLOCK, setup


def _seed(tmp_path, *, name="Excursión", start="2026-10-19", **extra):
    schema, repo = setup(tmp_path)
    create_entity(
        repo,
        schema,
        path="event.md",
        entity_id="event-e5-audit",
        metadata={
            "type": "event",
            "name": name,
            "event_status": "scheduled",
            "start_date": start,
            **extra,
        },
        content="",
        actor="fixture",
        now=CLOCK,
    )
    return schema, repo


def _candidate(source, operation, name, role_quotes):
    return validate_event_candidate(
        source,
        {
            "operation": operation,
            "title_quote": None,
            "event_reference": name,
            "query_quote": None,
            "temporal_mentions": [{"quote": q, "role": role} for q, role in role_quotes],
        },
    )


def _temporal(source, *resolved):
    return TemporalInterpretation(
        source,
        tuple(
            TemporalMention(
                quote,
                TemporalResolution(
                    TemporalResolutionKind.EXACT_DATETIME
                    if "T" in value
                    else TemporalResolutionKind.EXACT_DATE,
                    **(
                        {"exact_datetime": value, "timezone": "Europe/Paris"}
                        if "T" in value
                        else {"exact_date": value}
                    ),
                ),
            )
            for quote, value in resolved
        ),
    )


def _attempt(schema, repo, source, operation, name, quotes, dates):
    return execute_event_candidate(
        candidate=_candidate(source, operation, name, quotes),
        temporal=_temporal(source, *dates) if dates else None,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-independent-audit",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )


def _actual(repo):
    return parse_note(repo.read_text("event.md")).metadata


def test_cancel_wrong_day_does_not_cancel_only_matching_name(tmp_path):
    schema, repo = _seed(tmp_path)
    source = "Cancela Excursión del viernes."
    result = _attempt(
        schema,
        repo,
        source,
        "CANCEL",
        "Excursión",
        (("viernes", "DATE"),),
        (("viernes", "2026-10-23"),),
    )
    assert result.status.value == "needs_attention"
    assert _actual(repo)["event_status"] == "scheduled"
    assert _actual(repo)["revision"] == 1


def test_cancel_date_without_temporal_evidence_does_not_mutate(tmp_path):
    schema, repo = _seed(tmp_path)
    source = "Cancela Excursión del viernes."
    result = _attempt(schema, repo, source, "CANCEL", "Excursión", (("viernes", "DATE"),), ())
    assert result.status.value == "needs_attention"
    assert _actual(repo)["event_status"] == "scheduled"


def test_cancel_correct_day_still_performs_canonical_transition(tmp_path):
    schema, repo = _seed(tmp_path)
    source = "Cancela Excursión del lunes."
    result = _attempt(
        schema,
        repo,
        source,
        "CANCEL",
        "Excursión",
        (("lunes", "DATE"),),
        (("lunes", "2026-10-19"),),
    )
    assert result.status.value == "completed"
    assert _actual(repo)["event_status"] == "cancelled"


def test_cancel_one_occurrence_of_weekly_series_must_not_cancel_entire_series(tmp_path):
    schema, repo = _seed(
        tmp_path,
        start="2026-10-19",
        end_date="2026-12-28",
        recurrence_weekday=0,
    )
    source = "Cancela Excursión del lunes siguiente."
    result = _attempt(
        schema,
        repo,
        source,
        "CANCEL",
        "Excursión",
        (("lunes siguiente", "DATE"),),
        (("lunes siguiente", "2026-10-26"),),
    )
    assert result.status.value == "needs_attention"
    assert _actual(repo)["event_status"] == "scheduled"


def test_cancel_wrong_hour_on_same_day_does_not_cancel(tmp_path):
    schema, repo = _seed(tmp_path, start="2026-10-23", start_at="2026-10-23T15:00:00+02:00")
    source = "Cancela Excursión del viernes a las ocho."
    result = _attempt(
        schema,
        repo,
        source,
        "CANCEL",
        "Excursión",
        (("viernes a las ocho", "DATE"),),
        (("viernes a las ocho", "2026-10-23T08:00:00+02:00"),),
    )
    assert result.status.value == "needs_attention"
    assert _actual(repo)["event_status"] == "scheduled"


def test_update_start_end_pair_cannot_be_interpreted_as_old_to_new_interval(tmp_path):
    schema, repo = _seed(tmp_path, name="Teatro", start="2026-10-20")
    source = "Mueve Teatro del martes al jueves."
    result = _attempt(
        schema,
        repo,
        source,
        "UPDATE",
        "Teatro",
        (("martes", "START"), ("jueves", "END")),
        (("martes", "2026-10-20"), ("jueves", "2026-10-22")),
    )
    assert result.status.value == "needs_attention"
    assert _actual(repo)["start_date"] == "2026-10-20"
    assert "end_date" not in _actual(repo)


def test_update_explicit_old_and_new_date_uses_only_destination(tmp_path):
    schema, repo = _seed(tmp_path, name="Teatro", start="2026-10-20")
    source = "Mueve Teatro del martes al jueves."
    result = _attempt(
        schema,
        repo,
        source,
        "UPDATE",
        "Teatro",
        (("martes", "ORIGINAL_DATE"), ("jueves", "NEW_DATE")),
        (("martes", "2026-10-20"), ("jueves", "2026-10-22")),
    )
    assert result.status.value == "completed"
    assert _actual(repo)["start_date"] == "2026-10-22"
    assert "end_date" not in _actual(repo)


def test_update_wrong_original_date_must_not_change_event(tmp_path):
    schema, repo = _seed(tmp_path, name="Teatro", start="2026-10-19")
    source = "Mueve Teatro del martes al jueves."
    result = _attempt(
        schema,
        repo,
        source,
        "UPDATE",
        "Teatro",
        (("martes", "ORIGINAL_DATE"), ("jueves", "NEW_DATE")),
        (("martes", "2026-10-20"), ("jueves", "2026-10-22")),
    )
    assert result.status.value == "needs_attention"
    assert _actual(repo)["start_date"] == "2026-10-19"


def test_update_compressed_temporal_range_still_cannot_become_multi_day(tmp_path):
    from odyssey_core.temporal import DateRange

    schema, repo = _seed(tmp_path, name="Teatro", start="2026-10-20")
    source = "Mueve Teatro del martes al jueves."
    candidate = _candidate(source, "UPDATE", "Teatro", (("martes", "START"), ("jueves", "END")))
    # One resolved range overlaps both provider quotes, previously a valid
    # route to incorrectly materializing a Tuesday-through-Thursday Event.
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "del martes al jueves",
                TemporalResolution(
                    TemporalResolutionKind.DATE_RANGE,
                    date_range=DateRange("2026-10-20", "2026-10-23"),
                ),
            ),
        ),
    )
    result = execute_event_candidate(
        candidate=candidate,
        temporal=temporal,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-range-replay",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "needs_attention"
    assert _actual(repo)["start_date"] == "2026-10-20"
    assert "end_date" not in _actual(repo)


def test_update_date_range_without_source_bound_destination_is_rejected(tmp_path):
    from odyssey_core.temporal import DateRange

    schema, repo = _seed(tmp_path, name="Teatro", start="2026-10-20")
    source = "Mueve Teatro al periodo del martes al jueves."
    candidate = _candidate(source, "UPDATE", "Teatro", (("del martes al jueves", "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "del martes al jueves",
                TemporalResolution(
                    TemporalResolutionKind.DATE_RANGE,
                    date_range=DateRange("2026-10-20", "2026-10-23"),
                ),
            ),
        ),
    )
    result = execute_event_candidate(
        candidate=candidate,
        temporal=temporal,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-range-replay",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "needs_attention"
    assert _actual(repo)["start_date"] == "2026-10-20"
    assert "end_date" not in _actual(repo)


def test_source_bound_cancel_accepts_unique_exact_temporal_subphrase(tmp_path):
    """Shared Temporal may quote the date without the preceding weekday."""
    schema, repo = _seed(tmp_path, start="2026-10-26")
    source = "Cancela Excursión del lunes 26 de octubre de 2026."
    candidate = _candidate(
        source,
        "CANCEL",
        "Excursión",
        (("lunes 26 de octubre de 2026", "DATE"),),
    )
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "26 de octubre de 2026",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-26"),
            ),
        ),
    )
    result = execute_event_candidate(
        candidate=candidate,
        temporal=temporal,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-subphrase-cancel",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "completed"
    assert _actual(repo)["event_status"] == "cancelled"


def test_source_bound_cancel_rejects_weekday_when_full_numeric_date_was_quoted(tmp_path):
    schema, repo = _seed(tmp_path, start="2026-10-26")
    source = "Cancela Excursión del lunes 26 de octubre de 2026."
    candidate = _candidate(
        source,
        "CANCEL",
        "Excursión",
        (("lunes 26 de octubre de 2026", "DATE"),),
    )
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "lunes",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-26"),
            ),
        ),
    )
    result = execute_event_candidate(
        candidate=candidate,
        temporal=temporal,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-weekday-only-cancel",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "needs_attention"
    assert _actual(repo)["event_status"] == "scheduled"


def test_source_bound_reschedule_checks_distinct_old_and_new_temporal_subphrases(tmp_path):
    schema, repo = _seed(tmp_path, name="Teatro", start="2026-10-27")
    source = "Mueve Teatro del martes 27 de octubre de 2026 al jueves 29 de octubre de 2026."
    candidate = _candidate(
        source,
        "UPDATE",
        "Teatro",
        (
            ("martes 27 de octubre de 2026", "ORIGINAL_DATE"),
            ("jueves 29 de octubre de 2026", "NEW_DATE"),
        ),
    )
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "27 de octubre de 2026",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-27"),
            ),
            TemporalMention(
                "29 de octubre de 2026",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-29"),
            ),
        ),
    )
    result = execute_event_candidate(
        candidate=candidate,
        temporal=temporal,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-subphrase-reschedule",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "completed"
    assert _actual(repo)["start_date"] == "2026-10-29"
    assert "end_date" not in _actual(repo)
