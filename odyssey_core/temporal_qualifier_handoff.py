"""E2 lossless optional qualitative-time projection from existing verified carriers.

Never guesses a locale-specific daypart, hour, or date. Only a source-anchored
Router approximate-time span inside the SAME independent exact Temporal mention
can be carried as a qualitative qualifier, pending future UI/Writer consumers.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
from .domain_interpretation import DomainInterpretation
from .execution_context import QualitativeTime
from .temporal_interpretation import TemporalInterpretation
from .temporal_resolution import TemporalResolutionKind


def qualitative_source_time_role(role: str, text: str) -> bool:
    """Preserve nonnumeric source dayparts; numeric unresolved clocks stay guarded."""
    return role == "time_approx" or (role == "time" and not any(c.isdigit() for c in text))


def source_bound_qualitative_times(
    interpretation: TemporalInterpretation | None,
    context: CoreCandidateContext,
    domain: DomainInterpretation | None,
    *,
    timezone: str,
) -> tuple[QualitativeTime, ...]:
    """Conservatively preserve compound exact-date + approximate-time wording.

    Multiple approximate spans or separate dates within a phrase are not
    guessed together. Existing Temporal domain date anchors must agree exactly.
    This projection is informational: it grants no date or write authority.
    """
    if interpretation is None or domain is None:
        return ()
    context.validate(interpretation.source_text)
    if domain.source_text != interpretation.source_text:
        raise ValueError("Qualitative time domain source changed")
    source = interpretation.source_text
    # Two Core candidates may legitimately refer to the same physical
    # temporal phrase. Deduplicate the identical source span, not its text:
    # separate occurrences of the same wording must remain distinct/ambiguous.
    approximate_by_span = {
        (role.span.start, role.span.end, role.span.text): role.span
        for candidate in context.candidates
        for role in candidate.roles
        if qualitative_source_time_role(role.role, role.span.text)
    }
    approximate = tuple(approximate_by_span.values())
    if not approximate:
        return ()
    exact_dates = {
        (item.source_text, item.value)
        for item in domain.temporal_references()
        if len(item.value) == 10
    }
    cursor = 0
    result: list[QualitativeTime] = []
    for mention in interpretation.mentions:
        start = source.find(mention.temporal_text, cursor)
        if start < 0:
            raise ValueError("Temporal mention lost its exact source span")
        end = start + len(mention.temporal_text)
        cursor = end
        date = mention.resolution.exact_date
        if (
            mention.resolution.kind is not TemporalResolutionKind.EXACT_DATE
            or date is None
            or (mention.temporal_text, date) not in exact_dates
        ):
            continue
        inside = [span for span in approximate if start <= span.start < span.end <= end]
        if len(inside) != 1:
            continue
        result.append(QualitativeTime(mention.temporal_text, date, inside[0].text, timezone))
    # Temporal may resolve the date and preserve a separate non-clock phrase
    # as UNSPECIFIED. Their adjacency alone is insufficient: BOTH fragments
    # must be independently quoted roles of the SAME candidate, with one
    # exact date and one physical qualifier, and no intervening meaning.
    from .temporal_approximation_handoff import TEMPORAL_APPROXIMATE_LITERAL

    approximate_literals = {
        e.source_text for e in domain.evidence if e.kind == TEMPORAL_APPROXIMATE_LITERAL
    }
    if approximate_literals:
        date_mentions = [
            (m.temporal_text, m.resolution.exact_date)
            for m in interpretation.mentions
            if m.resolution.kind is TemporalResolutionKind.EXACT_DATE
            and (m.temporal_text, m.resolution.exact_date) in exact_dates
            and source.count(m.temporal_text) == 1
        ]
        unresolved = {
            m.temporal_text
            for m in interpretation.mentions
            if m.resolution.kind is TemporalResolutionKind.UNSPECIFIED
            and m.temporal_text in approximate_literals
            and source.count(m.temporal_text) == 1
        }
        for candidate in context.candidates:
            dates = [
                role.span
                for role in candidate.roles
                if role.role in {"date", "date_scope"}
                and any(role.span.text == word for word, _date in date_mentions)
            ]
            qualifiers = [
                role.span
                for role in candidate.roles
                if qualitative_source_time_role(role.role, role.span.text)
                and role.span.text in unresolved
            ]
            if len(dates) != 1 or len(qualifiers) != 1:
                continue
            date_span, qualifier_span = dates[0], qualifiers[0]
            if (
                date_span.end <= qualifier_span.start
                and not source[date_span.end : qualifier_span.start].strip()
            ):
                joined = source[date_span.start : qualifier_span.end]
            elif (
                qualifier_span.end <= date_span.start
                and not source[qualifier_span.end : date_span.start].strip()
            ):
                joined = source[qualifier_span.start : date_span.end]
            else:
                continue
            if source.count(joined) != 1:
                continue
            date_values = [value for word, value in date_mentions if word == date_span.text]
            if len(date_values) != 1 or date_values[0] is None:
                continue
            proposal = QualitativeTime(
                joined,
                date_values[0],
                qualifier_span.text,
                timezone,
                date_source_text=date_span.text,
            )
            if proposal not in result:
                result.append(proposal)
    return tuple(result)
