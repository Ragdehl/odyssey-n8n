"""Load the immutable five-case targeted Phase 15 follow-up experiment."""

from __future__ import annotations

from pathlib import Path

from benchmarks.phase14_request_plan_v3.benchmark import BenchmarkContractError, load_json

BENCHMARK_DIR = Path(__file__).resolve().parent
CASES_PATH = BENCHMARK_DIR / "cases.json"


def load_cases() -> list[dict[str, str]]:
    """Load the five human-approved targeted follow-up cases.

    Returns:
        The ordered targeted requests T01 through T05.

    Raises:
        BenchmarkContractError: If the targeted experiment is altered or malformed.
    """
    cases = load_json(CASES_PATH).get("cases")
    expected_ids = [f"T{index:02}" for index in range(1, 6)]
    if not isinstance(cases, list) or len(cases) != len(expected_ids):
        raise BenchmarkContractError("Phase 15 targeted cases must be exactly T01 through T05")
    if (
        any(not isinstance(case, dict) or set(case) != {"id", "request"} for case in cases)
        or [case["id"] for case in cases] != expected_ids
        or any(
            not isinstance(case["request"], str) or not case["request"].strip() for case in cases
        )
    ):
        raise BenchmarkContractError("Phase 15 targeted cases must be exactly T01 through T05")
    return cases
