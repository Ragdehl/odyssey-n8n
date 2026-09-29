"""Run the authorization-gated Luna-only semantic WRITE-resolution evidence."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_write_resolution_v1.evaluate import evaluate  # noqa: E402
from odyssey_core.experimental_luna_planning import (  # noqa: E402
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    OpenAILunaExperimentalPlanner,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)

SCHEMA_PATH = ROOT / "config" / "note-schema.json"
PRICING_PATH = ROOT / "benchmarks" / "performance_p1" / "pricing_snapshot.json"
OUTPUT_PATH = (
    ROOT / "benchmarks" / ".live-results" / "semantic-write-resolution-v1-active-schema-v9.jsonl"
)
INPUT_OVERHEAD_BYTES = 1024
# v9 reruns the unchanged planner contract with finer bounded local diagnostics.
ACTIVE_REGISTRY_PATH = Path(__file__).with_name("cases_active_schema.json")
MAX_COST_USD = Decimal("0.00")


def conservative_cost_ceiling(
    cases: list[dict[str, str]], context: dict[str, str], schema: dict[str, Any]
) -> tuple[Decimal, int]:
    """Price the Luna-only gate with no cache and a byte-count input upper bound."""
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))["models"][LUNA_EXPERIMENT_MODEL]
    output_schema = json.dumps(
        luna_experimental_result_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    )
    maximum_input = 0
    for case in cases:
        prompt = render_luna_experimental_prompt(schema, context)
        size = len((prompt + output_schema + case["request"]).encode("utf-8"))
        maximum_input = max(maximum_input, size)
    input_bound = maximum_input + INPUT_OVERHEAD_BYTES
    per_call = Decimal(input_bound) * Decimal(str(pricing["input_per_million"])) + Decimal(
        LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS
    ) * Decimal(str(pricing["output_per_million"]))
    return Decimal(len(cases)) * per_call / Decimal(1_000_000), input_bound


def run_cases(
    planner: OpenAILunaExperimentalPlanner,
    cases: list[dict[str, str]],
    evidence: TextIO,
) -> list[dict[str, Any]]:
    """Attempt every case once, flush immediately, and stop on the first unsafe result."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"])
            verdict = evaluate(result, case["expect"])
            row = {
                "case_id": case["id"],
                "model": planner.model,
                "reasoning_effort": planner.reasoning_effort,
                "passed": verdict.passed,
                "findings": list(verdict.findings),
                "result": asdict(result),
                "usage": planner.last_usage,
                "response_id": planner.last_response_id,
                "provider_status": planner.last_provider_status,
                "validation_stage": planner.last_validation_stage,
                "validation_code": planner.last_validation_code,
            }
        except Exception as error:
            row = {
                "case_id": case["id"],
                "model": planner.model,
                "reasoning_effort": planner.reasoning_effort,
                "passed": False,
                "findings": [planner.last_error_category or type(error).__name__[:120]],
                "usage": planner.last_usage,
                "response_id": planner.last_response_id,
                "provider_status": planner.last_provider_status,
                "validation_stage": planner.last_validation_stage,
                "validation_code": planner.last_validation_code,
            }
        rows.append(row)
        evidence.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        evidence.flush()
        if not row["passed"]:
            break
    return rows


def main(argv: list[str] | None = None) -> int:
    """Permanently refuse the retired legacy-WRITE v9 provider contract."""
    raise SystemExit(
        "Retired live runner: legacy semantic-write-resolution v9 cannot construct a provider"
    )


if __name__ == "__main__":
    raise SystemExit(main())
