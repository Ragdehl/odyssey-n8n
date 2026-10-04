"""One-shot no-mutation live gate for Tasks v0 routing and model-facing contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_apps import ApplicationDescriptor, ApplicationRegistry, OpenAIApplicationRouter
from odyssey_apps.router import ROUTER_MAX_OUTPUT_TOKENS
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
from odyssey_core.temporal_interpretation import (
    TEMPORAL_INTERPRETER_MAX_OUTPUT_TOKENS,
    OpenAITemporalInterpreter,
)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MATRIX = HERE / "matrix.json"
RESULTS = HERE / "results"
SCHEMA = ROOT / "config/note-schema.json"
MATRIX_SHA256 = "99d3301ce1860e2a81e69eba8a2b77028825d05f432c9a1fc9aab628133effb3"
AUTH_ENV = "ODYSSEY_RUN_TASKS_LIVE_V0"
MAX_CALLS = 14
CEILING_USD = 0.05
REGIONAL_MULTIPLIER = 1.10
RATES = {"gpt-6-luna": (0.10, 0.50), "gpt-5.6-luna": (0.20, 1.20)}
INPUT_ENVELOPE = {"gpt-6-luna": 10_000, "gpt-5.6-luna": 40_000}
SOURCE_FILES = (
    "odyssey_apps/router.py",
    "odyssey_apps/tasks/interpretation.py",
    "odyssey_apps/tasks/planning.py",
    "odyssey_apps/tasks/schema.py",
    "odyssey_core/temporal_interpretation.py",
    "odyssey_core/experimental_luna_planning.py",
    "odyssey_core/request_planning.py",
    "odyssey_core/domain_interpretation.py",
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def source_digest() -> str:
    h = hashlib.sha256()
    for rel in SOURCE_FILES:
        h.update(rel.encode())
        h.update(b"\0")
        h.update((ROOT / rel).read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def budget_upper() -> float:
    # 6 Router + 4 Tasks + 2 Temporal = 12 GPT-6 Luna; 2 shared planner = GPT-5.6 Luna.
    g6i, g6o = RATES["gpt-6-luna"]
    g5i, g5o = RATES["gpt-5.6-luna"]
    g6_out = (
        6 * ROUTER_MAX_OUTPUT_TOKENS
        + 4 * TASK_INTERPRETER_MAX_OUTPUT_TOKENS
        + 2 * TEMPORAL_INTERPRETER_MAX_OUTPUT_TOKENS
    )
    standard = (12 * INPUT_ENVELOPE["gpt-6-luna"] * g6i + g6_out * g6o) / 1_000_000
    standard += (
        2 * INPUT_ENVELOPE["gpt-5.6-luna"] * g5i + 2 * LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS * g5o
    ) / 1_000_000
    return standard * REGIONAL_MULTIPLIER


class RecordingResponses:
    def __init__(self, responses: Any):
        self._responses = responses
        self.records = []
        self.attempts = 0

    def create(self, **kwargs: Any):
        if self.attempts >= MAX_CALLS:
            raise RuntimeError("authorized call ceiling reached")
        if kwargs.get("model") not in RATES:
            raise RuntimeError("unauthorized model")
        self.attempts += 1
        response = self._responses.create(**kwargs)
        usage = getattr(response, "usage", None)
        row = {
            "model": kwargs.get("model"),
            "reasoning_effort": (kwargs.get("reasoning") or {}).get("effort"),
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "response_id": getattr(response, "id", None),
            "status": getattr(response, "status", None),
        }
        self.records.append(row)
        if self.cost() > CEILING_USD:
            raise RuntimeError("authorized cost ceiling exceeded")
        return response

    def cost(self) -> float:
        total = 0.0
        for row in self.records:
            ir, orate = RATES[row["model"]]
            total += row["input_tokens"] * ir / 1_000_000 + row["output_tokens"] * orate / 1_000_000
        return total * REGIONAL_MULTIPLIER


def catalog():
    desc = ApplicationDescriptor(
        "tasks", "task lifecycle, due dates, completion and obligations", ("temporal",)
    )
    return ApplicationRegistry.from_descriptors((desc,)).catalog(enabled_ids=("tasks",))


def props(plan: RequestPlan) -> tuple[dict[str, Any], dict[str, Any]]:
    assert len(plan.actions) == 1 and isinstance(plan.actions[0], WriteAction)
    primary = [u for u in plan.actions[0].units if not u.reference_lookup_only]
    assert len(primary) == 1
    u = primary[0]
    return (
        {"type": u.target.type, "intent": u.intent, "cardinality": u.cardinality},
        {p.field: (p.op, p.value) for p in u.properties},
    )


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
    rows = []
    tasks_by_id = {}
    temporal_by_id = {}

    # Router: specialized cases + two false-positive sentinels.
    router = OpenAIApplicationRouter(client, catalog())
    for case in matrix["router_cases"]:
        ok = False
        actual = None
        error = None
        try:
            result = router.route(case["source"])
            actual = [r.capability_id for r in result.routes]
            ok = result.outcome.value == "ROUTE" and actual == [case["expect"]]
        except Exception as exc:
            error = type(exc).__name__
        rows.append(
            {"gate": "router", "id": case["id"], "passed": ok, "actual": actual, "error": error}
        )

    # Tasks interpreter: lifecycle/query semantics only.
    task_interp = OpenAITaskInterpreter(client)
    for case in matrix["task_cases"]:
        ok = False
        actual = None
        error = None
        try:
            result = task_interp.interpret(case["source"])
            tasks_by_id[case["id"]] = result
            temporal_roles = [m.role.value for m in result.temporal_mentions]
            expected_roles = [role for _text, role in case["temporal"]]
            actual = {
                "operation": result.operation.value,
                "temporal_roles": temporal_roles,
                "query_scope": None if result.query_scope is None else result.query_scope.value,
            }
            ok = actual == {
                "operation": case["operation"],
                "temporal_roles": expected_roles,
                "query_scope": case["query_scope"],
            }
        except Exception as exc:
            error = type(exc).__name__
        rows.append(
            {"gate": "tasks", "id": case["id"], "passed": ok, "actual": actual, "error": error}
        )

    # Temporal: only cases Tasks explicitly delegated to it.
    temporal_interp = OpenAITemporalInterpreter(client, matrix["current_context"])
    task_for_source = {c["source"]: c["id"] for c in matrix["task_cases"]}
    for case in matrix["temporal_cases"]:
        ok = False
        actual = None
        error = None
        try:
            result = temporal_interp.interpret(case["source"])
            temporal_by_id[task_for_source[case["source"]]] = result
            mentions = []
            for m in result.mentions:
                value = m.resolution.exact_date or m.resolution.exact_datetime
                mentions.append((m.temporal_text, m.resolution.kind.value, value))
            actual = mentions
            matches = [
                m
                for m in mentions
                if case["text"] in m[0] and m[1] == case["kind"] and m[2] == case["value"]
            ]
            ok = len(matches) == 1 and len(mentions) == 1
        except Exception as exc:
            error = type(exc).__name__
        rows.append(
            {"gate": "temporal", "id": case["id"], "passed": ok, "actual": actual, "error": error}
        )

    base_schema = load(SCHEMA)
    schema = compose_application_schema(base_schema, (TASK_SCHEMA_EXTENSION,))
    # Shared semantic planner: CREATE and COMPLETE only; UPDATE path already has deterministic Core E2E.
    for task_id in matrix["planner_cases"]:
        case = next(c for c in matrix["task_cases"] if c["id"] == task_id)
        ok = False
        actual = None
        error = None
        try:
            task = tasks_by_id[task_id]
            domain = compose_task_domain_interpretation(
                task, temporal_by_id.get(task_id), now=matrix["now"]
            )
            planner = TaskCorePlanner(
                OpenAILunaExperimentalPlanner(
                    client, schema, matrix["current_context"], domain_interpretation=domain
                ),
                task,
            )
            result = planner.plan(case["source"])
            if isinstance(result, PlannerClarification):
                raise RuntimeError("clarification")
            target, properties = props(result)
            actual = {"target": target, "properties": properties}
            if task_id == "T1-create":
                ok = (
                    target == {"type": "task", "intent": "record", "cardinality": "one"}
                    and properties.get("status") == ("set", "pending")
                    and properties.get("target_date") == ("set", "2026-10-09")
                )
            else:
                ok = (
                    target == {"type": "task", "intent": "amend", "cardinality": "one"}
                    and properties.get("status") == ("set", "completed")
                    and properties.get("completed_at") == ("set", matrix["now"])
                )
        except Exception as exc:
            error = type(exc).__name__
        rows.append(
            {"gate": "planner", "id": task_id, "passed": ok, "actual": actual, "error": error}
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
        "sol_calls": 0,
        "budget_upper_usd": budget_upper(),
        "estimated_regional_cost_usd": recorder.cost(),
        "passed": recorder.attempts == MAX_CALLS and all(r["passed"] for r in rows),
        "rows": rows,
        "provider_records": recorder.records,
    }
    out = RESULTS / f"{artifact['source_digest'][:12]}.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider_attempts={artifact['provider_attempts']}")
    print(f"budget_upper_usd={artifact['budget_upper_usd']:.8f}")
    print(f"estimated_regional_cost_usd={artifact['estimated_regional_cost_usd']:.8f}")
    print(f"passed={artifact['passed']}")
    for r in rows:
        print(
            f"{r['gate']} {r['id']}: {'PASS' if r['passed'] else 'FAIL'} actual={r['actual']!r}{(' ' + r['error']) if r['error'] else ''}"
        )
    print(f"artifact={out.relative_to(ROOT)}")
    return 0 if artifact["passed"] else 1


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    args = ap.parse_args()
    raise SystemExit(main(args.preflight))
