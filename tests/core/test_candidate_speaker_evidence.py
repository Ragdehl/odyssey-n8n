"""Generic Core-reviewed speaker evidence cannot be replaced by Router hints."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_semantic_fact_candidate_proposal
from odyssey_core.candidate_attribution import (
    CandidateAttributionError,
    CandidateFactLinks,
    candidate_fact_graph_json_schema,
    inspect_candidate_fact_graph,
    validate_candidate_fact_graph_proposal,
)
from odyssey_core.candidate_context import CoreCandidateRole, CoreSourceSpan
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
    validate_candidate_coverage_manifest,
)
from odyssey_core.candidate_speaker_evidence import CoreSpeakerEvidence
from tests.runtime.test_hybrid_speaker_fact_e2e import DATA, SOURCE, _plan


def _fixture():
    context = to_core_candidate_context(validate_semantic_fact_candidate_proposal(SOURCE, DATA))
    context = replace(context, scoped_route_source=True, hybrid_interpretation_mode=True)
    context.validate(SOURCE)
    return context, _plan()


def test_versioned_speaker_review_contract_changes_only_for_self_fact_plans():
    old = candidate_fact_graph_json_schema()
    new = candidate_fact_graph_json_schema(with_speaker=True)
    assert "speaker_source_quote" not in old["properties"]["candidates"]["items"]["required"]
    assert "speaker_source_quote" in new["properties"]["candidates"]["items"]["required"]
    assert old["additionalProperties"] is False
    assert new["additionalProperties"] is False


def test_source_owned_speaker_proof_is_consumed_by_graph_and_core_coverage():
    context, plan = _fixture()
    link = CandidateFactLinks(
        "candidate-1", context.candidates[0].anchors[0].text, (0,), speaker_source_quote="compré"
    )
    graph = inspect_candidate_fact_graph(SOURCE, context, plan, (link,))
    assert not graph.may_authorize_writes
    attestation = (CoreSpeakerEvidence("candidate-1", 0, "compré"),)
    claim = (CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),)
    manifest = build_candidate_coverage_manifest(
        SOURCE, context, plan, claim, speaker_evidence=attestation
    )
    validate_candidate_coverage_manifest(SOURCE, context, plan, manifest)
    with pytest.raises(ValueError, match="speaker reference"):
        build_candidate_coverage_manifest(SOURCE, context, plan, claim)


@pytest.mark.parametrize("quote", ["compró", "Hoy", "pan", "yo", "", None, 33])
def test_graph_rejects_unanchored_claims_of_authenticated_speaker(quote):
    context, plan = _fixture()
    link = CandidateFactLinks(
        "candidate-1", context.candidates[0].anchors[0].text, (0,), speaker_source_quote=quote
    )
    with pytest.raises(CandidateAttributionError):
        inspect_candidate_fact_graph(SOURCE, context, plan, (link,))


def test_other_explicit_subject_blocks_predicate_only_speaker_proposal():
    context, plan = _fixture()
    subject = CoreCandidateRole("subject", CoreSourceSpan("Hoy", 0, 3))
    first = context.candidates[0]
    context = replace(context, candidates=(replace(first, roles=(*first.roles, subject)),))
    context.validate(SOURCE)
    link = CandidateFactLinks(
        "candidate-1", first.anchors[0].text, (0,), speaker_source_quote="compré"
    )
    with pytest.raises(CandidateAttributionError, match="speaker evidence"):
        inspect_candidate_fact_graph(SOURCE, context, plan, (link,))


def test_source_graph_requires_exact_speaker_field_and_plan_binding():
    context, plan = _fixture()
    entry = {
        "candidate_id": "candidate-1",
        "source_quote": context.candidates[0].anchors[0].text,
        "fact_ordinals": [0],
        "planned_fact_texts": [plan.actions[0].units[0].facts[0]],
        "pending_reason": None,
    }
    with pytest.raises(CandidateAttributionError, match="fields"):
        validate_candidate_fact_graph_proposal(SOURCE, context, plan, {"candidates": [entry]})
    graph = validate_candidate_fact_graph_proposal(
        SOURCE,
        context,
        plan,
        {"candidates": [{**entry, "speaker_source_quote": "compré"}]},
    )
    assert graph.matches_original_plan(SOURCE, plan)
    assert not graph.matches_original_plan(SOURCE + " extra", plan)
