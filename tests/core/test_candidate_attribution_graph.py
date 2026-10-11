"""N:M source evidence checks without converting source hints into write authority."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import (
    CandidateAttributionError,
    CandidateFactLinks,
    inspect_candidate_fact_graph,
)
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_complete_source_handoff import _arbitrary_proposal
from tests.runtime.test_fact_candidate_coverage_gate import _run
from tests.runtime.test_temporal_user_path_e2e import _day_plan


def _source_and_plan(candidate_count: int, fact_count: int):
    source, raw = _arbitrary_proposal(candidate_count)
    context = to_core_candidate_context(validate_fact_candidate_proposal(source, raw))
    base = _day_plan("2026-10-04", "Se registró el primer hecho.", "2026-10-04")
    unit = base.actions[0].units[0]
    unit = replace(
        unit,
        facts=tuple(f"Hecho independiente {i}." for i in range(fact_count)),
        fact_temporal_anchors=unit.fact_temporal_anchors * fact_count,
    )
    return source, context, RequestPlan((WriteAction((unit,)),), ())


@pytest.mark.parametrize(
    "candidate_count,fact_count",
    [(1, 1), (1, 3), (3, 1), (3, 5), (5, 3), (8, 13), (13, 8), (26, 26)],
)
def test_complete_source_to_core_graph_allows_arbitrary_fan_in_and_fan_out(
    candidate_count,
    fact_count,
):
    source, context, plan = _source_and_plan(candidate_count, fact_count)
    links = tuple(
        CandidateFactLinks(
            candidate.candidate_id,
            candidate.anchors[0].text,
            tuple(
                # Every source unit contributes to at least one fact, and all
                # facts have source evidence. Some ordinals may be shared.
                sorted(
                    {index % fact_count}
                    | {
                        ordinal
                        for ordinal in range(fact_count)
                        if ordinal % candidate_count == index
                    }
                ),
            ),
        )
        for index, candidate in enumerate(context.candidates)
    )
    graph = inspect_candidate_fact_graph(source, context, plan, links)
    assert graph.candidate_count == candidate_count
    assert graph.fact_count == fact_count
    assert graph.matches_original_plan(source, plan)
    assert not graph.matches_original_plan(source + " más", plan)
    assert not graph.semantically_verified
    assert not graph.may_authorize_writes
    assert len({number for link in links for number in link.fact_ordinals}) == fact_count


@pytest.mark.parametrize("candidate_count", [1, 3, 5])
def test_graph_missing_source_candidate_or_unclaimed_core_fact_is_rejected(candidate_count):
    source, context, plan = _source_and_plan(candidate_count, candidate_count + 1)
    base = tuple(
        CandidateFactLinks(c.candidate_id, c.anchors[0].text, (index,))
        for index, c in enumerate(context.candidates)
    )
    with pytest.raises(CandidateAttributionError, match="Every planned Core fact"):
        inspect_candidate_fact_graph(source, context, plan, base)
    with pytest.raises(CandidateAttributionError, match="Each source candidate"):
        inspect_candidate_fact_graph(source, context, plan, base[:-1])


@pytest.mark.parametrize("wrong_ordinals", [(99,), (0, 0), (True,), ("0",), (1, 0)])
def test_graph_forged_fact_edges_cannot_claim_verification(wrong_ordinals):
    source, context, plan = _source_and_plan(1, 2)
    with pytest.raises(CandidateAttributionError, match="Invalid, duplicated or invented"):
        inspect_candidate_fact_graph(
            source,
            context,
            plan,
            (
                CandidateFactLinks(
                    "candidate-1", context.candidates[0].anchors[0].text, wrong_ordinals
                ),
            ),
        )


def test_graph_missing_or_mismatched_quote_cannot_claim_provenance():
    source, context, plan = _source_and_plan(3, 1)
    claims = tuple(
        CandidateFactLinks(c.candidate_id, c.anchors[0].text, (0,)) for c in context.candidates
    )
    with pytest.raises(CandidateAttributionError, match="source quote"):
        inspect_candidate_fact_graph(
            source,
            context,
            plan,
            (replace(claims[0], source_quote="invented text"), *claims[1:]),
        )
    with pytest.raises(CandidateAttributionError, match="ID or ordering"):
        inspect_candidate_fact_graph(
            source,
            context,
            plan,
            (claims[1], claims[0], claims[2]),
        )


def test_graph_can_keep_unresolved_unit_pending_without_inventing_an_identity():
    source, context, plan = _source_and_plan(3, 1)
    context = replace(
        context,
        candidates=(
            context.candidates[0],
            replace(context.candidates[1], state="ambiguous_identity"),
            context.candidates[2],
        ),
    )
    links = (
        CandidateFactLinks("candidate-1", context.candidates[0].anchors[0].text, (0,)),
        CandidateFactLinks(
            "candidate-2", context.candidates[1].anchors[0].text, (), "ambiguous_identity"
        ),
        CandidateFactLinks("candidate-3", context.candidates[2].anchors[0].text, (0,)),
    )
    graph = inspect_candidate_fact_graph(source, context, plan, links)
    assert graph.links[1].pending_reason == "ambiguous_identity"
    with pytest.raises(CandidateAttributionError, match="Sensitive or ambiguous"):
        inspect_candidate_fact_graph(
            source,
            context,
            plan,
            (links[0], replace(links[1], fact_ordinals=(0,), pending_reason=None), links[2]),
        )


def test_a_graph_diagnostic_is_not_a_core_coverage_manifest_or_write_permission(tmp_path):
    source, context, plan = _source_and_plan(3, 1)
    graph = inspect_candidate_fact_graph(
        source,
        context,
        plan,
        tuple(
            CandidateFactLinks(c.candidate_id, c.anchors[0].text, (0,)) for c in context.candidates
        ),
    )
    # Core's EXISTING prewrite contract must refuse this diagnostic; it is
    # *not* a shortcut into materialization while independent semantic
    # attestation of N:M correspondences remains unavailable.
    result, repo = _run(tmp_path, source, context, plan, lambda *_: graph)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
    assert result.action_results == ()
    assert repo.list_markdown_paths() == []
