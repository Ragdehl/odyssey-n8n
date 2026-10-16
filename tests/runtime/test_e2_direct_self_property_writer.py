"""Direct SELF Person properties require independent Core-reviewed ownership.

The source candidate/Planner target alone do not authorize SELF. The same
normal Core Writer and persisted Markdown readback are used; no live provider.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidates import validate_semantic_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import (
    CandidateFactLinks,
    inspect_candidate_fact_graph,
    review_model_candidate_fact_coverage,
)
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_speaker_evidence import CoreSpeakerEvidence
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, SelectionCriteria, WriteAction
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.composition import _persistence_actor
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import USER_A
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_generic_candidate_source_relations import proposal, quote, unit
from tests.runtime.test_hybrid_v6_prewrite_writer_vertical import Reviewer

SOURCE = "A mí me gusta la gasolina"


def _proposal(source=SOURCE, *, experiencer_role="subject"):
    row = unit(source, source, kind="property", predicate="gusta")
    row["anchors"] = [quote("mí"), quote("gusta"), quote("gasolina")]
    if experiencer_role == "subject":
        roles = [
            {"role": "subject", "anchor": quote("mí")},
            {"role": "object", "anchor": quote("gasolina")},
        ]
    else:
        # In 'gustar', the thing liked can be grammatical SUBJECT and
        # the first-person experiencer is the indirect OBJECT.
        assert experiencer_role == "object"
        roles = [
            {"role": "subject", "anchor": quote("gasolina")},
            {"role": "object", "anchor": quote("mí")},
        ]
    row["scoped_source"].extend(roles)
    return proposal(source, [row], [("independent_assertion", 0)])


def _plan():
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(None, "mí", "person", (), None, self_target="self"),
                        "record",
                        (),
                        (),
                        ("Me gusta la gasolina.",),
                        (),
                    ),
                )
            ),
        ),
        (),
    )


class GraphReviewer:
    def __init__(self, speaker_quote):
        self.speaker_quote = speaker_quote

    def propose_graph(self, source, context, plan, **kwargs):
        del kwargs
        return inspect_candidate_fact_graph(
            source,
            context,
            plan,
            (
                CandidateFactLinks(
                    context.candidates[0].candidate_id,
                    context.candidates[0].anchors[0].text,
                    (0,),
                    speaker_source_quote=self.speaker_quote,
                ),
            ),
        )


@pytest.mark.parametrize("speaker_quote,allowed", [("mí", True), (None, False), ("gusta", False)])
@pytest.mark.parametrize("experiencer_role", ["subject", "object"])
def test_direct_person_self_property_uses_reviewed_source_owner_and_real_writer(
    tmp_path, speaker_quote, allowed, experiencer_role
):
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    binding = SelfBindingRepository(state, repo, SCHEMA)
    binding.bind(USER_A, "fixture-person-alex")
    actor = AuthenticatedActorContext(USER_A)
    before = repo.read_text("Alex.md")

    class Router:
        def propose(self, source):
            assert source == SOURCE
            return validate_semantic_fact_candidate_proposal(
                source, _proposal(experiencer_role=experiencer_role)
            )

    def coverage(source, context, plan):
        return review_model_candidate_fact_coverage(
            source, context, plan, GraphReviewer(speaker_quote)
        )

    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=None,
        core_planner_factory=lambda _context, _domain: SimpleNamespace(
            plan=lambda source, prior=(): _plan()
        ),
        candidate_coverage_factory=coverage,
        repository=repo,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor=_persistence_actor("self-property-acceptance", actor),
        authenticated_actor=actor,
        self_binding_repository=binding,
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "self-property-e2",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=Reviewer(),
    )
    if allowed:
        assert result.status is ApplicationStatus.COMPLETED, [
            (s.name, s.error_category) for s in result.operational.stages
        ]
        assert "Me gusta la gasolina." in repo.read_text("Alex.md")
        assert result.affected_stable_note_ids == ("fixture-person-alex",)
    else:
        assert result.status is ApplicationStatus.NEEDS_ATTENTION
        assert result.affected_stable_note_ids == ()
        assert repo.read_text("Alex.md") == before


def test_self_property_reviewer_attestation_is_required_even_for_matching_source(tmp_path):
    source = SOURCE
    valid = validate_semantic_fact_candidate_proposal(source, _proposal())
    context = compile_hybrid_candidate_bundle(valid).units[0].context
    plan = _plan()
    claim = (CoreCandidateCoverageClaim(context.candidates[0].candidate_id, "planned_fact", 0),)
    with pytest.raises(ValueError, match="SELF fact"):
        build_candidate_coverage_manifest(source, context, plan, claim)
    manifest = build_candidate_coverage_manifest(
        source,
        context,
        plan,
        claim,
        speaker_evidence=(CoreSpeakerEvidence(context.candidates[0].candidate_id, 0, "mí"),),
    )
    assert len(manifest.speaker_evidence) == 1
