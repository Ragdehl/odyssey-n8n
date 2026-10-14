"""V6 source review executes two unrelated facts through one actual Core Writer.

Provider-free disposable-vault gate: the prewrite Core reviewer cannot authorize
semantic writes, but approved split boundaries preserve the two exact original
scopes and their Temporal dates through canonical Markdown/readback.
"""

from __future__ import annotations

from types import SimpleNamespace

from odyssey_apps.fact_candidates import validate_semantic_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus
from odyssey_core.source_boundary_review import CoreSourceBoundaryReview
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.core.test_application_history import FakeHistoryRecorder
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import (
    _review_one_real_core_fact,
    _source_temporal,
)
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_generic_candidate_source_relations import proposal, unit
from tests.runtime.test_temporal_user_path_e2e import _day_plan

SOURCE = "Ayer compré pan. Mañana llamaré al banco."
DATA = proposal(
    SOURCE,
    [
        unit(SOURCE, "Ayer compré pan", predicate="compré", date="Ayer", kind="purchase_item"),
        unit(SOURCE, "Mañana llamaré al banco", predicate="llamaré", date="Mañana"),
    ],
    [("independent_assertion", 0), ("independent_assertion", 0)],
)


class Router:
    def __init__(self):
        self.requests = []
        self.model = "gpt-6-luna"
        self.reasoning_effort = "low"

    def propose(self, source):
        self.requests.append(source)
        return validate_semantic_fact_candidate_proposal(source, DATA)


class Reviewer:
    def __init__(self):
        self.requests = []
        self.model = "gpt-5.6-luna"
        self.reasoning_effort = "low"
        self.last_usage = {"input_tokens": 130, "output_tokens": 12}
        self.last_error_category = None

    def review(self, context):
        context.validate()
        self.requests.append(context)
        return CoreSourceBoundaryReview(
            context.source_digest,
            context.partition_digest,
            "accept",
            0,
            None,
        )


class Temporal:
    def __init__(self):
        self.sources = []

    def interpret(self, source):
        self.sources.append(source)
        return _source_temporal(source)


def test_v6_core_review_preserves_two_day_facts_through_real_writer(tmp_path):
    vault, context, semantic, embedder = fresh_corpus_vault(tmp_path / "vault")
    router = Router()
    reviewer = Reviewer()
    temporal = Temporal()
    core_sources = []
    progress = []

    def planner_factory(context, domain):
        def plan(text):
            core_sources.append(text)
            if "compré pan" in text:
                return _day_plan("2026-10-03", "Compré pan.", "2026-10-03")
            if "llamaré al banco" in text:
                return _day_plan("2026-10-05", "Llamaré al banco.", "2026-10-05")
            raise AssertionError("Unexpected ungrounded planned source")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        SOURCE,
        router=router,
        temporal=temporal,
        core_planner_factory=planner_factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=vault,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="v6-disposable-writer-gate",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "v6-integrated-source-guard",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=reviewer,
        history_recorder=FakeHistoryRecorder(),
        progress_callback=lambda stage, payload: progress.append(stage),
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert len(reviewer.requests) == 1
    assert router.requests == [SOURCE]
    assert "routing.boundary_review_started" in progress
    assert "routing.boundary_review_ready" in progress
    assert len(result.execution_flow["routes"]) == 2
    assert all(route["status"] == "completed" for route in result.execution_flow["routes"])
    assert core_sources == temporal.sources
    assert len(core_sources) == 2
    assert all(part != SOURCE for part in core_sources)
    assert [stage.name for stage in result.operational.stages].count(
        "candidate.source_boundary_review"
    ) == 1
    review_stage = next(
        stage
        for stage in result.operational.stages
        if stage.name == "candidate.source_boundary_review"
    )
    assert review_stage.model == "gpt-5.6-luna"
    assert review_stage.usage == {"input_tokens": 130, "output_tokens": 12}
    day_before = vault.read_text("calendar/days/2026-10-03.md")
    day_after = vault.read_text("calendar/days/2026-10-05.md")
    assert "Compré pan." in day_before
    assert "Llamaré al banco." in day_after
    assert day_before.count("<!-- odyssey:fact request=") == 1
    assert day_after.count("<!-- odyssey:fact request=") == 1
    assert "llamaré" not in day_before
    assert "compré" not in day_after
