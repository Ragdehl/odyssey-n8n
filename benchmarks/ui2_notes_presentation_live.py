"""Run the bounded UI-2 presentation-intent planner evidence gate once per frozen case."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from odyssey_core.cost_aware_planning import LunaFirstRequestPlanner  # noqa: E402
from odyssey_core.experimental_luna_planning import (  # noqa: E402
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    render_luna_experimental_prompt,
)
from odyssey_core.request_planning import (  # noqa: E402
    PLANNER_MAX_OUTPUT_TOKENS,
    PlannerClarification,
    RequestPlan,
    RetrieveAction,
    WriteAction,
    render_request_planner_prompt,
)

OUTPUT = Path(
    os.environ.get(
        "ODYSSEY_UI2_LIVE_OUTPUT",
        str(ROOT / "benchmarks" / ".live-results" / "ui2-notes-presentation-v1.jsonl"),
    )
)
BUDGET_USD = 0.15
CONTEXT = {"date": "2026-09-19", "time": "10:00", "timezone": "Europe/Paris"}
RATES = {"gpt-5.6-luna": (0.2, 1.2), "gpt-5.6-sol": (4.0, 20.0)}
CASES = (
    ("answer", "¿Dónde trabaja Marta?", "answer"),
    ("note_set", "Muéstrame todas las personas que conozco en Toulouse.", "note_set"),
    (
        "answer_and_note_set",
        "Explica cómo se relacionan las personas que conozco en Toulouse con Airbus y muéstrame sus notas.",
        "answer_and_note_set",
    ),
    ("ambiguous", "¿Qué sé sobre Airbus?", "answer"),
    ("clarification", "Haz algo útil con esto.", "clarification"),
    ("write", "Guarda que Marta trabaja en Airbus.", "write"),
    ("link_scope", "Muéstrame notas enlazadas desde Airbus.", "answer"),
)


def _cost(model: str, usage: dict[str, int] | None) -> float:
    """Return a no-cache conservative estimate from one bounded provider usage record."""
    if usage is None or model not in RATES:
        return 0.0
    input_rate, output_rate = RATES[model]
    return (
        usage.get("input_tokens", 0) * input_rate + usage.get("output_tokens", 0) * output_rate
    ) / 1_000_000


def _worst_case(schema: dict[str, Any], request: str) -> float:
    """Bound one complete production request, including its permitted Sol fallback."""
    luna_prompt = render_luna_experimental_prompt(schema, CONTEXT)
    sol_prompt = render_request_planner_prompt(schema, CONTEXT)
    # UTF-8/3 rounds upward and deliberately overestimates typical tokenization.
    luna_input = math.ceil(len((luna_prompt + request).encode("utf-8")) / 3)
    sol_input = math.ceil(len((sol_prompt + request).encode("utf-8")) / 3)
    luna = (
        luna_input * RATES["gpt-5.6-luna"][0]
        + LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS * RATES["gpt-5.6-luna"][1]
    ) / 1_000_000
    sol = (
        sol_input * RATES["gpt-5.6-sol"][0] + PLANNER_MAX_OUTPUT_TOKENS * RATES["gpt-5.6-sol"][1]
    ) / 1_000_000
    return luna + sol


def _passes(result: object, expected: str) -> bool:
    """Check only the frozen presentation and existing safety outcome for one case."""
    if expected == "clarification":
        return isinstance(result, PlannerClarification)
    if not isinstance(result, RequestPlan):
        return False
    if expected == "write":
        return (
            result.presentation_intent == "answer"
            and len(result.actions) == 1
            and isinstance(result.actions[0], WriteAction)
        )
    if expected in {"note_set", "answer_and_note_set"}:
        return (
            result.presentation_intent == expected
            and len(result.actions) == 1
            and isinstance(result.actions[0], RetrieveAction)
        )
    return result.presentation_intent == "answer"


def main() -> int:
    """Run sequentially until a malformed result, failure, or hard budget boundary occurs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args()
    if not args.confirm_live_provider_calls:
        parser.error("live provider calls require explicit confirmation")
    if OUTPUT.exists():
        parser.error(f"refusing to overwrite existing evidence: {OUTPUT}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    schema = json.loads((ROOT / "config" / "note-schema.json").read_text(encoding="utf-8"))
    spent = 0.0
    with OUTPUT.open("x", encoding="utf-8") as evidence:
        try:
            planner = LunaFirstRequestPlanner.from_environment(schema, CONTEXT)
        except Exception as error:
            evidence.write(
                json.dumps(
                    {
                        "status": "PROVIDER_UNAVAILABLE",
                        "error_category": type(error).__name__,
                        "spent_usd": 0.0,
                    }
                )
                + "\n"
            )
            evidence.flush()
            return 0
        for case_id, request, expected in CASES:
            ceiling = _worst_case(schema, request)
            if spent + ceiling > BUDGET_USD:
                row = {
                    "case_id": case_id,
                    "status": "BUDGET_STOP",
                    "spent_usd": spent,
                    "next_ceiling_usd": ceiling,
                    "remaining_usd": BUDGET_USD - spent,
                }
                evidence.write(json.dumps(row) + "\n")
                evidence.flush()
                return 0
            try:
                result = planner.plan(request)
                calls = planner.last_provider_calls
                actual = sum(_cost(call.model or "", call.usage) for call in calls)
                spent += actual
                row = {
                    "case_id": case_id,
                    "expected": expected,
                    "passed": _passes(result, expected),
                    "route": [call.name for call in calls],
                    "usage": [call.usage for call in calls],
                    "cost_usd": actual,
                    "spent_usd": spent,
                    "result": asdict(result),
                }
            except Exception as error:
                row = {
                    "case_id": case_id,
                    "expected": expected,
                    "passed": False,
                    "classification": "INVALID_FAIL_CLOSED",
                    "error_category": type(error).__name__,
                    "spent_usd": spent,
                }
            evidence.write(json.dumps(row, ensure_ascii=False) + "\n")
            evidence.flush()
            if not row["passed"]:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
