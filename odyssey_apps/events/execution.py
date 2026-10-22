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


def bound_occurrence(
    candidate: EventCandidate, temporal: TemporalInterpretation | None
) -> EventOccurrence:
    event = candidate.interpretation
    if temporal is None or temporal.source_text != event.source_text:
        raise EventRouteError("EVENT_TEMPORAL_MISSING")
    if any(
        mention.role in (EventTemporalRole.RECURRING_WEEKDAY, EventTemporalRole.RECURRENCE_RANGE)
        for mention in event.temporal_mentions
    ):
        # Shared Temporal currently has no trusted weekday enumeration;
        # do not parse language-specific words or manufacture recurrence.
        raise EventRouteError("EVENT_RECURRENCE_NEEDS_TEMPORAL_CONTRACT")
    trusted = []
    for mention in temporal.mentions:
        r = mention.resolution
        if not any(
            quote.quote in mention.temporal_text or mention.temporal_text in quote.quote
            for quote in event.temporal_mentions
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
        return EventOccurrence(TemporalAnchor.from_value(start), TemporalAnchor.from_value(end))
    if any(kind == "range" for kind, _, _ in trusted):
        raise EventRouteError("EVENT_TEMPORAL_MULTIPLE_RANGES")
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
    query_handler: Callable[[str], tuple[str, ...]] | None = None,
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
        matches = query_handler(event.source_text)
        return ApplicationResult(
            request_id,
            ApplicationStatus.COMPLETED,
            (),
            (),
            execution_flow={"events": {"operation": "query", "match_count": len(matches)}},
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
