"""Conservative, provider-free cost reservations for a future P1 live baseline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PRICING_PATH = Path(__file__).with_name("pricing_snapshot.json")
INITIAL_CEILING_USD = Decimal("0.20")


class BudgetError(ValueError):
    """Reject an unverified or unaffordable provider-call envelope before execution."""


@dataclass(frozen=True, slots=True)
class CallBound:
    """Bound all calls of one model/role that one frozen request could trigger."""

    name: str
    model: str
    max_input_tokens: int
    max_output_tokens: int
    max_calls: int


@dataclass(frozen=True, slots=True)
class CaseEnvelope:
    """Declare a reviewed upper bound for the entire request, including fallback."""

    case_id: str
    calls: tuple[CallBound, ...]
    verified: bool


def load_pricing(path: Path = PRICING_PATH) -> dict[str, Any]:
    """Load the dated P1 Standard-tier pricing authority without network access."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("service_tier") != "standard"
        or not isinstance(value.get("as_of"), str)
        or not isinstance(value.get("models"), dict)
        or value.get("long_context_threshold_input_tokens") != 272_000
    ):
        raise BudgetError("pricing snapshot is invalid")
    return value


def worst_case_cost(envelope: CaseEnvelope, pricing: dict[str, Any]) -> Decimal:
    """Price each reviewed call at its most expensive permitted input and output tier.

    The caller must prove that input-token and call-count bounds are true for the selected
    disposable runtime path. If it cannot, ``verified`` must remain false and execution refuses.
    """
    if not envelope.verified or not envelope.calls:
        raise BudgetError("request cost envelope is unverified")
    if not isinstance(pricing, dict):
        raise BudgetError("pricing snapshot is invalid")
    threshold = pricing.get("long_context_threshold_input_tokens")
    if type(threshold) is not int or threshold < 1 or not isinstance(pricing.get("models"), dict):
        raise BudgetError("pricing snapshot has no reviewed context tier")
    total = Decimal(0)
    for bound in envelope.calls:
        if (
            not bound.name
            or type(bound.max_input_tokens) is not int
            or type(bound.max_output_tokens) is not int
            or type(bound.max_calls) is not int
            or min(bound.max_input_tokens, bound.max_output_tokens) <= 0
            or bound.max_calls < 1
        ):
            raise BudgetError("request call bound is invalid")
        rates = pricing["models"].get(bound.model)
        if not isinstance(rates, dict):
            raise BudgetError("request model has no dated price")
        tier = rates.get("long_context") if bound.max_input_tokens > threshold else rates
        if not isinstance(tier, dict):
            raise BudgetError("request model has no reviewed long-context price")
        try:
            input_rates = tuple(
                Decimal(str(tier[key]))
                for key in (
                    "input_per_million",
                    "cached_input_per_million",
                    "cache_write_per_million",
                )
            )
            output_rate = Decimal(str(tier["output_per_million"]))
        except (KeyError, InvalidOperation, TypeError) as error:
            raise BudgetError("request model price is invalid") from error
        if any(not rate.is_finite() or rate < 0 for rate in (*input_rates, output_rate)):
            raise BudgetError("request model price is invalid")
        # Cache savings are not guaranteed. Cache writes can exceed ordinary input pricing.
        input_rate = max(input_rates)
        total += (
            bound.max_calls
            * (bound.max_input_tokens * input_rate + bound.max_output_tokens * output_rate)
            / Decimal(1_000_000)
        )
    return total


class BudgetGuard:
    """Reserve the entire worst-case next request before its first provider call."""

    def __init__(self, pricing: dict[str, Any], ceiling: Decimal = INITIAL_CEILING_USD) -> None:
        if ceiling <= 0 or ceiling > INITIAL_CEILING_USD:
            raise BudgetError("initial P1 ceiling must be within USD 0.20")
        self.pricing = pricing
        self.ceiling = ceiling
        self.charged = Decimal(0)
        self._reservation: Decimal | None = None

    def reserve(self, envelope: CaseEnvelope) -> Decimal:
        """Refuse an unsafe next request before the runner invokes its executor."""
        if self._reservation is not None:
            raise BudgetError("another request is already reserved")
        amount = worst_case_cost(envelope, self.pricing)
        if self.charged + amount > self.ceiling:
            raise BudgetError("next request could exceed the hard USD 0.20 ceiling")
        self._reservation = amount
        return amount

    def finish(self, measured_cost: Decimal | None) -> Decimal:
        """Keep the full worst-case reserve while recording actual cost separately.

        The reserve is not released between requests because incomplete call evidence or billing
        variance must never let a later request bypass the hard run ceiling.
        """
        if self._reservation is None:
            raise BudgetError("request has no cost reservation")
        reservation = self._reservation
        self._reservation = None
        # A request may already have billed provider work even when its reported cost is
        # malformed. Never release that possible spend into a later request's budget.
        self.charged += reservation
        if measured_cost is not None and (
            not isinstance(measured_cost, Decimal)
            or not measured_cost.is_finite()
            or measured_cost < 0
            or measured_cost > reservation
        ):
            raise BudgetError("observed cost exceeded its reviewed request bound")
        return reservation
