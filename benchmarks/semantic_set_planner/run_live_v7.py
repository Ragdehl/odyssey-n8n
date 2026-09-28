"""Run one immutable combined planner-shape gate; never execute Odyssey actions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_set_planner.run_live import reserve_evidence_path, run_cases  # noqa: E402
from benchmarks.semantic_set_planner.v7_gate import (  # noqa: E402
    CASE_ORDER,
    FINAL_CASE_ORDER,
    MAX_PROVIDER_CALLS,
    evaluate_historical_result,
    evaluate_v7_result,
    load_classifier_cases,
    load_historical_registry,
    load_v7_registry,
    run_classifier_cases,
    v7_preflight,
)
from odyssey_core.clarification import OpenAILunaClarificationClassifier  # noqa: E402
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner  # noqa: E402

OUTPUT_PATH = (
    ROOT / "benchmarks/.live-results/semantic-set-slice1-v7-final-combined-luna-gate.jsonl"
)
SCHEMA_PATH = ROOT / "config/note-schema.json"


def main(argv: list[str] | None = None) -> int:
    """Preflight the frozen combined gate; continue safe oracle failures only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    cases, oracles = load_v7_registry()
    historical_cases, historical_oracles = load_historical_registry()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    print(json.dumps(v7_preflight(schema, cases), ensure_ascii=False, sort_keys=True))
    if (
        not args.confirm_live_provider_calls
        or not os.environ.get("OPENAI_API_KEY")
        or OUTPUT_PATH.exists()
        or len(cases["cases"]) != len(CASE_ORDER)
        or tuple(case["id"] for case in [*cases["cases"], *historical_cases])
        != FINAL_CASE_ORDER[:-4]
    ):
        raise SystemExit("Live v7 combined gate preflight refused")
    with reserve_evidence_path(OUTPUT_PATH) as evidence:
        planner = OpenAILunaExperimentalPlanner.from_environment(schema, cases["fixed_context"])
        rows = run_cases(
            planner,
            cases["cases"],
            oracles,
            evidence,
            evaluator=evaluate_v7_result,
            continue_on_safe_fail=True,
        )
        if len(rows) == len(CASE_ORDER) and rows[-1]["classification"] != "FAIL_CLOSED":
            rows.extend(
                run_cases(
                    planner,
                    historical_cases,
                    historical_oracles,
                    evidence,
                    case_evaluator=evaluate_historical_result,
                    continue_on_safe_fail=True,
                )
            )
        if len(rows) == len(FINAL_CASE_ORDER) - 4 and rows[-1]["classification"] != "FAIL_CLOSED":
            rows.extend(
                run_classifier_cases(
                    OpenAILunaClarificationClassifier(), load_classifier_cases(), evidence
                )
            )
    return int(
        not (
            len(rows) == MAX_PROVIDER_CALLS and all(row["classification"] == "PASS" for row in rows)
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
