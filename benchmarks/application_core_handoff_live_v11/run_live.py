"""One-shot Core-only live gate after retained Router and Calendar evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
MATRIX = ROOT / "benchmarks/application_core_handoff_live_v11.json"
SCHEMA_PATH = ROOT / "config/note-schema.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_APPLICATION_CORE_HANDOFF_V11"
MATRIX_SHA256 = "d94e2fa7deb16e5a891f40ce28f19a362e8bcc2830cda27a572fee7a2d4207cb"
MAX_CALLS = 2
AUTHORIZED_CEILING_USD = 0.030
STANDARD_INPUT_USD_PER_M = 0.20
STANDARD_OUTPUT_USD_PER_M = 1.20
REGIONAL_MULTIPLIER = 1.10


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
    """Return conservative no-cache byte-as-token bounds for two Core attempts."""
    matrix = _load(MATRIX)
    schema = _load(SCHEMA_PATH)
    input_bytes = 0
    output_tokens = 0
    for case in matrix["cases"]:
        interpretation = _interpretation(case)
        prompt = render_luna_experimental_prompt(
            schema, matrix["current_context"], domain_interpretation=interpretation
        )
        provider_schema = json.dumps(
            luna_experimental_result_json_schema(schema, interpretation),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        input_bytes += (
            len(prompt.encode()) + len(provider_schema.encode()) + len(case["request"].encode())
        )
        output_tokens += LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS
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
    """Count attempts while retaining only bounded output and usage."""

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
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        return response


def _actual(plan: Any) -> dict[str, Any]:
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
    temporal_fact = next(
        (fact for fact in first.facts if "[[calendar/days/" in fact),
        None,
    )
    return {
        "kind": "write",
        "target_entity": first.target.entity,
        "reference_entity": reference_entity,
        "temporal_fact": temporal_fact,
    }


def _matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    if actual.get("target_entity") != expected["target_entity"]:
        return False
    if actual.get("reference_entity") != expected["reference_entity"]:
        return False
    fact = actual.get("temporal_fact")
    return isinstance(fact, str) and (
        f"[[calendar/days/{expected['date']}|{expected['temporal_text']}]]" in fact
    )


def _preflight() -> tuple[dict[str, Any], dict[str, Any]]:
    if _sha(MATRIX) != MATRIX_SHA256:
        raise SystemExit("v11 matrix changed; refusing live gate")
    if LUNA_EXPERIMENT_MODEL != "gpt-5.6-luna" or LUNA_EXPERIMENT_REASONING_EFFORT != "low":
        raise SystemExit("Core production model contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["regional_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("v11 live-gate budget changed; fresh authorization required")
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
        raise SystemExit("v11 already has retained live evidence; refusing a second run")
    return _load(MATRIX), _load(SCHEMA_PATH)


def _estimated_cost(records: list[dict[str, Any]]) -> float:
    return sum(
        record["input_tokens"] / 1_000_000 * STANDARD_INPUT_USD_PER_M
        + record["output_tokens"] / 1_000_000 * STANDARD_OUTPUT_USD_PER_M
        for record in records
    )


def run() -> int:
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
        interpretation = _interpretation(case)
        planner = OpenAILunaExperimentalPlanner(
            client,
            schema,
            matrix["current_context"],
            domain_interpretation=interpretation,
        )
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
        raise SystemExit("Authorized v11 live-gate ceiling exceeded")
    artifact = {
        "version": 11,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "router_retained_result": "v5 8/8",
        "calendar_retained_result": "v10 8/8",
        "matrix_sha256": MATRIX_SHA256,
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
