"""Run only the unattempted S04/S05 suffix of frozen Slice 3 evidence once authorized."""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.reference_relationship_v1.evaluate import load_frozen_registry  # noqa: E402
from benchmarks.reference_relationship_v1.run_live import (  # noqa: E402
    SCHEMA_PATH,
    conservative_cost_ceiling,
    run_cases,
)
from odyssey_core.cost_aware_planning import LunaFirstRequestPlanner  # noqa: E402

EXPECTED_FROZEN_CASE_IDS = (
    "R01",
    "W01",
    "W02",
    "C01",
    "P01",
    "S01",
    "S02",
    "S03",
    "S04",
    "S05",
)
CONTINUATION_CASE_IDS = ("S04", "S05")
OUTPUT_PATH = (
    ROOT / "benchmarks" / ".live-results" / "reference-relationship-v1-attempt-3-continuation.jsonl"
)
MAX_COST_USD = Decimal("0.37")


def load_continuation_cases() -> tuple[
    dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]
]:
    """Verify the original frozen registry and return only its fixed unattempted suffix.

    Raises:
        ValueError: If the frozen registry or oracle order has changed, or the exact suffix is absent.
    """
    registry, oracles = load_frozen_registry()
    case_ids = tuple(case["id"] for case in registry["cases"])
    if case_ids != EXPECTED_FROZEN_CASE_IDS or tuple(oracles) != EXPECTED_FROZEN_CASE_IDS:
        raise ValueError("Continuation requires the original ordered ten-case registry")
    cases = [case for case in registry["cases"] if case["id"] in CONTINUATION_CASE_IDS]
    if tuple(case["id"] for case in cases) != CONTINUATION_CASE_IDS:
        raise ValueError("Continuation requires exactly the fixed S04/S05 suffix")
    return registry, cases, oracles


def main(argv: list[str] | None = None) -> int:
    """Refuse unapproved continuation calls before reserving evidence or constructing a provider."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    registry, cases, oracles = load_continuation_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, luna_input, sol_input = conservative_cost_ceiling(
        cases, registry["fixed_context"], schema
    )
    print(
        f"logical_cases={len(cases)} provider_call_ceiling={len(cases) + 1} "
        f"no_cache_max_usd={cost:.6f} luna_input_bound={luna_input} "
        f"sol_input_bound={sol_input}"
    )
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    if cost > MAX_COST_USD:
        raise SystemExit(
            "Refusing live calls: continuation requires a fresh explicit cost authorization"
        )
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Refusing live calls: OPENAI_API_KEY is absent from process environment")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        evidence = OUTPUT_PATH.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise SystemExit(f"Refusing to overwrite existing evidence: {OUTPUT_PATH}") from error
    try:
        planner = LunaFirstRequestPlanner.from_environment(schema, registry["fixed_context"])
        run_cases(planner, cases, oracles, evidence)
    finally:
        evidence.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
