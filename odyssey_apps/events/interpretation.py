"""E5 Events preparatory domain semantics: no authority to mutate knowledge.

Events owns occurrence lifecycle roles only. Temporal resolves dates/times;
Core resolves identity, references and persistence; Calendar presents days.
Not wired to the runtime or schema until the E5 integration is reviewed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation


class EventInterpretationError(ValueError):
    """Events evidence is ambiguous, ungrounded or out of scope."""


def _unique_source_span(source: str, quote: str) -> tuple[int, int] | None:
    """Reject partial-word hits, missing source quotes and repeated occurrences."""
    start = -1
    for found in re.finditer(re.escape(quote), source):
        lo, hi = found.span()
        if (lo and (source[lo - 1].isalnum() or source[lo - 1] == "_")) or (
            hi < len(source) and (source[hi].isalnum() or source[hi] == "_")
        ):
            continue
        if start != -1:
            return None
        start = lo
    return (start, start + len(quote)) if start >= 0 else None


class EventOperation(StrEnum):
    ABSTAIN = "ABSTAIN"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    CANCEL = "CANCEL"
    QUERY = "QUERY"


class EventTemporalRole(StrEnum):
    DATE = "DATE"
    START = "START"
    END = "END"
    ORIGINAL_DATE = "ORIGINAL_DATE"
    NEW_DATE = "NEW_DATE"
    RECURRING_WEEKDAY = "RECURRING_WEEKDAY"
    RECURRENCE_RANGE = "RECURRENCE_RANGE"


@dataclass(frozen=True, slots=True)
class EventTemporalMention:
    """Exact source quote, never a guessed datetime or time zone."""

    quote: str
    role: EventTemporalRole

    def __post_init__(self) -> None:
        if not isinstance(self.quote, str) or not self.quote.strip() or len(self.quote) > 240:
            raise EventInterpretationError("Temporal mention needs a bounded exact quote")
        if not isinstance(self.role, EventTemporalRole):
            raise EventInterpretationError("Unknown Events temporal role")


@dataclass(frozen=True, slots=True)
class EventInterpretation:
    """Pure Events lifecycle interpretation, never a Core write plan."""

    source_text: str
    operation: EventOperation
    temporal_mentions: tuple[EventTemporalMention, ...] = ()
    event_reference: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_text, str)
            or not self.source_text.strip()
            or len(self.source_text) > 4096
        ):
            raise EventInterpretationError("Original Events source is missing or too long")
        if not isinstance(self.operation, EventOperation):
            raise EventInterpretationError("Unsupported Events lifecycle operation")
        if (
            not isinstance(self.temporal_mentions, tuple)
            or len(self.temporal_mentions) > 16
            or any(not isinstance(m, EventTemporalMention) for m in self.temporal_mentions)
        ):
            raise EventInterpretationError("Events temporal mentions are invalid")
        spans = [
            _unique_source_span(self.source_text, mention.quote)
            for mention in self.temporal_mentions
        ]
        if any(span is None for span in spans) or any(
            lo < other_hi and other_lo < hi
            for index, (lo, hi) in enumerate(spans)
            for other_lo, other_hi in spans[index + 1 :]
        ):
            raise EventInterpretationError("Temporal mention is duplicated or not source-bound")
        reference = self.event_reference
        if reference is not None and (
            not isinstance(reference, str)
            or not reference.strip()
            or len(reference) > 240
            or _unique_source_span(self.source_text, reference) is None
        ):
            raise EventInterpretationError("Event reference must occur exactly once in source")
        if self.operation is EventOperation.ABSTAIN and (self.temporal_mentions or reference):
            raise EventInterpretationError("Event abstention cannot convey mutation evidence")
        if self.operation is EventOperation.CREATE and reference is not None:
            raise EventInterpretationError("Event CREATE cannot assert an existing identity")
        if self.operation in (EventOperation.UPDATE, EventOperation.CANCEL) and reference is None:
            raise EventInterpretationError("Event mutation needs an unresolved source referent")

    def as_domain_interpretation(self) -> DomainInterpretation:
        """Delegate generic semantics to Core without Note IDs or write authority."""
        evidence = tuple(
            DomainEvidence("event.temporal_role", mention.quote, mention.role.value)
            for mention in self.temporal_mentions
        )
        if self.event_reference is not None:
            evidence += (
                DomainEvidence("event.reference", self.event_reference, self.event_reference),
            )
        return DomainInterpretation("events", self.source_text, self.operation.value, evidence)
