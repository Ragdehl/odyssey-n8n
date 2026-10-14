"""Safe original-source SPEAKER evidence through hybrid Core and actual Markdown Writer."""

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
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.request_planning import RequestPlan
from odyssey_core.semantic_write import (
    ApplyTo,
    IdentityBinding,
    IdentityIntent,
    IdentityPart,
    LiteralPart,
    SemanticFact,
    SemanticWriteIntent,
    SemanticWriteOperation,
    compile_semantic_write,
)
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.composition import _persistence_actor
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import USER_A, _source_temporal
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_generic_candidate_source_relations import proposal, unit
from tests.runtime.test_hybrid_v6_prewrite_writer_vertical import Reviewer

SOURCE = "Hoy compré pan."
DATA = proposal(
    SOURCE,
    [unit(SOURCE, "Hoy compré pan", predicate="compré", date="Hoy")],
    [("independent_assertion", 0)],
)


class Router:
    """Use an immutable v6 source proposal, not a guessed note identity."""

    def propose(self, source):
        assert source == SOURCE
        return validate_semantic_fact_candidate_proposal(source, DATA)


class Temporal:
    """Use original quoted date in canonical temporal interpreter fixture."""

    def interpret(self, source):
        return _source_temporal(source)


class SpeakerGraphReviewer:
    """Model stand-in that proposes a role without bypassing Core manifest checks."""

    def __init__(self, quote):
        self.quote = quote
        self.last_usage = None

    def propose_graph(self, source, context, plan, **_kwargs):
        assert context.hybrid_interpretation_mode
        return inspect_candidate_fact_graph(
            source,
            context,
            plan,
            (
                CandidateFactLinks(
                    "candidate-1",
                    context.candidates[0].anchors[0].text,
                    (0,),
                    speaker_source_quote=self.quote,
                ),
            ),
        )


def _plan():
    day = IdentityIntent("2026-10-04", IdentityBinding.DESCRIBED, note_type="calendar_day")
    speaker = IdentityIntent("yo", IdentityBinding.SELF, note_type="person")
    action = compile_semantic_write(
        SemanticWriteIntent(
            (
                SemanticWriteOperation(
                    day,
                    ApplyTo.ONE,
                    "record",
                    (
                        SemanticFact(
                            (
                                LiteralPart("Compré pan ("),
                                IdentityPart("yo", speaker),
                                LiteralPart(")."),
                            )
                        ),
                    ),
                ),
            )
        ),
        SCHEMA,
        authorized_calendar_dates=("2026-10-04",),
    )
    return RequestPlan((action,), ())


@pytest.mark.parametrize(
    "speaker_quote,expected", [("compré", "completed"), (None, "partial"), ("comió", "partial")]
)
def test_v6_speaker_evidence_requires_verified_proposal_and_real_authentication(
    tmp_path, speaker_quote, expected
):
    """Independent Core graph + coverage share one source-bound role, then the real Writer."""
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    binding = SelfBindingRepository(state, repo, SCHEMA)
    binding.bind(USER_A, "fixture-person-alex")
    auth = AuthenticatedActorContext(USER_A)
    previous_person = repo.read_text("Alex.md")
    original_day_paths = {
        path: repo.read_text(path)
        for path in repo.list_markdown_paths()
        if path.endswith("2026-10-04.md")
    }
    reviewer = SpeakerGraphReviewer(speaker_quote)

    def coverage(source, context, plan):
        return review_model_candidate_fact_coverage(source, context, plan, reviewer)

    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=Temporal(),
        core_planner_factory=lambda _context, _temporal: SimpleNamespace(
            plan=lambda _source: _plan()
        ),
        candidate_coverage_factory=coverage,
        repository=repo,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor=_persistence_actor("speaker-fact-vertical", auth),
        authenticated_actor=auth,
        self_binding_repository=binding,
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "speaker-fact-vertical",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=Reviewer(),
    )
    if expected == "completed":
        assert result.status is ApplicationStatus.COMPLETED, (
            result.planning_error,
            result.clarification_code,
            result.affected_stable_note_ids,
            [(a.status.value, a.reason) for a in result.action_results],
            [(x.name, x.outcome.value, x.error_category) for x in result.operational.stages],
            result.execution_flow,
        )
        day = repo.read_text("calendar/days/2026-10-04.md")
        assert "Compré pan ([[Alex|Alex]])." in day
        assert "<!-- odyssey:fact request=" in day
        assert result.affected_stable_note_ids
    else:
        assert result.status is ApplicationStatus.NEEDS_ATTENTION
        assert result.affected_stable_note_ids == ()
        assert original_day_paths == {
            path: repo.read_text(path)
            for path in repo.list_markdown_paths()
            if path.endswith("2026-10-04.md")
        }
    assert repo.read_text("Alex.md") == previous_person
