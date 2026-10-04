"""One-shot no-mutation Router/Core follow-up gate after disposable E2E findings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_apps import ApplicationDescriptor, ApplicationRegistry
from odyssey_apps.router import ROUTER_MAX_OUTPUT_TOKENS, OpenAIApplicationRouter
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    OpenAILunaExperimentalPlanner,
)
from odyssey_core.request_planning import (
    PLANNER_MAX_OUTPUT_TOKENS,
    OpenAIRequestPlanner,
    PlannerClarification,
    RequestPlan,
    WriteAction,
)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MATRIX = HERE / "matrix.json"
RESULTS = HERE / "results"
SCHEMA = ROOT / "config/note-schema.json"
MATRIX_SHA256 = "17ce0ed065d8eaae861668977b644b43ba0a101fa9b771ca88d3bd1bc0595194"
AUTH_ENV = "ODYSSEY_RUN_ROUTER_CORE_FOLLOWUP_V3"
MAX_CALLS = 9
PROPOSED_CEILING_USD = 0.31
REGIONAL_MULTIPLIER = 1.10
RATES = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.6-sol": (4.0, 20.0),
}
INPUT_TOKEN_ENVELOPE = {
    "gpt-6-luna": 10_000,
    "gpt-5.6-luna": 40_000,
    "gpt-5.6-sol": 40_000,
}
SOURCE_FILES = (
    "odyssey_apps/router.py",
    "odyssey_core/experimental_luna_planning.py",
    "odyssey_core/request_planning.py",
    "odyssey_core/semantic_write.py",
    "odyssey_core/domain_interpretation.py",
    "odyssey_core/temporal.py",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_digest() -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_FILES:
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update((ROOT / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _catalog():
    return ApplicationRegistry.from_descriptors(
        (
            ApplicationDescriptor(
                "tasks", "task lifecycle, due dates, completion and obligations", ("temporal",)
            ),
        )
    ).catalog()


def _budget_upper(matrix: dict[str, Any]) -> float:
    router_n = len(matrix["router_cases"])
    core_n = len(matrix["core_cases"])
    sol_n = len(matrix["sol_cases"])
    g6_in, g6_out = RATES["gpt-6-luna"]
    g5_in, g5_out = RATES["gpt-5.6-luna"]
    sol_in, sol_out = RATES["gpt-5.6-sol"]
    standard = (
        router_n
        * (INPUT_TOKEN_ENVELOPE["gpt-6-luna"] * g6_in + ROUTER_MAX_OUTPUT_TOKENS * g6_out)
        / 1_000_000
    )
    standard += (
        core_n
        * (
            INPUT_TOKEN_ENVELOPE["gpt-5.6-luna"] * g5_in
            + LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS * g5_out
        )
        / 1_000_000
    )
    standard += (
        sol_n
        * (INPUT_TOKEN_ENVELOPE["gpt-5.6-sol"] * sol_in + PLANNER_MAX_OUTPUT_TOKENS * sol_out)
        / 1_000_000
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
            raise RuntimeError("authorized live-gate cost ceiling exceeded")
        return response

    def estimated_cost(self, *, regional: bool) -> float:
        total = 0.0
        for row in self.records:
            input_rate, output_rate = RATES[row["model"]]
            total += row["input_tokens"] * input_rate / 1_000_000
            total += row["output_tokens"] * output_rate / 1_000_000
        return total * (REGIONAL_MULTIPLIER if regional else 1.0)


def _interpretation(case: dict[str, Any]) -> DomainInterpretation:
    return DomainInterpretation(
        "temporal",
        case["source"],
        "TEMPORAL_RESOLUTION",
        tuple(
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, text, value)
            for text, value in case["evidence"]
        ),
    )


def _core_actual(result: Any) -> dict[str, Any]:
    if isinstance(result, PlannerClarification):
        return {"kind": "clarify", "footprint": "", "anchors": []}
    assert isinstance(result, RequestPlan)
    units: list[dict[str, Any]] = []
    anchors: list[str] = []
    for action in result.actions:
        if not isinstance(action, WriteAction):
            continue
        for unit in action.units:
            unit_anchors = [
                anchor.value for group in unit.fact_temporal_anchors for anchor in group
            ]
            anchors.extend(unit_anchors)
            units.append(
                {
                    "target": {"query": unit.target.query, "type": unit.target.type},
                    "facts": list(unit.facts),
                    "references": [ref.mention for ref in unit.references],
                    "anchors": unit_anchors,
                }
            )
    footprint = json.dumps(units, ensure_ascii=False, separators=(",", ":")).casefold()
    return {"kind": "plan", "units": units, "footprint": footprint, "anchors": anchors}


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


def _preflight(*, live: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = _load(MATRIX)
    if _sha(MATRIX) != MATRIX_SHA256:
        raise SystemExit("frozen matrix digest changed")
    calls = len(matrix["router_cases"]) + len(matrix["core_cases"]) + len(matrix["sol_cases"])
    if calls != MAX_CALLS:
        raise SystemExit("frozen gate call count changed")
    if _budget_upper(matrix) > PROPOSED_CEILING_USD:
        raise SystemExit("proposed cost envelope changed")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--check"], check=False).returncode != 0:
        raise SystemExit("git diff --check failed")
    if live:
        if os.environ.get(AUTH_ENV) != "1":
            raise SystemExit(f"refusing live calls without {AUTH_ENV}=1")
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY unavailable")
        RESULTS.mkdir(parents=True, exist_ok=True)
        if any(RESULTS.glob("*.json")):
            raise SystemExit("v3 live evidence already exists; refusing a second run")
    return matrix, _load(SCHEMA)


def run(*, preflight_only: bool = False) -> int:
    matrix, schema = _preflight(live=not preflight_only)
    if preflight_only:
        print(f"router_calls={len(matrix['router_cases'])}")
        print(f"core_calls={len(matrix['core_cases'])}")
        print(f"sol_calls={len(matrix['sol_cases'])}")
        print(f"max_calls={MAX_CALLS}")
        print(f"budget_upper_usd={_budget_upper(matrix):.8f}")
        print(f"proposed_ceiling_usd={PROPOSED_CEILING_USD:.8f}")
        print(f"matrix_sha256={MATRIX_SHA256}")
        print(f"source_digest={_source_digest()}")
        print("mutation_authority=False")
        print("live_calls=0")
        return 0

    from openai import OpenAI

    base = OpenAI(max_retries=0, timeout=30.0)
    recorder = RecordingResponses(base.responses)
    client = SimpleNamespace(responses=recorder)
    rows: list[dict[str, Any]] = []

    router = OpenAIApplicationRouter(client, _catalog())
    for case in matrix["router_cases"]:
        try:
            actual = _router_actual(router.route(case["source"]))
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

    for case in matrix["core_cases"]:
        planner = OpenAILunaExperimentalPlanner(
            client,
            schema,
            matrix["current_context"],
            domain_interpretation=_interpretation(case),
        )
        try:
            actual = _core_actual(planner.plan(case["source"]))
            footprint_ok = all(
                token.casefold() in actual["footprint"] for token in case["must_contain"]
            )
            anchors_ok = Counter(actual["anchors"]) == Counter(case["expect_anchors"])
            passed = actual["kind"] == "plan" and footprint_ok and anchors_ok
            error = None
        except Exception as exc:
            actual, passed, error = {}, False, type(exc).__name__
        rows.append(
            {"gate": "core", "id": case["id"], "passed": passed, "actual": actual, "error": error}
        )

    for case in matrix["sol_cases"]:
        planner = OpenAIRequestPlanner(
            client,
            schema,
            matrix["current_context"],
            domain_interpretation=_interpretation(case),
        )
        try:
            actual = _core_actual(planner.plan(case["source"]))
            footprint_ok = all(
                token.casefold() in actual["footprint"] for token in case["must_contain"]
            )
            anchors_ok = Counter(actual["anchors"]) == Counter(case["expect_anchors"])
            passed = actual["kind"] == "plan" and footprint_ok and anchors_ok
            error = None
        except Exception as exc:
            actual, passed, error = {}, False, type(exc).__name__
        rows.append(
            {"gate": "sol", "id": case["id"], "passed": passed, "actual": actual, "error": error}
        )

    artifact = {
        "version": 3,
        "head": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "dirty_worktree": bool(
            subprocess.check_output(
                ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
            ).strip()
        ),
        "matrix_sha256": MATRIX_SHA256,
        "source_digest": _source_digest(),
        "provider_attempts": recorder.attempts,
        "automatic_retries": 0,
        "mutation_authority": False,
        "budget_upper_usd": _budget_upper(matrix),
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
        print(
            f"{row['gate']} {row['id']}: {'PASS' if row['passed'] else 'FAIL'}{(' ' + row['error']) if row['error'] else ''}"
        )
    print(f"artifact={output.relative_to(ROOT)}")
    return 0 if artifact["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(preflight_only=args.preflight))
