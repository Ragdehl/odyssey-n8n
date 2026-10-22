"""Events read projection from current canonical Markdown, never the model's guesses."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from odyssey_core.note_result_snapshots import NoteResultSnapshot
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import TemporalInterpretation
from odyssey_core.temporal_resolution import TemporalResolutionKind

from .execution import EventRouteError
from .provider import EventCandidate


def _date_filter(
    candidate: EventCandidate, temporal: TemporalInterpretation | None
) -> tuple[date, date] | None:
    if not candidate.interpretation.temporal_mentions:
        return None
    if temporal is None or temporal.source_text != candidate.interpretation.source_text:
        raise EventRouteError("EVENT_QUERY_TEMPORAL_REQUIRED")
    if len(temporal.mentions) != 1:
        raise EventRouteError("EVENT_QUERY_MULTIPLE_DATES")
    item = temporal.mentions[0]
    if not any(
        item.temporal_text in m.quote or m.quote in item.temporal_text
        for m in candidate.interpretation.temporal_mentions
    ):
        raise EventRouteError("EVENT_QUERY_TEMPORAL_NOT_GROUNDED")
    value = item.resolution
    if value.kind is TemporalResolutionKind.DATE_RANGE and value.date_range is not None:
        first = date.fromisoformat(value.date_range.start)
        last = date.fromisoformat(value.date_range.end_exclusive) - timedelta(days=1)
    elif value.kind in (TemporalResolutionKind.EXACT_DATE, TemporalResolutionKind.EXACT_DATETIME):
        first = date.fromisoformat((value.exact_date or value.exact_datetime)[:10])
        last = first
    else:
        raise EventRouteError("EVENT_QUERY_TEMPORAL_UNRESOLVED")
    if not 0 <= (last - first).days <= 366:
        raise EventRouteError("EVENT_QUERY_RANGE_TOO_BROAD")
    return first, last


def _overlaps(note: Any, requested: tuple[date, date] | None) -> bool:
    if requested is None:
        return True
    props = note.metadata
    start = date.fromisoformat(props["start_date"])
    end = date.fromisoformat(props.get("end_date", props["start_date"]))
    left, right = requested
    if start > right or end < left:
        return False
    weekday = props.get("recurrence_weekday")
    if weekday is None:
        return True
    day = max(start, left)
    last = min(end, right)
    for _ in range((last - day).days + 1):
        if day.weekday() == weekday:
            return True
        day += timedelta(days=1)
    return False


def event_note_snapshot(
    *,
    candidate: EventCandidate,
    temporal: TemporalInterpretation | None,
    repository: VaultRepository,
    schema: dict[str, Any],
    now: str,
) -> NoteResultSnapshot:
    """Return verified scheduled Event note IDs, current-state read only."""
    dates = _date_filter(candidate, temporal)
    term = (candidate.query_quote or "").casefold()
    notes = []
    for path in repository.list_markdown_paths():
        raw = repository.read_text(path)
        note = parse_note(raw)
        validate_note(note, schema)
        props = note.metadata
        if props.get("type") != "event" or props.get("event_status") != "scheduled":
            continue
        if term and term not in props["name"].casefold():
            continue
        if _overlaps(note, dates):
            notes.append((props["start_date"], props["id"]))
    notes.sort()
    ids = tuple(uid for _, uid in notes)
    return NoteResultSnapshot(
        query=candidate.interpretation.source_text[:512],
        filters=({"field": "type", "op": "eq", "value": "event"},),
        sort="updated_desc",
        ranking_version="e5-current-markdown-v1",
        executed_at=now,
        note_ids=ids[:64],
        total=len(ids),
        truncated=len(ids) > 64,
    )
