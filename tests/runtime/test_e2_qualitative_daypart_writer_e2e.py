"""Real Router/Temporal/Core Planner/coverage/Writer preserving original daypart."""

from __future__ import annotations

from types import SimpleNamespace

from odyssey_apps.fact_candidates import validate_semantic_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.composition import _persistence_actor
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import _review_one_real_core_fact
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_generic_candidate_source_relations import proposal, quote, unit
from tests.runtime.test_hybrid_v6_prewrite_writer_vertical import Reviewer
from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan

SOURCE = "Mañana por la tarde hablaré con Bea."
PHRASE = "Mañana por la tarde"
DAY = "2026-10-05"


class Router:
    def propose(self, original):
        assert original == SOURCE
        row = unit(SOURCE, SOURCE[:-1], predicate="hablaré", date=PHRASE)
        row["scoped_source"].append({"role": "time_approx", "anchor": quote("por la tarde")})
        row["scoped_source"].append({"role": "participants", "anchor": quote("Bea")})
        return validate_semantic_fact_candidate_proposal(
            SOURCE, proposal(SOURCE, [row], [("independent_assertion", 0)])
        )


class Temporal:
    timezone = "Europe/Paris"

    def interpret(self, original):
        assert original == SOURCE
        return TemporalInterpretation(
            original,
            (
                TemporalMention(
                    PHRASE,
                    TemporalResolution(
                        TemporalResolutionKind.EXACT_DATE,
                        exact_date=DAY,
                    ),
                ),
            ),
        )


class Factory:
    def __init__(self, *, fact: str):
        self.fact = fact
        self.seen = []

    def create_for_context(self, context):
        self.seen.append(context)
        assert len(context.qualitative_times) == 1
        assert context.qualitative_times[0].qualifier == "por la tarde"
        assert context.qualitative_times[0].date == DAY
        return SimpleNamespace(plan=lambda source: _linked_day_plan(DAY, self.fact, "Bea", DAY))


def test_daypart_reaches_real_markdown_and_readback_without_invented_clock(tmp_path):
    repo, ctx_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    original_bea = repo.read_text("Bea.md")
    factory = Factory(fact="Hablaré con {{ref:0}}.")
    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=ctx_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor=_persistence_actor("daypart-e2e", None),
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "daypart-e2e",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=Reviewer(),
    )
    assert result.status is ApplicationStatus.COMPLETED, (
        result.planning_error,
        [(action.status.value, action.reason) for action in result.action_results],
    )
    day = repo.read_text("calendar/days/2026-10-05.md")
    assert "Hablaré con [[Bea|Bea]] (por la tarde)." in day
    assert "15:00" not in day and "16:00" not in day
    assert repo.read_text("Bea.md") == original_bea
    assert len(factory.seen) == 1


def test_daypart_already_in_fact_is_not_repeated(tmp_path):
    repo, ctx_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    factory = Factory(fact="Hablaré con {{ref:0}} por la tarde.")
    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=ctx_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor=_persistence_actor("daypart-e2e", None),
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "daypart-e2e",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=Reviewer(),
    )
    assert result.status is ApplicationStatus.COMPLETED
    day = repo.read_text("calendar/days/2026-10-05.md")
    assert day.count("por la tarde") == 1
