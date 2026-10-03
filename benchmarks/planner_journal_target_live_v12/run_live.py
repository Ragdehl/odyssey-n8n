"""One-shot live gate for schema-driven journal target selection by entry date."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    OpenAILunaExperimentalPlanner,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)
from odyssey_core.request_planning import RequestPlan, WriteAction

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "benchmarks/planner_journal_target_live_v12.json"
SCHEMA_PATH = ROOT / "config/note-schema.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_PLANNER_JOURNAL_TARGET_V12"
MATRIX_SHA256 = "bbfea162ae7d1999f526d0f3bd070077ee3bb5e28bdc31683831f71e3e076039"
PROMPT_SHA256 = "ce32b76d5b2dccff8afd75f4310611ced1f07d79e646805dbb80be386e3a064e"
PROVIDER_SCHEMA_SHA256 = "65877ae84df406d36648c37a7ad4826033990a1d1b2cc8a1d1a193a5e7ecedce"
MAX_CALLS = 2
AUTHORIZED_CEILING_USD = 0.030
STANDARD_INPUT_USD_PER_M = 0.20
STANDARD_OUTPUT_USD_PER_M = 1.20
REGIONAL_MULTIPLIER = 1.10


def _load(path: Path) -> Any:
    """Load one UTF-8 JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def _sha_bytes(value: bytes) -> str:
    """Return one SHA-256 digest for a model-facing artifact."""
    return hashlib.sha256(value).hexdigest()


def budget_snapshot() -> dict[str, float | int]:
    """Return a conservative no-cache byte-as-token ceiling for the two calls."""
    matrix = _load(MATRIX)
    schema = _load(SCHEMA_PATH)
    prompt = render_luna_experimental_prompt(schema, matrix["current_context"])
    provider_schema = json.dumps(
        luna_experimental_result_json_schema(schema),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    per_case = len(prompt.encode()) + len(provider_schema.encode())
    input_bytes = sum(per_case + len(case["request"].encode()) for case in matrix["cases"])
    output_tokens = LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS * len(matrix["cases"])
    standard = input_bytes / 1_000_000 * STANDARD_INPUT_USD_PER_M
    standard += output_tokens / 1_000_000 * STANDARD_OUTPUT_USD_PER_M
    return {
        "calls": len(matrix["cases"]),
        "input_bytes_upper": input_bytes,
        "max_output_tokens": output_tokens,
        "standard_usd_upper": standard,
        "regional_usd_upper": standard * REGIONAL_MULTIPLIER,
    }


class RecordingResponses:
    """Count provider attempts while retaining only bounded usage and failure metadata."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.attempts = 0
        self.records: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        """Forward one zero-retry call and record bounded provider evidence."""
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


def _actual(plan: Any) -> dict[str, Any]:
    """Project only the journal-target semantics needed by this acceptance oracle."""
    if not isinstance(plan, RequestPlan) or len(plan.actions) != 1:
        return {"kind": type(plan).__name__}
    action = plan.actions[0]
    if not isinstance(action, WriteAction) or len(action.units) != 1:
        return {"kind": type(action).__name__}
    unit = action.units[0]
    return {
        "kind": "write",
        "target_type": unit.target.type,
        "filters": [
            {"field": item.field, "op": item.op, "value": item.value}
            for item in unit.target.filters
        ],
        "properties": [
            {"field": item.field, "op": item.op, "value": item.value} for item in unit.properties
        ],
        "facts": list(unit.facts),
    }


def _matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Require exact date identity evidence without constraining incidental wording."""
    value = expected["date"]
    if actual.get("target_type") != "journal_entry":
        return False
    if actual.get("filters") != [{"field": "entry_date", "op": "eq", "value": value}]:
        return False
    if actual.get("properties") != [{"field": "entry_date", "op": "set", "value": value}]:
        return False
    facts = actual.get("facts")
    if not isinstance(facts, list) or not facts:
        return False
    return expected["fact_contains"].casefold() in " ".join(facts).casefold()


def _contract_hashes(schema: dict[str, Any], context: dict[str, str]) -> tuple[str, str]:
    """Hash the exact production prompt and provider schema used by the gate."""
    prompt = render_luna_experimental_prompt(schema, context).encode("utf-8")
    provider_schema = json.dumps(
        luna_experimental_result_json_schema(schema),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha_bytes(prompt), _sha_bytes(provider_schema)


def _preflight() -> tuple[dict[str, Any], dict[str, Any]]:
    """Refuse provider authority unless every frozen gate condition still holds."""
    matrix = _load(MATRIX)
    schema = _load(SCHEMA_PATH)
    if _sha_bytes(MATRIX.read_bytes()) != MATRIX_SHA256:
        raise SystemExit("v12 matrix changed; refusing live gate")
    if LUNA_EXPERIMENT_MODEL != "gpt-5.6-luna" or LUNA_EXPERIMENT_REASONING_EFFORT != "low":
        raise SystemExit("Core production model contract changed")
    prompt_hash, schema_hash = _contract_hashes(schema, matrix["current_context"])
    if prompt_hash != PROMPT_SHA256 or schema_hash != PROVIDER_SCHEMA_SHA256:
        raise SystemExit("v12 candidate model-facing contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["regional_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("v12 live-gate budget changed; fresh authorization required")
    if os.environ.get(AUTH_ENV) != "1":
        raise SystemExit(f"Refusing live calls: set {AUTH_ENV}=1 only after explicit authorization")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Refusing live calls: OPENAI_API_KEY is unavailable")
    status = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    ).strip()
    if status:
        raise SystemExit("Refusing live calls from a dirty worktree")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if any(RESULTS_DIR.glob("*.json")):
        raise SystemExit("v12 already has retained live evidence; refusing a second run")
    return matrix, schema


def _estimated_cost(records: list[dict[str, Any]]) -> float:
    """Estimate Standard cost from observed token usage."""
    return sum(
        row["input_tokens"] / 1_000_000 * STANDARD_INPUT_USD_PER_M
        + row["output_tokens"] / 1_000_000 * STANDARD_OUTPUT_USD_PER_M
        for row in records
    )


def run() -> int:
    """Run the authorized one-shot gate and retain bounded auditable evidence."""
    matrix, schema = _preflight()
    try:
        from openai import OpenAI
    except ImportError as error:
        raise SystemExit("OpenAI SDK is required only for the authorized live gate") from error
    base = OpenAI(max_retries=0, timeout=30.0)
    recorder = RecordingResponses(base.responses)
    client = SimpleNamespace(responses=recorder)
    rows: list[dict[str, Any]] = []
    for case in matrix["cases"]:
        planner = OpenAILunaExperimentalPlanner(client, schema, matrix["current_context"])
        try:
            actual = _actual(planner.plan(case["request"]))
            error = None
        except Exception as exc:
            actual = {}
            error = type(exc).__name__
        rows.append(
            {
                "id": case["id"],
                "passed": error is None and _matches(actual, case["expect"]),
                "expect": case["expect"],
                "actual": actual,
                "error": error,
            }
        )
    standard = _estimated_cost(recorder.records)
    regional = standard * REGIONAL_MULTIPLIER
    if recorder.attempts > MAX_CALLS or regional > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized v12 live-gate ceiling exceeded")
    artifact = {
        "version": 12,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "matrix_sha256": MATRIX_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "provider_schema_sha256": PROVIDER_SCHEMA_SHA256,
        "provider_attempts": recorder.attempts,
        "completed_provider_responses": len(recorder.records),
        "automatic_retries": 0,
        "estimated_standard_cost_usd": standard,
        "estimated_regional_upper_usd": regional,
        "passed": all(row["passed"] for row in rows),
        "rows": rows,
        "provider_failures": recorder.failures,
    }
    out = RESULTS_DIR / f"{artifact['commit'][:12]}.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider_attempts={artifact['provider_attempts']}")
    print(f"completed_provider_responses={artifact['completed_provider_responses']}")
    print(f"standard_cost_usd={standard:.8f}")
    print(f"regional_upper_usd={regional:.8f}")
    print(f"passed={artifact['passed']}")
    print(f"artifact={out.relative_to(ROOT)}")
    return 0 if artifact["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
