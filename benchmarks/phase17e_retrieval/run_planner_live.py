"""Run focused live Sol/low evidence for atomic-fact decomposition."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from odyssey_core.request_planning import OpenAIRequestPlanner, WriteAction  # noqa: E402


def evaluate(plan: Any, case: dict[str, Any]) -> dict[str, Any]:
    """Apply a tolerant human-readable rubric to one validated planner result."""
    units = [
        unit for action in plan.actions if isinstance(action, WriteAction) for unit in action.units
    ]
    facts = [fact for unit in units for fact in unit.facts]
    text = " ".join(facts).casefold()
    entities = [str(unit.target.entity) for unit in units if unit.target.entity]
    failures = []
    if not case["min_facts"] <= len(facts) <= case["max_facts"]:
        failures.append(f"fact count {len(facts)} outside {case['min_facts']}..{case['max_facts']}")
    for required in case["required"]:
        if required.casefold() not in text:
            failures.append(f"missing material detail {required!r}")
    matched_entities = sum(
        any(expected.casefold() in entity.casefold() for entity in entities)
        for expected in case["entities"]
    )
    if matched_entities != len(case["entities"]):
        failures.append(f"target grouping missing entities {case['entities']!r}; got {entities!r}")
    return {
        "pass": not failures,
        "failures": failures,
        "unit_count": len(units),
        "fact_count": len(facts),
        "entities": entities,
        "facts": facts,
    }


def main() -> None:
    """Run current production planner settings and preserve sanitized inspectable evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cases", type=Path, default=Path(__file__).with_name("planner_cases.json")
    )
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    context = {"date": "2026-08-31", "time": "10:00", "timezone": "Europe/Paris"}
    rows = []
    try:
        from openai import OpenAI

        planner = OpenAIRequestPlanner(OpenAI(max_retries=0), schema, context)
        for case in cases:
            row = {
                "suite": "sol-atomic-decomposition",
                "case": case["id"],
                "model": "gpt-5.6-sol",
                "reasoning": "low",
                "request": case["request"],
            }
            try:
                plan = planner.plan(case["request"])
                row["evaluation"] = evaluate(plan, case)
                row["knowledge_units"] = [
                    asdict(unit)
                    for action in plan.actions
                    if isinstance(action, WriteAction)
                    for unit in action.units
                ]
            except Exception as error:
                row.update(
                    {
                        "evaluation": {
                            "pass": False,
                            "failures": [f"{type(error).__name__}: {error}"],
                        }
                    }
                )
            rows.append(row)
    except Exception as error:
        rows.append(
            {
                "suite": "sol-atomic-decomposition",
                "model": "gpt-5.6-sol",
                "reasoning": "low",
                "status": "blocked",
                "error": f"{type(error).__name__}: {error}",
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "cases": len(cases),
                "completed": sum("evaluation" in row for row in rows),
                "passed": sum(row.get("evaluation", {}).get("pass", False) for row in rows),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
