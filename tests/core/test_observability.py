"""Provider-free tests for the bounded operational evidence contract."""

from __future__ import annotations

from types import SimpleNamespace

from odyssey_core.observability import normalize_provider_usage


def test_provider_usage_normalization_keeps_only_supplied_counters() -> None:
    """Normalize SDK-style usage while dropping response content and credentials."""
    response = SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=100,
            input_tokens_details=SimpleNamespace(cached_tokens=20),
            output_tokens=30,
            output_tokens_details=SimpleNamespace(reasoning_tokens=5),
            prompt="not retained",
        )
    )

    assert normalize_provider_usage(response) == {
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "output_tokens": 30,
        "reasoning_tokens": 5,
    }


def test_provider_usage_without_usage_is_unavailable_not_zero() -> None:
    """Do not fabricate zero counters when a provider did not return usage."""
    assert normalize_provider_usage({"id": "response-without-usage"}) is None
