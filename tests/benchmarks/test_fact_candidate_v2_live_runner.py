"""Offline contract checks for the opt-in four-call synthetic GPT-6 runner."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_v2_live.run_live import (
    MAX_SPEND_USD,
    RUN_ENV,
    reviewed_calls,
    run_once,
)
from tests.apps.test_fact_candidates import CASES, _from_design


class _FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **request):
        self.calls.append(request)
        case = next(c for c in CASES if c["source"] == request["input"][1]["content"])
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps(_from_design(case), ensure_ascii=False),
            usage=SimpleNamespace(input_tokens=100, output_tokens=100),
        )


def test_bounded_requests_match_saved_reviewed_snapshot() -> None:
    calls, estimate = reviewed_calls()
    assert [case for case, _ in calls] == ["F14", "F27", "F09", "F10"]
    assert len(calls) == 4 and 0 < estimate < MAX_SPEND_USD
    assert all(
        c["model"] == "gpt-6-luna"
        and c["store"] is False
        and c["reasoning"]["effort"] == "low"
        and c["text"]["format"]["strict"] is True
        for _, c in calls
    )


def test_dry_run_never_invokes_client_or_requires_authorization(monkeypatch) -> None:
    monkeypatch.delenv(RUN_ENV, raising=False)
    result = run_once(live=False, client=object())
    assert result["mode"] == "DRY_RUN_NO_PROVIDER"
    assert result["live_model_quality_verified"] is False
    assert result["call_limit"] == 4


def test_live_requires_explicit_flag_even_with_injected_client(monkeypatch) -> None:
    monkeypatch.delenv(RUN_ENV, raising=False)
    with pytest.raises(ValueError, match="Explicit approved live flag"):
        run_once(live=True, client=SimpleNamespace(responses=_FakeResponses()))


def test_four_fake_responses_are_locally_reviewed_and_not_executed(monkeypatch) -> None:
    monkeypatch.setenv(RUN_ENV, "1")
    responses = _FakeResponses()
    result = run_once(live=True, client=SimpleNamespace(responses=responses))
    assert len(responses.calls) == 4
    assert len(result["results"]) == 4
    assert all(r["result"] == "source_valid" for r in result["results"])
    assert result["oracle_comparison"]["all_fixture_matches"] is True
    assert result["oracle_comparison"]["live_model_quality_verified"] is False
    assert result["live_model_quality_verified"] is False
    assert all(call["store"] is False for call in responses.calls)


def test_v2_prompt_retains_entire_v1_teaching_and_only_adds_semantic_clarity() -> None:
    """Review exact prompt inheritance, unchanged model/schema, and bounded calls."""
    old, _old_budget = reviewed_calls()
    revised, new_budget = reviewed_calls(prompt_revision="v2")
    assert 0 < new_budget <= MAX_SPEND_USD
    assert [id for id, _ in old] == [id for id, _ in revised]
    for (_case, prior), (_case2, current) in zip(old, revised, strict=True):
        prior_prompt = prior["input"][0]["content"]
        revised_prompt = current["input"][0]["content"]
        assert revised_prompt.startswith(prior_prompt)
        assert len(revised_prompt) > len(prior_prompt)
        for fragment in (
            "Split independent properties",
            "ONE mutual relationship",
            "date",
            "reference",
            "explicit sequencing",
        ):
            assert fragment in revised_prompt
        assert {k: v for k, v in prior.items() if k != "input"} == {
            k: v for k, v in current.items() if k != "input"
        }


def test_v2_fake_provider_outcomes_remain_source_only(monkeypatch) -> None:
    """New prompt still feeds the same local untrusted source validator."""
    monkeypatch.setenv(RUN_ENV, "1")
    responses = _FakeResponses()
    result = run_once(
        live=True,
        client=SimpleNamespace(responses=responses),
        prompt_revision="v2",
    )
    assert result["prompt_revision"] == "v2"
    assert len(responses.calls) == 4
    assert result["oracle_comparison"]["all_fixture_matches"] is True
    assert result["live_model_quality_verified"] is False


def test_v2_dry_run_cannot_call_provider(monkeypatch) -> None:
    monkeypatch.delenv(RUN_ENV, raising=False)
    result = run_once(live=False, client=object(), prompt_revision="v2")
    assert result["mode"] == "DRY_RUN_NO_PROVIDER"
    assert result["call_limit"] == 4
    assert result["conservative_reservation_usd"] < MAX_SPEND_USD
