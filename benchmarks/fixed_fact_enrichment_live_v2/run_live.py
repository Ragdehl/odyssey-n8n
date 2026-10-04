"""One-shot successor gate for Core fixed-destination semantic enrichment v2."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from benchmarks.fixed_fact_enrichment_live_v1 import run_live as prior
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    OpenAILunaExperimentalPlanner,
)
from odyssey_core.fixed_fact_capture import (
    FIXED_FACT_ENRICHMENT_CONTRACT_VERSION,
    FIXED_FACT_ENRICHMENT_MAX_OUTPUT_TOKENS,
    fixed_fact_enrichment_json_schema,
    render_fixed_fact_enrichment_prompt,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "config/note-schema.json"
CASES_PATH = Path(__file__).with_name("cases.json")
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_FIXED_FACT_ENRICHMENT_V2"
PRODUCTION_MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "low"
MAX_CALLS = 3
AUTHORIZED_CEILING_USD = Decimal("0.012")
CASES_SHA256 = "81a314ef316b8f306e3246149f264ab52102518967c9667cd8173bced384d47d"
PROMPT_SHA256 = "e47188a0f31785140728be90c44b630c0ee7b34735d22284b043b9431427be69"
PROVIDER_SCHEMA_SHA256 = "f8c259623f1f30e2a9bf8598d64c304dc2428f213d6a773997912c248ad1d687"
INPUT_OVERHEAD_BYTES = 1024
STANDARD_INPUT_USD_PER_M = Decimal("0.20")
STANDARD_OUTPUT_USD_PER_M = Decimal("1.20")


def load_cases() -> list[dict[str, str]]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"version", "cases"}:
        raise RuntimeError("fixed-fact v2 registry shape is invalid")
    if payload["version"] != "fixed-fact-enrichment-live-v2" or not isinstance(
        payload["cases"], list
    ):
        raise RuntimeError("fixed-fact v2 registry version is invalid")
    return payload["cases"]


def contract_hashes(schema: dict[str, Any]) -> tuple[str, str]:
    prompt = render_fixed_fact_enrichment_prompt().encode("utf-8")
    provider = json.dumps(
        fixed_fact_enrichment_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(prompt).hexdigest(), hashlib.sha256(provider).hexdigest()


def budget_snapshot() -> dict[str, Decimal | int]:
    cases = load_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    prompt = render_fixed_fact_enrichment_prompt()
    provider = json.dumps(
        fixed_fact_enrichment_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    )
    input_bound = (
        max(len((prompt + provider + case["text"]).encode("utf-8")) for case in cases)
        + INPUT_OVERHEAD_BYTES
    )
    per_call = (
        Decimal(input_bound) * STANDARD_INPUT_USD_PER_M
        + Decimal(FIXED_FACT_ENRICHMENT_MAX_OUTPUT_TOKENS) * STANDARD_OUTPUT_USD_PER_M
    ) / Decimal(1_000_000)
    return {
        "calls": len(cases),
        "input_bound": input_bound,
        "conservative_usd_upper": per_call * Decimal(len(cases)),
    }


def _preflight() -> tuple[list[dict[str, str]], dict[str, Any]]:
    cases = load_cases()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if hashlib.sha256(CASES_PATH.read_bytes()).hexdigest() != CASES_SHA256:
        raise SystemExit("fixed-fact v2 case registry changed")
    if FIXED_FACT_ENRICHMENT_CONTRACT_VERSION != "fixed-fact-semantic-enrichment-v2":
        raise SystemExit("fixed-fact v2 production contract version changed")
    if contract_hashes(schema) != (PROMPT_SHA256, PROVIDER_SCHEMA_SHA256):
        raise SystemExit("fixed-fact v2 model-facing contract changed")
    if (LUNA_EXPERIMENT_MODEL, LUNA_EXPERIMENT_REASONING_EFFORT) != (
        PRODUCTION_MODEL,
        REASONING_EFFORT,
    ):
        raise SystemExit("fixed-fact v2 production model contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["conservative_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("fixed-fact v2 budget changed; fresh authorization required")
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
        raise SystemExit("fixed-fact v2 already has retained live evidence")
    return cases, schema


def run() -> int:
    cases, schema = _preflight()
    from openai import OpenAI

    recorder = prior.RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    planner = OpenAILunaExperimentalPlanner(
        SimpleNamespace(responses=recorder),
        schema,
        {"date": "2026-10-03", "time": "20:30", "timezone": "Europe/Paris"},
    )
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            fact = planner.enrich_fixed_fact(case["text"])
            passed, findings = prior.evaluate(fact, case)
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
        raise SystemExit("Authorized fixed-fact v2 ceiling exceeded")
    acceptable = all(row["passed"] for row in rows)
    artifact = {
        "version": 2,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "cases_sha256": CASES_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "provider_schema_sha256": PROVIDER_SCHEMA_SHA256,
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
