"""Preserve the consumed Luna semantic-write-frontend-v1 live-evidence lineage."""

from __future__ import annotations

import argparse
import hashlib
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
from odyssey_core.request_planning import RequestPlan  # noqa: E402

SCHEMA_PATH = ROOT / "config/note-schema.json"
PRICING_PATH = ROOT / "benchmarks/performance_p1/pricing_snapshot.json"
FROZEN_SWR_PATH = ROOT / "benchmarks/semantic_write_resolution_v1/cases_active_schema.json"
SENTINELS_PATH = Path(__file__).with_name("sentinels.json")
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-write-frontend-v1-luna-gate.jsonl"
INPUT_OVERHEAD_BYTES = 1024
# Reset after the authorized v1 attempt; any successor run requires fresh explicit authorization.
MAX_COST_USD = Decimal("0.00")
GATE_CONSUMED = True


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Load hash-pinned SWR cases plus only the new read/delegate/order sentinels."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for path, expected in (
        (FROZEN_SWR_PATH, manifest["sha256"]["frozen_swr_cases"]),
        (SENTINELS_PATH, manifest["sha256"]["sentinels"]),
    ):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Gate input hash mismatch: {path.name}")
    swr = json.loads(FROZEN_SWR_PATH.read_text(encoding="utf-8"))
    sentinels = json.loads(SENTINELS_PATH.read_text(encoding="utf-8"))
    if swr["fixed_context"] != sentinels["fixed_context"]:
        raise RuntimeError("Gate contexts diverged")
    cases = [{**case, "lineage": "frozen_swr"} for case in swr["cases"]]
    cases.extend({**case, "lineage": "frontend_sentinel"} for case in sentinels["cases"])
    return cases, sentinels["fixed_context"]


def conservative_cost_ceiling(
    cases: list[dict[str, Any]], context: dict[str, str], schema: dict[str, Any]
) -> tuple[Decimal, int]:
    """Calculate a no-cache byte upper bound without constructing or calling a provider."""
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))["models"][LUNA_EXPERIMENT_MODEL]
    prompt = render_luna_experimental_prompt(schema, context)
    output_schema = json.dumps(
        luna_experimental_result_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    )
    maximum_input = max(
        len((prompt + output_schema + case["request"]).encode("utf-8")) for case in cases
    )
    input_bound = maximum_input + INPUT_OVERHEAD_BYTES
    per_call = Decimal(input_bound) * Decimal(str(pricing["input_per_million"])) + Decimal(
        LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS
    ) * Decimal(str(pricing["output_per_million"]))
    return Decimal(len(cases)) * per_call / Decimal(1_000_000), input_bound


def _case_passed(result: Any, case: dict[str, Any]) -> tuple[bool, list[str]]:
    """Apply the frozen SWR oracle or the narrow action-order sentinel."""
    if case["lineage"] == "frozen_swr":
        verdict = evaluate(result, case["expect"])
        return verdict.passed, list(verdict.findings)
    if not isinstance(result, RequestPlan):
        return False, ["expected_request_plan"]
    actual = [action.kind for action in result.actions]
    expected = case["expect_action_kinds"]
    return (actual == expected, [] if actual == expected else ["action_order"])


def run_cases(
    planner: OpenAILunaExperimentalPlanner,
    cases: list[dict[str, Any]],
    evidence: TextIO,
) -> list[dict[str, Any]]:
    """Run once per case, write incrementally, and stop at the first failed oracle."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"])
            passed, findings = _case_passed(result, case)
            row = {
                "case_id": case["id"],
                "model": planner.model,
                "reasoning_effort": planner.reasoning_effort,
                "passed": passed,
                "findings": findings,
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
    """Refuse every invocation because the v1 lineage and artifact are permanently consumed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.parse_args(argv)
    raise SystemExit("Refusing live calls: semantic-write-frontend-v1 is permanently consumed")


if __name__ == "__main__":
    raise SystemExit(main())
