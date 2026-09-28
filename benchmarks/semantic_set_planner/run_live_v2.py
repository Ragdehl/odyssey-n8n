"""Run the corrected six-case Luna planner gate only with fresh explicit authorization."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_set_planner.gate import MAX_PROVIDER_CALLS  # noqa: E402
from benchmarks.semantic_set_planner.run_live import (  # noqa: E402
    reserve_evidence_path,
    run_cases,
)
from benchmarks.semantic_set_planner.v2_gate import (  # noqa: E402
    TEACHING_EXAMPLES_PATH,
    evaluate_v2_result,
    load_v2_registry,
    v2_preflight,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner  # noqa: E402

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-set-slice1-v2-luna-gate.jsonl"
SCHEMA_PATH = ROOT / "config/note-schema.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Require an explicit future live-provider confirmation flag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Perform every deterministic refusal check before constructing a Luna client."""
    args = parse_args(argv)
    cases_payload, oracles = load_v2_registry()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    details = v2_preflight(schema, cases_payload)
    print(json.dumps(details, ensure_ascii=False, sort_keys=True))
    if (
        not args.confirm_live_provider_calls
        or not os.environ.get("OPENAI_API_KEY")
        or OUTPUT_PATH.exists()
        or len(cases_payload["cases"]) != MAX_PROVIDER_CALLS
    ):
        raise SystemExit("Live semantic-set v2 gate preflight refused")
    teaching = json.loads(TEACHING_EXAMPLES_PATH.read_text(encoding="utf-8"))["examples"]
    evidence = reserve_evidence_path(OUTPUT_PATH)
    try:
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, cases_payload["fixed_context"], teaching_examples=teaching
        )
        rows = run_cases(
            planner,
            cases_payload["cases"],
            oracles,
            evidence,
            evaluator=evaluate_v2_result,
        )
    finally:
        evidence.close()
    return int(
        not (
            len(rows) == MAX_PROVIDER_CALLS and all(row["classification"] == "PASS" for row in rows)
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
