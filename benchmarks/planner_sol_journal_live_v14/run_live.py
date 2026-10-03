"""One-shot Sol fallback gate for the schema-driven Journal date target contract."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_core.request_planning import (
    PLANNER_AUTOMATIC_RETRIES,
    PLANNER_MAX_OUTPUT_TOKENS,
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    OpenAIRequestPlanner,
    RequestPlan,
    WriteAction,
    planner_result_json_schema,
    render_request_planner_prompt,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "config/note-schema.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_PLANNER_SOL_JOURNAL_V14"
CURRENT_CONTEXT = {"date": "2026-10-03", "time": "17:00", "timezone": "Europe/Paris"}
REQUEST = "Escribe en mi diario que hoy he tenido un día muy tranquilo."
EXPECTED_DATE = "2026-10-03"
MAX_CALLS = 1
AUTHORIZED_CEILING_USD = Decimal("0.021")
INPUT_USD_PER_M = Decimal("0.20")
OUTPUT_USD_PER_M = Decimal("1.20")
PROMPT_SHA256 = "25194c0ae978f80ff12406934ab3a5aeb84407cfd3e1313961ad816217c1779f"
PROVIDER_SCHEMA_SHA256 = "dd7fba6948ce1503518f17df233b1842bda7316d45bf693f95c8c0cf538a518f"


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _contract_hashes(schema: dict[str, Any]) -> tuple[str, str]:
    prompt = render_request_planner_prompt(schema, CURRENT_CONTEXT).encode("utf-8")
    provider = json.dumps(
        planner_result_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(prompt).hexdigest(), hashlib.sha256(provider).hexdigest()


def budget_snapshot() -> dict[str, Decimal | int]:
    schema = _schema()
    prompt = render_request_planner_prompt(schema, CURRENT_CONTEXT).encode("utf-8")
    provider = json.dumps(
        planner_result_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    input_bytes = len(prompt) + len(provider) + len(REQUEST.encode("utf-8"))
    upper = (
        Decimal(input_bytes) * INPUT_USD_PER_M
        + Decimal(PLANNER_MAX_OUTPUT_TOKENS) * OUTPUT_USD_PER_M
    ) / Decimal(1_000_000)
    return {"calls": 1, "input_bytes_upper": input_bytes, "standard_usd_upper": upper}


class RecordingResponses:
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


def _actual(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, RequestPlan) or len(plan.actions) != 1:
        return {"kind": type(plan).__name__}
    action = plan.actions[0]
    if not isinstance(action, WriteAction) or len(action.units) != 1:
        return {"kind": type(action).__name__}
    unit = action.units[0]
    return {
        "kind": "write",
        "target_type": unit.target.type,
        "filters": [(item.field, item.op, item.value) for item in unit.target.filters],
        "properties": [(item.field, item.op, item.value) for item in unit.properties],
        "facts": list(unit.facts),
    }


def _matches(actual: dict[str, Any]) -> bool:
    return (
        actual.get("target_type") == "journal_entry"
        and actual.get("filters") == [("entry_date", "eq", EXPECTED_DATE)]
        and actual.get("properties") == [("entry_date", "set", EXPECTED_DATE)]
        and "tranquilo" in " ".join(actual.get("facts", ())).casefold()
    )


def _preflight() -> dict[str, Any]:
    schema = _schema()
    if (PLANNER_MODEL, PLANNER_REASONING_EFFORT, PLANNER_AUTOMATIC_RETRIES) != (
        "gpt-5.6-sol",
        "low",
        0,
    ):
        raise SystemExit("Sol fallback production contract changed")
    if _contract_hashes(schema) != (PROMPT_SHA256, PROVIDER_SCHEMA_SHA256):
        raise SystemExit("v14 Sol candidate contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["standard_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("v14 Sol budget changed; fresh authorization required")
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
        raise SystemExit("v14 already has retained evidence; refusing a second run")
    return schema


def run() -> int:
    schema = _preflight()
    from openai import OpenAI

    recorder = RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    planner = OpenAIRequestPlanner(SimpleNamespace(responses=recorder), schema, CURRENT_CONTEXT)
    error = None
    try:
        actual = _actual(planner.plan(REQUEST))
    except Exception as exc:
        actual = {}
        error = type(exc).__name__
    passed = error is None and _matches(actual)
    actual_cost = sum(
        (
            Decimal(row["input_tokens"]) * INPUT_USD_PER_M
            + Decimal(row["output_tokens"]) * OUTPUT_USD_PER_M
        )
        / Decimal(1_000_000)
        for row in recorder.records
    )
    if recorder.attempts > MAX_CALLS or actual_cost > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized v14 Sol ceiling exceeded")
    artifact = {
        "version": 14,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "model": PLANNER_MODEL,
        "reasoning_effort": PLANNER_REASONING_EFFORT,
        "provider_attempts": recorder.attempts,
        "completed_provider_responses": len(recorder.records),
        "automatic_retries": 0,
        "estimated_standard_cost_usd": str(actual_cost),
        "passed": passed,
        "actual": actual,
        "error": error,
        "provider_failures": recorder.failures,
    }
    out = RESULTS_DIR / f"{artifact['commit'][:12]}.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider_attempts={recorder.attempts}")
    print(f"completed_provider_responses={len(recorder.records)}")
    print(f"standard_cost_usd={actual_cost}")
    print(f"passed={passed}")
    print(f"artifact={out.relative_to(ROOT)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
