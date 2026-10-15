"""Preserve non-exact time wording while retaining independent exact dates.

An independently validated Temporal UNSPECIFIED result cannot become
an exact instant. In hybrid mode, Core may still plan separate events
using genuine exact date/time anchors and source-exact approximate
wording. Both Router time_approx source spans and Temporal UNSPECIFIED
must agree. Neither one alone is authoritative to invent an instant.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
from .domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from .temporal_interpretation import (
    TemporalInterpretation,
    TemporalInterpreterError,
)
from .temporal_resolution import TemporalResolutionKind

TEMPORAL_APPROXIMATE_LITERAL = "temporal_approximate_literal"


def compose_safe_approximate_group(
    interpretation: TemporalInterpretation,
    context: CoreCandidateContext,
) -> DomainInterpretation:
    context.validate(interpretation.source_text)
    if (
        not context.hybrid_interpretation_mode
        or len(context.candidates) < 1
        or any(candidate.state != "candidate" for candidate in context.candidates)
    ):
        raise TemporalInterpreterError("Approximate time needs validated hybrid source")
    unresolved = [
        item
        for item in interpretation.mentions
        if item.resolution.kind is TemporalResolutionKind.UNSPECIFIED
    ]
    # Router `time` also denotes EXACT clocks; do not count those as
    # approximate merely because the same candidate has an UNSPECIFIED
    # daypart. The only admissible literal is an independent Temporal quote.
    from .temporal_qualifier_handoff import qualitative_source_time_role

    unresolved_quotes = {item.temporal_text for item in unresolved}
    approximate_roles = [
        role.span
        for candidate in context.candidates
        for role in candidate.roles
        if qualitative_source_time_role(role.role, role.span.text)
        and role.span.text in unresolved_quotes
    ]
    if not unresolved or not approximate_roles or len(unresolved) != len(approximate_roles):
        raise TemporalInterpreterError("Approximate source/Temporal evidence differs")
    role_offsets = [(span.start, span.end, span.text) for span in approximate_roles]
    if len(role_offsets) != len(set(role_offsets)):
        raise TemporalInterpreterError("Duplicate approximate source roles")
    # Validate each exact source occurrence rather than trusting a guess
    # about the hour's literal value or treating an unsupported date as safe.
    for mention in unresolved:
        candidates = [
            span
            for span in approximate_roles
            if span.text == mention.temporal_text
            and interpretation.source_text[span.start : span.end] == span.text
        ]
        if len(candidates) != 1:
            raise TemporalInterpreterError(
                "Unspecified Temporal wording lacks unique approximate source role"
            )
    if any(
        item.resolution.kind is TemporalResolutionKind.DATE_RANGE
        for item in interpretation.mentions
    ):
        raise TemporalInterpreterError("Unsupported date range cannot become approximate literal")
    evidence: list[DomainEvidence] = []
    for mention in interpretation.mentions:
        value = mention.resolution.exact_date or mention.resolution.exact_datetime
        if mention.resolution.kind is TemporalResolutionKind.UNSPECIFIED:
            evidence.append(
                DomainEvidence(
                    TEMPORAL_APPROXIMATE_LITERAL,
                    mention.temporal_text,
                    "APPROXIMATE_UNRESOLVED",
                )
            )
        elif (
            mention.resolution.kind
            in {
                TemporalResolutionKind.EXACT_DATE,
                TemporalResolutionKind.EXACT_DATETIME,
            }
            and value is not None
        ):
            evidence.append(
                DomainEvidence(
                    TEMPORAL_REFERENCE_EVIDENCE,
                    mention.temporal_text,
                    value,
                )
            )
        else:
            raise TemporalInterpreterError(
                "Non-exact Temporal item not authorized for hybrid group"
            )
    if not any(x.kind == TEMPORAL_REFERENCE_EVIDENCE for x in evidence):
        raise TemporalInterpreterError(
            "No independently resolved date or instant in approximate group"
        )
    return DomainInterpretation(
        capability_id="temporal",
        source_text=interpretation.source_text,
        intent="TEMPORAL_RESOLUTION",
        evidence=tuple(evidence),
    )
