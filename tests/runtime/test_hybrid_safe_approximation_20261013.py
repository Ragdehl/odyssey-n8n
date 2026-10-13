"""Approximate time cannot become a fabricated exact instant or vanish."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.temporal_approximation_handoff import (
    TEMPORAL_APPROXIMATE_LITERAL,
    compose_safe_approximate_group,
)
from odyssey_core.temporal_interpretation import (
    OpenAITemporalInterpreter,
    TemporalInterpretation,
    TemporalInterpreterError,
    TemporalMention,
)
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK
from tests.runtime.test_full_message_corpus_regression import ROOT
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider


def _original_temporal_and_context():
    src = next(row["source"] for row in CASES if row["id"] == "F02")
    receipt = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_router_v5_end_to_end_v4/F02.json").read_text()
    )
    records = receipt["real_model_outputs"]
    context = (
        compile_hybrid_candidate_bundle(
            OpenAIFactCandidateRouter(FrozenProvider(records[:1]), prompt_revision="v5").propose(
                src
            )
        )
        .units[0]
        .context
    )
    temporal = OpenAITemporalInterpreter(
        FrozenProvider(records[1:2]),
        CLOCK,
        max_output_tokens=1536,
        scoped_date_time_context=True,
    ).interpret(context.source)
    return temporal, context


def test_exact_dates_and_unresolved_approximation_coexist_without_converting_clock():
    temporal, context = _original_temporal_and_context()
    with pytest.raises(TemporalInterpreterError):
        temporal.core_domain_interpretation()
    result = compose_safe_approximate_group(temporal, context)
    assert len(result.temporal_references()) == 4
    assert [
        (item.source_text, item.value)
        for item in result.evidence
        if item.kind == TEMPORAL_APPROXIMATE_LITERAL
    ] == [("sobre las 16h", "APPROXIMATE_UNRESOLVED")]
    assert not any(item.source_text == "sobre las 16h" for item in result.temporal_references())
    assert {(item.source_text, item.value) for item in result.temporal_references()} == {
        ("Esta tarde", "2026-10-04"),
        ("mañana", "2026-10-05"),
        ("el domingo", "2026-10-11"),
        ("a las 11h", "2026-10-11T11:00:00+02:00"),
    }


def test_missing_approximation_role_fails_closed():
    temporal, context = _original_temporal_and_context()
    first = context.candidates[0]
    without = replace(
        first, roles=tuple(role for role in first.roles if role.role != "time_approx")
    )
    with pytest.raises((ValueError, TemporalInterpreterError)):
        compose_safe_approximate_group(
            temporal, replace(context, candidates=(without, *context.candidates[1:]))
        )


def test_unresolved_clock_without_exact_source_matching_approx_role_fails_closed():
    temporal, context = _original_temporal_and_context()
    replaced_mentions = tuple(
        TemporalMention(
            item.temporal_text,
            TemporalResolution(TemporalResolutionKind.UNSPECIFIED)
            if item.temporal_text == "a las 11h"
            else item.resolution,
        )
        for item in temporal.mentions
    )
    with pytest.raises(TemporalInterpreterError):
        compose_safe_approximate_group(
            TemporalInterpretation(temporal.source_text, replaced_mentions),
            context,
        )
