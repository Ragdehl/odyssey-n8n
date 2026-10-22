"""Independent E5 post-audit regressions: omitted and shortened target dates."""

from __future__ import annotations

import pytest

from odyssey_apps.events.execution import execute_event_candidate
from odyssey_apps.events.mutations import EventMutationService
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from tests.apps.events.test_e5_independent_audit_findings import (
    _actual,
    _candidate,
    _seed,
)
from tests.apps.events.test_event_calendar_vertical import CLOCK


def run(schema, repo, candidate, temporal=None):
    return execute_event_candidate(
        candidate=candidate,
        temporal=temporal,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-review-fail-closed",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )


def test_next_monday_must_not_shrink_to_monday_when_identifying_target(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion", start="2026-10-19")
    source = "Cancel Excursion next Monday."
    candidate = _candidate(source, "CANCEL", "Excursion", (("next Monday", "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "Monday",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-19"),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_TARGET_TEMPORAL_SOURCE_MISMATCH"
    assert _actual(repo)["event_status"] == "scheduled"


def test_source_date_omitted_by_event_model_must_not_authorize_cancel(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion", start="2026-10-19")
    candidate = _candidate("Cancel Excursion next Monday.", "CANCEL", "Excursion", ())
    result = run(schema, repo, candidate)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_DATE_EVIDENCE_REQUIRED"
    assert _actual(repo)["event_status"] == "scheduled"


def test_date_omitted_but_hidden_inside_full_reference_still_abstains(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion next Monday", start="2026-10-19")
    candidate = _candidate("Cancel Excursion next Monday.", "CANCEL", "Excursion next Monday", ())
    result = run(schema, repo, candidate)
    assert result.status.value == "needs_attention"
    assert _actual(repo)["event_status"] == "scheduled"


def test_explicit_bare_cancel_still_works_without_temporal_mentions(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion", start="2026-10-19")
    candidate = _candidate("Cancel Excursion.", "CANCEL", "Excursion", ())
    result = run(schema, repo, candidate)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_DATE_EVIDENCE_REQUIRED"
    assert _actual(repo)["event_status"] == "scheduled"


def test_bare_cancel_preserves_literal_identity_suffix(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion E5 A1B2C3D4", start="2026-10-19")
    candidate = _candidate("Cancel Excursion E5 A1B2C3D4.", "CANCEL", "Excursion E5 A1B2C3D4", ())
    result = run(schema, repo, candidate)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_DATE_EVIDENCE_REQUIRED"
    assert _actual(repo)["event_status"] == "scheduled"


def test_unrecognized_cancel_command_cannot_write_without_qualifiers(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion", start="2026-10-19")
    candidate = _candidate("I might cancel Excursion.", "CANCEL", "Excursion", ())
    result = run(schema, repo, candidate)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_DATE_EVIDENCE_REQUIRED"
    assert _actual(repo)["event_status"] == "scheduled"


def test_independent_temporal_finds_date_omitted_by_event_model(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion", start="2026-10-19")
    source = "Cancel Excursion next Monday."
    candidate = _candidate(source, "CANCEL", "Excursion", ())
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "next Monday",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-26"),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_DATE_EVIDENCE_REQUIRED"
    assert _actual(repo)["event_status"] == "scheduled"


def test_relative_week_hidden_inside_full_event_reference_still_abstains(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion in two weeks", start="2026-10-19")
    candidate = _candidate("Cancel Excursion in two weeks.", "CANCEL", "Excursion in two weeks", ())
    result = run(schema, repo, candidate)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_DATE_EVIDENCE_REQUIRED"
    assert _actual(repo)["event_status"] == "scheduled"


def test_calendar_month_hidden_inside_title_cannot_bypass_temporal_review(tmp_path):
    schema, repo = _seed(tmp_path, name="Concierto en octubre", start="2026-10-19")
    candidate = _candidate("Cancela Concierto en octubre.", "CANCEL", "Concierto en octubre", ())
    result = run(schema, repo, candidate)
    assert result.status.value == "needs_attention"
    assert _actual(repo)["event_status"] == "scheduled"


def test_both_models_shorten_next_monday_to_monday_must_not_cancel(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion", start="2026-10-19")
    source = "Cancel Excursion next Monday."
    candidate = _candidate(source, "CANCEL", "Excursion", (("Monday", "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "Monday",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-19"),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_SOURCE_COVERAGE_UNVERIFIED"
    assert _actual(repo)["event_status"] == "scheduled"


def test_unquoted_clock_inside_event_reference_must_not_cancel(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion at 5pm", start="2026-10-19")
    candidate = _candidate("Cancel Excursion at 5pm.", "CANCEL", "Excursion at 5pm", ())
    result = run(schema, repo, candidate)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_DATE_EVIDENCE_REQUIRED"
    assert _actual(repo)["event_status"] == "scheduled"


def test_unquoted_ordinal_inside_event_reference_must_not_cancel(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion on the 19th", start="2026-10-19")
    candidate = _candidate("Cancel Excursion on the 19th.", "CANCEL", "Excursion on the 19th", ())
    result = run(schema, repo, candidate)
    assert result.status.value == "needs_attention"
    assert _actual(repo)["event_status"] == "scheduled"


def test_clock_hidden_in_event_reference_still_fails_with_verified_weekday(tmp_path):
    schema, repo = _seed(tmp_path, name="Excursion at 5pm", start="2026-10-19")
    source = "Cancel Excursion at 5pm on Monday."
    candidate = _candidate(source, "CANCEL", "Excursion at 5pm", (("Monday", "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "Monday",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-19"),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_SOURCE_COVERAGE_UNVERIFIED"
    assert _actual(repo)["event_status"] == "scheduled"


@pytest.mark.parametrize(
    "clock",
    (
        "5 pm",
        "5 p.m.",
        "5p.m.",
        "5 AM",
        "17 h",
        "17h30",
        "17 h 30",
        "17:30",
        "5 hours",
        "5pm",
    ),
)
def test_clock_absorbed_into_event_reference_must_abstain(tmp_path, clock):
    # Persisted canonical Event has a different time: independent Temporal
    # quoting only Monday cannot authorize a mutation of the 18:00 event.
    name = f"Excursion {clock}"
    schema, repo = _seed(
        tmp_path, name=name, start="2026-10-19", start_at="2026-10-19T18:00:00+02:00"
    )
    source = f"Cancel {name} on Monday."
    candidate = _candidate(source, "CANCEL", name, (("Monday", "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "Monday",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-19"),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_CANCEL_SOURCE_COVERAGE_UNVERIFIED"
    assert _actual(repo)["event_status"] == "scheduled"
    assert _actual(repo)["revision"] == 1


def test_full_quoted_clock_and_date_can_cancel_correct_target(tmp_path):
    schema, repo = _seed(
        tmp_path, name="Excursion", start="2026-10-19", start_at="2026-10-19T17:00:00+02:00"
    )
    source = "Cancel Excursion 5 pm on Monday."
    candidate = _candidate(source, "CANCEL", "Excursion", (("5 pm on Monday", "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "5 pm on Monday",
                TemporalResolution(
                    TemporalResolutionKind.EXACT_DATETIME,
                    exact_datetime="2026-10-19T17:00:00+02:00",
                    timezone="Europe/Paris",
                ),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "completed"
    assert _actual(repo)["event_status"] == "cancelled"


def test_date_only_cancellation_remains_supported_for_timed_event(tmp_path):
    schema, repo = _seed(
        tmp_path, name="Excursion", start="2026-10-19", start_at="2026-10-19T18:00:00+02:00"
    )
    source = "Cancel Excursion on Monday."
    candidate = _candidate(source, "CANCEL", "Excursion", (("Monday", "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "Monday",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-19"),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "completed"
    assert _actual(repo)["event_status"] == "cancelled"


@pytest.mark.parametrize(
    "clock",
    (
        "5 pm",
        "5 p.m.",
        "17 h",
        "17h30",
        "17:30",
        "at five",
        "a las ocho",
        "por la tarde",
    ),
)
def test_quoted_time_cannot_be_resolved_to_date_only(tmp_path, clock):
    # Independent audit found Temporal could quote the *whole* source but
    # resolve only Monday, silently dropping the clock and cancelling 18:00.
    schema, repo = _seed(
        tmp_path, name="Excursion", start="2026-10-19", start_at="2026-10-19T18:00:00+02:00"
    )
    source = f"Cancel Excursion {clock} on Monday."
    quote = f"{clock} on Monday"
    candidate = _candidate(source, "CANCEL", "Excursion", ((quote, "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                quote,
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-19"),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_TARGET_CLOCK_UNVERIFIED"
    assert _actual(repo)["event_status"] == "scheduled"
    assert _actual(repo)["revision"] == 1


@pytest.mark.parametrize(
    "clock",
    ("5 o’clock", "5 o'clock", "5 oclock", "5 o clock", "at six", "a las siete", "late in the day"),
)
def test_non_date_words_cannot_hitchhike_on_exact_date(tmp_path, clock):
    schema, repo = _seed(
        tmp_path, name="Excursion", start="2026-10-19", start_at="2026-10-19T18:00:00+02:00"
    )
    source = f"Cancel Excursion {clock} on Monday."
    quote = f"{clock} on Monday"
    candidate = _candidate(source, "CANCEL", "Excursion", ((quote, "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                quote,
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-19"),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_TARGET_CLOCK_UNVERIFIED"
    assert _actual(repo)["event_status"] == "scheduled"
    assert _actual(repo)["revision"] == 1


@pytest.mark.parametrize(
    ("source", "quote"),
    (
        ("Cancel Excursion next Monday.", "next Monday"),
        ("Annule Excursion du lundi 26 octobre 2026.", "lundi 26 octobre 2026"),
    ),
)
def test_complete_source_quoted_date_remains_cancellable(tmp_path, source, quote):
    schema, repo = _seed(tmp_path, name="Excursion", start="2026-10-26")
    candidate = _candidate(source, "CANCEL", "Excursion", ((quote, "DATE"),))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                quote,
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-26"),
            ),
        ),
    )
    result = run(schema, repo, candidate, temporal)
    assert result.status.value == "completed"
    assert _actual(repo)["event_status"] == "cancelled"
