"""Offline regression of previously recorded REAL provider replies through current contracts.

Only original stored GPT-6 Router, GPT-6 Temporal and GPT-5.6 Core responses.
No new requests, personal vault, write authorization, mini-planner or secrets.
Failures are retained as explicit regression findings rather than patched
with source sentence or participant vocabulary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_core.candidate_dependencies import (
    CandidateDependencyError,
    trace_core_candidate_dependencies,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA

_ROOT = Path(__file__).resolve().parents[2]
_FIRST_ROUTER = _ROOT / "benchmarks/fact_candidate_v2_live/results/20261010T193754Z.json"
_REST_ROUTER = _ROOT / "benchmarks/fact_candidate_v2_live/remaining_results"
_FULL_CORE = _ROOT / "benchmarks/fact_candidate_core_live/results/20261010T200525Z.json"
_FOCUSED_TEMPORAL = _ROOT / "benchmarks/fact_candidate_v2_live/observed_f08_temporal.json"


def _saved_router_outputs():
    first = json.loads(_FIRST_ROUTER.read_text(encoding="utf-8"))
    assert first["prompt_revision"] == "v3"
    saved = dict(first["raw_router_json"])
    for file in _REST_ROUTER.glob("*.json"):
        row = json.loads(file.read_text(encoding="utf-8"))
        assert row["provider_status"] == "completed"
        assert row["validation"] == "source_valid"
        assert row["case"] not in saved
        saved[row["case"]] = json.loads(row["raw_model_response"])
    assert set(saved) == {case["id"] for case in CASES}
    return saved


@pytest.mark.parametrize("case", CASES, ids=lambda x: x["id"])
def test_real_gpt6_router_outputs_remain_source_validated_and_replayable(case):
    """27 authentic model outputs; keep the one failed inheritance visible."""
    raw = _saved_router_outputs()[case["id"]]
    fake, calls = _sdk_fake(raw)
    proposal = OpenAIFactCandidateRouter(fake, prompt_revision="v3").propose(case["source"])
    assert proposal.source == case["source"]
    assert len(calls) == 1
    assert calls[0]["store"] is False
    assert 1 <= len(proposal.candidates) <= 26

    context = to_core_candidate_context(proposal)
    if case["id"] == "F27":
        # Recorded model inherited an implicit subject from a previous unit
        # that contained no explicit subject source anchor. An actual model
        # guess is not an original-source attestation. Do not fabricate it.
        with pytest.raises(CandidateDependencyError, match="no evidence"):
            trace_core_candidate_dependencies(case["source"], context)
    else:
        projected = trace_core_candidate_dependencies(case["source"], context)
        assert len(projected) == len(proposal.candidates)
        assert all(
            unit.candidate_id == p.candidate_id
            for unit, p in zip(projected, proposal.candidates, strict=True)
        )


def test_recorded_gpt6_temporal_interpretation_keeps_original_relative_time_scopes():
    case = next(item for item in CASES if item["id"] == "F08")
    router_raw = _saved_router_outputs()["F08"]
    router_sdk, router_calls = _sdk_fake(router_raw)
    proposal = OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3").propose(case["source"])
    receipt = json.loads(_FOCUSED_TEMPORAL.read_text(encoding="utf-8"))
    assert receipt["provider_status"] == "completed"
    temporal_sdk, temporal_calls = _sdk_fake(json.loads(receipt["raw_output"]))
    interpretation = OpenAITemporalInterpreter(temporal_sdk, CLOCK).interpret(case["source"])
    bindings = bind_temporal_to_fact_candidates(proposal, interpretation)
    assert len(bindings) == len(receipt["bindings"])
    assert len(router_calls) == len(temporal_calls) == 1
    assert any(b.role in {"time", "time_relation"} for b in bindings)
    assert all(b.candidate_id in {c.candidate_id for c in proposal.candidates} for b in bindings)


@pytest.mark.parametrize("case_id", ["F09", "F10"])
def test_recorded_real_gpt56_core_accepts_one_whole_original_message(case_id):
    case = next(item for item in CASES if item["id"] == case_id)
    saved = _saved_router_outputs()
    router_sdk, calls = _sdk_fake(saved[case_id])
    proposal = OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3").propose(case["source"])
    context = to_core_candidate_context(proposal)
    receipt = json.loads(_FULL_CORE.read_text(encoding="utf-8"))
    [row] = [row for row in receipt["results"] if row["case"] == case_id]
    assert row["provider_status"] == "completed"
    assert row["outcome"] == "PLAN"
    core_sdk, core_calls = _sdk_fake(json.loads(row["raw_model_response"]))
    plan = OpenAILunaExperimentalPlanner(core_sdk, SCHEMA, CLOCK, candidate_context=context).plan(
        case["source"]
    )
    assert isinstance(plan, RequestPlan)
    assert len(core_calls) == 1
    assert core_calls[0]["model"] == "gpt-5.6-luna"
    assert core_calls[0]["input"][1]["content"] == case["source"]
    assert len(calls) == 1
    # A successfully parsed real Core plan alone neither proves source
    # completeness nor authorizes any writing.
    assert (
        sum(
            len(unit.facts)
            for action in plan.actions
            if isinstance(action, WriteAction)
            for unit in action.units
        )
        > 0
    )
