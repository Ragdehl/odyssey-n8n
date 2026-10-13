"""Normalize only source-duplicated clock wording in hybrid Day fact parts.

Core's Day renderer already displays a verified datetime clock. A model may
also put the *prefix of that same source clock phrase* into the preceding
literal. Remove only demonstrably duplicated source bytes. Never infer, move,
or rewrite a semantic event, identity, time value or unrelated wording.
"""

from __future__ import annotations

from dataclasses import replace

from .semantic_write import (
    IdentityPart,
    LiteralPart,
    SemanticFact,
    SemanticWriteIntent,
    TemporalReferencePart,
)
from .temporal import CALENDAR_DAY_TYPE


def normalize_hybrid_day_clock_prefix(
    intent: SemanticWriteIntent, original_source: str
) -> SemanticWriteIntent:
    if not isinstance(intent, SemanticWriteIntent) or not isinstance(original_source, str):
        raise ValueError("Validated semantic write intent and exact source required")
    operations = []
    for operation in intent.operations:
        facts = []
        for fact in operation.facts:
            parts = list(fact.parts)
            clocks = [
                (idx, part)
                for idx, part in enumerate(parts)
                if isinstance(part, TemporalReferencePart)
                and operation.target.note_type == CALENDAR_DAY_TYPE
                and operation.target.description == part.anchor.date
                and part.anchor.display_time is not None
            ]
            if len(clocks) == 1:
                idx, clock = clocks[0]
                if (
                    idx > 0
                    and isinstance(parts[idx - 1], LiteralPart)
                    and clock.text in original_source
                ):
                    before = parts[idx - 1]
                    # Only an exact word-boundary prefix of the VERIFIED clock
                    # phrase may be duplicated. An unrelated trailing word
                    # cannot be dropped, regardless of model confidence.
                    prefixes = [
                        clock.text[:size]
                        for size in range(3, len(clock.text))
                        if clock.text[size - 1].isspace()
                        and before.text.endswith(clock.text[:size])
                    ]
                    # In a multi-event Day capture the clock is already
                    # rendered as HH:MM on EACH fact. Repeating the entire
                    # exact original time phrase in a literal is redundant.
                    if len(operation.facts) > 1 and before.text.endswith(clock.text):
                        prefixes.append(clock.text)
                    if prefixes:
                        overlap = max(prefixes, key=len)
                        cleaned = before.text[: -len(overlap)].rstrip()
                        if idx == len(parts) - 1 and cleaned and cleaned[-1] not in ".!?":
                            cleaned += "."
                        parts[idx - 1] = LiteralPart(cleaned)
                # A same-Day clock is rendered before the fact, not inside
                # the trailing literal. Omit meaningless trailing whitespace
                # and finish the sentence if the model ended on the clock.
                if (
                    idx == len(parts) - 1
                    and (
                        len(operation.facts) > 1
                        or any(isinstance(p, IdentityPart) for p in fact.parts)
                    )
                    and clock.text in original_source
                    and isinstance(parts[idx - 1], LiteralPart)
                ):
                    preceding = parts[idx - 1]
                    cleaned = preceding.text.rstrip()
                    if cleaned != preceding.text and cleaned:
                        if cleaned[-1] not in ".!?":
                            cleaned += "."
                        parts[idx - 1] = LiteralPart(cleaned)
            # A date-only reference rendered on another Note becomes a
            # calendar link. Keep the following independent literal legible,
            # without changing the target date, fact or identity.
            for pos in range(len(parts) - 1):
                link = parts[pos]
                after = parts[pos + 1]
                if (
                    isinstance(link, TemporalReferencePart)
                    and link.anchor.display_time is None
                    and not (
                        operation.target.note_type == CALENDAR_DAY_TYPE
                        and operation.target.description == link.anchor.date
                    )
                    and isinstance(after, LiteralPart)
                    and after.text
                    and after.text[0].isalnum()
                ):
                    parts[pos + 1] = LiteralPart(" " + after.text)
            facts.append(SemanticFact(tuple(parts)))
        operations.append(replace(operation, facts=tuple(facts)))
    return SemanticWriteIntent(tuple(operations))
