"""Prepared GPT-6-first planner regression gate; zero authority until explicitly authorized."""

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

import odyssey_core.experimental_luna_planning as luna_planning  # noqa: E402
from benchmarks.semantic_write_frontend_v1 import run_live as _v1  # noqa: E402
from benchmarks.semantic_write_frontend_v8 import run_live as _v8  # noqa: E402
from odyssey_core.request_planning import RequestPlan, WriteAction  # noqa: E402

MODEL = "gpt-6-luna"
REASONING_EFFORT = "low"
MAX_COST_USD = Decimal("0.00")
INPUT_PER_MILLION = Decimal("0.10")
OUTPUT_PER_MILLION = Decimal("0.50")
INPUT_OVERHEAD_BYTES = 1024
SCHEMA_PATH = ROOT / "config/note-schema.json"
ADDITIONAL_CASES_PATH = Path(__file__).with_name("additional_cases.json")
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/planner-prompt-regression-v1-gpt6-luna.jsonl"


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Reuse the frozen v8 matrix and add only three clarification-entry sentinels."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    v8_manifest = json.loads(_v8.MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["sha256"]["base_frozen_swr_cases"] != v8_manifest["sha256"]["frozen_swr_cases"]:
        raise RuntimeError("base SWR hash diverged")
    if manifest["sha256"]["base_sentinels"] != v8_manifest["sha256"]["sentinels"]:
        raise RuntimeError("base sentinel hash diverged")
    if (
        hashlib.sha256(ADDITIONAL_CASES_PATH.read_bytes()).hexdigest()
        != manifest["sha256"]["additional_cases"]
    ):
        raise RuntimeError("additional regression cases changed after freeze")
    base, context = _v8.load_gate_cases()
    extra = json.loads(ADDITIONAL_CASES_PATH.read_text(encoding="utf-8"))
    if extra["fixed_context"] != context:
        raise RuntimeError("regression contexts diverged")
    cases = list(base)
    cases.extend({**case, "lineage": "clarification_entry"} for case in extra["cases"])
    return cases, context


def conservative_cost_ceiling(
    cases: list[dict[str, Any]], context: dict[str, str], schema: dict[str, Any]
) -> tuple[Decimal, int]:
    """Bound all calls with no cache credit and the largest case-specific recent context."""
    output_schema = json.dumps(
        luna_planning.luna_experimental_result_json_schema(schema),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    maximum_input = 0
    for case in cases:
        prompt = luna_planning.render_luna_experimental_prompt(
            schema,
            context,
            conversation_context=case.get("conversation_context", ()),
        )
        size = len((prompt + output_schema + case["request"]).encode("utf-8"))
        maximum_input = max(maximum_input, size)
    input_bound = maximum_input + INPUT_OVERHEAD_BYTES
    per_call = (
        Decimal(input_bound) * INPUT_PER_MILLION
        + Decimal(luna_planning.LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS) * OUTPUT_PER_MILLION
    ) / Decimal(1_000_000)
    return Decimal(len(cases)) * per_call, input_bound


def _clarification_entry_passed(result: Any, case: dict[str, Any]) -> tuple[bool, list[str]]:
    """Require a representable one-member relational WRITE without choosing a canonical identity."""
    if not isinstance(result, RequestPlan) or len(result.actions) != 1:
        return False, ["expected_single_request_plan"]
    action = result.actions[0]
    if not isinstance(action, WriteAction) or len(action.units) != 1:
        return False, ["expected_single_write"]
    unit = action.units[0]
    target = unit.target
    relation = target.relational_reference
    expected = case["expect"]
    findings: list[str] = []
    if relation is None:
        findings.append("missing_relational_candidate_scope")
    else:
        if relation.source_kind != expected["source_kind"]:
            findings.append("wrong_source_kind")
        if relation.members != expected["members"]:
            findings.append("wrong_member_extent")
    if target.type != expected["note_type"]:
        findings.append("wrong_note_type")
    if target.entity is not None or target.self_target is not None:
        findings.append("identity_was_preselected")
    if unit.intent != "record" or tuple(unit.facts) != (expected["fact"],):
        findings.append("write_payload_changed")
    return not findings, findings


def _case_passed(result: Any, case: dict[str, Any]) -> tuple[bool, list[str]]:
    if case["lineage"] == "clarification_entry":
        return _clarification_entry_passed(result, case)
    return _v1._case_passed(result, case)


def run_cases(
    planner: luna_planning.OpenAILunaExperimentalPlanner,
    cases: list[dict[str, Any]],
    evidence: TextIO,
) -> list[dict[str, Any]]:
    """Collect the full matrix even when one oracle fails."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"], case.get("conversation_context", ()))
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
    return rows


def _build_planner(schema: dict[str, Any], context: dict[str, str]):
    """Swap only the benchmark process to GPT-6; the production default remains unchanged."""
    luna_planning.LUNA_EXPERIMENT_MODEL = MODEL
    planner = luna_planning.OpenAILunaExperimentalPlanner.from_environment(schema, context)
    if planner.model != MODEL or planner.reasoning_effort != REASONING_EFFORT:
        raise SystemExit("Refusing live calls: planner model/effort mismatch")
    return planner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_live_provider_calls:
        raise SystemExit("Refusing live calls: explicit confirmation flag is required")
    cases, context = load_gate_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ceiling, _bound = conservative_cost_ceiling(cases, context, schema)
    if MAX_COST_USD <= 0 or ceiling > MAX_COST_USD:
        raise SystemExit("Refusing live calls: planner-prompt-regression-v1 has zero authority")
    if OUTPUT_PATH.exists():
        raise SystemExit("Refusing live calls: evidence artifact already exists")
    planner = _build_planner(schema, context)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("x", encoding="utf-8") as evidence:
        rows = run_cases(planner, cases, evidence)
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
