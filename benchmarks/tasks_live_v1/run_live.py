"""One-shot live gate for Tasks v0.1 interpreter and shared-planner contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    OpenAITaskInterpreter,
    TaskCorePlanner,
    compose_task_domain_interpretation,
)
from odyssey_apps.tasks.interpretation import TASK_INTERPRETER_MAX_OUTPUT_TOKENS
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    OpenAILunaExperimentalPlanner,
)
from odyssey_core.request_planning import PlannerClarification, RequestPlan, WriteAction
from odyssey_core.temporal_interpretation import parse_temporal_interpretation

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MATRIX = HERE / "matrix.json"
RESULTS = HERE / "results"
SCHEMA = ROOT / "config/note-schema.json"
MATRIX_SHA256 = "84b38f9005fac11d22e8928b8b3c952242143c74ec711ed8d6f49dddf6c08feb"
AUTH_ENV = "ODYSSEY_RUN_TASKS_LIVE_V1"
MAX_CALLS = 8
CEILING_USD = 0.05
REGIONAL_MULTIPLIER = 1.10
RATES = {"gpt-6-luna": (0.10, 0.50), "gpt-5.6-luna": (0.20, 1.20)}
INPUT_ENVELOPE = {"gpt-6-luna": 10_000, "gpt-5.6-luna": 40_000}
SOURCE_FILES = (
    "odyssey_apps/tasks/interpretation.py",
    "odyssey_apps/tasks/planning.py",
    "odyssey_apps/tasks/schema.py",
    "odyssey_apps/schema_extensions.py",
    "odyssey_core/planner_capabilities.py",
    "odyssey_core/schema_types.py",
    "odyssey_core/experimental_luna_planning.py",
    "odyssey_core/request_planning.py",
    "odyssey_core/domain_interpretation.py",
)


def load(path: Path) -> Any:
    """Load one frozen JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def source_digest() -> str:
    """Bind evidence to the exact model-facing production source."""
    digest = hashlib.sha256()
    for relative in SOURCE_FILES:
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update((ROOT / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def budget_upper() -> float:
    """Return a deliberately conservative authorized-cost envelope."""
    g6_input, g6_output = RATES["gpt-6-luna"]
    g56_input, g56_output = RATES["gpt-5.6-luna"]
    standard = (
        5 * INPUT_ENVELOPE["gpt-6-luna"] * g6_input
        + 5 * TASK_INTERPRETER_MAX_OUTPUT_TOKENS * g6_output
    ) / 1_000_000
    standard += (
        3 * INPUT_ENVELOPE["gpt-5.6-luna"] * g56_input
        + 3 * LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS * g56_output
    ) / 1_000_000
    return standard * REGIONAL_MULTIPLIER


class RecordingResponses:
    """Enforce call/model/cost ceilings around the provider without retries."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.records: list[dict[str, Any]] = []
        self.attempts = 0

    def create(self, **kwargs: Any) -> Any:
        if self.attempts >= MAX_CALLS:
            raise RuntimeError("authorized call ceiling reached")
        model = kwargs.get("model")
        if model not in RATES:
            raise RuntimeError("unauthorized model")
        self.attempts += 1
        response = self._responses.create(**kwargs)
        usage = getattr(response, "usage", None)
        self.records.append(
            {
                "model": model,
                "reasoning_effort": (kwargs.get("reasoning") or {}).get("effort"),
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                "response_id": getattr(response, "id", None),
                "status": getattr(response, "status", None),
            }
        )
        if self.cost() > CEILING_USD:
            raise RuntimeError("authorized cost ceiling exceeded")
        return response

    def cost(self) -> float:
        total = 0.0
        for row in self.records:
            input_rate, output_rate = RATES[row["model"]]
            total += row["input_tokens"] * input_rate / 1_000_000
            total += row["output_tokens"] * output_rate / 1_000_000
        return total * REGIONAL_MULTIPLIER


def _deterministic_temporal(source: str):  # type: ignore[no-untyped-def]
    """Supply the unchanged Temporal dependency without spending a provider call."""
    return parse_temporal_interpretation(
        {
            "mentions": [
                {
                    "temporal_text": "el viernes",
                    "temporal": {
                        "kind": "EXACT_DATE",
                        "exact_date": "2026-10-09",
                        "exact_datetime": None,
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                }
            ]
        },
        source,
        timezone="Europe/Paris",
    )


def _primary(plan: RequestPlan):  # type: ignore[no-untyped-def]
    assert len(plan.actions) == 1 and isinstance(plan.actions[0], WriteAction)
    units = [unit for unit in plan.actions[0].units if not unit.reference_lookup_only]
    assert len(units) == 1
    return units[0]


def _task_actual(result) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "operation": result.operation.value,
        "temporal": [(item.text, item.role.value) for item in result.temporal_mentions],
        "relationships": [(item.text, item.role.value) for item in result.relationship_mentions],
        "clear_fields": list(result.clear_fields),
        "query_scope": None if result.query_scope is None else result.query_scope.value,
    }


def main(preflight: bool = False) -> int:
    matrix = load(MATRIX)
    if hashlib.sha256(MATRIX.read_bytes()).hexdigest() != MATRIX_SHA256:
        raise SystemExit("matrix changed")
    if budget_upper() >= CEILING_USD:
        raise SystemExit(f"budget envelope too large: {budget_upper():.8f}")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--check"], check=False).returncode:
        raise SystemExit("diff check failed")
    if preflight:
        print(f"max_calls={MAX_CALLS}")
        print(f"budget_upper_usd={budget_upper():.8f}")
        print(f"matrix_sha256={MATRIX_SHA256}")
        print("mutation_authority=False")
        print("router_calls=0")
        print("temporal_provider_calls=0")
        print("sol_calls=0")
        return 0
    if os.environ.get(AUTH_ENV) != "1":
        raise SystemExit(f"missing {AUTH_ENV}=1")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY unavailable")
    RESULTS.mkdir(exist_ok=True)
    if any(RESULTS.glob("*.json")):
        raise SystemExit("gate already has evidence; refusing rerun")

    from openai import OpenAI

    recorder = RecordingResponses(OpenAI(max_retries=0, timeout=30.0).responses)
    client = SimpleNamespace(responses=recorder)
    rows: list[dict[str, Any]] = []
    interpreted = {}

    interpreter = OpenAITaskInterpreter(client)
    for case in matrix["task_cases"]:
        actual = None
        error = None
        passed = False
        try:
            result = interpreter.interpret(case["source"])
            interpreted[case["id"]] = result
            actual = _task_actual(result)
            passed = actual == {
                "operation": case["operation"],
                "temporal": [tuple(item) for item in case["temporal"]],
                "relationships": [tuple(item) for item in case["relationships"]],
                "clear_fields": [],
                "query_scope": case["query_scope"],
            }
        except Exception as exc:
            error = type(exc).__name__
        rows.append(
            {"gate": "tasks", "id": case["id"], "passed": passed, "actual": actual, "error": error}
        )

    base_schema = load(SCHEMA)
    schema = compose_application_schema(base_schema, (TASK_SCHEMA_EXTENSION,))
    task_cases = {case["id"]: case for case in matrix["task_cases"]}
    for case in matrix["planner_cases"]:
        actual = None
        error = None
        passed = False
        try:
            if case["kind"] == "task":
                task_case = task_cases[case["task_case"]]
                task = interpreted[case["task_case"]]
                temporal = (
                    _deterministic_temporal(task_case["source"]) if task.temporal_mentions else None
                )
                domain = compose_task_domain_interpretation(task, temporal, now=matrix["now"])
                planner = TaskCorePlanner(
                    OpenAILunaExperimentalPlanner(
                        client, schema, matrix["current_context"], domain_interpretation=domain
                    ),
                    task,
                )
                result = planner.plan(task_case["source"])
            else:
                planner = OpenAILunaExperimentalPlanner(client, schema, matrix["current_context"])
                result = planner.plan(case["source"])
            if isinstance(result, PlannerClarification):
                raise RuntimeError("clarification")
            unit = _primary(result)
            actual = {
                "target_type": unit.target.type,
                "intent": unit.intent,
                "cardinality": unit.cardinality,
                "properties": {item.field: (item.op, item.value) for item in unit.properties},
                "facts": list(unit.facts),
            }
            if case["id"] == "P1-create-date":
                passed = (
                    actual["target_type"] == "task"
                    and actual["intent"] == "record"
                    and actual["cardinality"] == "one"
                    and actual["properties"].get("status") == ("set", "pending")
                    and actual["properties"].get("target_date") == ("set", "2026-10-09")
                    and any(fact.startswith("[ ] ") for fact in unit.facts)
                )
            elif case["id"] == "P2-complete":
                passed = (
                    actual["target_type"] == "task"
                    and actual["intent"] == "amend"
                    and actual["cardinality"] == "one"
                    and actual["properties"].get("status") == ("set", "completed")
                    and actual["properties"].get("completed_at") == ("set", matrix["now"])
                )
            else:
                passed = (
                    actual["target_type"] == "task"
                    and actual["intent"] == "record"
                    and actual["cardinality"] == "one"
                    and not actual["properties"]
                    and any("comisiones" in fact.casefold() for fact in unit.facts)
                )
        except Exception as exc:
            error = type(exc).__name__
        rows.append(
            {
                "gate": "planner",
                "id": case["id"],
                "passed": passed,
                "actual": actual,
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
        "matrix_sha256": MATRIX_SHA256,
        "source_digest": source_digest(),
        "provider_attempts": recorder.attempts,
        "automatic_retries": 0,
        "mutation_authority": False,
        "router_calls": 0,
        "temporal_provider_calls": 0,
        "sol_calls": 0,
        "budget_upper_usd": budget_upper(),
        "estimated_regional_cost_usd": recorder.cost(),
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
        status = "PASS" if row["passed"] else "FAIL"
        suffix = f" {row['error']}" if row["error"] else ""
        print(f"{row['gate']} {row['id']}: {status} actual={row['actual']!r}{suffix}")
    print(f"artifact={output.relative_to(ROOT)}")
    return 0 if artifact["passed"] else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(main(arguments.preflight))
