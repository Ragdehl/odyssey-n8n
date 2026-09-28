"""Retry one immutable planner-only v7 recheck after a DNS-only provider failure."""

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
    MAX_PLANNER_CALLS,
    PLANNER_ORDER,
    evaluate_historical_result,
    evaluate_v7_result,
    load_historical_registry,
    load_v7_registry,
    v7_planner_preflight,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner  # noqa: E402

OUTPUT_PATH = (
    ROOT
    / "benchmarks/.live-results/semantic-set-slice1-v7-final-planner-recheck-luna-gate-retry1.jsonl"
)
SCHEMA_PATH = ROOT / "config/note-schema.json"


def main(argv: list[str] | None = None) -> int:
    """Require explicit authorization and rerun the unchanged frozen 18-case gate once."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    cases, oracles = load_v7_registry()
    historical_cases, historical_oracles = load_historical_registry()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    preflight = v7_planner_preflight(schema, cases)
    print(json.dumps(preflight, ensure_ascii=False, sort_keys=True))
    if (
        not args.confirm_live_provider_calls
        or not os.environ.get("OPENAI_API_KEY")
        or OUTPUT_PATH.exists()
        or len(cases["cases"]) != len(CASE_ORDER)
        or tuple(case["id"] for case in [*cases["cases"], *historical_cases]) != PLANNER_ORDER
        or preflight["maximum_provider_calls"] != MAX_PLANNER_CALLS
    ):
        raise SystemExit("Live v7 planner-only retry preflight refused")
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
    return int(
        not (
            len(rows) == MAX_PLANNER_CALLS and all(row["classification"] == "PASS" for row in rows)
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
