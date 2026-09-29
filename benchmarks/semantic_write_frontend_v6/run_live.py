"""Prepare the authorization-gated semantic-write-frontend-v6 Luna evidence."""

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
from benchmarks.semantic_write_frontend_v5 import run_live as _v5  # noqa: E402
from odyssey_core.experimental_luna_planning import (  # noqa: E402
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    OpenAILunaExperimentalPlanner,
)

SCHEMA_PATH = _v5.SCHEMA_PATH
FROZEN_SWR_PATH = _v5.FROZEN_SWR_PATH
SENTINELS_PATH = _v5.SENTINELS_PATH
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-write-frontend-v6-luna-gate.jsonl"
# Explicitly authorized by the user on 2026-09-29 for the 13-case semantic-write-frontend-v6 gate.
MAX_COST_USD = Decimal("0.166712")
conservative_cost_ceiling = _v5.conservative_cost_ceiling
run_cases = _v5.run_cases


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    return _v5.load_gate_cases()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    cases, context = load_gate_cases()
    schema = json.loads(SCHEMA_PATH.read_text())
    cost, input_bound = conservative_cost_ceiling(cases, context, schema)
    print(
        f"logical_cases={len(cases)} provider_call_ceiling={len(cases)} retries=0 sol_calls=0 "
        f"model={LUNA_EXPERIMENT_MODEL} effort={LUNA_EXPERIMENT_REASONING_EFFORT} "
        f"no_cache_max_usd={cost:.6f} luna_input_bound={input_bound}"
    )
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls without --confirm-live-provider-calls")
    if cost > MAX_COST_USD:
        raise SystemExit(
            f"Refusing live calls: conservative ceiling exceeds ${MAX_COST_USD:.2f} authorization"
        )
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Refusing live calls: OPENAI_API_KEY is absent from process environment")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        evidence = OUTPUT_PATH.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise SystemExit(f"Refusing to overwrite existing evidence: {OUTPUT_PATH}") from error
    try:
        planner = OpenAILunaExperimentalPlanner.from_environment(schema, context)
        rows = run_cases(planner, cases, evidence)
    finally:
        evidence.close()
    return 0 if len(rows) == len(cases) and all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
