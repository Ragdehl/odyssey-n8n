"""One-shot no-mutation Router -> Temporal -> Core regression gate."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_apps import ApplicationDescriptor, ApplicationRegistry, RouteOutcome
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
from odyssey_core.request_planning import PlannerClarification, RequestPlan, WriteAction
from odyssey_core.temporal_interpretation import (
    TEMPORAL_INTERPRETER_MAX_OUTPUT_TOKENS,
    OpenAITemporalInterpreter,
)
from odyssey_core.temporal_resolution import TemporalResolutionKind

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MATRIX = HERE / "matrix.json"
RESULTS = HERE / "results"
SCHEMA = ROOT / "config/note-schema.json"
AUTH_ENV = "ODYSSEY_RUN_ROUTER_TEMPORAL_CORE_V1"
MAX_CALLS = 14
AUTHORIZED_CEILING_USD = 0.10
REGIONAL_MULTIPLIER = 1.10
RATES = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.6-luna": (0.20, 1.20),
}
# Deliberately much larger than observed input counts; used only for authorization preflight.
INPUT_TOKEN_ENVELOPE = {"gpt-6-luna": 10_000, "gpt-5.6-luna": 40_000}
SOURCE_FILES = (
    "odyssey_apps/router.py",
    "odyssey_core/temporal_interpretation.py",
    "odyssey_core/domain_interpretation.py",
    "odyssey_core/experimental_luna_planning.py",
    "odyssey_core/request_planning.py",
    "odyssey_core/semantic_write.py",
    "odyssey_core/temporal.py",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_digest() -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_FILES:
        path = ROOT / relative
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
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
    temporal_n = len(matrix["temporal_cases"])
    core_n = len(matrix["core_cases"])
    g6_calls = router_n + temporal_n
    g6_in, g6_out = RATES["gpt-6-luna"]
    g5_in, g5_out = RATES["gpt-5.6-luna"]
    usd = (
        g6_calls
        * (
            INPUT_TOKEN_ENVELOPE["gpt-6-luna"] * g6_in
            + max(ROUTER_MAX_OUTPUT_TOKENS, TEMPORAL_INTERPRETER_MAX_OUTPUT_TOKENS) * g6_out
        )
        / 1_000_000
    )
    usd += (
        core_n
        * (
            INPUT_TOKEN_ENVELOPE["gpt-5.6-luna"] * g5_in
            + LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS * g5_out
        )
        / 1_000_000
    )
    return usd * REGIONAL_MULTIPLIER


class RecordingResponses:
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
        if self.estimated_cost(regional=True) > AUTHORIZED_CEILING_USD:
            raise RuntimeError("authorized live-gate cost ceiling exceeded")
        return response

    def estimated_cost(self, *, regional: bool) -> float:
        total = 0.0
        for row in self.records:
            rates = RATES[row["model"]]
            total += row["input_tokens"] * rates[0] / 1_000_000
            total += row["output_tokens"] * rates[1] / 1_000_000
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
        return {"kind": "clarify", "code": result.code, "footprint": "", "anchors": []}
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
                    "target": {
                        "entity": unit.target.entity,
                        "query": unit.target.query,
                        "type": unit.target.type,
                        "self_target": unit.target.self_target,
                    },
                    "facts": list(unit.facts),
                    "references": [
                        {
                            "mention": ref.mention,
                            "role": ref.role,
                            "query": ref.selection.query if ref.selection else None,
                        }
                        for ref in unit.references
                    ],
                    "reference_lookup_only": unit.reference_lookup_only,
                    "anchors": unit_anchors,
                }
            )
    footprint = json.dumps(units, ensure_ascii=False, separators=(",", ":")).casefold()
    return {"kind": "plan", "units": units, "footprint": footprint, "anchors": anchors}


def _preflight() -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = _load(MATRIX)
    calls = len(matrix["router_cases"]) + len(matrix["temporal_cases"]) + len(matrix["core_cases"])
    if calls != MAX_CALLS:
        raise SystemExit("frozen gate call count changed")
    if _budget_upper(matrix) > AUTHORIZED_CEILING_USD:
        raise SystemExit("authorized cost envelope changed")
    if os.environ.get(AUTH_ENV) != "1":
        raise SystemExit(f"refusing live calls without {AUTH_ENV}=1")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY unavailable")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--check"], check=False).returncode != 0:
        raise SystemExit("git diff --check failed")
    RESULTS.mkdir(parents=True, exist_ok=True)
    if any(RESULTS.glob("*.json")):
        raise SystemExit("v1 live evidence already exists; refusing a second run")
    return matrix, _load(SCHEMA)


def run() -> int:
    matrix, schema = _preflight()
    from openai import OpenAI

    base = OpenAI(max_retries=0, timeout=30.0)
    recorder = RecordingResponses(base.responses)
    client = SimpleNamespace(responses=recorder)
    rows: list[dict[str, Any]] = []

    router = OpenAIApplicationRouter(client, _catalog())
    for case in matrix["router_cases"]:
        try:
            plan = router.route(case["source"])
            actual = {
                "outcome": plan.outcome.value,
                "routes": [[route.capability_id, route.source_text] for route in plan.routes],
            }
            passed = (
                plan.outcome is RouteOutcome.ROUTE
                and len(plan.routes) == 1
                and plan.routes[0].capability_id == case["expect_capability"]
                and plan.routes[0].source_text == case["source"]
            )
            error = None
        except Exception as exc:
            actual, passed, error = {}, False, type(exc).__name__
        rows.append(
            {"gate": "router", "id": case["id"], "passed": passed, "actual": actual, "error": error}
        )

    temporal = OpenAITemporalInterpreter(client, matrix["current_context"])
    for case in matrix["temporal_cases"]:
        try:
            result = temporal.interpret(case["source"])
            actual_mentions: list[list[str]] = []
            range_actual = None
            for mention in result.mentions:
                resolution = mention.resolution
                if resolution.kind is TemporalResolutionKind.EXACT_DATE:
                    actual_mentions.append([mention.temporal_text, resolution.exact_date or ""])
                elif resolution.kind is TemporalResolutionKind.EXACT_DATETIME:
                    actual_mentions.append([mention.temporal_text, resolution.exact_datetime or ""])
                elif (
                    resolution.kind is TemporalResolutionKind.DATE_RANGE
                    and resolution.date_range is not None
                ):
                    range_actual = [
                        mention.temporal_text,
                        resolution.date_range.start,
                        resolution.date_range.end_exclusive,
                    ]
            if "expect" in case:
                actual = {"mentions": actual_mentions}
                passed = actual_mentions == case["expect"]
            else:
                actual = {"range": range_actual}
                passed = range_actual == case["expect_range"]
            error = None
        except Exception as exc:
            actual, passed, error = {}, False, type(exc).__name__
        rows.append(
            {
                "gate": "temporal",
                "id": case["id"],
                "passed": passed,
                "actual": actual,
                "error": error,
            }
        )

    for case in matrix["core_cases"]:
        interpretation = _interpretation(case)
        planner = OpenAILunaExperimentalPlanner(
            client, schema, matrix["current_context"], domain_interpretation=interpretation
        )
        try:
            result = planner.plan(case["source"])
            actual = _core_actual(result)
            footprint_ok = all(
                token.casefold() in actual["footprint"] for token in case["must_contain"]
            )
            anchors_ok = Counter(actual["anchors"]) == Counter(case["expect_anchors"])
            passed = actual["kind"] == "plan" and footprint_ok and anchors_ok
            error = None
        except Exception as exc:
            actual, passed, error = {}, False, type(exc).__name__
        rows.append(
            {
                "gate": "core",
                "id": case["id"],
                "passed": passed,
                "actual": actual,
                "expect_anchors": case["expect_anchors"],
                "must_contain": case["must_contain"],
                "error": error,
            }
        )

    artifact = {
        "version": 1,
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
        print(
            f"{row['gate']} {row['id']}: {'PASS' if row['passed'] else 'FAIL'}{(' ' + row['error']) if row['error'] else ''}"
        )
    print(f"artifact={output.relative_to(ROOT)}")
    return 0 if artifact["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
