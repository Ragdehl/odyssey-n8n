"""Actual pre-write provider timing remains visible without changing write authority."""

from __future__ import annotations

from types import SimpleNamespace

from odyssey_core.application import ApplicationStatus
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import (
    RecordedRouter,
    _review_one_real_core_fact,
    _source_temporal,
)
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_temporal_user_path_e2e import _day_plan


class _MeasuredRouter(RecordedRouter):
    model = "recorded-router"
    reasoning_effort = "low"

    def propose(self, source):
        # A real monotonic interval, rather than injected telemetry, protects
        # against reintroducing the zero-duration selected-router adapter.
        from time import perf_counter

        started = perf_counter()
        while perf_counter() == started:
            pass
        self.last_usage = {"input_tokens": 7, "output_tokens": 3}
        return super().propose(source)


class _MeasuredTemporal:
    model = "recorded-temporal"
    reasoning_effort = "low"
    last_usage = {"input_tokens": 5, "output_tokens": 2}

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def interpret(self, source):
        if self.fail:
            raise RuntimeError("untrusted provider detail")
        return _source_temporal(source)


def _run(tmp_path, *, temporal):
    source = "Ayer hablé con Eric. Mañana iré al cine con él. Hoy compré pan."
    repository, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    before = {path: repository.read_text(path) for path in repository.list_markdown_paths()}

    def planner_factory(_context, _domain):
        def plan(scoped):
            if "hablé con Eric" in scoped:
                return _day_plan("2026-10-03", "Hablé con Eric.", "2026-10-03")
            if "compré pan" in scoped:
                return _day_plan("2026-10-04", "Compré pan.", "2026-10-04")
            raise AssertionError("dependent route must not be planned without Core proof")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        source,
        router=_MeasuredRouter("F13"),
        temporal=temporal,
        core_planner_factory=planner_factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repository,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="candidate-route-telemetry",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "candidate-route-telemetry",
    )
    return result, repository, before


def test_dispatch_records_actual_router_and_temporal_stages_not_zero_adapter(tmp_path):
    result, _repository, _before = _run(tmp_path, temporal=_MeasuredTemporal())

    proposal = result.operational.stages[0]
    assert proposal.name == "candidate.source_proposal"
    assert proposal.outcome.value == "completed"
    assert proposal.duration_ms is not None and proposal.duration_ms >= 0
    assert proposal.model == "recorded-router"
    assert proposal.usage == {"input_tokens": 7, "output_tokens": 3}
    assert not any(stage.name == "application.router" for stage in result.operational.stages)
    temporal = [
        stage
        for stage in result.operational.stages
        if stage.name == "candidate.temporal_interpretation"
    ]
    assert temporal and all(stage.outcome.value == "completed" for stage in temporal)
    assert all(stage.model == "recorded-temporal" for stage in temporal)
    assert all(stage.usage == {"input_tokens": 5, "output_tokens": 2} for stage in temporal)
    route_stage_counts = [route["stage_count"] for route in result.execution_flow["routes"]]
    assert route_stage_counts[1] == 0  # blocked dependent route did not invent a stage
    assert route_stage_counts[0] > 0 and route_stage_counts[2] > 0
    assert sum(route_stage_counts) == len(result.operational.stages) - 1


def test_temporal_provider_failure_is_timed_fail_closed_without_markdown_write(tmp_path):
    result, repository, before = _run(tmp_path, temporal=_MeasuredTemporal(fail=True))

    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    temporal = [
        stage
        for stage in result.operational.stages
        if stage.name == "candidate.temporal_interpretation"
    ]
    assert temporal and all(stage.outcome.value == "failed" for stage in temporal)
    assert all(stage.error_category == "RuntimeError" for stage in temporal)
    assert {path: repository.read_text(path) for path in repository.list_markdown_paths()} == before
