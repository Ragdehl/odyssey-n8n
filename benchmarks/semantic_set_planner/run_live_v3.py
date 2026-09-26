"""Run the frozen v3 Luna planner gate only after separate explicit authorization."""

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
from benchmarks.semantic_set_planner.run_live import reserve_evidence_path, run_cases  # noqa: E402
from benchmarks.semantic_set_planner.v3_gate import (  # noqa: E402
    TEACHING_EXAMPLES_PATH,
    evaluate_v3_result,
    load_v3_registry,
    v3_preflight,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner  # noqa: E402

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-set-slice1-v3-luna-gate.jsonl"
SCHEMA_PATH = ROOT / "config/note-schema.json"


def run_v3_gate(output_path: Path, argv: list[str] | None = None) -> int:
    """Run frozen v3 contracts once into one reviewed, exclusively reserved evidence path.

    Args:
        output_path: Fixed wrapper-owned JSONL path that must not already exist.
        argv: Optional runner arguments, including the explicit live-call confirmation.

    Returns:
        Zero only when all six frozen cases pass.

    Raises:
        SystemExit: If a deterministic authorization, environment, or evidence guard refuses.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    cases, oracles = load_v3_registry()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    print(json.dumps(v3_preflight(schema, cases), ensure_ascii=False, sort_keys=True))
    if (
        not args.confirm_live_provider_calls
        or not os.environ.get("OPENAI_API_KEY")
        or output_path.exists()
        or len(cases["cases"]) != MAX_PROVIDER_CALLS
    ):
        raise SystemExit("Live semantic-set v3 gate preflight refused")
    teaching = json.loads(TEACHING_EXAMPLES_PATH.read_text(encoding="utf-8"))["examples"]
    with reserve_evidence_path(output_path) as evidence:
        planner = OpenAILunaExperimentalPlanner.from_environment(
            schema, cases["fixed_context"], teaching_examples=teaching
        )
        rows = run_cases(planner, cases["cases"], oracles, evidence, evaluator=evaluate_v3_result)
    return int(
        not (len(rows) == MAX_PROVIDER_CALLS and all(r["classification"] == "PASS" for r in rows))
    )


def main(argv: list[str] | None = None) -> int:
    """Run v3 attempt 1 only after all deterministic refusal checks pass."""
    return run_v3_gate(OUTPUT_PATH, argv)


if __name__ == "__main__":
    raise SystemExit(main())
