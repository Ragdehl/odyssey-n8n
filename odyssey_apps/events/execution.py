"""Bounded E5 route executor: source-bound Events, shared Temporal and E3 receipts.

A route passed to this adapter must be an authorized Events app destination.
Without an authenticated principal it never calls the mutation service.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
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


def _source_has_clock_qualifier(text: str) -> bool:
    """Does a source span demand independent verification of clock time?

    Exact date alone cannot authorize cancellation if its own source quote
    includes a wall clock (numeric, textual or daypart). Conservative refusals
    are safer than silently cancelling another occurrence on the same date.
    """
    return (
        re.search(
            r"\b(?:[01]?\d|2[0-3])\s*(?:[ap]\s*\.?\s*m\.?|"
            r"h(?:eures?)?|heures?|hrs?|hours?|o'clock)\b"
            r"|\b(?:[01]?\d|2[0-3])\s*(?:h|:)\s*[0-5]\d\b"
            r"|\b(?:am|pm|noon|midnight|midi|minuit|"
            r"morning|afternoon|evening|tonight|matin|soir|après-midi)\b"
            r"|\ba\s+las\b|\b(?:por|de)\s+la\s+(?:mañana|tarde|noche)\b"
            r"|\b(?:at|à)\s+(?:one|two|three|four|five|six|seven|"
            r"eight|nine|ten|eleven|twelve|\d{1,2})\b",
            text.casefold(),
        )
        is not None
    )


# A DATE-only resolution must account for its *whole* original source quote.
# Enumerating clock spellings is not enough ("o'clock" vs "o’clock").
# Unknown words fail closed; this grammar is intentionally limited to
# ES/FR/EN date vocabulary and numeric date forms.
_DATE_ONLY_WORDS = frozenset(_WEEKDAYS) | frozenset(
    """
    january february march april may june july august september october november december
    enero febrero marzo abril mayo junio julio agosto septiembre setiembre octubre noviembre diciembre
    janvier février fevrier mars avril mai juin juillet août aout septembre octobre novembre décembre decembre
    on the of in at from this next last coming following today tomorrow yesterday
    el la los las del de al a en para por este esta próximo proximo próxima proxima siguiente
    hoy mañana ayer
    le du des au aux de la d à ce cet cette prochain prochaine suivant suivante
    demain hier aujourd hui
    week weeks semaine semaines semana semanas
    """.split()
)


def _source_is_unqualified_date(quote: str) -> bool:
    """Do not trust DATE-only output from a quote with unknown semantic tokens."""
    words = re.findall(r"[^\W\d_]+|\d+", quote.casefold(), flags=re.UNICODE)
    if not words or any(word not in _DATE_ONLY_WORDS and not word.isdecimal() for word in words):
        return False
    # A single unqualified number beside a weekday may be a time ("Monday 5").
    # Allow numbers only with source evidence of a month/year or a date separator.
    if any(word.isdecimal() for word in words) and not (
        any(
            word
            in _DATE_ONLY_WORDS.intersection(
                {
                    "january",
                    "february",
                    "march",
                    "april",
                    "may",
                    "june",
                    "july",
                    "august",
                    "september",
                    "october",
                    "november",
                    "december",
                    "enero",
                    "febrero",
                    "marzo",
                    "abril",
                    "mayo",
                    "junio",
                    "julio",
                    "agosto",
                    "septiembre",
                    "setiembre",
                    "octubre",
                    "noviembre",
                    "diciembre",
                    "janvier",
                    "février",
                    "fevrier",
                    "mars",
                    "avril",
                    "mai",
                    "juin",
                    "juillet",
                    "août",
                    "aout",
                    "décembre",
                    "decembre",
                }
            )
            for word in words
        )
        or re.search(r"\b\d{4}\b", quote)
        or re.search(r"\b\d{1,2}[-/.]\d{1,2}\b", quote)
    ):
        return False
    return True


def _exact_anchor_for_quote(
    candidate: EventCandidate,
    temporal: TemporalInterpretation | None,
    role: EventTemporalRole,
) -> TemporalAnchor:
    """Resolve exactly one model-quoted source span with shared E2 Temporal.

    Source/role quotes are not dates. Never interpret missing source evidence
    from a model's assertion or another Event's canonical metadata.
    """
    source = candidate.interpretation.source_text
    if temporal is None or temporal.source_text != source:
        raise EventRouteError("EVENT_TARGET_TEMPORAL_REQUIRED")
    quoted = [
        mention.quote
        for mention in candidate.interpretation.temporal_mentions
        if mention.role is role
    ]
    if len(quoted) != 1:
        raise EventRouteError("EVENT_TARGET_TEMPORAL_ROLE_AMBIGUOUS")

    def same_source_span(bound: str, resolved: str) -> bool:
        if bound == resolved:
            return True
        longer, shorter = sorted((bound, resolved), key=len, reverse=True)
        # Only allow an omitted LEADING weekday/article before a fully
        # explicit dated source span. Relative modifiers ('next Monday')
        # alter identity and must never be silently dropped.
        if source.count(shorter) != 1 or not re.search(r"\b\d{4}\b", shorter):
            return False
        if re.search(r"\b\d{1,2}\b", shorter) is None or not longer.endswith(shorter):
            return False
        prefix = longer[: -len(shorter)].strip().casefold()
        return prefix in {
            "el",
            "le",
            "on",
            "lunes",
            "martes",
            "miércoles",
            "miercoles",
            "jueves",
            "viernes",
            "sábado",
            "sabado",
            "domingo",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "lundi",
            "mardi",
            "mercredi",
            "jeudi",
            "vendredi",
            "samedi",
            "dimanche",
        }

    matches = [m for m in temporal.mentions if same_source_span(quoted[0], m.temporal_text)]
    if len(matches) != 1:
        raise EventRouteError("EVENT_TARGET_TEMPORAL_SOURCE_MISMATCH")
    resolution = matches[0].resolution
    if resolution.kind not in (
        TemporalResolutionKind.EXACT_DATE,
        TemporalResolutionKind.EXACT_DATETIME,
    ):
        raise EventRouteError("EVENT_TARGET_TEMPORAL_NOT_EXACT")
    value = resolution.exact_date or resolution.exact_datetime
    if value is None:
        raise EventRouteError("EVENT_TARGET_TEMPORAL_UNRESOLVED")
    anchor = TemporalAnchor.from_value(value)
    if anchor.time is None and (
        _source_has_clock_qualifier(quoted[0]) or not _source_is_unqualified_date(quoted[0])
    ):
        raise EventRouteError("EVENT_TARGET_CLOCK_UNVERIFIED")
    return anchor


def _reference_has_no_temporal_qualifier(reference: str | None) -> bool:
    """Fail closed when the Event name quote hides a relative day or clock."""
    if not isinstance(reference, str) or not reference.strip():
        return False
    if _source_has_clock_qualifier(reference):
        return False
    return (
        re.search(
            r"\b(?:next|last|today|tomorrow|yesterday|this|monday|tuesday|"
            r"wednesday|thursday|friday|saturday|sunday|"
            r"lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|"
            r"mañana|hoy|ayer|siguiente|próximo|proximo|próxima|proxima|"
            r"lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|"
            r"demain|aujourd'hui|hier|prochain|prochaine|"
            r"day|days|week|weeks|month|months|year|years|"
            r"día|dia|días|dias|semana|semanas|mes|meses|año|años|"
            r"jour|jours|semaine|semaines|mois|année|annee|années|annees|"
            r"january|february|march|april|may|june|july|august|september|october|"
            r"november|december|enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            r"septiembre|octubre|noviembre|diciembre|janvier|février|fevrier|mars|"
            r"avril|mai|juin|juillet|août|aout|décembre|decembre|at|on)\b"
            r"|\b\d{4}\b|\b\d{1,2}[-/.]\d{1,2}\b"
            r"|\b\d{1,2}(?:am|pm|st|nd|rd|th|h)\b"
            # Prevent a clock hidden inside the Event title from bypassing
            # Temporal verification (5 pm, 5 p.m., 17 h, 17h30, 17:30).
            r"|\b(?:[01]?\d|2[0-3])\s*(?:[ap]\s*\.?\s*m\.?|h(?:eures?)?|heures?|hrs?|hours?)\b"
            r"|\b(?:[01]?\d|2[0-3])\s*(?:h|:)\s*[0-5]\d\b"
            r"|\b(?:am|pm|noon|midnight|morning|afternoon|evening|tonight)\b"
            r"|\ba\s+las\b",
            reference.casefold(),
        )
        is None
    )


def _cancel_source_has_full_coverage(candidate: EventCandidate) -> bool:
    """Only an exact source-wide partition permits a dated Event mutation.

    All content must be accounted for by the explicit CANCEL command, the
    unique Event reference, one full date/time quote and harmless connectors.
    A dropped word like 'next' or an unreviewed time can never disappear
    from the evidence by two providers agreeing on a shorter quote.
    """
    event = candidate.interpretation
    source = event.source_text
    reference = event.event_reference
    qualified = event.temporal_mentions
    if (
        not _reference_has_no_temporal_qualifier(reference)
        or len(qualified) != 1
        or qualified[0].role not in (EventTemporalRole.DATE, EventTemporalRole.START)
    ):
        return False
    assert reference is not None
    event_hits = list(re.finditer(re.escape(reference), source))
    date_hits = list(re.finditer(re.escape(qualified[0].quote), source))
    if len(event_hits) != 1 or len(date_hits) != 1:
        return False
    event_hit, date_hit = event_hits[0], date_hits[0]
    if event_hit.end() >= date_hit.start():
        return False
    punctuation = " \\t.,;:!?¿¡"
    prefix = " ".join(source[: event_hit.start()].strip(punctuation).casefold().split())
    between = " ".join(
        source[event_hit.end() : date_hit.start()].strip(punctuation).casefold().split()
    )
    suffix = source[date_hit.end() :].strip(punctuation)
    return (
        not suffix
        and prefix
        in {
            "cancela",
            "cancela el",
            "cancela la",
            "cancelar",
            "por favor cancela",
            "por favor cancela el",
            "por favor cancela la",
            "cancel",
            "cancel the",
            "please cancel",
            "please cancel the",
            "annule",
            "annule le",
            "annule la",
            "annuler",
            "supprime",
            "supprime le",
            "supprime la",
            "elimina",
            "elimina el",
            "elimina la",
            "borra",
            "borra el",
            "borra la",
        }
        and between
        in {
            "",
            "el",
            "del",
            "de",
            "la",
            "de la",
            "de los",
            "para",
            "para el",
            "a",
            "al",
            "en",
            "a las",
            "on",
            "the",
            "at",
            "for",
            "le",
            "du",
            "au",
            "à",
            "pour",
        }
    )


def _target_identity_anchor(
    candidate: EventCandidate, temporal: TemporalInterpretation | None
) -> TemporalAnchor | None:
    """Date/time qualifiers of an existing target must be checked BEFORE E3."""
    event = candidate.interpretation
    if event.operation is EventOperation.UPDATE:
        roles = {m.role for m in event.temporal_mentions}
        return (
            _exact_anchor_for_quote(candidate, temporal, EventTemporalRole.ORIGINAL_DATE)
            if EventTemporalRole.ORIGINAL_DATE in roles
            else None
        )
    if event.operation is not EventOperation.CANCEL:
        return None
    if not event.temporal_mentions:
        raise EventRouteError("EVENT_CANCEL_DATE_EVIDENCE_REQUIRED")
    if not _cancel_source_has_full_coverage(candidate):
        raise EventRouteError("EVENT_CANCEL_SOURCE_COVERAGE_UNVERIFIED")
    if len(temporal.mentions if temporal is not None else ()) != 1:
        raise EventRouteError("EVENT_CANCEL_TEMPORAL_INCOMPLETE")
    role = event.temporal_mentions[0].role
    if role not in (EventTemporalRole.DATE, EventTemporalRole.START):
        raise EventRouteError("EVENT_CANCEL_QUALIFIER_UNSUPPORTED")
    return _exact_anchor_for_quote(candidate, temporal, role)


def _matches_canonical_target(metadata: dict[str, Any], anchor: TemporalAnchor | None) -> bool:
    if anchor is None:
        return True
    # A single dated occurrence cannot safely authorize cancellation of a
    # whole weekly series or multi-day Event. Undated explicit series-level
    # cancellation still uses the existing exact-name + E3 CAS path.
    if metadata.get("recurrence_weekday") is not None:
        return False
    if metadata.get("end_date", metadata.get("start_date")) != metadata.get("start_date"):
        return False
    if anchor.date != metadata.get("start_date"):
        return False
    if anchor.time is not None:
        recorded = metadata.get("start_at")
        if not isinstance(recorded, str):
            return False
        return datetime.fromisoformat(anchor.value) == datetime.fromisoformat(recorded)
    return True


def bound_occurrence(
    candidate: EventCandidate, temporal: TemporalInterpretation | None
) -> EventOccurrence:
    event = candidate.interpretation
    if temporal is None or temporal.source_text != event.source_text:
        raise EventRouteError("EVENT_TEMPORAL_MISSING")
    weekday = _source_weekday(candidate)
    if event.operation is EventOperation.UPDATE and any(
        item.role in (EventTemporalRole.START, EventTemporalRole.END)
        for item in event.temporal_mentions
    ):
        # Those roles describe a CREATE interval, never "old -> new" dates.
        # Reject even when shared Temporal condenses both quotes into a
        # single DATE_RANGE; otherwise an UPDATE can silently span days.
        raise EventRouteError("EVENT_UPDATE_INTERVAL_ROLES_UNSUPPORTED")
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
    if event.operation is EventOperation.UPDATE and any(
        mention.role in (EventTemporalRole.ORIGINAL_DATE, EventTemporalRole.NEW_DATE)
        for mention in event.temporal_mentions
    ):
        roles = tuple(m.role for m in event.temporal_mentions)
        if (
            roles.count(EventTemporalRole.NEW_DATE) != 1
            or roles.count(EventTemporalRole.ORIGINAL_DATE) > 1
            or len(temporal.mentions) != len(roles)
            or any(
                role not in (EventTemporalRole.ORIGINAL_DATE, EventTemporalRole.NEW_DATE)
                for role in roles
            )
        ):
            raise EventRouteError("EVENT_UPDATE_OLD_NEW_ROLES_INCOMPLETE")
        if EventTemporalRole.ORIGINAL_DATE in roles:
            _exact_anchor_for_quote(candidate, temporal, EventTemporalRole.ORIGINAL_DATE)
        destination = _exact_anchor_for_quote(candidate, temporal, EventTemporalRole.NEW_DATE)
        return EventOccurrence(destination)
    if event.operation is EventOperation.UPDATE and any(kind == "range" for kind, _, _ in trusted):
        # "move from Tuesday to Thursday" and "move to a multi-day range"
        # cannot be distinguished safely by range evidence alone.
        raise EventRouteError("EVENT_UPDATE_RANGE_NEEDS_EXPLICIT_DESTINATION")
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
    if event.operation is EventOperation.UPDATE:
        # A START+END pair can describe one multi-day CREATE, but cannot
        # silently become an UPDATE "from [old] to [new]" interval.
        # Such UPDATEs require explicit OLD_DATE / NEW_DATE target semantics.
        raise EventRouteError("EVENT_UPDATE_ORIGIN_DESTINATION_AMBIGUOUS")
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
) -> tuple[str, int, str, dict[str, Any]] | None:
    """Resolve one canonical Event by exact name or verified original-source quote.

    A provider may shorten a title ('Excursión escolar') while the source
    preserves a distinguishing suffix ('Excursión escolar E5 ABC123').
    Source recovery requires the entire quoted reference inside that SAME
    Event's fact content AND the canonical name as a word-bounded prefix;
    it never uses similarity, location or inferred references.
    """
    if not isinstance(reference, str) or not reference.strip():
        return None
    matches = []
    quoted = re.compile(r"(?<!\w)" + re.escape(reference) + r"(?!\w)", re.IGNORECASE)
    for path in repository.list_markdown_paths():
        raw = repository.read_text(path)
        note = parse_note(raw)
        validate_note(note, schema)
        if note.metadata.get("type") != "event" or note.metadata.get("deleted") is True:
            continue
        name = note.metadata["name"]
        name_matches = quoted.search(name) is not None
        source_matches = (
            re.match(r"\A" + re.escape(name) + r"(?=\W|$)", reference, re.IGNORECASE) is not None
            and quoted.search(note.content) is not None
        )
        if name_matches or source_matches:
            matches.append(
                (
                    note.metadata["id"],
                    note.metadata["revision"],
                    hashlib.sha256(raw.encode()).hexdigest(),
                    dict(note.metadata),
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
            presentation_intent="note_set",
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
            anchor = _target_identity_anchor(candidate, temporal)
            if not _matches_canonical_target(target[3], anchor):
                return attention("EVENT_TARGET_DATE_MISMATCH")
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
        return attention(error.code)
    except EventRouteError as error:
        # Preserve a fixed internal refusal code; do not expose source text.
        return attention(str(error))
    except ValueError:
        return attention("EVENT_INPUT_VALIDATION_REJECTED")
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
