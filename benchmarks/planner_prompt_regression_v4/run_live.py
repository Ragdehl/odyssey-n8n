"""Focused current-schema successor gate for the three obsolete v3 relational fixtures."""

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
from benchmarks.semantic_write_resolution_current_v1.evaluate import evaluate, load_registry
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
MAX_CALLS = 3
AUTHORIZED_CEILING_USD = Decimal("0.040")
MATRIX_SHA256 = "383dfa94fc4e11e34cab5fb96b128ad8c6945dee5bfe98ecc061c850f22407fa"
PROMPT_SHA256 = prior.PROMPT_SHA256
PROVIDER_SCHEMA_SHA256 = prior.PROVIDER_SCHEMA_SHA256
TEACHING_SHA256 = prior.TEACHING_SHA256


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Load only the three current-schema successors under the already-tested v3 context."""
    registry = load_registry()
    _inherited, context = base.load_gate_cases()
    if registry["fixed_context"] != context:
        raise RuntimeError("current bounded-source registry context diverged from v3")
    cases = list(registry["cases"])
    if len(cases) != MAX_CALLS:
        raise RuntimeError("current bounded-source gate must contain exactly three cases")
    return cases, context


def _matrix_payload(cases: list[dict[str, Any]], context: dict[str, str]) -> bytes:
    """Serialize the focused successor matrix deterministically for one content hash."""
    return prior._matrix_payload(cases, context)


def budget_snapshot() -> dict[str, Decimal | int]:
    """Return the conservative three-call ceiling for the focused successor gate."""
    cases, context = load_gate_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, _costs, input_bound = base.total_conservative_cost_ceiling(cases, context, schema)
    return {"calls": len(cases), "input_bound": input_bound, "conservative_usd_upper": cost}


def _preflight() -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    """Grant provider authority only to the frozen three-case successor and unchanged v3 contract."""
    cases, context = load_gate_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if hashlib.sha256(_matrix_payload(cases, context)).hexdigest() != MATRIX_SHA256:
        raise SystemExit("v4 focused successor matrix changed")
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
        raise SystemExit("v4 focused successor budget changed; fresh authorization required")
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
    """Run the authorized three-case successor once and retain bounded auditable evidence."""
    cases, context, schema = _preflight()
    from openai import OpenAI

    recorder = prior.RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    planner = OpenAILunaExperimentalPlanner(SimpleNamespace(responses=recorder), schema, context)
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"])
            verdict = evaluate(result, case["expect"])
            passed = verdict.passed
            findings = list(verdict.findings)
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
        raise SystemExit("Authorized v4 focused successor ceiling exceeded")
    acceptable = all(row["passed"] for row in rows)
    artifact = {
        "version": 4,
        "scope": "three-current-bounded-source-successors",
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
