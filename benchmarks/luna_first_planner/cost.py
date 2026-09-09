"""Deterministic, usage-backed cost accounting for Luna-first routing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from benchmarks.luna_first_planner.evaluate import Classification

USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
    "reasoning_tokens",
)


@dataclass(frozen=True, slots=True)
class UsageTotals:
    """Keep all provider token categories separate, including non-extra-billed reasoning."""

    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    reasoning_tokens: int


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """Represent component costs derived from one dated pricing snapshot."""

    ordinary_input_usd: Decimal
    cached_input_usd: Decimal
    cache_write_usd: Decimal
    output_usd: Decimal
    total_usd: Decimal


@dataclass(frozen=True, slots=True)
class RoutingCostComparison:
    """Compare Sol-always with Luna plus Sol only after recorded escalation."""

    sol_always_usd: Decimal | None
    luna_first_usd: Decimal | None
    savings_usd: Decimal | None
    unavailable_reasons: tuple[str, ...]


def parse_usage(value: Mapping[str, Any]) -> UsageTotals | None:
    """Parse only complete, non-negative actual usage without filling missing counters."""
    if any(not isinstance(value.get(field), int) or value[field] < 0 for field in USAGE_FIELDS):
        return None
    return UsageTotals(**{field: value[field] for field in USAGE_FIELDS})


def aggregate_usage(values: Sequence[Mapping[str, Any]]) -> UsageTotals | None:
    """Sum complete actual usage records while preserving each counter category."""
    parsed = [parse_usage(value) for value in values]
    if any(value is None for value in parsed):
        return None
    return UsageTotals(
        **{
            field: sum(getattr(value, field) for value in parsed if value is not None)
            for field in USAGE_FIELDS
        }
    )


def estimate_usage_cost(usage: UsageTotals, rates: Mapping[str, Any]) -> CostEstimate | None:
    """Price actual usage, returning unavailable when a required rate or counter is unsafe."""
    input_rate = _rate(rates, "input_per_million", "input")
    cached_rate = _rate(rates, "cached_input_per_million", "cached_input")
    output_rate = _rate(rates, "output_per_million", "output")
    cache_write_rate = _rate(rates, "cache_write_per_million", "cache_write")
    if input_rate is None or cached_rate is None or output_rate is None:
        return None
    if usage.cache_write_tokens and cache_write_rate is None:
        return None
    cache_write_rate = cache_write_rate or Decimal(0)
    ordinary_tokens = usage.input_tokens - usage.cached_input_tokens - usage.cache_write_tokens
    if ordinary_tokens < 0 or usage.reasoning_tokens > usage.output_tokens:
        return None
    million = Decimal(1_000_000)
    ordinary_cost = Decimal(ordinary_tokens) * input_rate / million
    cached_cost = Decimal(usage.cached_input_tokens) * cached_rate / million
    cache_write_cost = Decimal(usage.cache_write_tokens) * cache_write_rate / million
    output_cost = Decimal(usage.output_tokens) * output_rate / million
    return CostEstimate(
        ordinary_input_usd=ordinary_cost,
        cached_input_usd=cached_cost,
        cache_write_usd=cache_write_cost,
        output_usd=output_cost,
        total_usd=ordinary_cost + cached_cost + cache_write_cost + output_cost,
    )


def compare_routing_costs(
    case_ids: Sequence[str],
    classifications: Mapping[str, Classification],
    luna_usage: Mapping[str, Mapping[str, Any]],
    sol_usage: Mapping[str, Mapping[str, Any]],
    pricing_models: Mapping[str, Mapping[str, Any]],
) -> RoutingCostComparison:
    """Compare routes using actual counters only; never synthesize missing fallback usage."""
    reasons: list[str] = []
    sol_all = _cost_for_cases(case_ids, sol_usage, pricing_models.get("gpt-5.6-sol"))
    if sol_all is None:
        reasons.append("sol_always_usage_or_pricing_unavailable")
    luna_all = _cost_for_cases(case_ids, luna_usage, pricing_models.get("gpt-5.6-luna"))
    if luna_all is None:
        reasons.append("luna_usage_or_pricing_unavailable")
    escalated_ids = [
        case_id
        for case_id in case_ids
        if classifications.get(case_id)
        in {
            Classification.SAFE_ESCALATE,
            Classification.FORCED_ESCALATE,
            Classification.INVALID_FAIL_CLOSED,
        }
    ]
    sol_fallback = _cost_for_cases(escalated_ids, sol_usage, pricing_models.get("gpt-5.6-sol"))
    if sol_fallback is None:
        reasons.append("sol_fallback_usage_or_pricing_unavailable")
    luna_first = None if luna_all is None or sol_fallback is None else luna_all + sol_fallback
    savings = None if sol_all is None or luna_first is None else sol_all - luna_first
    return RoutingCostComparison(sol_all, luna_first, savings, tuple(reasons))


def _cost_for_cases(
    case_ids: Sequence[str],
    usage_by_case: Mapping[str, Mapping[str, Any]],
    rates: Mapping[str, Any] | None,
) -> Decimal | None:
    """Return a usage-backed total for exactly the requested IDs."""
    if rates is None or any(case_id not in usage_by_case for case_id in case_ids):
        return None
    usage = aggregate_usage([usage_by_case[case_id] for case_id in case_ids])
    estimate = None if usage is None else estimate_usage_cost(usage, rates)
    return None if estimate is None else estimate.total_usd


def _rate(rates: Mapping[str, Any], current: str, historical: str) -> Decimal | None:
    """Read either supported dated repository pricing shape without changing its evidence."""
    raw = rates.get(current, rates.get(historical))
    if not isinstance(raw, (int, float, str)) or isinstance(raw, bool):
        return None
    return Decimal(str(raw))
