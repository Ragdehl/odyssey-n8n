"""One-shot Calendar-focused GPT-6 Luna/low live gate after Router v5 passed 8/8."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_apps.calendar.planning import (
    CALENDAR_PLANNER_MAX_OUTPUT_TOKENS,
    CALENDAR_PLANNER_MODEL,
    CALENDAR_PLANNER_REASONING_EFFORT,
    OpenAICalendarPlanner,
    TemporalReferencePart,
    calendar_plan_json_schema,
    render_calendar_prompt,
)
from odyssey_core.semantic_write import IdentityPart

ROOT = Path(__file__).resolve().parents[2]
CALENDAR_MATRIX = ROOT / "benchmarks/calendar_planner/regression_v3.json"
SCHEMA_PATH = ROOT / "config/note-schema.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_APPLICATION_ROUTER_CALENDAR_V7"
CALENDAR_MATRIX_SHA256 = "7aca0adc8b436644f4b550c4fd7ee8c4047a6d5cb3fdcfaad1f5ba4d31ad1f86"
ROUTER_V5_PASS_COMMIT = "e186cf48561cfda9097f42268c8efaa82bab18bf"
STANDARD_INPUT_USD_PER_M = 0.10
STANDARD_OUTPUT_USD_PER_M = 0.50
REGIONAL_MULTIPLIER = 1.10
MAX_CALLS = 10
AUTHORIZED_CEILING_USD = 0.012


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def budget_snapshot() -> dict[str, float | int]:
    """Return a conservative no-cache ceiling for the 10-case Calendar-only gate."""
    matrix = _load_json(CALENDAR_MATRIX)
    schema = _load_json(SCHEMA_PATH)
    prompt = render_calendar_prompt(
        current_context=matrix["current_context"], conversation_context=()
    )
    provider_schema = json.dumps(
        calendar_plan_json_schema(schema), ensure_ascii=False, separators=(",", ":")
    )
    input_bytes = sum(
        len(prompt.encode()) + len(provider_schema.encode()) + len(case["request"].encode())
        for case in matrix["cases"]
    )
    output_tokens = len(matrix["cases"]) * CALENDAR_PLANNER_MAX_OUTPUT_TOKENS
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
    """Retain bounded attempt diagnostics plus successful synthetic outputs and usage."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.attempts = 0
        self.records: list[dict[str, Any]] = []
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
                "attempt": self.attempts,
                "output_text": getattr(response, "output_text", None),
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        return response


def _provider_failure_after(
    recorder: RecordingResponses, before_attempts: int
) -> dict[str, Any] | None:
    if recorder.attempts <= before_attempts or not recorder.failures:
        return None
    failure = recorder.failures[-1]
    return failure if failure["attempt"] > before_attempts else None


def _calendar_actual(plan: Any) -> dict[str, Any]:
    actual: dict[str, Any] = {
        "outcome": plan.outcome.value,
        "intent": plan.intent.value if plan.intent is not None else None,
        "temporal_kind": plan.temporal.kind.value,
        "failure_code": plan.failure_code.value if plan.failure_code is not None else None,
    }
    if plan.temporal.exact_date is not None:
        actual["exact_date"] = plan.temporal.exact_date
    if plan.temporal.date_range is not None:
        actual["range_start"] = plan.temporal.date_range.start
        actual["range_end_exclusive"] = plan.temporal.date_range.end_exclusive
    if plan.semantic_write is not None:
        temporal_texts: list[str] = []
        identities: list[str] = []
        for operation in plan.semantic_write.operations:
            target_name = operation.target.direct_name or operation.target.description
            if target_name not in identities:
                identities.append(target_name)
            for fact in operation.facts:
                for part in fact.parts:
                    if isinstance(part, TemporalReferencePart):
                        temporal_texts.append(part.text)
                    elif isinstance(part, IdentityPart) and part.text not in identities:
                        identities.append(part.text)
        if temporal_texts:
            actual["temporal_text"] = temporal_texts[0]
        actual["identity_mentions"] = identities
    return actual


def _expected_subset(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _raw_for_call(recorder: RecordingResponses, before: int) -> Any:
    if len(recorder.records) <= before:
        return None
    raw = recorder.records[-1]["output_text"]
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _git_head() -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()


def _router_boundary_unchanged_since_v5() -> bool:
    """Keep the already-passed Router evidence reusable for this Calendar-only successor."""
    return (
        subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "diff",
                "--quiet",
                ROUTER_V5_PASS_COMMIT,
                "--",
                "odyssey_apps/router.py",
                "odyssey_apps/calendar/__init__.py",
            ],
            check=False,
        ).returncode
        == 0
    )


def _preflight() -> tuple[dict[str, Any], dict[str, Any]]:
    if _sha256(CALENDAR_MATRIX) != CALENDAR_MATRIX_SHA256:
        raise SystemExit("Calendar matrix changed; refusing live gate")
    if not _router_boundary_unchanged_since_v5():
        raise SystemExit("Router boundary changed since its retained 8/8 evidence")
    if CALENDAR_PLANNER_REASONING_EFFORT != "low":
        raise SystemExit("Calendar effort is not the authorized low-effort candidate")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["regional_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("Live-gate ceiling changed; fresh authorization required")
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
        raise SystemExit("Attempt v7 already has retained live evidence; refusing a second run")
    return _load_json(CALENDAR_MATRIX), _load_json(SCHEMA_PATH)


def run() -> int:
    """Execute one frozen 10-case Calendar Luna/low gate and retain bounded evidence."""
    matrix, schema = _preflight()
    try:
        from openai import OpenAI
    except ImportError as error:
        raise SystemExit("OpenAI SDK is required only for the authorized live gate") from error
    base = OpenAI(max_retries=0, timeout=30.0)
    recorder = RecordingResponses(base.responses)
    calendar = OpenAICalendarPlanner(
        SimpleNamespace(responses=recorder), schema, matrix["current_context"]
    )
    rows: list[dict[str, Any]] = []
    for case in matrix["cases"]:
        before_records = len(recorder.records)
        before_attempts = recorder.attempts
        try:
            actual = _calendar_actual(calendar.plan(case["request"]))
            error = None
        except Exception as exc:
            actual = {}
            error = type(exc).__name__
        rows.append(
            {
                "gate": "calendar",
                "id": case["id"],
                "passed": error is None and _expected_subset(actual, case["expect"]),
                "expect": case["expect"],
                "actual": actual,
                "raw_output": _raw_for_call(recorder, before_records),
                "provider_failure": _provider_failure_after(recorder, before_attempts),
                "error": error,
            }
        )

    input_tokens = sum(item["input_tokens"] for item in recorder.records)
    output_tokens = sum(item["output_tokens"] for item in recorder.records)
    standard_cost = input_tokens / 1_000_000 * STANDARD_INPUT_USD_PER_M
    standard_cost += output_tokens / 1_000_000 * STANDARD_OUTPUT_USD_PER_M
    regional_upper = standard_cost * REGIONAL_MULTIPLIER
    if recorder.attempts > MAX_CALLS or regional_upper > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized live-gate ceiling exceeded")

    artifact = {
        "version": 7,
        "commit": _git_head(),
        "router_evidence_commit": ROUTER_V5_PASS_COMMIT,
        "router_retained_result": "8/8",
        "calendar_matrix_sha256": CALENDAR_MATRIX_SHA256,
        "calendar_model": CALENDAR_PLANNER_MODEL,
        "calendar_reasoning_effort": CALENDAR_PLANNER_REASONING_EFFORT,
        "provider_attempts": recorder.attempts,
        "completed_provider_responses": len(recorder.records),
        "automatic_retries": 0,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_standard_cost_usd": standard_cost,
        "estimated_regional_upper_usd": regional_upper,
        "passed": all(row["passed"] for row in rows),
        "rows": rows,
    }
    output_path = RESULTS_DIR / f"{artifact['commit'][:12]}.json"
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"provider_attempts={artifact['provider_attempts']}")
    print(f"completed_provider_responses={artifact['completed_provider_responses']}")
    print(f"standard_cost_usd={standard_cost:.8f}")
    print(f"regional_upper_usd={regional_upper:.8f}")
    print(f"passed={artifact['passed']}")
    print(f"artifact={output_path.relative_to(ROOT)}")
    return 0 if artifact["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
