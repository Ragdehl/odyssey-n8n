"""One-shot live evidence gate for Journal-converged Router + Calendar contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from benchmarks.calendar_legacy_descriptor import CALENDAR_DESCRIPTOR
from odyssey_apps import ApplicationDescriptor, ApplicationRegistry
from odyssey_apps.calendar.planning import (
    CALENDAR_PLANNER_MAX_OUTPUT_TOKENS,
    CALENDAR_PLANNER_MODEL,
    CALENDAR_PLANNER_REASONING_EFFORT,
    OpenAICalendarPlanner,
    calendar_plan_json_schema,
    render_calendar_prompt,
)
from odyssey_apps.router import (
    ROUTER_MAX_OUTPUT_TOKENS,
    ROUTER_MODEL,
    ROUTER_REASONING_EFFORT,
    OpenAIApplicationRouter,
    render_router_prompt,
    route_plan_json_schema,
)

ROOT = Path(__file__).resolve().parents[2]
ROUTER_MATRIX = ROOT / "benchmarks/application_router/regression_v3.json"
CALENDAR_MATRIX = ROOT / "benchmarks/calendar_planner/regression_v7.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
AUTH_ENV = "ODYSSEY_RUN_APPLICATION_ROUTER_CALENDAR_V11"
ROUTER_MATRIX_SHA256 = "7e27bb18901157df548eb8703d454b7574d74b04dcb8547892bc5ddc2891b44a"
CALENDAR_MATRIX_SHA256 = "6e21c1cefaab2db06ebe233f0311c5191e969adcc9a449a935e9b3d861e58380"
ROUTER_PROMPT_SHA256 = "1140626c2c05ec02d33aebc96456e4dc7387a8cab6340b18427c8fb8843d06d6"
ROUTER_SCHEMA_SHA256 = "86ddd47fd22d1e6f3496d784679f6e71ac0b44a89b16d6d487a3298ea162908e"
CALENDAR_PROMPT_SHA256 = "ecdfd472ef2a51ab32dd9512132bc77d77462e8fef81444971da844d2d6ab711"
CALENDAR_SCHEMA_SHA256 = "2230bfa0bf885b0c97e5bd458cebda6d38ebca8ec555fdbb72736fbc911f7e3c"
MAX_CALLS = 18
AUTHORIZED_CEILING_USD = 0.013
STANDARD_INPUT_USD_PER_M = 0.10
STANDARD_OUTPUT_USD_PER_M = 0.50
REGIONAL_MULTIPLIER = 1.10


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog():  # type: ignore[no-untyped-def]
    registry = ApplicationRegistry.from_descriptors(
        (
            CALENDAR_DESCRIPTOR,
            ApplicationDescriptor(
                "tasks", "task lifecycle, due dates, completion and obligations", ("temporal",)
            ),
        )
    )
    return registry.catalog(enabled_ids=("calendar",))


def _contract_hashes() -> tuple[str, str, str, str]:
    calendar_matrix = _load(CALENDAR_MATRIX)
    catalog = _catalog()
    router_prompt = render_router_prompt(catalog, ()).encode("utf-8")
    router_schema = json.dumps(
        route_plan_json_schema(catalog), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    calendar_prompt = render_calendar_prompt(
        current_context=calendar_matrix["current_context"], conversation_context=()
    ).encode("utf-8")
    calendar_schema = json.dumps(
        calendar_plan_json_schema(), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return tuple(
        _sha_bytes(value)
        for value in (router_prompt, router_schema, calendar_prompt, calendar_schema)
    )  # type: ignore[return-value]


def budget_snapshot() -> dict[str, float | int]:
    router_matrix = _load(ROUTER_MATRIX)
    calendar_matrix = _load(CALENDAR_MATRIX)
    catalog = _catalog()
    rp = render_router_prompt(catalog, ()).encode("utf-8")
    rs = json.dumps(
        route_plan_json_schema(catalog), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    cp = render_calendar_prompt(
        current_context=calendar_matrix["current_context"], conversation_context=()
    ).encode("utf-8")
    cs = json.dumps(calendar_plan_json_schema(), ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    input_bytes = sum(
        len(rp) + len(rs) + len(case["source"].encode("utf-8")) for case in router_matrix["cases"]
    ) + sum(
        len(cp) + len(cs) + len(case["request"].encode("utf-8"))
        for case in calendar_matrix["cases"]
    )
    calls = len(router_matrix["cases"]) + len(calendar_matrix["cases"])
    max_output_tokens = (
        len(router_matrix["cases"]) * ROUTER_MAX_OUTPUT_TOKENS
        + len(calendar_matrix["cases"]) * CALENDAR_PLANNER_MAX_OUTPUT_TOKENS
    )
    standard = input_bytes / 1_000_000 * STANDARD_INPUT_USD_PER_M
    standard += max_output_tokens / 1_000_000 * STANDARD_OUTPUT_USD_PER_M
    return {
        "calls": calls,
        "input_bytes_upper": input_bytes,
        "max_output_tokens": max_output_tokens,
        "standard_usd_upper": standard,
        "regional_usd_upper": standard * REGIONAL_MULTIPLIER,
    }


class RecordingResponses:
    """Count zero-retry attempts while retaining bounded synthetic evidence only."""

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
                "output_text": getattr(response, "output_text", None),
            }
        )
        return response


def _router_actual(plan: Any) -> dict[str, Any]:
    return {
        "outcome": plan.outcome.value,
        "routes": [[route.capability_id, route.source_text] for route in plan.routes],
    }


def _router_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    if actual.get("outcome") != expected.get("outcome"):
        return False
    actual_routes = actual.get("routes", [])
    expected_routes = expected.get("routes", [])
    if len(actual_routes) != len(expected_routes):
        return False
    return all(
        actual_route[0] == expected_route[0]
        and actual_route[1].strip() == expected_route[1].strip()
        for actual_route, expected_route in zip(actual_routes, expected_routes, strict=True)
    )


def _calendar_actual(plan: Any) -> dict[str, Any]:
    actual: dict[str, Any] = {
        "outcome": plan.outcome.value,
        "intent": plan.intent.value if plan.intent is not None else None,
        "temporal_kind": plan.temporal.kind.value,
        "temporal_text": plan.temporal_text,
        "capture_text": plan.capture_text,
        "failure_code": plan.failure_code.value if plan.failure_code is not None else None,
    }
    if plan.temporal.exact_date is not None:
        actual["exact_date"] = plan.temporal.exact_date
    if plan.temporal.date_range is not None:
        actual["range_start"] = plan.temporal.date_range.start
        actual["range_end_exclusive"] = plan.temporal.date_range.end_exclusive
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


def _preflight() -> tuple[dict[str, Any], dict[str, Any]]:
    if _sha_bytes(ROUTER_MATRIX.read_bytes()) != ROUTER_MATRIX_SHA256:
        raise SystemExit("v11 Router matrix changed")
    if _sha_bytes(CALENDAR_MATRIX.read_bytes()) != CALENDAR_MATRIX_SHA256:
        raise SystemExit("v11 Calendar matrix changed")
    if _contract_hashes() != (
        ROUTER_PROMPT_SHA256,
        ROUTER_SCHEMA_SHA256,
        CALENDAR_PROMPT_SHA256,
        CALENDAR_SCHEMA_SHA256,
    ):
        raise SystemExit("v11 Router/Calendar model-facing contract changed")
    if (ROUTER_MODEL, ROUTER_REASONING_EFFORT) != ("gpt-6-luna", "medium"):
        raise SystemExit("v11 Router model contract changed")
    if (CALENDAR_PLANNER_MODEL, CALENDAR_PLANNER_REASONING_EFFORT) != ("gpt-6-luna", "low"):
        raise SystemExit("v11 Calendar model contract changed")
    budget = budget_snapshot()
    if budget["calls"] != MAX_CALLS or budget["regional_usd_upper"] > AUTHORIZED_CEILING_USD:
        raise SystemExit("v11 budget changed; fresh authorization required")
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
        raise SystemExit("v11 already has retained live evidence; refusing a second run")
    return _load(ROUTER_MATRIX), _load(CALENDAR_MATRIX)


def _estimated_standard_cost(records: list[dict[str, Any]]) -> float:
    return sum(
        row["input_tokens"] / 1_000_000 * STANDARD_INPUT_USD_PER_M
        + row["output_tokens"] / 1_000_000 * STANDARD_OUTPUT_USD_PER_M
        for row in records
    )


def run() -> int:
    router_matrix, calendar_matrix = _preflight()
    from openai import OpenAI

    recorder = RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    client = SimpleNamespace(responses=recorder)
    router = OpenAIApplicationRouter(client, _catalog())
    calendar = OpenAICalendarPlanner(client, calendar_matrix["current_context"])
    rows: list[dict[str, Any]] = []
    for case in router_matrix["cases"]:
        before = len(recorder.records)
        try:
            actual = _router_actual(router.route(case["source"]))
            error = None
        except Exception as exc:
            actual, error = {}, type(exc).__name__
        rows.append(
            {
                "gate": "router",
                "id": case["id"],
                "passed": error is None and _router_matches(actual, case["expect"]),
                "expect": case["expect"],
                "actual": actual,
                "raw_output": _raw_for_call(recorder, before),
                "error": error,
            }
        )
    for case in calendar_matrix["cases"]:
        before = len(recorder.records)
        try:
            actual = _calendar_actual(calendar.plan(case["request"]))
            error = None
        except Exception as exc:
            actual, error = {}, type(exc).__name__
        rows.append(
            {
                "gate": "calendar",
                "id": case["id"],
                "passed": error is None and _expected_subset(actual, case["expect"]),
                "expect": case["expect"],
                "actual": actual,
                "raw_output": _raw_for_call(recorder, before),
                "error": error,
            }
        )
    standard = _estimated_standard_cost(recorder.records)
    regional = standard * REGIONAL_MULTIPLIER
    if recorder.attempts > MAX_CALLS or regional > AUTHORIZED_CEILING_USD:
        raise SystemExit("Authorized v11 ceiling exceeded")
    artifact = {
        "version": 11,
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "router_matrix_sha256": ROUTER_MATRIX_SHA256,
        "calendar_matrix_sha256": CALENDAR_MATRIX_SHA256,
        "router_model": ROUTER_MODEL,
        "calendar_model": CALENDAR_PLANNER_MODEL,
        "router_reasoning_effort": ROUTER_REASONING_EFFORT,
        "calendar_reasoning_effort": CALENDAR_PLANNER_REASONING_EFFORT,
        "provider_attempts": recorder.attempts,
        "completed_provider_responses": len(recorder.records),
        "automatic_retries": 0,
        "estimated_standard_cost_usd": standard,
        "estimated_regional_upper_usd": regional,
        "passed": all(row["passed"] for row in rows),
        "rows": rows,
        "provider_failures": recorder.failures,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
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
