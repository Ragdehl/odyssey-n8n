"""Content-free deterministic diagnostic rendering for one bounded P1 request."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any

from odyssey_core.observability import reconcile_duration


def _estimated_call_cost(call: dict[str, Any], pricing: dict[str, Any]) -> Decimal | None:
    """Price supplied usage once, with unavailable rather than fabricated zero counters."""
    usage = call.get("usage")
    rates = pricing.get("models", {}).get(call.get("model"))
    if not isinstance(usage, dict) or not isinstance(rates, dict):
        return None
    counters = (
        usage.get("input_tokens"),
        usage.get("cached_input_tokens"),
        usage.get("output_tokens"),
    )
    if any(type(value) is not int or value < 0 for value in counters):
        return None
    input_tokens, cached_tokens, output_tokens = counters
    if cached_tokens > input_tokens or usage.get("cache_write_tokens", 0) != 0:
        return None
    try:
        ordinary_rate = Decimal(str(rates["input_per_million"]))
        cached_rate = Decimal(str(rates["cached_input_per_million"]))
        output_rate = Decimal(str(rates["output_per_million"]))
    except (KeyError, InvalidOperation, TypeError):
        return None
    if not all(
        rate.is_finite() and rate >= 0 for rate in (ordinary_rate, cached_rate, output_rate)
    ):
        return None
    return (
        (input_tokens - cached_tokens) * ordinary_rate
        + cached_tokens * cached_rate
        + output_tokens * output_rate
    ) / Decimal(1_000_000)


def format_request_report(
    case_id: str, operational: dict[str, Any], pricing: dict[str, Any]
) -> str:
    """Show parent wall, child intervals, residual coverage, and independent call costs.

    Raises:
        ValueError: When the root timing hierarchy cannot be reconciled safely.
    """
    total = operational.get("total_duration_ms")
    coverage = operational.get("coverage")
    stages = operational.get("stages")
    if (
        type(total) not in (int, float)
        or not isfinite(total)
        or total < 0
        or not isinstance(coverage, dict)
        or type(coverage.get("coverage_pct")) not in (int, float)
        or type(coverage.get("unattributed_ms")) not in (int, float)
        or not isinstance(stages, list)
    ):
        raise ValueError("request timing coverage is unavailable")
    intervals = []
    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError("request stage is malformed")
        start, duration = stage.get("start_offset_ms"), stage.get("duration_ms")
        if start is None or duration is None:
            continue
        if type(start) not in (int, float) or type(duration) not in (int, float):
            raise ValueError("request timing coverage is unavailable")
        intervals.append((start, duration))
    actual_coverage = reconcile_duration(total, tuple(intervals))
    if actual_coverage is None or (
        abs(actual_coverage.coverage_pct - coverage["coverage_pct"]) > 0.01
        or abs(actual_coverage.unattributed_ms - coverage["unattributed_ms"]) > 0.01
    ):
        raise ValueError("request timing coverage does not reconcile")
    lines = [
        f"CASE {case_id}",
        f"REQUEST {total:.1f} ms",
        f"COVERAGE {coverage['coverage_pct']:.1f}%",
        f"UNATTRIBUTED {coverage['unattributed_ms']:.1f} ms",
    ]
    costs: list[Decimal | None] = []
    for stage in stages:
        lines.append(f"{stage['name']} {stage.get('duration_ms')} ms [{stage['outcome']}]")
        for span in stage.get("substeps", ()):
            lines.append(f"  {span['name']} {span['duration_ms']} ms [{span['outcome']}]")
        for call in stage.get("provider_calls", ()):
            cost = _estimated_call_cost(call, pricing)
            costs.append(cost)
            usage = call.get("usage") or {}
            token_text = (
                f"{usage.get('input_tokens', '—')} -> {usage.get('output_tokens', '—')} tokens"
            )
            price_text = f"${cost:.6f}" if cost is not None else "unavailable"
            lines.append(
                f"  {call['name']} #{call.get('ordinal', '—')} {call.get('model') or '—'} "
                f"{call.get('duration_ms')} ms {token_text} {price_text} [{call['outcome']}]"
            )
            if call.get("validation_code"):
                lines.append(
                    f"    validation {call.get('validation_stage') or '—'}: {call['validation_code']}"
                )
            for span in call.get("substeps", ()):
                lines.append(f"    {span['name']} {span['duration_ms']} ms [{span['outcome']}]")
    total_cost = (
        sum(costs, Decimal(0)) if costs and all(cost is not None for cost in costs) else None
    )
    lines.append(
        f"API ESTIMATE {f'${total_cost:.6f}' if total_cost is not None else 'unavailable'}"
    )
    lines.append(f"PRICING BASIS {pricing.get('as_of', 'unavailable')}")
    return "\n".join(lines)
