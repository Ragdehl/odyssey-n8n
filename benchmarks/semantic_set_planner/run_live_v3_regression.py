"""Run the frozen v3 historical-regression gate only with explicit authorization."""

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
from benchmarks.semantic_set_planner.v3_gate import TEACHING_EXAMPLES_PATH  # noqa: E402
from benchmarks.semantic_set_planner.v3_regression_gate import (  # noqa: E402
    MAX_PROVIDER_CALLS,
    evaluate_v3_regression_result,
    load_v3_regression_registry,
    v3_regression_preflight,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner  # noqa: E402

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-set-slice1-v3-regression-luna-gate.jsonl"
SCHEMA_PATH = ROOT / "config/note-schema.json"


def main(argv: list[str] | None = None) -> int:
    """Refuse every live precondition failure before creating a provider client."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    cases, oracles = load_v3_regression_registry()
    schema = json.loads(SCHEMA_PATH.read_text())
    teaching = json.loads(TEACHING_EXAMPLES_PATH.read_text())["examples"]
    print(json.dumps(v3_regression_preflight(schema, cases, teaching), sort_keys=True))
    if (
        not args.confirm_live_provider_calls
        or not os.environ.get("OPENAI_API_KEY")
        or OUTPUT_PATH.exists()
    ):
        raise SystemExit("Live semantic-set v3 regression gate preflight refused")
    with reserve_evidence_path(OUTPUT_PATH) as evidence:
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, cases["fixed_context"], teaching_examples=teaching
        )
        rows = run_cases(
            planner,
            cases["cases"],
            oracles,
            evidence,
            evaluator=lambda result, oracle: evaluate_v3_regression_result(
                oracle["id"], result, oracle
            ),
        )
    return int(
        not (
            len(rows) == MAX_PROVIDER_CALLS and all(row["classification"] == "PASS" for row in rows)
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
