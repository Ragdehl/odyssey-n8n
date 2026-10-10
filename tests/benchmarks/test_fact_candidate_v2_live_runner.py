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
