"""One-shot Sol fallback gate for the Journal-converged ordinary Core contract."""

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
from odyssey_core.request_planning import (
    PLANNER_AUTOMATIC_RETRIES,
    PLANNER_MAX_OUTPUT_TOKENS,
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    OpenAIRequestPlanner,
    planner_result_json_schema,
    render_request_planner_prompt,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "config/note-schema.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_PLANNER_SOL_FALLBACK_V15"
CASE_ID = "SWR01-self-coworkers"
PROMPT_SHA256 = "a696410a65ec841c153498bee9788f116fb8b1620bde83882c4d3d6495ee0633"
PROVIDER_SCHEMA_SHA256 = "433c43a72f335f22bcfd22fe3311a728acf8a1c4edf5e3d58d0ac3d9654d75db"
MAX_CALLS = 1
AUTHORIZED_CEILING_USD = Decimal("0.020")
INPUT_USD_PER_M = Decimal("0.20")
OUTPUT_USD_PER_M = Decimal("1.20")


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _case_and_context() -> tuple[dict[str, Any], dict[str, str]]:
    cases, context = base.load_gate_cases()
    return next(case for case in cases if case["id"] == CASE_ID), context


def _contract_hashes(schema: dict[str, Any], context: dict[str, str]) -> tuple[str, str]:
    prompt = render_request_planner_prompt(schema, context).encode("utf-8")
    provider = json.dumps(
        planner_result_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(prompt).hexdigest(), hashlib.sha256(provider).hexdigest()


def budget_snapshot() -> dict[str, Decimal | int]:
    schema = _schema()
    case, context = _case_and_context()
    prompt = render_request_planner_prompt(schema, context).encode("utf-8")
    provider = json.dumps(
        planner_result_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    input_bytes = len(prompt) + len(provider) + len(case["request"].encode("utf-8"))
    upper = (
        Decimal(input_bytes) * INPUT_USD_PER_M
        + Decimal(PLANNER_MAX_OUTPUT_TOKENS) * OUTPUT_USD_PER_M
    ) / Decimal(1_000_000)
    return {"calls": 1, "input_bytes_upper": input_bytes, "standard_usd_upper": upper}


class RecordingResponses:
    """Retain bounded usage and transport failure metadata only."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.attempts = 0
        self.records: list[dict[str, int]] = []
        self.failures: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
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
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        return response


def _preflight() -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    schema = _schema()
    case, context = _case_and_context()
    if (PLANNER_MODEL, PLANNER_REASONING_EFFORT, PLANNER_AUTOMATIC_RETRIES) != (
        "gpt-5.6-sol",
        "low",
        0,
    ):
        raise SystemExit("v15 Sol production contract changed")
    if _contract_hashes(schema, context) != (PROMPT_SHA256, PROVIDER_SCHEMA_SHA256):
        raise SystemExit("v15 Sol candidate contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["standard_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("v15 Sol budget changed; fresh authorization required")
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
        raise SystemExit("v15 already has retained evidence; refusing a second run")
    return case, context, schema


def _estimated_cost(records: list[dict[str, int]]) -> Decimal:
    return sum(
        (
            Decimal(row["input_tokens"]) * INPUT_USD_PER_M
            + Decimal(row["output_tokens"]) * OUTPUT_USD_PER_M
        )
        / Decimal(1_000_000)
        for row in records
    )


def run() -> int:
    case, context, schema = _preflight()
    from openai import OpenAI

    recorder = RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    planner = OpenAIRequestPlanner(SimpleNamespace(responses=recorder), schema, context)
    try:
        result = planner.plan(case["request"], case.get("conversation_context", ()))
        passed, findings = base._case_passed(result, case)
        error = None
    except Exception as exc:
        passed = False
        findings = [type(exc).__name__[:120]]
        error = type(exc).__name__
    actual_cost = _estimated_cost(recorder.records)
    if recorder.attempts > MAX_CALLS or actual_cost > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized v15 Sol ceiling exceeded")
    artifact = {
        "version": 15,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "case_id": CASE_ID,
        "model": PLANNER_MODEL,
        "reasoning_effort": PLANNER_REASONING_EFFORT,
        "provider_attempts": recorder.attempts,
        "completed_provider_responses": len(recorder.records),
        "automatic_retries": 0,
        "estimated_standard_cost_usd": str(actual_cost),
        "passed": passed,
        "findings": findings,
        "error": error,
        "provider_failures": recorder.failures,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{artifact['commit'][:12]}.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider_attempts={artifact['provider_attempts']}")
    print(f"completed_provider_responses={artifact['completed_provider_responses']}")
    print(f"standard_cost_usd={actual_cost}")
    print(f"passed={passed}")
    print(f"artifact={out.relative_to(ROOT)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
