"""Offline-only safety checks for the real entire-message smoke runner."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_core_live.run_complete_message_smoke import (
    MAX_SPEND_USD,
    PREVIOUS_ESTIMATED_SPEND_USD,
    CappedResponses,
    current_capture_time,
    dry_run,
)


def test_live_smoke_clock_is_offset_aware_and_second_precision():
    now = current_capture_time()
    assert now.microsecond == 0
    assert now.tzinfo is not None
    assert now.utcoffset() is not None
    assert now.isoformat().count(":") >= 3


def test_smoke_is_offline_by_default_and_budget_remains_bounded():
    result = dry_run()
    assert result["new_provider_calls"] == 0
    assert result["active"] is False
    assert MAX_SPEND_USD - PREVIOUS_ESTIMATED_SPEND_USD > 0


def test_smoke_budget_refuses_oversized_real_provider_request_before_transport():
    calls = []
    response = SimpleNamespace(status="completed", usage=None)
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or response)
    )
    bounded = CappedResponses(
        client=client,
        models={"gpt-5.6-luna": {"input_per_million": 0.2, "output_per_million": 1.2}},
    )
    with pytest.raises(ValueError, match="Provider cap reached"):
        bounded.create(
            model="gpt-5.6-luna",
            store=False,
            input=[{"role": "system", "content": "x" * 200000}],
            max_output_tokens=2048,
        )
    assert calls == []


def test_smoke_provider_counts_actual_usage_without_retry_or_cache_discount():
    calls = []
    response = SimpleNamespace(
        status="completed",
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or response)
    )
    bounded = CappedResponses(
        client=client,
        models={"gpt-6-luna": {"input_per_million": 0.1, "output_per_million": 0.5}},
    )
    bounded.create(
        model="gpt-6-luna",
        store=False,
        input=[{"role": "user", "content": "synthetic source"}],
        max_output_tokens=512,
    )
    assert len(calls) == 1
    assert bounded.calls[0]["input_tokens"] == 100
    assert bounded.calls[0]["output_tokens"] == 50
    assert bounded.spent <= MAX_SPEND_USD
