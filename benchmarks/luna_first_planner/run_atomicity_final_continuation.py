"""Authorization-gated Luna-only continuation for the two untouched sentinels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.luna_first_planner.evaluate_atomicity import load_registry
from benchmarks.luna_first_planner.evaluate_v2 import evaluate_result_v2, load_frozen_registry_v2
from benchmarks.luna_first_planner.run_atomicity_live import _run_set
from benchmarks.luna_first_planner.run_continuation import reserve_evidence_path_at
from benchmarks.luna_first_planner.run_live_v2 import SCHEMA_PATH
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner

ROOT = Path(__file__).resolve().parents[2]
FINAL_CONTINUATION_IDS = ("SE01", "SA02")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/luna-atomicity-final-continuation-v1.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Run exactly the two evidence-confirmed untouched sentinels once."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")

    atomic_cases, _ = load_registry()
    v2_cases, v2_oracles = load_frozen_registry_v2()
    cases_by_id = {case["id"]: case for case in v2_cases["cases"]}
    selected = [cases_by_id[case_id] for case_id in FINAL_CONTINUATION_IDS]
    if tuple(case["id"] for case in selected) != FINAL_CONTINUATION_IDS:
        raise SystemExit("Final continuation case registry drifted")

    with reserve_evidence_path_at(OUTPUT_PATH) as evidence:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, atomic_cases["fixed_context"]
        )
        _run_set(
            planner,
            selected,
            v2_oracles,
            evidence,
            "regression_sentinel",
            lambda case_id: lambda result, oracle: evaluate_result_v2(case_id, result, oracle),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
