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
            # A date-only Temporal part pointing to the SAME calendar_day
            # destination repeats the verified date already represented by
            # that Note. Remove only that redundant typed reference, never
            # an exact event clock or a reference to a different day.
            if operation.target.note_type == CALENDAR_DAY_TYPE:
                parts = [
                    part
                    for part in parts
                    if not (
                        isinstance(part, TemporalReferencePart)
                        and part.anchor.display_time is None
                        and part.anchor.date == operation.target.description
                        and part.text in original_source
                    )
                ]
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
            # A routed source can start with an isolated additive coordinator
            # from its original sentence, such as "y hoy ...". On a durable
            # canonical entity history it is not a standalone fact clause.
            # Only an EXACT SOURCE-MATCHED connector and a fully composed
            # one-actor/one-day source-backed fact permit grammatical display
            # cleanup. We retain the SAME event, Note target, recipient and
            # Temporal evidence, moving the date link to a trailing adjunct.
            # No negative/adversative connectors, unverified references,
            # time-bearing instants or non-canonical Day facts are rewritten.
            if (
                operation.target.note_type != CALENDAR_DAY_TYPE
                and len(parts) == 5
                and isinstance(parts[0], LiteralPart)
                and parts[0].text.strip().casefold() in {"y", "and", "et", "e", "und"}
                and original_source.lstrip().startswith(parts[0].text.strip() + " ")
                and isinstance(parts[1], TemporalReferencePart)
                and parts[1].anchor.display_time is None
                and parts[1].text in original_source
                and isinstance(parts[2], LiteralPart)
                and parts[2].text.startswith(" ")
                and parts[2].text.lstrip()
                and parts[2].text.lstrip()[0].islower()
                and isinstance(parts[3], IdentityPart)
                and isinstance(parts[4], LiteralPart)
                and parts[4].text.strip() in {".", "!", "?"}
            ):
                spoken = parts[2].text.lstrip()
                parts = [
                    LiteralPart(spoken[:1].upper() + spoken[1:]),
                    parts[3],
                    LiteralPart(" "),
                    parts[1],
                    parts[4],
                ]
            # Verified same-Day clock between two literals moves to the
            # canonical HH:MM prefix. Remove only surplus boundary spacing.
            for pos in range(1, len(parts) - 1):
                clock = parts[pos]
                before = parts[pos - 1]
                after = parts[pos + 1]
                if (
                    isinstance(clock, TemporalReferencePart)
                    and clock.anchor.display_time is not None
                    and operation.target.note_type == CALENDAR_DAY_TYPE
                    and operation.target.description == clock.anchor.date
                    and clock.text in original_source
                    and isinstance(before, LiteralPart)
                    and isinstance(after, LiteralPart)
                    and before.text.endswith(" ")
                    and after.text.startswith(" ")
                    # A short leading clock connector such as "A las " is
                    # NOT an event predicate. Preserve its original literal
                    # for the independent source reviewer, even when clumsy.
                    # Only normalize whitespace after a complete preceding
                    # clause fragment with multiple source terms.
                    and len(before.text.split()) >= 3
                ):
                    parts[pos - 1] = LiteralPart(before.text[:-1])
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
