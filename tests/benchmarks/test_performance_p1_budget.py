"""Provider-free P1A oracles for the hard live-baseline budget boundary."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.performance_p1.budget import (
    BudgetError,
    BudgetGuard,
    CallBound,
    CaseEnvelope,
    load_pricing,
    worst_case_cost,
)
from benchmarks.performance_p1.report import format_request_report
from benchmarks.performance_p1.run_live import main as live_main
from benchmarks.performance_p1.runner import CaseResult, run_cases

PRICING = {
    "as_of": "2026-09-07",
    "long_context_threshold_input_tokens": 272_000,
    "models": {
        "luna": {
            "input_per_million": 1,
            "cached_input_per_million": 0.1,
            "cache_write_per_million": 1,
            "output_per_million": 2,
        },
        "sol": {
            "input_per_million": 10,
            "cached_input_per_million": 1,
            "cache_write_per_million": 10,
            "output_per_million": 20,
        },
    },
}
EMPTY_OPERATIONAL = {
    "total_duration_ms": 1,
    "coverage": {
        "attributed_ms": 0,
        "unattributed_ms": 1,
        "coverage_pct": 0,
        "overlapping_ms": 0,
    },
    "stages": [],
}


def envelope(case_id: str, *, sol_tokens: int = 1000) -> CaseEnvelope:
    """Reserve Luna and a possible Sol fallback for one whole synthetic request."""
    return CaseEnvelope(
        case_id,
        (
            CallBound("planner.luna", "luna", 1000, 1000, 1),
            CallBound("planner.sol_fallback", "sol", sol_tokens, sol_tokens, 1),
        ),
        True,
    )


def test_next_request_is_refused_before_executor_when_worst_case_exceeds_cap(tmp_path) -> None:
    """A cheap first result cannot permit the next bounded request to exceed USD 0.20."""
    invoked: list[str] = []

    def executor(case: dict) -> CaseResult:
        invoked.append(case["id"])
        return CaseResult(True, "completed", Decimal("0.001"), EMPTY_OPERATIONAL)

    evidence = tmp_path / "evidence.jsonl"
    guard = BudgetGuard(PRICING)
    with pytest.raises(BudgetError, match="could exceed"):
        run_cases(
            [{"id": "first"}, {"id": "second"}],
            {"first": envelope("first"), "second": envelope("second", sol_tokens=7000)},
            executor,
            guard,
            evidence,
            confirmed=True,
        )
    assert invoked == ["first"]
    rows = evidence.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["case_id"] == "first"
    assert guard.charged == worst_case_cost(envelope("first"), PRICING)


def test_missing_usage_consumes_full_reserve_and_prevents_overspend(tmp_path) -> None:
    """Unavailable provider usage never becomes a zero-dollar charge."""
    invoked: list[str] = []

    def executor(case: dict) -> CaseResult:
        invoked.append(case["id"])
        return CaseResult(True, "completed", None, EMPTY_OPERATIONAL)

    guard = BudgetGuard(PRICING, Decimal("0.06"))
    with pytest.raises(BudgetError, match="could exceed"):
        run_cases(
            [{"id": "first"}, {"id": "second"}],
            {"first": envelope("first"), "second": envelope("second")},
            executor,
            guard,
            tmp_path / "evidence.jsonl",
            confirmed=True,
        )
    assert invoked == ["first"]
    assert guard.charged == worst_case_cost(envelope("first"), PRICING)


def test_runner_requires_confirmation_and_never_overwrites_evidence(tmp_path) -> None:
    """Neither an absent confirmation nor an existing artifact reaches an executor."""
    called = False

    def executor(_case: dict) -> CaseResult:
        nonlocal called
        called = True
        raise AssertionError("executor must not run")

    evidence = tmp_path / "evidence.jsonl"
    with pytest.raises(ValueError, match="explicit confirmation"):
        run_cases([], {}, executor, BudgetGuard(PRICING), evidence, confirmed=False)
    assert not evidence.exists()
    evidence.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_cases([], {}, executor, BudgetGuard(PRICING), evidence, confirmed=True)
    assert evidence.read_text(encoding="utf-8") == "existing" and not called


def test_live_entry_point_requires_explicit_confirmation(tmp_path) -> None:
    """The live command does not reach the DEV path without an explicit acknowledgement."""
    evidence = tmp_path / "future.jsonl"
    with pytest.raises(SystemExit, match="without --confirm-live-provider-calls"):
        live_main(["--evidence-path", str(evidence)])
    assert not evidence.exists()


def test_unverified_or_malformed_bounds_fail_before_request(tmp_path) -> None:
    """Pricing, call count, and verified upper bounds are mandatory before any request."""
    invoked = False

    def executor(_case: dict) -> CaseResult:
        nonlocal invoked
        invoked = True
        raise AssertionError("executor must not run")

    invalid = CaseEnvelope("bad", (CallBound("planner", "luna", 100, 100, 1),), False)
    with pytest.raises(BudgetError, match="unverified"):
        run_cases(
            [{"id": "bad"}],
            {"bad": invalid},
            executor,
            BudgetGuard(PRICING),
            tmp_path / "bad.jsonl",
            confirmed=True,
        )
    assert not invoked
    assert worst_case_cost(envelope("safe"), PRICING) == Decimal("0.033")
    with pytest.raises(BudgetError, match="invalid"):
        worst_case_cost(
            CaseEnvelope("bad", (CallBound("planner", "luna", True, 100, 1),), True),
            PRICING,
        )


def test_malformed_result_stops_without_retry(tmp_path) -> None:
    """One malformed result stops after the only executor invocation."""
    calls = 0

    def executor(_case: dict) -> object:
        nonlocal calls
        calls += 1
        return {"status": "completed"}

    with pytest.raises(ValueError, match="malformed evidence"):
        run_cases(
            [{"id": "first"}],
            {"first": envelope("first")},
            executor,
            BudgetGuard(PRICING),
            tmp_path / "evidence.jsonl",
            confirmed=True,
        )
    assert calls == 1


def test_diagnostic_report_preserves_two_attempts_and_unavailable_cost() -> None:
    """The report never hides fallback or invents missing usage."""
    operational = {
        "total_duration_ms": 9000,
        "coverage": {"coverage_pct": 90, "unattributed_ms": 900},
        "stages": [
            {
                "name": "planner",
                "outcome": "completed",
                "duration_ms": 8100,
                "start_offset_ms": 0,
                "provider_calls": [
                    {
                        "name": "planner.luna",
                        "ordinal": 1,
                        "model": "luna",
                        "duration_ms": 3000,
                        "outcome": "failed",
                        "usage": {
                            "input_tokens": 1000,
                            "cached_input_tokens": 0,
                            "output_tokens": 100,
                        },
                        "validation_stage": "SELECTION",
                        "validation_code": "EMPTY_QUERY",
                    },
                    {
                        "name": "planner.sol_fallback",
                        "ordinal": 2,
                        "model": "sol",
                        "duration_ms": 5000,
                        "outcome": "completed",
                        "usage": None,
                    },
                ],
            }
        ],
    }
    text = format_request_report("R1", operational, PRICING)
    assert "planner.luna #1" in text and "planner.sol_fallback #2" in text
    assert "validation SELECTION: EMPTY_QUERY" in text
    assert "API ESTIMATE unavailable" in text
    assert "PRICING BASIS 2026-09-07" in text
    operational["stages"][0]["duration_ms"] = 9100
    with pytest.raises(ValueError, match="does not reconcile"):
        format_request_report("R1", operational, PRICING)


def test_exact_full_request_reserve_is_allowed_and_never_released() -> None:
    """The guard admits equality and retains the full bound after cheaper actual usage."""
    request = envelope("exact")
    amount = worst_case_cost(request, PRICING)
    guard = BudgetGuard(PRICING, amount)
    assert guard.reserve(request) == amount
    assert guard.finish(Decimal("0.001")) == amount
    assert guard.charged == amount
    with pytest.raises(BudgetError, match="could exceed"):
        guard.reserve(request)


def test_invalid_observed_cost_does_not_release_possible_spend() -> None:
    """A malformed post-call estimate cannot make already possible billing disappear."""
    request = envelope("one")
    amount = worst_case_cost(request, PRICING)
    guard = BudgetGuard(PRICING, amount)
    guard.reserve(request)
    with pytest.raises(BudgetError, match="exceeded"):
        guard.finish(amount + Decimal("0.001"))
    assert guard.charged == amount
    with pytest.raises(BudgetError, match="could exceed"):
        guard.reserve(request)


def test_unknown_model_and_missing_output_bound_refuse() -> None:
    """An unknown rate or output maximum cannot be priced as zero."""
    with pytest.raises(BudgetError, match="no dated price"):
        worst_case_cost(
            CaseEnvelope("unknown", (CallBound("answerer", "unknown", 100, 100, 1),), True),
            PRICING,
        )
    with pytest.raises(BudgetError, match="invalid"):
        worst_case_cost(
            CaseEnvelope("uncapped", (CallBound("answerer", "luna", 100, None, 1),), True),  # type: ignore[arg-type]
            PRICING,
        )
    missing_write_rate = {
        **PRICING,
        "models": {
            "luna": {
                key: value
                for key, value in PRICING["models"]["luna"].items()
                if key != "cache_write_per_million"
            }
        },
    }
    with pytest.raises(BudgetError, match="price is invalid"):
        worst_case_cost(
            CaseEnvelope("missing", (CallBound("answerer", "luna", 100, 100, 1),), True),
            missing_write_rate,
        )


def test_long_context_without_frozen_uplift_refuses() -> None:
    """The guard cannot underprice the model's published long-context tier."""
    frozen = {
        "long_context_threshold_input_tokens": 272_000,
        "models": {
            "gpt-5.6-sol": {
                "input_per_million": 4,
                "cached_input_per_million": 0.4,
                "cache_write_per_million": 5,
                "output_per_million": 20,
            }
        },
    }
    with pytest.raises(BudgetError, match="long-context price"):
        worst_case_cost(
            CaseEnvelope(
                "large",
                (CallBound("planner.sol_fallback", "gpt-5.6-sol", 272_001, 4096, 1),),
                True,
            ),
            frozen,
        )


def test_frozen_pricing_uses_correct_tier_and_no_cache_savings() -> None:
    """The worst-case reserve includes cache-write and whole-call long-context rates."""
    pricing = load_pricing()
    assert pricing["as_of"] == "2026-09-23"
    at_threshold = CaseEnvelope(
        "short", (CallBound("planner.sol_fallback", "gpt-5.6-sol", 272_000, 4096, 1),), True
    )
    above_threshold = CaseEnvelope(
        "long", (CallBound("planner.sol_fallback", "gpt-5.6-sol", 272_001, 4096, 1),), True
    )
    assert worst_case_cost(at_threshold, pricing) == Decimal("1.44192")
    assert worst_case_cost(above_threshold, pricing) == Decimal("2.84289")


def test_snapshot_with_wrong_tier_or_threshold_refuses(tmp_path) -> None:
    """A future baseline cannot silently use a different service or threshold."""
    pricing = load_pricing()
    path = tmp_path / "wrong-pricing.json"
    for override in ({"service_tier": "fast"}, {"long_context_threshold_input_tokens": 999_999}):
        path.write_text(json.dumps({**pricing, **override}), encoding="utf-8")
        with pytest.raises(BudgetError, match="snapshot is invalid"):
            load_pricing(path)


def test_report_prices_observed_long_context_and_cache_write() -> None:
    """Observed usage uses its actual tier while preserving missing data as unavailable."""
    from benchmarks.performance_p1.report import _estimated_call_cost

    pricing = load_pricing()
    call = {
        "model": "gpt-5.6-sol",
        "usage": {
            "input_tokens": 272_001,
            "cached_input_tokens": 0,
            "cache_write_tokens": 1,
            "output_tokens": 100,
        },
    }
    assert _estimated_call_cost(call, pricing) == Decimal("2.17901")
    del call["usage"]["output_tokens"]
    assert _estimated_call_cost(call, pricing) is None


def test_frozen_case_audit_fails_closed_and_read_witness_exceeds_ceiling() -> None:
    """Current product paths have no certified per-case envelope under USD 0.20."""
    root = Path(__file__).resolve().parents[2]
    audit = json.loads(
        (root / "benchmarks/performance_p1/envelope_audit.json").read_text(encoding="utf-8")
    )
    assert set(audit["cases"]) == {"R1", "R2", "W1", "W2", "W3", "C1", "N1"}
    assert audit["certified"] is False
    assert audit["seven_case_max_usd"] is None
    assert all(case["max_cost_usd"] is None for case in audit["cases"].values())
    rates = audit["roles"]
    output_only = sum(
        (
            Decimal(
                str(
                    rates[name]["configured_max_output_tokens"]
                    or audit["model_hard_max_output_tokens"]
                )
            )
            * Decimal(rates[name]["frozen_rate_usd_per_million"]["output_including_reasoning"])
            / Decimal(1_000_000)
        )
        for name in ("planner.luna", "planner.sol_fallback", "answerer")
    )
    assert output_only == Decimal(audit["output_only_read_fallback_witness_usd"])
    assert output_only > Decimal(audit["ceiling_usd"])
    planner_only = sum(
        (
            Decimal(rates[name]["configured_max_output_tokens"])
            * Decimal(rates[name]["frozen_rate_usd_per_million"]["output_including_reasoning"])
            / Decimal(1_000_000)
        )
        for name in ("planner.luna", "planner.sol_fallback")
    )
    assert planner_only * 7 == Decimal(audit["seven_case_planner_output_only_witness_usd"])
