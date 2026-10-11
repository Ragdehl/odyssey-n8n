"""Model-shaped complete-message gate: frozen requests and safe boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_core_live import run_full_source_live as gate
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_dependencies import CandidateDependencyError
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.complete_source_handoff import (
    collect_complete_source_evidence,
    plan_complete_source_with_core,
)
from tests.apps.test_fact_candidates import CASES
from tests.benchmarks.test_recorded_real_models_source_replay import _saved_router_outputs
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA


@pytest.mark.parametrize("case,count", [("F23", 2), ("F26", 2), ("F13", 3)])
def test_real_archived_router_to_full_source_core_wire_is_pinned(case, count):
    """Real saved Router; complete source; once-only ordinary Core compiler."""
    source, evidence, wire = gate.request_for(case)
    assert source == next(c["source"] for c in CASES if c["id"] == case)
    assert len(evidence.context.candidates) == count
    assert wire["input"][1]["content"] == source
    assert wire["model"] == "gpt-5.6-luna"
    assert wire["reasoning"] == {"effort": "low"}
    assert wire["store"] is False
    assert wire["max_output_tokens"] == 2048
    if gate.DATES[case]:
        assert len(evidence.temporal_interpretation.mentions) == len(gate.DATES[case])
    assert gate.prepare_review() == json.loads(gate.FREEZE.read_text())


def test_first_gate_has_sufficient_preapproved_budget_without_new_spending():
    preview = gate.run("F23")
    assert preview["mode"] == "OFFLINE_DRY_RUN"
    assert preview["source_was_complete"]
    assert preview["may_write_notes"] is False
    assert preview["semantic_coverage_verified"] is False
    assert preview["previous_estimated_usd"] + preview["maximum_reserved_usd"] <= 0.07


@pytest.mark.parametrize("case", ["F26", "F13"])
def test_later_live_cannot_skip_first_actual_provider_receipt(case):
    with pytest.raises(ValueError, match="receipts"):
        gate.preflight(case)


def test_live_flag_alone_cannot_make_provider_call(monkeypatch):
    monkeypatch.delenv(gate.APPROVAL_FLAG, raising=False)
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: pytest.fail("Billed!")))
    with pytest.raises(ValueError, match="permission"):
        gate.run("F23", live=True, client=client)


def test_one_fake_live_escalation_writes_only_disposable_receipt(tmp_path, monkeypatch):
    """Provider JSON from one full message is captured but cannot become a write."""
    monkeypatch.setattr(gate, "RESULTS", tmp_path)
    monkeypatch.setenv(gate.APPROVAL_FLAG, "1")
    sdk, calls = _sdk_fake(
        {
            "result": {
                "outcome": "ESCALATE",
                "actions": None,
                "limitations": None,
                "clarification_code": None,
            }
        }
    )
    output = gate.run("F23", live=True, client=sdk)
    assert output["outcome"] == "ESCALATE"
    assert output["validation"] == "compiled"
    assert output["atomic_fact_count"] == 0
    assert output["may_write_notes"] is False
    assert len(calls) == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_known_real_full_source_f14_escalation_remains_visible():
    """The new connector must not turn recorded GPT-5.6 ESCALATE into PLAN."""
    source = next(c["source"] for c in CASES if c["id"] == "F14")
    root = Path(__file__).resolve().parents[2]
    model = json.loads(
        (root / "benchmarks/fact_candidate_core_live/results/20261010T202736Z-F14.json").read_text()
    )
    assert model["outcome"] == "ESCALATE"
    router_sdk, _ = _sdk_fake(_saved_router_outputs()["F14"])
    temporal_sdk, _ = _sdk_fake(
        {
            "mentions": [
                _exact_date("Ayer", "2026-10-03"),
                _exact_date("Mañana", "2026-10-05"),
            ]
        }
    )
    evidence = collect_complete_source_evidence(
        source,
        router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(temporal_sdk, CLOCK),
    )
    core_sdk, calls = _sdk_fake(json.loads(model["raw_model_response"]))
    outcome = plan_complete_source_with_core(
        evidence,
        core_planner_factory=lambda context, domain: OpenAILunaExperimentalPlanner(
            core_sdk, SCHEMA, CLOCK, candidate_context=context, domain_interpretation=domain
        ),
    )
    assert getattr(outcome, "outcome", None) == "ESCALATE"
    assert len(calls) == 1
    assert calls[0]["input"][1]["content"] == source


def test_known_real_router_f27_broken_inheritance_blocks_before_core():
    """No synthetic repair of an absent original-source subject link."""
    source = next(c["source"] for c in CASES if c["id"] == "F27")
    router_sdk, _ = _sdk_fake(_saved_router_outputs()["F27"])
    with pytest.raises(CandidateDependencyError, match="no evidence"):
        collect_complete_source_evidence(
            source, router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3")
        )
