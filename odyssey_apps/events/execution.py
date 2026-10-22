"""Bounded E5 route executor: source-bound Events, shared Temporal and E3 receipts.

A route passed to this adapter must be an authorized Events app destination.
Without an authenticated principal it never calls the mutation service.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    UnitResult,
    UnitStatus,
)
from odyssey_core.note_result_snapshots import NoteResultSnapshot
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal import TemporalAnchor
from odyssey_core.temporal_interpretation import TemporalInterpretation
from odyssey_core.temporal_resolution import TemporalResolutionKind

from .interpretation import EventOperation, EventTemporalRole
from .mutations import EventMutationError, EventMutationService, EventOccurrence
from .provider import EventCandidate


class EventRouteError(ValueError):
    """A source/temporal/target mapping is not reliably proven."""


_WEEKDAYS = {
    "lunes": 0,
    "monday": 0,
    "lundi": 0,
    "martes": 1,
    "tuesday": 1,
    "mardi": 1,
    "miércoles": 2,
    "miercoles": 2,
    "wednesday": 2,
    "mercredi": 2,
    "jueves": 3,
    "thursday": 3,
    "jeudi": 3,
    "viernes": 4,
    "friday": 4,
    "vendredi": 4,
    "sábado": 5,
    "sabado": 5,
    "saturday": 5,
    "samedi": 5,
    "domingo": 6,
    "sunday": 6,
    "dimanche": 6,
}


def _source_weekday(candidate: EventCandidate) -> int | None:
    """Map one Events model-quoted literal weekday, never guessed recurrence."""
    quotes = [
        m.quote
        for m in candidate.interpretation.temporal_mentions
        if m.role is EventTemporalRole.RECURRING_WEEKDAY
    ]
    if not quotes:
        return None
    if len(quotes) != 1:
        raise EventRouteError("EVENT_WEEKDAY_AMBIGUOUS")
    matches = [
        _WEEKDAYS[t] for t in re.findall(r"\b[\wÀ-ÿ]+\b", quotes[0].casefold()) if t in _WEEKDAYS
    ]
    if len(matches) != 1:
        raise EventRouteError("EVENT_WEEKDAY_NOT_LITERAL")
    return matches[0]


def bound_occurrence(
    candidate: EventCandidate, temporal: TemporalInterpretation | None
) -> EventOccurrence:
    event = candidate.interpretation
    if temporal is None or temporal.source_text != event.source_text:
        raise EventRouteError("EVENT_TEMPORAL_MISSING")
    weekday = _source_weekday(candidate)
    if weekday is not None and not any(
        m.role is EventTemporalRole.RECURRENCE_RANGE for m in event.temporal_mentions
    ):
        raise EventRouteError("EVENT_RECURRENCE_RANGE_REQUIRED")
    trusted = []
    for mention in temporal.mentions:
        r = mention.resolution
        if not any(
            quote.quote in mention.temporal_text or mention.temporal_text in quote.quote
            for quote in event.temporal_mentions
            if quote.role is not EventTemporalRole.RECURRING_WEEKDAY
        ):
            raise EventRouteError("EVENT_TEMPORAL_SOURCE_MISMATCH")
        if r.kind is TemporalResolutionKind.DATE_RANGE and r.date_range is not None:
            trusted.append(("range", r.date_range.start, r.date_range.end_exclusive))
        elif r.kind in (TemporalResolutionKind.EXACT_DATE, TemporalResolutionKind.EXACT_DATETIME):
            value = r.exact_date or r.exact_datetime
            if value is None:
                raise EventRouteError("EVENT_TEMPORAL_UNRESOLVED")
            trusted.append(("exact", value, None))
        else:
            raise EventRouteError("EVENT_TEMPORAL_UNRESOLVED")
    if not trusted:
        raise EventRouteError("EVENT_TEMPORAL_MISSING")
    if len(trusted) == 1 and trusted[0][0] == "range":
        start, exclusive = trusted[0][1:]
        end = (date.fromisoformat(exclusive) - timedelta(days=1)).isoformat()
        return EventOccurrence(
            TemporalAnchor.from_value(start), TemporalAnchor.from_value(end), weekday
        )
    if any(kind == "range" for kind, _, _ in trusted):
        raise EventRouteError("EVENT_TEMPORAL_MULTIPLE_RANGES")
    if weekday is not None:
        raise EventRouteError("EVENT_RECURRENCE_NEEDS_VERIFIED_RANGE")
    values = tuple(dict.fromkeys(value for _, value, _ in trusted))
    if len(values) == 1:
        return EventOccurrence(TemporalAnchor.from_value(values[0]))
    exact_dates = {value[:10] for value in values}
    if len(exact_dates) == 1 and len([value for value in values if "T" in value]) == 1:
        value = next(value for value in values if "T" in value)
        return EventOccurrence(TemporalAnchor.from_value(value))
    # Ranged endpoints may only be paired when the model's role assertions
    # are bound to distinct source mentions and unambiguous Temporal values.
    if len(values) == 2 and len(temporal.mentions) == 2:
        role_for = {}
        for item in temporal.mentions:
            matches = [m.role for m in event.temporal_mentions if m.quote == item.temporal_text]
            if len(matches) != 1 or matches[0] not in (
                EventTemporalRole.START,
                EventTemporalRole.END,
            ):
                raise EventRouteError("EVENT_INTERVAL_ROLES_UNVERIFIED")
            role_for[matches[0]] = item.resolution.exact_date or item.resolution.exact_datetime
        if set(role_for) == {EventTemporalRole.START, EventTemporalRole.END}:
            return EventOccurrence(
                TemporalAnchor.from_value(role_for[EventTemporalRole.START]),
                TemporalAnchor.from_value(role_for[EventTemporalRole.END]),
            )
    raise EventRouteError("EVENT_TEMPORAL_AMBIGUOUS")


def current_exact_event(
    repository: VaultRepository, schema: dict[str, Any], reference: str
) -> tuple[str, int, str] | None:
    """Resolve only a unique exact word-bounded event-name mention, never similarity."""
    if not isinstance(reference, str) or not reference.strip():
        return None
    matches = []
    for path in repository.list_markdown_paths():
        raw = repository.read_text(path)
        note = parse_note(raw)
        validate_note(note, schema)
        if note.metadata.get("type") != "event" or note.metadata.get("deleted") is True:
            continue
        name = note.metadata["name"]
        if re.search(r"(?<!\w)" + re.escape(reference) + r"(?!\w)", name, re.IGNORECASE):
            matches.append(
                (
                    note.metadata["id"],
                    note.metadata["revision"],
                    hashlib.sha256(raw.encode()).hexdigest(),
                )
            )
    return matches[0] if len(matches) == 1 else None


def execute_event_candidate(
    *,
    candidate: EventCandidate,
    temporal: TemporalInterpretation | None,
    repository: VaultRepository,
    schema: dict[str, Any],
    mutations: EventMutationService,
    request_id: str,
    actor: Any,
    now: str,
    authenticated: bool,
    query_handler: Callable[[EventCandidate, TemporalInterpretation | None], NoteResultSnapshot]
    | None = None,
) -> ApplicationResult:
    """Execute only a validated Events route with a trusted principal + locator."""
    event = candidate.interpretation

    def attention(code: str) -> ApplicationResult:
        return ApplicationResult(
            request_id, ApplicationStatus.NEEDS_ATTENTION, (), (), planning_error=code
        )

    if not authenticated:
        return attention("EVENT_AUTH_REQUIRED")
    if event.operation is EventOperation.ABSTAIN:
        return attention("EVENT_ROUTING_ABSTAIN")
    if event.operation is EventOperation.QUERY:
        # No source-derived target or mutation authorization. Query results
        # become navigable note IDs only through current canonical readback.
        if query_handler is None:
            return attention("EVENT_QUERY_NOT_CONNECTED")
        try:
            snapshot = query_handler(candidate, temporal)
        except (EventRouteError, ValueError):
            return attention("EVENT_QUERY_UNRESOLVED")
        if not isinstance(snapshot, NoteResultSnapshot):
            return attention("EVENT_QUERY_UNVERIFIED")
        return ApplicationResult(
            request_id,
            ApplicationStatus.COMPLETED,
            (),
            (),
            presentation_intent="show_notes",
            note_result_snapshot=snapshot.to_payload(),
            execution_flow={"events": {"operation": "query", "match_count": snapshot.total}},
        )
    try:
        if event.operation is EventOperation.CREATE:
            occurrence = bound_occurrence(candidate, temporal)
            receipt = mutations.create(
                name=candidate.title_quote or "",
                source_text=event.source_text,
                occurrence=occurrence,
                request_id=request_id,
                actor=actor,
                now=now,
            )
            note_id = receipt.target_id
            history = receipt.history
            operation = "created"
        elif event.operation in (EventOperation.UPDATE, EventOperation.CANCEL):
            target = current_exact_event(repository, schema, event.event_reference or "")
            if target is None:
                return attention("EVENT_TARGET_AMBIGUOUS_OR_MISSING")
            occurrence = (
                bound_occurrence(candidate, temporal)
                if event.operation is EventOperation.UPDATE
                else None
            )
            receipt = mutations.change(
                note_id=target[0],
                expected_revision=target[1],
                expected_source_hash=target[2],
                request_id=request_id,
                actor=actor,
                now=now,
                operation="reschedule" if occurrence is not None else "cancel",
                occurrence=occurrence,
            )
            note_id = receipt.target_id
            history = receipt.history
            operation = "rescheduled" if occurrence is not None else "cancelled"
        else:
            return attention("EVENT_OPERATION_UNSUPPORTED")
    except EventMutationError as error:
        if error.physical_write:
            return ApplicationResult(
                request_id,
                ApplicationStatus.PARTIAL,
                (),
                (error.target_id,) if error.target_id else (),
                planning_error="EVENT_POSTWRITE_UNVERIFIED",
            )
        return attention("EVENT_TEMPORAL_OR_WRITE_REJECTED")
    except (EventRouteError, ValueError):
        return attention("EVENT_TEMPORAL_OR_WRITE_REJECTED")
    return ApplicationResult(
        request_id,
        ApplicationStatus.COMPLETED,
        (
            ActionResult(
                0,
                "write",
                ActionStatus.COMPLETED,
                unit_results=(UnitResult(0, UnitStatus.SUCCEEDED, operation, note_id),),
            ),
        ),
        (note_id,),
        history=history,
        execution_flow={"events": {"operation": operation, "affected_count": 1}},
    )
