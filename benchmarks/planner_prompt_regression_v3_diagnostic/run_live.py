from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from benchmarks.planner_prompt_regression_v1 import run_live as base
from benchmarks.planner_prompt_regression_v3 import run_live as v3
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_PLANNER_PROMPT_V3_DIAGNOSTIC"
CASE_IDS = (
    "SWR10-relational-target-two-bounded-references",
    "SWF-MIXED-ORDER-01",
)
MAX_CALLS = 2
AUTHORIZED_CEILING_USD = Decimal("0.026")


def _selected_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    cases, context = base.load_gate_cases()
    selected = [case for case in cases if case["id"] in CASE_IDS]
    if [case["id"] for case in selected] != list(CASE_IDS):
        raise SystemExit("Diagnostic case set changed")
    return selected, context


def budget_snapshot() -> dict[str, Decimal | int]:
    cases, context = _selected_cases()
    schema = json.loads(v3.SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, input_bound = base.conservative_cost_ceiling(cases, context, schema, v3.PRODUCTION_MODEL)
    return {"calls": len(cases), "input_bound": input_bound, "conservative_usd_upper": cost}


def _preflight() -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    cases, context = _selected_cases()
    schema = json.loads(v3.SCHEMA_PATH.read_text(encoding="utf-8"))
    if v3._contract_hashes(schema, context) != (
        v3.PROMPT_SHA256,
        v3.PROVIDER_SCHEMA_SHA256,
        v3.TEACHING_SHA256,
    ):
        raise SystemExit("Diagnostic candidate contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["conservative_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("Diagnostic budget changed; fresh authorization required")
    if os.environ.get(AUTH_ENV) != "1":
        raise SystemExit(f"Refusing live calls: set {AUTH_ENV}=1 only after explicit authorization")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Refusing live calls: OPENAI_API_KEY unavailable")
    if subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    ).strip():
        raise SystemExit("Refusing live calls from a dirty worktree")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if any(RESULTS_DIR.glob("*.json")):
        raise SystemExit("Diagnostic already has retained evidence; refusing a second run")
    return cases, context, schema


def _case_row(planner: Any, case: dict[str, Any]) -> dict[str, Any]:
    try:
        result = planner.plan(case["request"], case.get("conversation_context", ()))
        passed, findings = base._case_passed(result, case)
        return {
            "case_id": case["id"],
            "passed": passed,
            "findings": findings,
            "result": asdict(result),
            "usage": planner.last_usage,
            "validation_stage": planner.last_validation_stage,
            "validation_code": planner.last_validation_code,
            "error": None,
        }
    except Exception as error:
        return {
            "case_id": case["id"],
            "passed": False,
            "findings": [planner.last_error_category or type(error).__name__[:120]],
            "usage": planner.last_usage,
            "validation_stage": planner.last_validation_stage,
            "validation_code": planner.last_validation_code,
            "error": type(error).__name__,
        }


def run() -> int:
    cases, context, schema = _preflight()
    from openai import OpenAI

    recorder = v3.RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    planner = OpenAILunaExperimentalPlanner(SimpleNamespace(responses=recorder), schema, context)
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    rows: list[dict[str, Any]] = []
    for case in cases:
        before = recorder.attempts
        row = _case_row(planner, case)
        if recorder.attempts - before != 1:
            raise SystemExit("Diagnostic case did not use exactly one provider attempt")
        rows.append(row)
        out = RESULTS_DIR / f"{commit[:12]}__{case['id']}.json"
        out.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    actual_cost = v3._estimated_cost(recorder.records)
    if recorder.attempts != MAX_CALLS or actual_cost > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized diagnostic ceiling exceeded")
    summary = {
        "commit": commit,
        "provider_attempts": recorder.attempts,
        "completed_provider_responses": len(recorder.records),
        "automatic_retries": 0,
        "estimated_standard_cost_usd": str(actual_cost),
        "case_ids": list(CASE_IDS),
        "failed_case_ids": [row["case_id"] for row in rows if not row["passed"]],
        "provider_failures": recorder.failures,
    }
    (RESULTS_DIR / f"{commit[:12]}__summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"provider_attempts={summary['provider_attempts']}")
    print(f"completed_provider_responses={summary['completed_provider_responses']}")
    print(f"standard_cost_usd={actual_cost}")
    print(f"failed_case_ids={summary['failed_case_ids']}")
    return 0 if not recorder.failures else 1


if __name__ == "__main__":
    raise SystemExit(run())
