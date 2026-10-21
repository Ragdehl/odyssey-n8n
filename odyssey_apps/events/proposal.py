"""Strict, provider-agnostic Events proposal boundary; never gives write authority.

The input is an untrusted model candidate (including offline recorded replies).
Only Events lifecycle and verbatim source mentions may enter DomainInterpretation.
Core still resolves all canonical targets; Temporal resolves real dates; a model
proposal does not attest factual correctness or authorize a mutation.
"""

from __future__ import annotations

from .interpretation import (
    EventInterpretation,
    EventInterpretationError,
    EventOperation,
    EventTemporalMention,
    EventTemporalRole,
)

_PROPOSAL_KEYS = frozenset({"operation", "temporal_mentions", "event_reference"})
_MENTION_KEYS = frozenset({"quote", "role"})


def validate_event_proposal(original_source: str, proposal: object) -> EventInterpretation:
    """Check an untrusted interpreter reply against an exact source and schema.

    Deliberately refuses convenient extra fields such as note ID, target,
    timezone, concrete date, person assignment, task/reminder instructions,
    or text rewritten by a provider. This boundary is not an E2E GPT test.
    """
    if not isinstance(proposal, dict) or set(proposal) != _PROPOSAL_KEYS:
        raise EventInterpretationError("Untrusted Events proposal has unknown or missing fields")
    operation = proposal["operation"]
    if not isinstance(operation, str) or operation not in EventOperation._value2member_map_:
        raise EventInterpretationError("Unrecognized Events proposal operation")
    mentions = proposal["temporal_mentions"]
    if not isinstance(mentions, list) or len(mentions) > 16:
        raise EventInterpretationError("Events proposal temporal mentions must be a bounded list")
    validated = []
    for row in mentions:
        if not isinstance(row, dict) or set(row) != _MENTION_KEYS:
            raise EventInterpretationError("Events temporal proposal contains unapproved fields")
        role = row["role"]
        quote = row["quote"]
        if not isinstance(role, str) or role not in EventTemporalRole._value2member_map_:
            raise EventInterpretationError("Events temporal role was not approved")
        validated.append(EventTemporalMention(quote, EventTemporalRole(role)))
    reference = proposal["event_reference"]
    if reference is not None and not isinstance(reference, str):
        raise EventInterpretationError("Events reference must be a literal source quote")
    return EventInterpretation(
        source_text=original_source,
        operation=EventOperation(operation),
        temporal_mentions=tuple(validated),
        event_reference=reference,
    )
