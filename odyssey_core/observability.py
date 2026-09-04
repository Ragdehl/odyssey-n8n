"""Bounded request-operational evidence shared by Core and the runtime adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class OperationalOutcome(StrEnum):
    """Describe the bounded outcome of one observable request stage."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_CALLED = "not_called"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class OperationalStage:
    """Expose safe metadata for one meaningful request boundary."""

    name: str
    outcome: OperationalOutcome
    duration_ms: float | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    usage: dict[str, int] | None = None
    estimated_cost_usd: float | None = None
    error_category: str | None = None


@dataclass(frozen=True, slots=True)
class OperationalEvidence:
    """Group bounded stage evidence and total monotonic elapsed time for one request."""

    total_duration_ms: float | None = None
    stages: tuple[OperationalStage, ...] = ()


def normalize_provider_usage(value: Any) -> dict[str, int] | None:
    """Keep only supplied Responses token counters and represent absent usage honestly.

    Args:
        value: A provider response, usage mapping, or usage-like SDK object.

    Returns:
        A fixed allowlist of non-negative counters, or ``None`` when no usable counters exist.
    """
    usage: Any = value
    if not isinstance(usage, Mapping):
        usage = getattr(value, "usage", None)
    if isinstance(usage, Mapping) and "usage" in usage:
        usage = usage.get("usage")
    if usage is None:
        return None

    def field(source: Any, name: str) -> Any:
        if isinstance(source, Mapping):
            return source.get(name)
        return getattr(source, name, None)

    counters: dict[str, int] = {}
    for name in (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "output_tokens",
        "reasoning_tokens",
    ):
        raw = field(usage, name)
        if isinstance(raw, int) and raw >= 0:
            counters[name] = raw
    input_details = field(usage, "input_tokens_details")
    cached = field(input_details, "cached_tokens")
    if isinstance(cached, int) and cached >= 0:
        counters["cached_input_tokens"] = cached
    output_details = field(usage, "output_tokens_details")
    reasoning = field(output_details, "reasoning_tokens")
    if isinstance(reasoning, int) and reasoning >= 0:
        counters["reasoning_tokens"] = reasoning
    return counters or None
