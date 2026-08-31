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


def normalized_units(plan_or_units: Any) -> list[Any]:
    """Normalize live planner plans and serialized KnowledgeUnits to one evaluator input."""
    if isinstance(plan_or_units, list):
        return plan_or_units
    return [
        unit
        for action in plan_or_units.actions
        if isinstance(action, WriteAction)
        for unit in action.units
    ]


def _unit_value(unit: Any, key: str) -> Any:
    """Read a field from either a validated object or serialized benchmark mapping."""
    if isinstance(unit, dict):
        return unit.get(key)
    return getattr(unit, key, None)


def _target_value(unit: Any, key: str) -> Any:
    """Read a target field from either serialized or validated KnowledgeUnit data."""
    target = _unit_value(unit, "target")
    if isinstance(target, dict):
        return target.get(key)
    return getattr(target, key, None)


def evaluate_units(units: list[Any], case: dict[str, Any]) -> dict[str, Any]:
    """Apply the semantic planner rubric to normalized live or serialized KnowledgeUnits.

    Reference mentions are included as evidence, while target identity accepts either an explicit
    entity or the planner's human-readable query when entity is intentionally null.
    """
    facts = [fact for unit in units for fact in (_unit_value(unit, "facts") or ())]
    evidence = []
    for unit in units:
        evidence.extend(_unit_value(unit, "facts") or ())
        evidence.extend(
            str(reference.get("mention", ""))
            for reference in (_unit_value(unit, "references") or ())
            if isinstance(reference, dict)
        )
    text = " ".join(evidence).casefold()
    targets = []
    for unit in units:
        for key in ("entity", "query"):
            value = _target_value(unit, key)
            if value:
                targets.append(str(value))
    failures = []
    if not case["min_facts"] <= len(facts) <= case["max_facts"]:
        failures.append(f"fact count {len(facts)} outside {case['min_facts']}..{case['max_facts']}")
    for required in case["required"]:
        if required.casefold() not in text:
            failures.append(f"missing material detail {required!r}")
    matched_entities = sum(
        any(expected.casefold() in target.casefold() for target in targets)
        for expected in case["entities"]
    )
    if matched_entities != len(case["entities"]):
        failures.append(f"target grouping missing entities {case['entities']!r}; got {targets!r}")
    return {
        "pass": not failures,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "unit_count": len(units),
        "fact_count": len(facts),
        "entities": targets,
        "facts": list(facts),
    }


def evaluate(plan: Any, case: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a validated live planner result through the shared normalized boundary."""
    return evaluate_units(normalized_units(plan), case)


def reevaluate_saved_results(input_path: Path, cases_path: Path, output_path: Path) -> int:
    """Re-evaluate serialized planner units offline without making provider calls."""
    cases = {case["id"]: case for case in json.loads(cases_path.read_text(encoding="utf-8"))}
    rows = []
    for line in input_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        case = cases[row["case"]]
        if "knowledge_units" in row:
            row["evaluation"] = evaluate_units(row["knowledge_units"], case)
        rows.append(row)
    output_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    return sum(row.get("evaluation", {}).get("pass", False) for row in rows)


def provider_diagnostic(error: BaseException) -> dict[str, str]:
    """Classify a wrapped provider failure without exposing credentials or request content."""
    root = error
    while root.__cause__ is not None:
        root = root.__cause__
    message = str(root)
    for marker in ("sk-", "Bearer ", "api_key="):
        if marker in message:
            message = message.split(marker, 1)[0] + "[REDACTED]"
    lowered = message.casefold()
    category = (
        "network/provider access"
        if any(word in lowered for word in ("connect", "dns", "resolve", "name resolution"))
        else "provider/model access or implementation"
    )
    return {"category": category, "root_type": type(root).__name__, "message": message[:300]}


def main() -> None:
    """Run current production planner settings and preserve sanitized inspectable evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline-input", type=Path)
    parser.add_argument(
        "--cases", type=Path, default=Path(__file__).with_name("planner_cases.json")
    )
    args = parser.parse_args()
    if args.offline_input:
        passed = reevaluate_saved_results(args.offline_input, args.cases, args.output)
        print(json.dumps({"offline": True, "passed": passed, "output": str(args.output)}))
        return
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
                            "failures": [f"{type(error).__name__}: provider call failed"],
                        },
                        "provider_diagnostic": provider_diagnostic(error),
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
