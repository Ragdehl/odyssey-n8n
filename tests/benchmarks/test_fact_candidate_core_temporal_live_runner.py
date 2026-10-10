"""Provider-free safety and request contract tests for staged F14/F27 Core gate."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_core_live import run_temporal_live as gate
from tests.runtime.test_fact_candidate_semantic_luna_vertical import _raw_semantic_plan
from tests.runtime.test_fact_candidate_sequential_vertical import _model_payload


def _fake_model(case_id: str):
    payload = _raw_semantic_plan() if case_id == "F14" else _model_payload()
    calls = []

    class FakeResponses:
        def create(self, **request):
            calls.append(request)
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps(payload, ensure_ascii=False),
                usage=SimpleNamespace(input_tokens=1000, output_tokens=900),
            )

    return SimpleNamespace(responses=FakeResponses()), calls


def test_f14_reviewed_request_is_bounded_and_fully_source_only() -> None:
    source, context, temporal, request, upper, previous = gate.preflight("F14")
    assert source.startswith("Ayer hablé con Eric")
    assert len(context.candidates) == 2
    assert temporal.core_domain_interpretation() is not None
    assert request["model"] == "gpt-5.6-luna"
    assert request["reasoning"] == {"effort": "low"}
    assert request["store"] is False
    assert request["max_output_tokens"] == 2048
    assert request["text"]["format"]["strict"] is True
    assert upper < 0.035
    assert previous == gate.BASELINE_ROUTER_AND_CORE_ESTIMATE_USD
    assert previous + upper < gate.AUTHORIZED_CUMULATIVE_CAP_USD


def test_f27_requires_saved_previous_receipt_for_budget(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(gate, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="Exactly one saved F14"):
        gate.preflight("F27")


def test_second_stage_budget_accounts_first_real_usage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(gate, "RESULTS", tmp_path)
    (tmp_path / "replayed-F14.json").write_text(
        json.dumps(
            {
                "mode": "LIVE_CORE_PLAN_ONLY",
                "case": "F14",
                "usage": {"input_tokens": 11000, "output_tokens": 800},
            }
        )
    )
    *_args, upper, previous = gate.preflight("F27")
    assert 0.03 < upper < 0.035
    assert previous > gate.BASELINE_ROUTER_AND_CORE_ESTIMATE_USD
    assert previous + upper < gate.AUTHORIZED_CUMULATIVE_CAP_USD


def test_budget_blocks_unreasonably_large_observed_usage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(gate, "RESULTS", tmp_path)
    (tmp_path / "replayed-F14.json").write_text(
        json.dumps(
            {
                "mode": "LIVE_CORE_PLAN_ONLY",
                "case": "F14",
                "usage": {"input_tokens": 2000000, "output_tokens": 100000},
            }
        )
    )
    with pytest.raises(ValueError, match="ceiling"):
        gate.preflight("F27")


def test_unauthorized_live_stage_never_calls_sdk(monkeypatch) -> None:
    monkeypatch.delenv(gate.RUN_ENV, raising=False)
    fake, calls = _fake_model("F14")
    with pytest.raises(ValueError, match="approval"):
        gate.run_case("F14", live=True, client=fake)
    assert not calls


def test_f14_fake_model_compiler_can_be_replayed_without_writes(monkeypatch) -> None:
    monkeypatch.setenv(gate.RUN_ENV, "1")
    fake, calls = _fake_model("F14")
    receipt = gate.run_case("F14", live=True, client=fake)
    assert len(calls) == 1
    assert receipt["validation"] == "locally_valid"
    assert receipt["outcome"] == "PLAN"
    assert receipt["action_count"] == 1
    assert receipt["may_authorize_writes"] is False
    assert receipt["usage"] == {"input_tokens": 1000, "output_tokens": 900}


def test_f27_fake_model_compiler_can_be_replayed_after_receipt(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(gate, "RESULTS", tmp_path)
    (tmp_path / "replayed-F14.json").write_text(
        json.dumps(
            {
                "mode": "LIVE_CORE_PLAN_ONLY",
                "case": "F14",
                "usage": {"input_tokens": 11000, "output_tokens": 800},
            }
        )
    )
    monkeypatch.setenv(gate.RUN_ENV, "1")
    fake, calls = _fake_model("F27")
    receipt = gate.run_case("F27", live=True, client=fake)
    assert len(calls) == 1
    assert receipt["validation"] == "locally_valid"
    assert receipt["outcome"] == "PLAN"
    assert receipt["action_count"] == 1
    assert receipt["may_authorize_writes"] is False


@pytest.mark.parametrize(
    "case_id,change",
    [
        ("F14", "drop_future_date"),
        ("F14", "drop_future_reference"),
        ("F14", "future_not_pending"),
        ("F27", "drop_future_date"),
        ("F27", "drop_future_reference"),
        ("F27", "future_not_pending"),
    ],
)
def test_pending_temporal_clause_guard_abstains_on_unverified_evidence(
    case_id: str, change: str
) -> None:
    """A disconnected date or unverified pronoun must not be silently excluded."""
    from dataclasses import replace

    from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
    from odyssey_core.request_planning import RequestPlanningError
    from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA

    source, context = gate._context(case_id)
    future = context.candidates[-1]
    if change == "drop_future_date":
        future = replace(future, roles=tuple(r for r in future.roles if r.role != "date"))
    elif change == "drop_future_reference":
        future = replace(future, roles=tuple(r for r in future.roles if r.role != "reference"))
    else:
        future = replace(future, state="candidate")
    context = replace(context, candidates=(*context.candidates[:-1], future))
    client, _calls = _fake_model(case_id)
    planner = OpenAILunaExperimentalPlanner(
        client,
        SCHEMA,
        CLOCK,
        domain_interpretation=gate.temporal_evidence(source).core_domain_interpretation(),
        candidate_context=context,
    )
    with pytest.raises(RequestPlanningError, match="required temporal wording"):
        planner.plan(source)


def test_scoped_partial_is_opt_in_and_preserves_existing_model_contract() -> None:
    """Original frozen provider input must remain byte-for-byte unchanged."""
    for case_id in ("F14", "F27"):
        _s, _c, _t, original, _upper = gate.reviewed_case(case_id)
        _s, _c, _t, partial, _upper = gate.reviewed_case(case_id, partial_guidance=True)
        assert original["model"] == partial["model"] == "gpt-5.6-luna"
        assert original["text"] == partial["text"]
        assert original["input"][1] == partial["input"][1]
        assert {
            key: val for key, val in original.items() if key not in {"input", "prompt_cache_key"}
        } == {key: val for key, val in partial.items() if key not in {"input", "prompt_cache_key"}}
        assert original["prompt_cache_key"] != partial["prompt_cache_key"]
        old_rules = json.dumps(original["input"][0]["content"], ensure_ascii=False)
        new_rules = json.dumps(partial["input"][0]["content"], ensure_ascii=False)
        assert "Scoped source-candidate partial-write rule" not in old_rules
        assert "Scoped source-candidate partial-write rule" in new_rules
        assert "Do NOT emit the ambiguous candidate" in new_rules
        assert "mandatory candidate-" in new_rules
        assert "Never use an identity mentioned by the user" in new_rules
    dry = gate.run_case("F14", live=False, partial_guidance=True)
    assert dry["mode"] == "DRY_RUN_NO_PROVIDER"
    assert dry["previous_test_estimated_usd"] > gate.BASELINE_ROUTER_AND_CORE_ESTIMATE_USD
    assert (
        dry["previous_test_estimated_usd"] + dry["conservative_call_reservation_usd"]
        < gate.AUTHORIZED_CUMULATIVE_CAP_USD
    )


def test_partial_prompt_revision_fake_produces_core_plan_but_never_writes(
    monkeypatch,
) -> None:
    """A safe Core-shaped positive response is parsable under the new prompt."""
    monkeypatch.setenv(gate.RUN_ENV, "1")
    client, calls = _fake_model("F14")
    result = gate.run_case("F14", live=True, client=client, partial_guidance=True)
    assert len(calls) == 1
    assert result["prompt_revision"] == "opt_in_scoped_partial"
    assert result["outcome"] == "PLAN"
    assert result["validation"] == "locally_valid"
    assert result["may_authorize_writes"] is False
