"""Fail-closed checks for the original provider Router -> Temporal -> Core pilot.

No live provider calls, source rewriting, operational state or user Notes.
The existing provider adapters and prior frozen real Router JSON remain the
source of truth for these negative scenarios.
"""

from __future__ import annotations

import json

import pytest

from benchmarks.fact_candidate_v2_live import run_remaining
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.dependent_candidate_pipeline import DependentCandidatePipeline
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK


def _router(case_id):
    source = next(item["source"] for item in CASES if item["id"] == case_id)
    receipt = json.loads(next(run_remaining.RESULTS.glob(f"*--{case_id}.json")).read_text())
    fake, calls = _sdk_fake(json.loads(receipt["raw_model_response"]))
    return source, OpenAIFactCandidateRouter(fake, prompt_revision="v3"), calls


@pytest.mark.parametrize(
    "mentions",
    [
        [_exact_date("ayer", "2026-10-03")],
        [_exact_date("hoy", "2026-10-04")],
        [
            _exact_date("ayer", "2026-10-03"),
            _exact_date("hoy", "2026-10-04"),
            _exact_date("ayer", "2026-10-03"),
        ],
    ],
)
def test_missing_or_extra_temporal_mention_aborts_before_core(mentions):
    source, router, router_calls = _router("F26")
    temporal_fake, temporal_calls = _sdk_fake({"mentions": mentions})
    used = []

    def never_plan(domain):
        used.append(domain)
        pytest.fail("Core must never plan with unproven dates")

    pilot = DependentCandidatePipeline(
        router, OpenAITemporalInterpreter(temporal_fake, CLOCK), never_plan
    )
    with pytest.raises(ValueError):
        pilot.prepare(source)
    assert len(router_calls) == 1
    assert len(temporal_calls) == 1
    assert used == []


def test_real_router_output_cannot_be_reused_for_a_changed_original_message():
    source, router, router_calls = _router("F23")
    temporal_fake, temporal_calls = _sdk_fake({"mentions": []})
    used = []
    pilot = DependentCandidatePipeline(
        router,
        OpenAITemporalInterpreter(temporal_fake, CLOCK),
        lambda domain: used.append(domain) or pytest.fail("Core must not run"),
    )
    with pytest.raises(ValueError):
        pilot.prepare(source.replace("Router", "Motor"))
    assert len(router_calls) == 1
    assert temporal_calls == []
    assert used == []


def test_core_escalation_cannot_be_laundered_into_a_writeable_plan():
    source, router, router_calls = _router("F23")
    temporal_fake, temporal_calls = _sdk_fake({"mentions": []})
    planning_calls = []

    class EscalatingCore:
        def plan(self, request):
            planning_calls.append(request)
            return "ESCALATE"

    pilot = DependentCandidatePipeline(
        router,
        OpenAITemporalInterpreter(temporal_fake, CLOCK),
        lambda _: EscalatingCore(),
    )
    with pytest.raises(ValueError, match="Core must independently plan"):
        pilot.prepare(source)
    assert len(router_calls) == 1
    assert not temporal_calls
    assert len(planning_calls) == 1


def test_relative_clock_cannot_be_smuggled_as_a_confirmed_exact_date():
    source, router, router_calls = _router("F08")
    # The same-hour phrase is original user evidence, not an independently
    # confirmed calendar instant without Temporal's exact clock result.
    temporal_fake, temporal_calls = _sdk_fake(
        {
            "mentions": [
                _exact_date("Mañana", "2026-10-10"),
                _exact_date("a las 10", "2026-10-10"),
                _exact_date("a la misma hora", "2026-10-10"),
            ]
        }
    )
    plans = []
    pilot = DependentCandidatePipeline(
        router,
        OpenAITemporalInterpreter(temporal_fake, CLOCK),
        lambda domain: plans.append(domain) or pytest.fail("No Core plan allowed"),
    )
    with pytest.raises(ValueError):
        pilot.prepare(source)
    assert len(router_calls) == 1
    assert plans == []
    assert len(temporal_calls) <= 1
