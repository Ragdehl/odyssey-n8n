"""Authorization-gated Luna-only runner for atomicity cases and sentinels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.luna_first_planner.evaluate_atomicity import evaluate_atomicity, load_registry
from benchmarks.luna_first_planner.evaluate_v2 import evaluate_result_v2, load_frozen_registry_v2
from benchmarks.luna_first_planner.run_continuation import reserve_evidence_path_at
from benchmarks.luna_first_planner.run_live_v2 import SCHEMA_PATH
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner

ROOT = Path(__file__).resolve().parents[2]
CASE_IDS = tuple(f"AT{index:02d}" for index in range(1, 11))
SENTINEL_IDS = ("HD03", "HO02", "SW01", "SD02", "SC02", "SE01", "SA02")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/luna-atomicity-v1.jsonl"


def frozen_cases() -> list[dict[str, str]]:
    """Return the exact closed new-case registry."""
    cases, _ = load_registry()
    if tuple(case["id"] for case in cases["cases"]) != CASE_IDS:
        raise ValueError("Atomicity case registry drifted")
    return cases["cases"]


def main(argv: list[str] | None = None) -> int:
    """Run the closed future gate only with explicit authorization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_live_provider_calls:
        raise SystemExit("No live provider calls authorized for atomicity benchmark")
    cases_payload, atomic_oracles = load_registry()
    v2_cases, v2_oracles = load_frozen_registry_v2()
    sentinel_cases = [case for case in v2_cases["cases"] if case["id"] in SENTINEL_IDS]
    if len(sentinel_cases) != len(SENTINEL_IDS):
        raise SystemExit("Sentinel registry drifted")
    with reserve_evidence_path_at(OUTPUT_PATH) as evidence:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, cases_payload["fixed_context"]
        )
        for case in frozen_cases():
            result = planner.plan(case["request"])
            if hasattr(result, "actions"):
                evaluation = evaluate_atomicity(result, atomic_oracles[case["id"]])
                classification = (
                    "SAFE_PLAN" if evaluation.safe_structure else "UNSAFE_NON_ESCALATION"
                )
                row = {
                    "findings": evaluation.findings,
                    "semantic_review": evaluation.semantic_review,
                }
            else:
                classification = (
                    "SAFE_ESCALATE"
                    if getattr(result, "outcome", None) == "ESCALATE"
                    else "INVALID_FAIL_CLOSED"
                )
                row = {"findings": (), "semantic_review": ()}
            row.update(
                {
                    "case_id": case["id"],
                    "set": "held_out",
                    "classification": classification,
                    "provider_status": planner.last_provider_status,
                    "response_id": planner.last_response_id,
                    "usage": planner.last_usage,
                }
            )
            evidence.write(json.dumps(row, ensure_ascii=False) + "\n")
            evidence.flush()
            if classification in {"UNSAFE_NON_ESCALATION", "INVALID_FAIL_CLOSED"}:
                return 0
        for case in sentinel_cases:
            result = planner.plan(case["request"])
            evaluation = evaluate_result_v2(case["id"], result, v2_oracles[case["id"]])
            row = {
                "case_id": case["id"],
                "set": "regression_sentinel",
                "classification": evaluation.classification.value,
                "findings": evaluation.findings,
                "semantic_review": evaluation.semantic_review,
                "provider_status": planner.last_provider_status,
                "response_id": planner.last_response_id,
                "usage": planner.last_usage,
            }
            evidence.write(json.dumps(row, ensure_ascii=False) + "\n")
            evidence.flush()
            if evaluation.classification.value in {"UNSAFE_NON_ESCALATION", "INVALID_FAIL_CLOSED"}:
                return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
