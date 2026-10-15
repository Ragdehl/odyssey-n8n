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
        if role.role == "time_approx"
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
    return tuple(result)
