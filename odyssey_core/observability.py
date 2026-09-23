"""Bounded request-operational evidence shared by Core and the runtime adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Any


class OperationalOutcome(StrEnum):
    """Describe the bounded outcome of one observable request stage."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_CALLED = "not_called"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class OperationalSpan:
    """Measure one bounded child interval relative to its enclosing stage or attempt."""

    name: str
    outcome: OperationalOutcome
    start_offset_ms: float
    duration_ms: float
    error_category: str | None = None


@dataclass(frozen=True, slots=True)
class DurationCoverage:
    """Represent the union of known child intervals within one parent wall interval."""

    attributed_ms: float
    unattributed_ms: float
    coverage_pct: float
    overlapping_ms: float


@dataclass(slots=True)
class SpanRecorder:
    """Collect ordered, request-local child intervals without retaining their inputs."""

    origin: float
    monotonic: Callable[[], float]
    spans: tuple[OperationalSpan, ...] = ()

    def add(
        self,
        name: str,
        started: float,
        outcome: OperationalOutcome = OperationalOutcome.COMPLETED,
        error: Exception | None = None,
    ) -> None:
        """Append one elapsed child interval with a deterministic occurrence ordinal in its name."""
        finished = self.monotonic()
        self.spans += (
            OperationalSpan(
                name=name,
                outcome=outcome,
                start_offset_ms=(started - self.origin) * 1000,
                duration_ms=(finished - started) * 1000,
                error_category=type(error).__name__ if error is not None else None,
            ),
        )

    def invoke(self, name: str, operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Measure one semantic, I/O, or repeated boundary while preserving its exceptions."""
        started = self.monotonic()
        try:
            result = operation(*args, **kwargs)
        except Exception as error:
            self.add(name, started, OperationalOutcome.FAILED, error)
            raise
        self.add(name, started)
        return result


def reconcile_duration(
    total_duration_ms: float,
    intervals: tuple[tuple[float, float], ...],
) -> DurationCoverage | None:
    """Union child wall intervals without double counting overlaps.

    Args:
        total_duration_ms: Measured parent wall interval in milliseconds.
        intervals: Child start offsets and durations relative to that parent.

    Returns:
        Coverage and explicit residual, or ``None`` for impossible or malformed timing.
    """
    if not isfinite(total_duration_ms) or total_duration_ms < 0:
        return None
    ordered: list[tuple[float, float]] = []
    sum_durations = 0.0
    for start, duration in intervals:
        if not all(isfinite(value) for value in (start, duration)):
            return None
        if start < 0 or duration < 0 or start + duration > total_duration_ms + 0.001:
            return None
        ordered.append((start, min(total_duration_ms, start + duration)))
        sum_durations += duration
    ordered.sort()
    covered = 0.0
    end = 0.0
    for start, finish in ordered:
        covered += max(0.0, finish - max(start, end))
        end = max(end, finish)
    residual = max(0.0, total_duration_ms - covered)
    return DurationCoverage(
        attributed_ms=covered,
        unattributed_ms=residual,
        coverage_pct=100.0 if total_duration_ms == 0 else 100.0 * covered / total_duration_ms,
        overlapping_ms=max(0.0, sum_durations - covered),
    )


@dataclass(frozen=True, slots=True)
class ProviderCallEvidence:
    """Expose safe metadata for one provider call within an operational stage."""

    name: str
    outcome: OperationalOutcome
    duration_ms: float | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    usage: dict[str, int] | None = None
    error_category: str | None = None
    validation_stage: str | None = None
    validation_code: str | None = None
    attempt_count: int | None = None
    response_id: str | None = None
    provider_status: str | None = None
    incomplete_reason: str | None = None
    output_text_chars: int | None = None
    output_text_bytes: int | None = None
    parse_status: str | None = None
    result_kind: str | None = None
    result_counts: dict[str, int] | None = None
    start_offset_ms: float | None = None
    ordinal: int | None = None
    substeps: tuple[OperationalSpan, ...] = ()
    input_sizes: dict[str, int] | None = None


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
    provider_calls: tuple[ProviderCallEvidence, ...] = ()
    start_offset_ms: float | None = None
    substeps: tuple[OperationalSpan, ...] = ()


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
