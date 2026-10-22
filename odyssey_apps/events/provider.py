"""E5 real-model Events interpreter: closed intent plus one exact event title quote.

Provider output has no note ID, actor, path or write authorization.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from .interpretation import EventInterpretation, EventInterpretationError, EventOperation
from .proposal import validate_event_proposal

EVENTS_PROMPT = """Classify ONLY the current exact source as an Events-calendar operation.
An Event is a scheduled occurrence (appointment, meeting, outing, school activity,
performance, camp, trip, bounded recurring activity), NOT a task, reminder,
historical memory, or any dated statement. For mixed Tasks+Events in the SAME
route ABSTAIN: Router must split them first. For ambiguous target, ABSTAIN.
For CREATE, title_quote must quote an exact, unique, nonempty noun phrase that
names the EVENT within source_text (not an invented paraphrase), preferably
excluding dates. UPDATE/CANCEL require event_reference: the exact unique source
phrase referring to the event, without claiming any repository identity.
For QUERY, title_quote=null and event_reference=null. query_quote may quote
one exact unique noun/name qualifier of the intended events (e.g. 'colegio'),
or null for all events; never invent search filters. For other operations
query_quote=null. ABSTAIN: all mentions empty and all quote fields null.
Temporal mentions quote EXACT unique, full-word nonoverlapping substrings.
Roles DATE, START, END, RECURRING_WEEKDAY, RECURRENCE_RANGE.
Never resolve dates, time zones, participants, or note IDs. Return strict JSON."""

ROLES = ["DATE", "START", "END", "RECURRING_WEEKDAY", "RECURRENCE_RANGE"]
PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["ABSTAIN", "CREATE", "UPDATE", "CANCEL", "QUERY"]},
        "temporal_mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "role": {"type": "string", "enum": ROLES},
                },
                "required": ["quote", "role"],
                "additionalProperties": False,
            },
        },
        "event_reference": {"type": ["string", "null"]},
        "title_quote": {"type": ["string", "null"]},
        "query_quote": {"type": ["string", "null"]},
    },
    "required": ["operation", "temporal_mentions", "event_reference", "title_quote", "query_quote"],
    "additionalProperties": False,
}


def _exact_unique_phrase(source: str, quote: str) -> bool:
    if (
        not isinstance(quote, str)
        or not quote.strip()
        or quote != quote.strip()
        or len(quote) > 200
    ):
        return False
    hits = tuple(re.finditer(re.escape(quote), source))
    return len(hits) == 1 and not (
        (hits[0].start() and source[hits[0].start() - 1].isalnum())
        or (hits[0].end() < len(source) and source[hits[0].end()].isalnum())
    )


@dataclass(frozen=True, slots=True)
class EventCandidate:
    interpretation: EventInterpretation
    title_quote: str | None
    query_quote: str | None = None


def validate_event_candidate(source: str, result: object) -> EventCandidate:
    if not isinstance(result, dict) or set(result) != {
        "operation",
        "temporal_mentions",
        "event_reference",
        "title_quote",
        "query_quote",
    }:
        raise EventInterpretationError("Event provider result has unexpected fields")
    title = result["title_quote"]
    query = result["query_quote"]
    interpretation = validate_event_proposal(
        source, {key: result[key] for key in ("operation", "temporal_mentions", "event_reference")}
    )
    if interpretation.operation is EventOperation.CREATE:
        if not _exact_unique_phrase(source, title):
            raise EventInterpretationError("Event title must be an exact unique source phrase")
    elif title is not None:
        raise EventInterpretationError("Only Event CREATE may name a proposed title")
    if interpretation.operation is EventOperation.QUERY:
        if query is not None and not _exact_unique_phrase(source, query):
            raise EventInterpretationError("Event query must quote one exact unique filter")
    elif query is not None:
        raise EventInterpretationError("Only Event QUERY may supply a query filter")
    if (
        interpretation.operation in (EventOperation.CREATE, EventOperation.UPDATE)
        and not interpretation.temporal_mentions
    ):
        raise EventInterpretationError(
            "Event creation/rescheduling requires temporal source evidence"
        )
    return EventCandidate(interpretation, title, query)


class OpenAIEventInterpreter:
    model = "gpt-6-luna"
    reasoning_effort = "low"
    last_usage: object | None = None

    def __init__(self, client: Any) -> None:
        self.client = client

    @classmethod
    def from_environment(cls) -> OpenAIEventInterpreter:
        if not os.environ.get("OPENAI_API_KEY"):
            raise EventInterpretationError("Events provider credentials unavailable")
        from openai import OpenAI

        return cls(OpenAI(max_retries=0, timeout=48.0))

    def interpret(self, source: str) -> EventCandidate:
        if not isinstance(source, str) or not source.strip() or len(source) > 4096:
            raise EventInterpretationError("Event source is invalid")
        response = self.client.responses.create(
            model=self.model,
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=1600,
            store=False,
            input=[
                {"role": "system", "content": EVENTS_PROMPT},
                {"role": "user", "content": source},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "e5_event_intent_v2",
                    "strict": True,
                    "schema": PROPOSAL_SCHEMA,
                }
            },
        )
        self.last_usage = getattr(response, "usage", None)
        try:
            return validate_event_candidate(source, json.loads(response.output_text))
        except (ValueError, TypeError, KeyError) as exc:
            raise EventInterpretationError("Event provider failed source validation") from exc
