"""E5 trusted mutations prove the shared Core Writer/E3 gate path.

The chat delivery manifest is intentionally not part of this service yet;
these are isolated preauthorized mutation commands, NOT model permissions.
"""

from __future__ import annotations

import hashlib

import pytest

from odyssey_apps.events import EventMutationError, EventMutationService, EventOccurrence
from odyssey_core import create_entity
from odyssey_core.notes import parse_note
from odyssey_core.temporal import TemporalAnchor
from tests.apps.events.test_event_calendar_vertical import CLOCK, calendar, setup


def make_event(tmp_path, name="Foto del colegio", occurrence=None):
    schema, repo = setup(tmp_path)
    service = EventMutationService(repo, schema)
    receipt = service.create(
        name=name,
        source_text="Foto del colegio el 22 de noviembre.",
        occurrence=occurrence or EventOccurrence(TemporalAnchor("2026-11-22")),
        request_id="event-created-001",
        actor="fixture",
        now=CLOCK,
    )
    return schema, repo, service, receipt


def test_core_e3_create_materializes_one_canonical_event_and_calendar_readback(tmp_path):
    schema, repo, _service, receipt = make_event(tmp_path)
    assert receipt.persistence.id == receipt.target_id
    assert receipt.readback.metadata["type"] == "event"
    assert receipt.readback.metadata["event_status"] == "scheduled"
    assert receipt.readback.metadata["start_date"] == "2026-11-22"
    assert receipt.readback.metadata["revision"] == 1
    assert receipt.readback.content.count("Foto del colegio el 22 de noviembre.") == 1
    assert (
        hashlib.sha256(repo.read_text(receipt.target_path).encode()).hexdigest()
        == receipt.source_hash
    )
    assert (
        sum(
            parse_note(repo.read_text(path)).metadata["type"] == "event"
            for path in repo.list_markdown_paths()
        )
        == 1
    )
    query = calendar(tmp_path, repo, schema)
    assert query.day("2026-11-22").events[0].source.id == receipt.target_id
    assert query.day("2026-11-22").tasks == ()


def test_core_e3_cancel_preserves_event_identity_and_soft_lifecycle(tmp_path):
    schema, repo, service, receipt = make_event(tmp_path)
    changed = service.change(
        note_id=receipt.target_id,
        expected_revision=1,
        expected_source_hash=receipt.source_hash,
        request_id="event-cancelled-002",
        actor="fixture",
        now="2026-10-21T13:00:00+02:00",
        operation="cancel",
    )
    assert changed.before_revision == 1 and changed.after_revision == 2
    assert changed.readback.metadata["event_status"] == "cancelled"
    assert changed.readback.metadata.get("deleted") is not True
    assert (
        sum(
            parse_note(repo.read_text(path)).metadata["type"] == "event"
            for path in repo.list_markdown_paths()
        )
        == 1
    )
    assert parse_note(repo.read_text(receipt.target_path)).content == receipt.readback.content
    assert calendar(tmp_path, repo, schema).day("2026-11-22").events == ()
    before = repo.read_text(receipt.target_path)
    with pytest.raises(EventMutationError, match="EVENT_TARGET_UNAVAILABLE"):
        service.change(
            note_id=receipt.target_id,
            expected_revision=1,
            expected_source_hash=receipt.source_hash,
            request_id="event-stale-003",
            actor="fixture",
            now="2026-10-21T13:05:00+02:00",
            operation="cancel",
        )
    assert repo.read_text(receipt.target_path) == before


def test_core_e3_reschedule_overwrites_old_coordinates_not_identity(tmp_path):
    schema, repo, service, receipt = make_event(tmp_path)
    changed = service.change(
        note_id=receipt.target_id,
        expected_revision=1,
        expected_source_hash=receipt.source_hash,
        request_id="event-reschedule-002",
        actor="fixture",
        now="2026-10-21T13:00:00+02:00",
        operation="reschedule",
        occurrence=EventOccurrence(
            TemporalAnchor("2026-11-26", "16:00:00", "+01:00"),
            TemporalAnchor("2026-11-26", "17:30:00", "+01:00"),
        ),
    )
    assert changed.readback.metadata["start_date"] == "2026-11-26"
    assert changed.readback.metadata["start_at"] == "2026-11-26T16:00:00+01:00"
    assert changed.readback.metadata["end_at"] == "2026-11-26T17:30:00+01:00"
    assert changed.readback.metadata["id"] == receipt.target_id
    day_old = calendar(tmp_path, repo, schema).day("2026-11-22")
    day_new = calendar(tmp_path, repo, schema).schedule("2026-11-26", 1).days[0]
    assert day_old.events == ()
    assert len(day_new.timed) == 1
    assert day_new.timed[0].start_time == "16:00"
    assert day_new.timed[0].end_time == "17:30"
    assert (
        sum(
            parse_note(repo.read_text(path)).metadata["type"] == "event"
            for path in repo.list_markdown_paths()
        )
        == 1
    )


def test_core_e3_reschedule_removes_old_recurrence_and_end_date(tmp_path):
    schema, repo, service, receipt = make_event(
        tmp_path,
        occurrence=EventOccurrence(TemporalAnchor("2027-04-05"), TemporalAnchor("2027-06-28"), 0),
    )
    changed = service.change(
        note_id=receipt.target_id,
        expected_revision=1,
        expected_source_hash=receipt.source_hash,
        request_id="event-reschedule-002",
        actor="fixture",
        now="2026-10-21T13:00:00+02:00",
        operation="reschedule",
        occurrence=EventOccurrence(TemporalAnchor("2027-05-01")),
    )
    meta = changed.readback.metadata
    assert "end_date" not in meta and "recurrence_weekday" not in meta
    assert calendar(tmp_path, repo, schema).day("2027-04-05").events == ()
    assert len(calendar(tmp_path, repo, schema).day("2027-05-01").events) == 1


@pytest.mark.parametrize(
    "start,end,weekday",
    [
        (TemporalAnchor("2026-11-22"), TemporalAnchor("2026-11-21"), None),
        (TemporalAnchor("2027-04-05"), None, 0),
        (TemporalAnchor("2027-04-05", "09:00:00", "+02:00"), TemporalAnchor("2027-06-28"), 0),
        (TemporalAnchor("2027-04-05"), TemporalAnchor("2027-06-28"), 7),
    ],
)
def test_invalid_temporal_intent_does_not_enter_e3(start, end, weekday):
    with pytest.raises(EventMutationError):
        EventOccurrence(start, end, weekday)


def test_event_mutation_cannot_target_core_person_note(tmp_path):
    schema, repo = setup(tmp_path)
    create_entity(
        repo,
        schema,
        path="person.md",
        entity_id="person-1",
        metadata={"name": "Beatriz", "type": "person"},
        content="",
        actor="fixture",
        now=CLOCK,
    )
    raw = repo.read_text("person.md")
    service = EventMutationService(repo, schema)
    with pytest.raises(EventMutationError, match="EVENT_TARGET_UNAVAILABLE"):
        service.change(
            note_id="person-1",
            expected_revision=1,
            expected_source_hash=hashlib.sha256(raw.encode()).hexdigest(),
            request_id="forged-event-cancel",
            actor="fixture",
            now=CLOCK,
            operation="cancel",
        )
    assert repo.read_text("person.md") == raw


def test_source_validation_fails_before_any_write(tmp_path):
    _schema, repo = setup(tmp_path)
    service = EventMutationService(repo, _schema)
    with pytest.raises(EventMutationError, match="EVENT_SOURCE_INVALID"):
        service.create(
            name="",
            source_text="Foto del colegio",
            occurrence=EventOccurrence(TemporalAnchor("2026-11-22")),
            request_id="invalid-event",
            actor="fixture",
            now=CLOCK,
        )
    assert not tuple(repo.list_markdown_paths())
