"""Fail-closed reuse of one explicitly shared clock for multiple exact dates.

Temporal is the date authority. This adapter ONLY composes dates returned
as EXACT_DATE by Temporal with one exact *source* clock phrase which Temporal
left UNSPECIFIED. It is not a date parser or a time guesser. The router's
untrusted source roles can constrain applicability but never supply a date.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from .candidate_context import CoreCandidateContext
from .domain_interpretation import TEMPORAL_REFERENCE_EVIDENCE, DomainEvidence, DomainInterpretation
from .temporal_interpretation import TemporalInterpretation, TemporalInterpreterError
from .temporal_resolution import TemporalResolutionKind, _normalize_provider_datetime

_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _weekday(text: str) -> int | None:
    lower = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(char for char in lower if not unicodedata.combining(char))
    matches = {_WEEKDAYS[word] for word in re.findall(r"[^\W_]+", plain) if word in _WEEKDAYS}
    return next(iter(matches)) if len(matches) == 1 else None


def compose_shared_clock_group(
    interpretation: TemporalInterpretation,
    context: CoreCandidateContext,
    *,
    timezone: str,
) -> DomainInterpretation:
    context.validate(interpretation.source_text)
    if (
        len(context.candidates) < 2
        or len(context.candidates) > 6
        or any(c.state != "candidate" for c in context.candidates)
        or any(
            role.role in {"condition", "polarity", "replacement", "time_approx"}
            for c in context.candidates
            for role in c.roles
        )
        or re.search(
            r"\b(?:no|nunca|excepto|si|salvo|antes|despues|después)\b",
            interpretation.source_text.casefold(),
        )
    ):
        raise TemporalInterpreterError("Shared clock lacks unambiguous positive source scope")
    clock_roles = [
        [role.span for role in c.roles if role.role == "time"] for c in context.candidates
    ]
    if not clock_roles or any(len(roles) != 1 for roles in clock_roles):
        raise TemporalInterpreterError(
            "Every group event must explicitly own the same source clock"
        )
    clocks = {(roles[0].start, roles[0].end, roles[0].text) for roles in clock_roles}
    if len(clocks) != 1:
        raise TemporalInterpreterError("Shared clock belongs to different source spans")
    clock_text = clock_roles[0][0].text
    parsed = re.fullmatch(
        r"a las\s+([01]?\d|2[0-3])(?:(?:[:h])([0-5]\d))?\s*h?",
        clock_text.strip(),
        flags=re.IGNORECASE,
    )
    if parsed is None:
        raise TemporalInterpreterError("Shared clock is not an explicit unambiguous wall time")
    hh, mm = int(parsed[1]), int(parsed[2] or "0")
    source_mentions = interpretation.mentions
    dates = [m for m in source_mentions if m.resolution.kind is TemporalResolutionKind.EXACT_DATE]
    unknown = [
        m for m in source_mentions if m.resolution.kind is TemporalResolutionKind.UNSPECIFIED
    ]
    ranges = [m for m in source_mentions if m.resolution.kind is TemporalResolutionKind.DATE_RANGE]
    if (
        len(dates) != len(context.candidates)
        or len(unknown) != 1
        or unknown[0].temporal_text != clock_text
        or len(ranges) > 1
        or len(source_mentions) != len(dates) + len(unknown) + len(ranges)
    ):
        raise TemporalInterpreterError("Temporal failed to resolve all and only the shared dates")
    distinct: set[str] = set()
    for c in context.candidates:
        roles = [r.span.text for r in c.roles if r.role == "date"]
        if len(roles) != 1:
            raise TemporalInterpreterError("Shared-clock event has no distinct source date")
        matching = [m for m in dates if roles[0] in m.temporal_text]
        if len(matching) != 1 or not matching[0].resolution.exact_date:
            raise TemporalInterpreterError("Shared-clock date ownership is ambiguous")
        calendar_day = matching[0].resolution.exact_date
        weekday = _weekday(roles[0])
        if weekday is None or date.fromisoformat(calendar_day).weekday() != weekday:
            raise TemporalInterpreterError("Source weekday conflicts with Temporal exact date")
        if calendar_day in distinct:
            raise TemporalInterpreterError("Shared-clock calendar dates are duplicated")
        distinct.add(calendar_day)
    if ranges:
        rng = ranges[0].resolution.date_range
        if (
            rng is None
            or not all(rng.start <= day < rng.end_exclusive for day in distinct)
            or not all(
                any(
                    r.role == "date_scope" and r.span.text in ranges[0].temporal_text
                    for r in c.roles
                )
                for c in context.candidates
            )
        ):
            raise TemporalInterpreterError("Exact event dates contradict their bounded date range")
    anchors: list[DomainEvidence] = []
    for mention in dates:
        day = mention.resolution.exact_date
        assert day is not None
        try:
            instant = _normalize_provider_datetime(f"{day}T{hh:02d}:{mm:02d}:00", timezone=timezone)
        except (ValueError, TypeError) as exc:
            raise TemporalInterpreterError("Clock is invalid or DST ambiguous for a date") from exc
        anchors.append(DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, mention.temporal_text, day))
        anchors.append(DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, clock_text, instant))
    return DomainInterpretation(
        "temporal", interpretation.source_text, "TEMPORAL_RESOLUTION", tuple(anchors)
    )
