"""Run the frozen semantic WRITE v8 matrix once with GPT-6 Luna / low only."""

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

import odyssey_core.experimental_luna_planning as luna_planning  # noqa: E402
from benchmarks.semantic_write_frontend_v8 import run_live as _v8  # noqa: E402

MODEL = "gpt-6-luna"
REASONING_EFFORT = "low"
MAX_COST_USD = Decimal("0.0809432")
INPUT_PER_MILLION = Decimal("0.10")
OUTPUT_PER_MILLION = Decimal("0.50")
SCHEMA_PATH = _v8.SCHEMA_PATH
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-write-frontend-gpt6-luna-v1.jsonl"


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    return _v8.load_gate_cases()


def conservative_cost_ceiling(cases, context, schema) -> tuple[Decimal, int]:
    _old_cost, input_bound = _v8.conservative_cost_ceiling(cases, context, schema)
    per_call = (
        Decimal(input_bound) * INPUT_PER_MILLION
        + Decimal(luna_planning.LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS) * OUTPUT_PER_MILLION
    )
    return Decimal(len(cases)) * per_call / Decimal(1_000_000), input_bound


def _build_planner(schema, context):
    # Benchmark-only model swap. Production default remains gpt-5.6-luna.
    luna_planning.LUNA_EXPERIMENT_MODEL = MODEL
    planner = luna_planning.OpenAILunaExperimentalPlanner.from_environment(schema, context)
    if planner.model != MODEL or planner.reasoning_effort != REASONING_EFFORT:
        raise SystemExit("Refusing live calls: benchmark planner model/effort mismatch")
    return planner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    cases, context = load_gate_cases()
    schema = json.loads(SCHEMA_PATH.read_text())
    cost, input_bound = conservative_cost_ceiling(cases, context, schema)
    print(
        f"logical_cases={len(cases)} provider_call_ceiling={len(cases)} retries=0 sol_calls=0 "
        f"model={MODEL} effort={REASONING_EFFORT} no_cache_max_usd={cost:.7f} "
        f"luna_input_bound={input_bound}"
    )
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    if cost > MAX_COST_USD:
        raise SystemExit(
            f"Refusing live calls: conservative ceiling exceeds ${MAX_COST_USD:.7f} authorization"
        )
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Refusing live calls: OPENAI_API_KEY is absent from process environment")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        evidence = OUTPUT_PATH.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise SystemExit(f"Refusing to overwrite existing evidence: {OUTPUT_PATH}") from error
    try:
        planner = _build_planner(schema, context)
        rows = _v8.run_all_cases(planner, cases, evidence)
    finally:
        evidence.close()
    return 0 if len(rows) == len(cases) and all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
