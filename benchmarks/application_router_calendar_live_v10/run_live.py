"""One-shot live gate for minimal Calendar interpretation and app-to-Core handoff."""

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
    calendar_plan_json_schema,
    render_calendar_prompt,
)
from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
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
CALENDAR_MATRIX = ROOT / "benchmarks/calendar_planner/regression_v6.json"
CORE_MATRIX = ROOT / "benchmarks/application_router_calendar_live_v10_core.json"
SCHEMA_PATH = ROOT / "config/note-schema.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_APPLICATION_ROUTER_CALENDAR_V10"
CALENDAR_MATRIX_SHA256 = "056b33f6cffd3c179dc7ba3e2f9a82695933cfe90f34b9624a063ea9f9a1b9e2"
CORE_MATRIX_SHA256 = "ac0d8d94ac721d4a956af825dc9729ac560afd07cbf0bc0c93b2eda12167e6e4"
PRE_REDESIGN_COMMIT = "e78781b6c2bf614848c0a99130df3ef4043b7fe1"
ROUTER_RETAINED_RESULT = "v5 8/8"
MAX_CALLS = 10
AUTHORIZED_CEILING_USD = 0.034
REGIONAL_MULTIPLIER = 1.10
RATES = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.6-luna": (0.20, 1.20),
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _interpretation(case: dict[str, Any]) -> DomainInterpretation:
    raw = case["domain_interpretation"]
    return DomainInterpretation(
        raw["capability_id"],
        case["request"],
        raw["intent"],
        tuple(
            DomainEvidence(item["kind"], item["source_text"], item["value"])
            for item in raw["evidence"]
        ),
    )


def budget_snapshot() -> dict[str, float | int]:
    """Return a conservative no-cache byte-as-token upper bound for all bounded provider attempts."""
    calendar = _load(CALENDAR_MATRIX)
    core = _load(CORE_MATRIX)
    schema = _load(SCHEMA_PATH)
    totals: dict[str, int] = {model: 0 for model in RATES}
    outputs: dict[str, int] = {model: 0 for model in RATES}

    calendar_prompt = render_calendar_prompt(current_context=calendar["current_context"])
    calendar_schema = json.dumps(
        calendar_plan_json_schema(), ensure_ascii=False, separators=(",", ":")
    )
    for case in calendar["cases"]:
        totals[CALENDAR_PLANNER_MODEL] += (
            len(calendar_prompt.encode())
            + len(calendar_schema.encode())
            + len(case["request"].encode())
        )
        outputs[CALENDAR_PLANNER_MODEL] += CALENDAR_PLANNER_MAX_OUTPUT_TOKENS

    for case in core["cases"]:
        interpretation = _interpretation(case)
        prompt = render_luna_experimental_prompt(
            schema, core["current_context"], domain_interpretation=interpretation
        )
        provider_schema = json.dumps(
            luna_experimental_result_json_schema(schema, interpretation),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        totals[LUNA_EXPERIMENT_MODEL] += (
            len(prompt.encode()) + len(provider_schema.encode()) + len(case["request"].encode())
        )
        outputs[LUNA_EXPERIMENT_MODEL] += LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS

    standard = 0.0
    for model, (input_rate, output_rate) in RATES.items():
        standard += totals[model] / 1_000_000 * input_rate
        standard += outputs[model] / 1_000_000 * output_rate
    return {
        "calls": len(calendar["cases"]) + len(core["cases"]),
        "input_bytes_upper": sum(totals.values()),
        "max_output_tokens": sum(outputs.values()),
        "standard_usd_upper": standard,
        "regional_usd_upper": standard * REGIONAL_MULTIPLIER,
    }


class RecordingResponses:
    """Count every provider attempt while retaining only bounded synthetic output and usage."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.attempts = 0
        self.records: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.attempts += 1
        model = kwargs.get("model")
        try:
            response = self._responses.create(**kwargs)
        except Exception as error:
            self.failures.append(
                {
                    "attempt": self.attempts,
                    "model": model,
                    "error_type": type(error).__name__,
                    "status_code": getattr(error, "status_code", None),
                }
            )
            raise
        usage = getattr(response, "usage", None)
        self.records.append(
            {
                "attempt": self.attempts,
                "model": model,
                "output_text": getattr(response, "output_text", None),
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        return response


def _calendar_actual(plan: Any) -> dict[str, Any]:
    result = {
        "outcome": plan.outcome.value,
        "intent": plan.intent.value if plan.intent is not None else None,
        "temporal_kind": plan.temporal.kind.value,
        "failure_code": plan.failure_code.value if plan.failure_code is not None else None,
    }
    if plan.temporal.exact_date is not None:
        result["exact_date"] = plan.temporal.exact_date
    if plan.temporal.date_range is not None:
        result["range_start"] = plan.temporal.date_range.start
        result["range_end_exclusive"] = plan.temporal.date_range.end_exclusive
    if plan.temporal_text is not None:
        result["temporal_text"] = plan.temporal_text
    return result


def _core_actual(plan: Any) -> dict[str, Any]:
    if (
        not isinstance(plan, RequestPlan)
        or len(plan.actions) != 1
        or not isinstance(plan.actions[0], WriteAction)
    ):
        return {"kind": type(plan).__name__}
    action = plan.actions[0]
    if not action.units:
        return {"kind": "write", "units": 0}
    first = action.units[0]
    reference_entity = None
    if first.references:
        index = first.references[0].target_index
        if 0 <= index < len(action.units):
            reference_entity = action.units[index].target.entity
    temporal = None
    for fact in first.facts:
        if "[[calendar/days/" in fact:
            temporal = fact
            break
    return {
        "kind": "write",
        "target_entity": first.target.entity,
        "reference_entity": reference_entity,
        "temporal_fact": temporal,
    }


def _expected_subset(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _core_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    if (
        actual.get("target_entity") != expected["target_entity"]
        or actual.get("reference_entity") != expected["reference_entity"]
    ):
        return False
    fact = actual.get("temporal_fact")
    return (
        isinstance(fact, str)
        and f"[[calendar/days/{expected['date']}|{expected['temporal_text']}]]" in fact
    )


def _preflight() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if _sha(CALENDAR_MATRIX) != CALENDAR_MATRIX_SHA256 or _sha(CORE_MATRIX) != CORE_MATRIX_SHA256:
        raise SystemExit("v10 matrix changed; refusing live gate")
    if CALENDAR_PLANNER_MODEL != "gpt-6-luna" or CALENDAR_PLANNER_REASONING_EFFORT != "low":
        raise SystemExit("Calendar production model contract changed")
    if LUNA_EXPERIMENT_MODEL != "gpt-5.6-luna" or LUNA_EXPERIMENT_REASONING_EFFORT != "low":
        raise SystemExit("Core Luna production model contract changed")
    if (
        subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "diff",
                "--quiet",
                PRE_REDESIGN_COMMIT,
                "--",
                "odyssey_apps/router.py",
                "odyssey_apps/calendar/__init__.py",
            ],
            check=False,
        ).returncode
        != 0
    ):
        raise SystemExit(
            "Router model-facing boundary changed; retained Router evidence cannot be reused"
        )
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["regional_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("v10 live-gate budget changed; fresh authorization required")
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
        raise SystemExit("v10 already has retained live evidence; refusing a second run")
    return _load(CALENDAR_MATRIX), _load(CORE_MATRIX), _load(SCHEMA_PATH)


def _estimated_cost(records: list[dict[str, Any]]) -> float:
    total = 0.0
    for record in records:
        input_rate, output_rate = RATES[record["model"]]
        total += record["input_tokens"] / 1_000_000 * input_rate
        total += record["output_tokens"] / 1_000_000 * output_rate
    return total


def run() -> int:
    calendar_matrix, core_matrix, schema = _preflight()
    try:
        from openai import OpenAI
    except ImportError as error:
        raise SystemExit("OpenAI SDK is required only for the authorized live gate") from error
    base = OpenAI(max_retries=0, timeout=30.0)
    recorder = RecordingResponses(base.responses)
    client = SimpleNamespace(responses=recorder)
    calendar = OpenAICalendarPlanner(client, calendar_matrix["current_context"])
    rows: list[dict[str, Any]] = []

    for case in calendar_matrix["cases"]:
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
                "error": error,
            }
        )

    for case in core_matrix["cases"]:
        interpretation = _interpretation(case)
        planner = OpenAILunaExperimentalPlanner(
            client, schema, core_matrix["current_context"], domain_interpretation=interpretation
        )
        try:
            actual = _core_actual(planner.plan(case["request"]))
            error = None
        except Exception as exc:
            actual = {}
            error = type(exc).__name__
        rows.append(
            {
                "gate": "core_luna_handoff",
                "id": case["id"],
                "passed": error is None and _core_matches(actual, case["expect"]),
                "expect": case["expect"],
                "actual": actual,
                "error": error,
            }
        )

    standard = _estimated_cost(recorder.records)
    regional = standard * REGIONAL_MULTIPLIER
    if recorder.attempts > MAX_CALLS or regional > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized v10 live-gate ceiling exceeded")
    artifact = {
        "version": 10,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "router_retained_result": ROUTER_RETAINED_RESULT,
        "calendar_matrix_sha256": CALENDAR_MATRIX_SHA256,
        "core_matrix_sha256": CORE_MATRIX_SHA256,
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
