"""Authorization-gated continuation for the nine never-attempted cases."""

from __future__ import annotations

import argparse
import json

from benchmarks.luna_first_planner.evaluate_atomicity import evaluate_atomicity, load_registry
from benchmarks.luna_first_planner.evaluate_v2 import evaluate_result_v2, load_frozen_registry_v2
from benchmarks.luna_first_planner.run_atomicity_live import _run_set
from benchmarks.luna_first_planner.run_continuation import reserve_evidence_path_at
from benchmarks.luna_first_planner.run_live_v2 import SCHEMA_PATH
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner

CONTINUATION_IDS = ("AT09", "AT10", "HD03", "HO02", "SW01", "SD02", "SC02", "SE01", "SA02")
OUTPUT_PATH = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "benchmarks/.live-results/luna-atomicity-continuation-v1.jsonl"
)


def main(argv: list[str] | None = None) -> int:
    """Run only the closed continuation set after exclusive evidence reservation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    if not parser.parse_args(argv).confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    atomic_cases, atomic_oracles = load_registry()
    v2_cases, v2_oracles = load_frozen_registry_v2()
    cases = {case["id"]: case for case in atomic_cases["cases"]}
    cases.update({case["id"]: case for case in v2_cases["cases"]})
    selected = [cases[case_id] for case_id in CONTINUATION_IDS]
    with reserve_evidence_path_at(OUTPUT_PATH) as evidence:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, atomic_cases["fixed_context"]
        )
        if _run_set(
            planner,
            selected[:2],
            atomic_oracles,
            evidence,
            "held_out",
            lambda _: evaluate_atomicity,
        ):
            return 0
        if _run_set(
            planner,
            selected[2:],
            v2_oracles,
            evidence,
            "regression_sentinel",
            lambda case_id: lambda result, oracle: evaluate_result_v2(case_id, result, oracle),
        ):
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
