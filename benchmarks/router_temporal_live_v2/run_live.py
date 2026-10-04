"""One-shot no-mutation live gate for the current Router v6 + Temporal v1 contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_apps import ApplicationDescriptor, ApplicationRegistry
from odyssey_apps.router import ROUTER_MAX_OUTPUT_TOKENS, OpenAIApplicationRouter
from odyssey_core.temporal_interpretation import (
    TEMPORAL_INTERPRETER_MAX_OUTPUT_TOKENS,
    OpenAITemporalInterpreter,
)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MATRIX = HERE / "matrix.json"
RESULTS = HERE / "results"
ROUTER_SOURCE_MATRIX = ROOT / "benchmarks/application_router/regression_v6.json"
TEMPORAL_SOURCE_MATRIX = ROOT / "benchmarks/temporal_interpreter/regression_v1.json"

MATRIX_SHA256 = "e6ea6722307f11af1d034b6156545771d7ff54abea9f272e7e6f87cb8110ac69"
ROUTER_SOURCE_SHA256 = "cdc2b55c54f5e690c82e33bf526ed7191fe5aa866ad86a1b7ee501fdd319ff8f"
TEMPORAL_SOURCE_SHA256 = "245960c46257e348f25e99c38166b93c06d5ee82512567e84ab44338c728b027"
AUTH_ENV = "ODYSSEY_RUN_ROUTER_TEMPORAL_V2"
MAX_CALLS = 23
PROPOSED_CEILING_USD = 0.04
REGIONAL_MULTIPLIER = 1.10
RATES = {"gpt-6-luna": (0.10, 0.50)}
INPUT_TOKEN_ENVELOPE = 10_000
SOURCE_FILES = (
    "odyssey_apps/router.py",
    "odyssey_core/temporal_interpretation.py",
    "odyssey_core/temporal_resolution.py",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_digest() -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_FILES:
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _catalog():  # type: ignore[no-untyped-def]
    return ApplicationRegistry.from_descriptors(
        (
            ApplicationDescriptor(
                "tasks",
                "task lifecycle, due dates, completion and obligations",
                ("temporal",),
            ),
        )
    ).catalog()


def _budget_upper(matrix: dict[str, Any]) -> float:
    calls = len(matrix["router_cases"]) + len(matrix["temporal_cases"])
    input_rate, output_rate = RATES["gpt-6-luna"]
    output_envelope = max(ROUTER_MAX_OUTPUT_TOKENS, TEMPORAL_INTERPRETER_MAX_OUTPUT_TOKENS)
    standard = (
        calls * (INPUT_TOKEN_ENVELOPE * input_rate + output_envelope * output_rate) / 1_000_000
    )
    return standard * REGIONAL_MULTIPLIER


class RecordingResponses:
    """Record provider usage while enforcing the one-shot call and cost ceilings."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.records: list[dict[str, Any]] = []
        self.attempts = 0

    def create(self, **kwargs: Any) -> Any:
        if self.attempts >= MAX_CALLS:
            raise RuntimeError("live gate call ceiling reached")
        self.attempts += 1
        response = self._responses.create(**kwargs)
        usage = getattr(response, "usage", None)
        self.records.append(
            {
                "model": kwargs.get("model"),
                "reasoning_effort": (kwargs.get("reasoning") or {}).get("effort"),
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                "response_id": getattr(response, "id", None),
                "status": getattr(response, "status", None),
                "output_text": getattr(response, "output_text", None),
            }
        )
        if self.estimated_cost(regional=True) > PROPOSED_CEILING_USD:
            raise RuntimeError("live-gate cost ceiling exceeded")
        return response

    def estimated_cost(self, *, regional: bool) -> float:
        total = 0.0
        for row in self.records:
            input_rate, output_rate = RATES[row["model"]]
            total += row["input_tokens"] * input_rate / 1_000_000
            total += row["output_tokens"] * output_rate / 1_000_000
        return total * (REGIONAL_MULTIPLIER if regional else 1.0)


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


def _temporal_actual(result: Any) -> dict[str, Any]:
    mentions: list[dict[str, Any]] = []
    for mention in result.mentions:
        resolution = mention.resolution
        date_range = resolution.date_range
        mentions.append(
            {
                "temporal_text": mention.temporal_text,
                "temporal": {
                    "kind": resolution.kind.value,
                    "exact_date": resolution.exact_date,
                    "exact_datetime": resolution.exact_datetime,
                    "range_start": date_range.start if date_range is not None else None,
                    "range_end_exclusive": (
                        date_range.end_exclusive if date_range is not None else None
                    ),
                },
            }
        )
    return {"mentions": mentions}


def _preflight(*, require_live_auth: bool) -> dict[str, Any]:
    matrix = _load(MATRIX)
    router_source = _load(ROUTER_SOURCE_MATRIX)
    temporal_source = _load(TEMPORAL_SOURCE_MATRIX)

    if _sha(MATRIX) != MATRIX_SHA256:
        raise SystemExit("frozen v2 matrix hash changed")
    if _sha(ROUTER_SOURCE_MATRIX) != ROUTER_SOURCE_SHA256:
        raise SystemExit("Router v6 source matrix changed")
    if _sha(TEMPORAL_SOURCE_MATRIX) != TEMPORAL_SOURCE_SHA256:
        raise SystemExit("Temporal v1 source matrix changed")
    if matrix["router_cases"] != router_source["cases"]:
        raise SystemExit("frozen live Router cases drifted from Router v6")
    if matrix["temporal_cases"] != temporal_source["cases"]:
        raise SystemExit("frozen live Temporal cases drifted from Temporal v1")
    if matrix["route_source_comparison"] != router_source["route_source_comparison"]:
        raise SystemExit("Router route-source comparison contract drifted")

    calls = len(matrix["router_cases"]) + len(matrix["temporal_cases"])
    if calls != MAX_CALLS:
        raise SystemExit("frozen gate call count changed")
    if _budget_upper(matrix) > PROPOSED_CEILING_USD:
        raise SystemExit("proposed cost envelope changed")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--check"], check=False).returncode != 0:
        raise SystemExit("git diff --check failed")

    if require_live_auth:
        if os.environ.get(AUTH_ENV) != "1":
            raise SystemExit(f"refusing live calls without {AUTH_ENV}=1")
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY unavailable")
        RESULTS.mkdir(parents=True, exist_ok=True)
        if any(RESULTS.glob("*.json")):
            raise SystemExit("v2 live evidence already exists; refusing a second run")
    return matrix


def _print_preflight(matrix: dict[str, Any]) -> None:
    print(f"router_calls={len(matrix['router_cases'])}")
    print(f"temporal_calls={len(matrix['temporal_cases'])}")
    print(f"max_calls={MAX_CALLS}")
    print(f"budget_upper_usd={_budget_upper(matrix):.8f}")
    print(f"proposed_ceiling_usd={PROPOSED_CEILING_USD:.8f}")
    print(f"matrix_sha256={_sha(MATRIX)}")
    print(f"source_digest={_source_digest()}")
    print("mutation_authority=False")
    print("live_calls=0")


def run_live() -> int:
    matrix = _preflight(require_live_auth=True)
    from openai import OpenAI

    base = OpenAI(max_retries=0, timeout=30.0)
    recorder = RecordingResponses(base.responses)
    client = SimpleNamespace(responses=recorder)
    rows: list[dict[str, Any]] = []

    router = OpenAIApplicationRouter(client, _catalog())
    for case in matrix["router_cases"]:
        try:
            plan = router.route(case["source"])
            actual = _router_actual(plan)
            passed = _router_matches(actual, case["expect"])
            error = None
        except Exception as exc:
            actual, passed, error = {}, False, type(exc).__name__
        rows.append(
            {
                "gate": "router",
                "id": case["id"],
                "passed": passed,
                "actual": actual,
                "expected": case["expect"],
                "error": error,
            }
        )

    temporal = OpenAITemporalInterpreter(client, matrix["current_context"])
    for case in matrix["temporal_cases"]:
        try:
            result = temporal.interpret(case["source"])
            actual = _temporal_actual(result)
            passed = actual == case["expect"]
            error = None
        except Exception as exc:
            actual, passed, error = {}, False, type(exc).__name__
        rows.append(
            {
                "gate": "temporal",
                "id": case["id"],
                "passed": passed,
                "actual": actual,
                "expected": case["expect"],
                "error": error,
            }
        )

    artifact = {
        "version": 2,
        "head": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "dirty_worktree": bool(
            subprocess.check_output(
                ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
            ).strip()
        ),
        "matrix_sha256": _sha(MATRIX),
        "source_digest": _source_digest(),
        "provider_attempts": recorder.attempts,
        "automatic_retries": 0,
        "mutation_authority": False,
        "budget_upper_usd": _budget_upper(matrix),
        "estimated_standard_cost_usd": recorder.estimated_cost(regional=False),
        "estimated_regional_cost_usd": recorder.estimated_cost(regional=True),
        "passed": recorder.attempts == MAX_CALLS and all(row["passed"] for row in rows),
        "rows": rows,
        "provider_records": recorder.records,
    }
    output = RESULTS / f"{artifact['source_digest'][:12]}.json"
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"provider_attempts={artifact['provider_attempts']}")
    print(f"budget_upper_usd={artifact['budget_upper_usd']:.8f}")
    print(f"estimated_regional_cost_usd={artifact['estimated_regional_cost_usd']:.8f}")
    print(f"passed={artifact['passed']}")
    for row in rows:
        suffix = f" {row['error']}" if row["error"] else ""
        print(f"{row['gate']} {row['id']}: {'PASS' if row['passed'] else 'FAIL'}{suffix}")
    print(f"artifact={output.relative_to(ROOT)}")
    return 0 if artifact["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="validate the frozen gate and print its cost envelope without calling the provider",
    )
    args = parser.parse_args()
    if args.preflight:
        matrix = _preflight(require_live_auth=False)
        _print_preflight(matrix)
        return 0
    return run_live()


if __name__ == "__main__":
    raise SystemExit(main())
