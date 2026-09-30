"""Run the frozen semantic WRITE v8 matrix once with GPT-6 Luna / low only."""

from __future__ import annotations

import argparse
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
MAX_COST_USD = Decimal("0.00")
GATE_CONSUMED = True
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
    parser.parse_args(argv)
    raise SystemExit(
        "Refusing live calls: semantic-write-frontend-gpt6-luna-v1 is permanently consumed"
    )


if __name__ == "__main__":
    raise SystemExit(main())
