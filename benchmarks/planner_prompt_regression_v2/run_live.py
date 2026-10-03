"""One-shot production planner regression gate for the accepted journal-schema candidate."""

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
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    OpenAILunaExperimentalPlanner,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "config/note-schema.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_PLANNER_PROMPT_REGRESSION_V2"
PRODUCTION_MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "low"
MAX_CALLS = 16
AUTHORIZED_CEILING_USD = Decimal("0.215")
MATRIX_SHA256 = "d091a4f5d5ddd03a8d7f7edc1285f593847770dd4205619b56cfab3d265f4190"
PROMPT_SHA256 = "07363348d91bded42affe314a386eb6400c3b761e6d7f565e208c7b55e721da1"
PROVIDER_SCHEMA_SHA256 = "65877ae84df406d36648c37a7ad4826033990a1d1b2cc8a1d1a193a5e7ecedce"
TEACHING_SHA256 = "e3ad1321ab56fb0ce0a3b587a73c07f282c748ec6ae0f203bb50ca13d1d3f5c0"
STANDARD_INPUT_USD_PER_M = Decimal("0.20")
STANDARD_OUTPUT_USD_PER_M = Decimal("1.20")


def _matrix_payload(cases: list[dict[str, Any]], context: dict[str, str]) -> bytes:
    """Serialize the inherited frozen matrix deterministically for one content hash."""
    return json.dumps(
        {"context": context, "cases": cases},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _contract_hashes(schema: dict[str, Any], context: dict[str, str]) -> tuple[str, str, str]:
    """Hash the exact production prompt, provider schema, and teaching examples."""
    prompt = render_luna_experimental_prompt(schema, context).encode("utf-8")
    provider = json.dumps(
        luna_experimental_result_json_schema(schema),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    teaching = base.TEACHING_PATH.read_bytes()
    return tuple(hashlib.sha256(value).hexdigest() for value in (prompt, provider, teaching))


def budget_snapshot() -> dict[str, Decimal | int]:
    """Return the conservative complete-matrix cost ceiling inherited from v1."""
    cases, context = base.load_gate_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    cost, _costs, input_bound = base.total_conservative_cost_ceiling(cases, context, schema)
    return {"calls": len(cases), "input_bound": input_bound, "conservative_usd_upper": cost}


class RecordingResponses:
    """Count provider attempts while retaining only bounded usage/failure metadata."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.attempts = 0
        self.records: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        """Forward one zero-retry call and retain bounded provider evidence."""
        self.attempts += 1
        try:
            response = self._responses.create(**kwargs)
        except Exception as error:
            self.failures.append(
                {
                    "attempt": self.attempts,
                    "error_type": type(error).__name__,
                    "status_code": getattr(error, "status_code", None),
                }
            )
            raise
        usage = getattr(response, "usage", None)
        self.records.append(
            {
                "attempt": self.attempts,
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        return response


def _preflight() -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    """Refuse provider authority unless the frozen candidate and bounded gate still match."""
    cases, context = base.load_gate_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if hashlib.sha256(_matrix_payload(cases, context)).hexdigest() != MATRIX_SHA256:
        raise SystemExit("v2 regression matrix changed")
    if (LUNA_EXPERIMENT_MODEL, LUNA_EXPERIMENT_REASONING_EFFORT) != (
        PRODUCTION_MODEL,
        REASONING_EFFORT,
    ):
        raise SystemExit("production planner model contract changed")
    if _contract_hashes(schema, context) != (
        PROMPT_SHA256,
        PROVIDER_SCHEMA_SHA256,
        TEACHING_SHA256,
    ):
        raise SystemExit("v2 candidate model-facing contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["conservative_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("v2 regression budget changed; fresh authorization required")
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
        raise SystemExit("v2 already has retained live evidence; refusing a second run")
    return cases, context, schema


def _estimated_cost(records: list[dict[str, Any]]) -> Decimal:
    """Estimate standard provider cost from observed token usage."""
    return sum(
        (
            Decimal(row["input_tokens"]) * STANDARD_INPUT_USD_PER_M
            + Decimal(row["output_tokens"]) * STANDARD_OUTPUT_USD_PER_M
        )
        / Decimal(1_000_000)
        for row in records
    )


def run() -> int:
    """Run the authorized complete matrix once and retain auditable evidence."""
    cases, context, schema = _preflight()
    from openai import OpenAI

    base_client = OpenAI(max_retries=0, timeout=30.0)
    recorder = RecordingResponses(base_client.responses)
    planner = OpenAILunaExperimentalPlanner(SimpleNamespace(responses=recorder), schema, context)
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"], case.get("conversation_context", ()))
            passed, findings = base._case_passed(result, case)
            error = None
        except Exception as exc:
            result = None
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
    actual_cost = _estimated_cost(recorder.records)
    if recorder.attempts > MAX_CALLS or actual_cost > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized v2 regression ceiling exceeded")
    acceptable = base._matrix_acceptable(rows)
    artifact = {
        "version": 2,
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
