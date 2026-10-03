"""One-shot current-schema Core planner regression gate after Journal convergence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from benchmarks.planner_prompt_regression_v1 import run_live as base
from benchmarks.planner_prompt_regression_v3 import run_live as prior
from benchmarks.semantic_write_resolution_current_v1.evaluate import (
    evaluate as evaluate_current_bounded_source,
)
from benchmarks.semantic_write_resolution_current_v1.evaluate import (
    load_registry as load_current_registry,
)
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    OpenAILunaExperimentalPlanner,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "config/note-schema.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_PLANNER_PROMPT_REGRESSION_V4"
PRODUCTION_MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "low"
MAX_CALLS = 16
AUTHORIZED_CEILING_USD = Decimal("0.210")
MATRIX_SHA256 = "3bb4cceeac6b0226c9139cd1f5b19d3d7e95e3794cdb4aa8dc4665b4aa908ac6"
PROMPT_SHA256 = prior.PROMPT_SHA256
PROVIDER_SCHEMA_SHA256 = prior.PROVIDER_SCHEMA_SHA256
TEACHING_SHA256 = prior.TEACHING_SHA256
ACCEPTED_FAILURE_IDS: frozenset[str] = frozenset()

_REPLACEMENTS = {
    "SWR07-qualified-event-member": "CSWR01-qualified-bounded-source-member",
    "SWR08-relational-target-described-reference": "CSWR02-relational-target-one-bounded-reference",
    "SWR10-relational-target-two-bounded-references": "CSWR03-relational-target-two-bounded-references",
}


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Replace only obsolete Journal/event fixtures with current canonical-source successors."""
    inherited, context = base.load_gate_cases()
    current = {case["id"]: case for case in load_current_registry()["cases"]}
    cases: list[dict[str, Any]] = []
    for case in inherited:
        successor_id = _REPLACEMENTS.get(case["id"])
        if successor_id is None:
            cases.append(case)
            continue
        successor = current[successor_id]
        cases.append(
            {
                "id": successor["id"],
                "request": successor["request"],
                "expect": successor["expect"],
                "lineage": "current_bounded_source",
            }
        )
    if len(cases) != len(inherited) or any(
        old in {item["id"] for item in cases} for old in _REPLACEMENTS
    ):
        raise RuntimeError("current Core regression replacement matrix is invalid")
    return cases, context


def _matrix_payload(cases: list[dict[str, Any]], context: dict[str, str]) -> bytes:
    return prior._matrix_payload(cases, context)


def _case_passed(result: Any, case: dict[str, Any]) -> tuple[bool, list[str]]:
    """Use the generic current bounded-source evaluator only for the three successor cases."""
    if case.get("lineage") == "current_bounded_source":
        verdict = evaluate_current_bounded_source(result, case["expect"])
        return verdict.passed, list(verdict.findings)
    return base._case_passed(result, case)


def _matrix_acceptable(rows: list[dict[str, Any]]) -> bool:
    """Require every current v4 sentinel to pass; only obsolete fixtures were replaced."""
    failed = {row["case_id"] for row in rows if not row["passed"]}
    return failed <= ACCEPTED_FAILURE_IDS


def budget_snapshot() -> dict[str, Decimal | int]:
    """Return the conservative complete-matrix cost ceiling for the current successor matrix."""
    cases, context = load_gate_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, _costs, input_bound = base.total_conservative_cost_ceiling(cases, context, schema)
    return {"calls": len(cases), "input_bound": input_bound, "conservative_usd_upper": cost}


def _preflight() -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    """Grant provider authority only to the frozen current-schema matrix and exact contract."""
    cases, context = load_gate_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if hashlib.sha256(_matrix_payload(cases, context)).hexdigest() != MATRIX_SHA256:
        raise SystemExit("v4 regression matrix changed")
    if (LUNA_EXPERIMENT_MODEL, LUNA_EXPERIMENT_REASONING_EFFORT) != (
        PRODUCTION_MODEL,
        REASONING_EFFORT,
    ):
        raise SystemExit("production planner model contract changed")
    if prior._contract_hashes(schema, context) != (
        PROMPT_SHA256,
        PROVIDER_SCHEMA_SHA256,
        TEACHING_SHA256,
    ):
        raise SystemExit("v4 candidate model-facing contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["conservative_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("v4 regression budget changed; fresh authorization required")
    if os.environ.get(AUTH_ENV) != "1":
        raise SystemExit(f"Refusing live calls: set {AUTH_ENV}=1 only after explicit authorization")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Refusing live calls: OPENAI_API_KEY is unavailable")
    if subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    ).strip():
        raise SystemExit("Refusing live calls from a dirty worktree")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if any(RESULTS_DIR.glob("*.json")):
        raise SystemExit("v4 already has retained live evidence; refusing a second run")
    return cases, context, schema


def run() -> int:
    """Run the authorized current-schema matrix once and retain bounded auditable evidence."""
    cases, context, schema = _preflight()
    from openai import OpenAI

    recorder = prior.RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    planner = OpenAILunaExperimentalPlanner(SimpleNamespace(responses=recorder), schema, context)
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"], case.get("conversation_context", ()))
            passed, findings = _case_passed(result, case)
            error = None
        except Exception as exc:
            passed = False
            findings = [planner.last_error_category or type(exc).__name__[:120]]
            error = type(exc).__name__
        rows.append(
            {
                "case_id": case["id"],
                "passed": passed,
                "findings": findings,
                "error": error,
                "usage": planner.last_usage,
            }
        )
    actual_cost = prior._estimated_cost(recorder.records)
    if recorder.attempts > MAX_CALLS or actual_cost > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized v4 regression ceiling exceeded")
    acceptable = _matrix_acceptable(rows)
    artifact = {
        "version": 4,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "matrix_sha256": MATRIX_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "provider_schema_sha256": PROVIDER_SCHEMA_SHA256,
        "teaching_examples_sha256": TEACHING_SHA256,
        "provider_attempts": recorder.attempts,
        "completed_provider_responses": len(recorder.records),
        "automatic_retries": 0,
        "sol_calls": 0,
        "estimated_standard_cost_usd": str(actual_cost),
        "acceptable": acceptable,
        "failed_case_ids": [row["case_id"] for row in rows if not row["passed"]],
        "rows": rows,
        "provider_failures": recorder.failures,
    }
    out = RESULTS_DIR / f"{artifact['commit'][:12]}.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider_attempts={recorder.attempts}")
    print(f"completed_provider_responses={len(recorder.records)}")
    print(f"standard_cost_usd={actual_cost}")
    print(f"acceptable={acceptable}")
    print(f"failed_case_ids={artifact['failed_case_ids']}")
    print(f"artifact={out.relative_to(ROOT)}")
    return 0 if acceptable else 1


if __name__ == "__main__":
    raise SystemExit(run())
