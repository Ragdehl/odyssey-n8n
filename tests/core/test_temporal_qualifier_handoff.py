"""Time-of-day qualifiers survive Core E2 handoff without an invented hour."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.candidate_context import (
    CoreCandidate,
    CoreCandidateContext,
    CoreCandidateRole,
    CoreSourceSpan,
)
from odyssey_core.domain_interpretation import DomainEvidence
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_qualifier_handoff import source_bound_qualitative_times
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind


def pair(source, phrase, qualifier):
    span = CoreSourceSpan(phrase, source.index(phrase), source.index(phrase) + len(phrase))
    roles = ()
    if qualifier:
        pos = source.index(qualifier)
        roles = (
            CoreCandidateRole("time_approx", CoreSourceSpan(qualifier, pos, pos + len(qualifier))),
        )
    ctx = CoreCandidateContext(
        source, (CoreCandidate("candidate-1", "occurrence", "candidate", (span,), roles, ()),)
    )
    ctx.validate(source)
    return ctx


@pytest.mark.parametrize(
    "source,phrase,qualifier,day",
    [
        (
            "Mañana por la tarde hablaré con María.",
            "Mañana por la tarde",
            "por la tarde",
            "2026-10-16",
        ),
        ("Esta noche haré un informe.", "Esta noche", "noche", "2026-10-15"),
        (
            "Demain dans l'après-midi je travaillerai.",
            "Demain dans l'après-midi",
            "dans l'après-midi",
            "2026-10-16",
        ),
        (
            "Tomorrow in the evening I will call.",
            "Tomorrow in the evening",
            "in the evening",
            "2026-10-16",
        ),
    ],
)
def test_exact_date_and_source_approximate_span_preserve_qualifier(source, phrase, qualifier, day):
    ctx = pair(source, phrase, qualifier)
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                phrase, TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date=day)
            ),
        ),
    )
    domain = temporal.core_domain_interpretation()
    result = source_bound_qualitative_times(temporal, ctx, domain, timezone="Europe/Paris")
    assert len(result) == 1
    assert result[0].source_text == phrase
    assert result[0].date == day
    assert result[0].qualifier == qualifier
    assert not hasattr(result[0], "exact_time")


def test_today_only_retains_date_without_a_qualifier():
    source = "Hoy vi a Marta."
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "Hoy",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-15"),
            ),
        ),
    )
    assert (
        source_bound_qualitative_times(
            temporal,
            pair(source, "Hoy", None),
            temporal.core_domain_interpretation(),
            timezone="Europe/Paris",
        )
        == ()
    )


def test_exact_clock_and_unrelated_approximate_source_cannot_be_qualifier():
    source = "Mañana a las 17:00 vi a Marta por la tarde."
    ctx = pair(source, "Mañana", "por la tarde")
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "Mañana",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-16"),
            ),
        ),
    )
    assert (
        source_bound_qualitative_times(
            temporal, ctx, temporal.core_domain_interpretation(), timezone="Europe/Paris"
        )
        == ()
    )


def test_source_mismatch_and_unverified_date_cannot_claim_daypart():
    source = "Mañana por la tarde vi a Marta."
    phrase = "Mañana por la tarde"
    ctx = pair(source, phrase, "por la tarde")
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                phrase,
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-16"),
            ),
        ),
    )
    domain = temporal.core_domain_interpretation()
    assert (
        source_bound_qualitative_times(
            temporal,
            ctx,
            replace(domain, evidence=(DomainEvidence("temporal_reference", phrase, "2026-10-17"),)),
            timezone="Europe/Paris",
        )
        == ()
    )
    with pytest.raises(ValueError, match="source changed|not grounded"):
        source_bound_qualitative_times(
            temporal, ctx, replace(domain, source_text="Marta"), timezone="Europe/Paris"
        )


def test_shared_original_temporal_span_is_one_qualifier_not_two_claims():
    source = "Mañana por la tarde hablaré y escribiré."
    daypart = "por la tarde"
    at = source.index(daypart)
    shared_span = CoreSourceSpan(daypart, at, at + len(daypart))
    candidates = []
    for index, verb in enumerate(("hablaré", "escribiré"), 1):
        start = source.index(verb)
        candidates.append(
            CoreCandidate(
                f"candidate-{index}",
                "occurrence",
                "candidate",
                (CoreSourceSpan(verb, start, start + len(verb)),),
                (CoreCandidateRole("time_approx", shared_span),),
                (),
            )
        )
    ctx = CoreCandidateContext(source, tuple(candidates))
    temporal = TemporalInterpretation(
        source,
        (
            TemporalMention(
                "Mañana por la tarde",
                TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-10-16"),
            ),
        ),
    )
    qualifiers = source_bound_qualitative_times(
        temporal, ctx, temporal.core_domain_interpretation(), timezone="Europe/Paris"
    )
    assert [(q.qualifier, q.date) for q in qualifiers] == [(daypart, "2026-10-16")]
    # The duplicated candidate does NOT certify which of two facts owns it;
    # Core's later fact-ownership mapping must still prove that separately.
