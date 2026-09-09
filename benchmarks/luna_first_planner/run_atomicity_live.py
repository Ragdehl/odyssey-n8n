"""Authorization-gated Luna-only runner for atomicity cases and sentinels."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
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


def _write_row(evidence, row: dict) -> None:
    """Persist one bounded row before another provider attempt."""
    evidence.write(json.dumps(row, ensure_ascii=False) + "\n")
    evidence.flush()


def _run_one(planner, case, oracle, evidence, set_name: str, evaluate):
    """Run one case fail-closed and retain validated result evidence only."""
    try:
        result = planner.plan(case["request"])
        if set_name == "held_out" and hasattr(result, "actions"):
            outcome = evaluate(result, oracle)
            if not outcome.safe_structure:
                classification = "UNSAFE_NON_ESCALATION"
            elif outcome.semantic_review:
                classification = "SEMANTIC_REVIEW"
            else:
                classification = "SAFE_PLAN"
            row = {
                "findings": outcome.findings,
                "semantic_review": outcome.semantic_review,
                "result": asdict(result),
            }
        elif set_name == "regression_sentinel":
            # All non-atomicity outcomes, including CLARIFY, are classified by
            # the canonical versioned evaluator.  Do not reduce valid
            # non-PLAN results to an ESCALATE/invalid binary here.
            outcome = evaluate(result, oracle)
            classification = outcome.classification.value
            row = {
                "findings": outcome.findings,
                "semantic_review": outcome.semantic_review,
                "result": asdict(result),
            }
        else:
            classification = (
                "SAFE_ESCALATE"
                if getattr(result, "outcome", None) == "ESCALATE"
                else "INVALID_FAIL_CLOSED"
            )
            row = {"findings": (), "semantic_review": (), "result": asdict(result)}
    except Exception as error:
        classification = "INVALID_FAIL_CLOSED"
        row = {"error_category": type(error).__name__[:120]}
    row.update(
        {
            "case_id": case["id"],
            "set": set_name,
            "classification": classification,
            "provider_status": planner.last_provider_status,
            "response_id": planner.last_response_id,
            "usage": planner.last_usage,
        }
    )
    _write_row(evidence, row)
    return classification


def frozen_cases() -> list[dict[str, str]]:
    """Return the exact closed new-case registry."""
    cases, _ = load_registry()
    if tuple(case["id"] for case in cases["cases"]) != CASE_IDS:
        raise ValueError("Atomicity case registry drifted")
    return cases["cases"]


def _run_set(planner, cases, oracles, evidence, set_name: str, evaluator_factory) -> bool:
    """Run one labeled set and report whether a stop classification occurred."""
    for case in cases:
        evaluator = evaluator_factory(case["id"])
        classification = _run_one(planner, case, oracles[case["id"]], evidence, set_name, evaluator)
        if classification in {"UNSAFE_NON_ESCALATION", "INVALID_FAIL_CLOSED"}:
            return True
    return False


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
        if _run_set(
            planner,
            frozen_cases(),
            atomic_oracles,
            evidence,
            "held_out",
            lambda _: evaluate_atomicity,
        ):
            return 0
        if _run_set(
            planner,
            sentinel_cases,
            v2_oracles,
            evidence,
            "regression_sentinel",
            lambda case_id: lambda result, oracle: evaluate_result_v2(case_id, result, oracle),
        ):
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
