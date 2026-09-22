"""Conservative, provider-free cost reservations for a future P1 live baseline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PRICING_PATH = Path(__file__).resolve().parents[1] / "phase20_answerer/pricing_snapshot.json"
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
    """Load the existing dated benchmark pricing authority without network access."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("models"), dict):
        raise BudgetError("pricing snapshot is invalid")
    return value


def worst_case_cost(envelope: CaseEnvelope, pricing: dict[str, Any]) -> Decimal:
    """Price uncached maximum input and output for every possible call in a reviewed envelope.

    The caller must prove that input-token and call-count bounds are true for the selected
    disposable runtime path. If it cannot, ``verified`` must remain false and execution refuses.
    """
    if not envelope.verified or not envelope.calls:
        raise BudgetError("request cost envelope is unverified")
    total = Decimal(0)
    for bound in envelope.calls:
        if (
            not bound.name
            or type(bound.max_input_tokens) is not int
            or type(bound.max_output_tokens) is not int
            or type(bound.max_calls) is not int
            or min(bound.max_input_tokens, bound.max_output_tokens) < 0
            or bound.max_calls < 1
        ):
            raise BudgetError("request call bound is invalid")
        rates = pricing["models"].get(bound.model)
        if not isinstance(rates, dict):
            raise BudgetError("request model has no dated price")
        try:
            input_rate = Decimal(str(rates["input_per_million"]))
            output_rate = Decimal(str(rates["output_per_million"]))
        except (KeyError, InvalidOperation, TypeError) as error:
            raise BudgetError("request model price is invalid") from error
        if (
            not input_rate.is_finite()
            or not output_rate.is_finite()
            or min(input_rate, output_rate) < 0
        ):
            raise BudgetError("request model price is invalid")
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
        if measured_cost is not None and (
            not isinstance(measured_cost, Decimal)
            or not measured_cost.is_finite()
            or measured_cost < 0
            or measured_cost > reservation
        ):
            raise BudgetError("observed cost exceeded its reviewed request bound")
        self.charged += reservation
        return reservation
