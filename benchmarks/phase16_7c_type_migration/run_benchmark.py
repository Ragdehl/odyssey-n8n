"""Run focused production Sol/low Phase 16.7C planner evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from odyssey_core.request_planning import OpenAIRequestPlanner  # noqa: E402


def evaluate(plan: Any, expectation: dict[str, Any]) -> list[str]:
    """Return semantic-contract failures without constraining harmless planner wording."""
    failures: list[str] = []
    actions = plan.actions
    if "action" in expectation:
        if len(actions) != 1 or actions[0].kind != expectation["action"]:
            return [f"expected one {expectation['action']} action"]
    units = [unit for action in actions if action.kind == "write" for unit in action.units]
    if "migration" in expectation:
        if len(actions) != 1 or len(units) != 1:
            failures.append("migration requires one write action and one unit")
        elif units[0].intent != "amend" or units[0].cardinality != "one":
            failures.append("migration must be single amend")
        elif units[0].destination_type != expectation["migration"]:
            failures.append("wrong destination type")
        elif any(change.field == "type" for change in units[0].properties):
            failures.append("type property change is forbidden")
        elif expectation.get("entry_date") and not any(
            change.field == "entry_date" and change.value == expectation["entry_date"]
            for change in units[0].properties
        ):
            failures.append("required destination entry_date missing")
    if expectation.get("no_migration") and any(unit.destination_type is not None for unit in units):
        failures.append("ordinary behavior emitted destination_type")
    if "intent" in expectation and (not units or units[0].intent != expectation["intent"]):
        failures.append("ordinary intent changed")
    if "cardinality" in expectation and (
        not units or units[0].cardinality != expectation["cardinality"]
    ):
        failures.append("cardinality changed")
    if expectation.get("references") and not any(unit.references for unit in units):
        failures.append("reference sentinel lost references")
    return failures


def main() -> int:
    """Call the production planner once per frozen case and record sanitized results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-id", action="append")
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_name("cases.json").read_text())
    if args.case_id:
        cases = [case for case in cases if case["id"] in set(args.case_id)]
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    planner = OpenAIRequestPlanner.from_environment(
        schema, {"date": "2026-08-28", "time": "10:00", "timezone": "Europe/Paris"}
    )
    rows = []
    for case in cases:
        try:
            plan = planner.plan(case["request"])
            failures = evaluate(plan, case["expect"])
            rows.append(
                {
                    "id": case["id"],
                    "request": case["request"],
                    "expect": case["expect"],
                    "status": "PASS" if not failures else "FAIL",
                    "failures": failures,
                    "plan": asdict(plan),
                }
            )
        except Exception as error:
            rows.append(
                {
                    "id": case["id"],
                    "request": case["request"],
                    "expect": case["expect"],
                    "status": "ERROR",
                    "error_type": type(error).__name__,
                    "error": str(error)[:300],
                }
            )
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model": "gpt-5.6-sol",
        "reasoning_effort": "low",
        "store": False,
        "model_selection": False,
        "cases": rows,
        "summary": {
            "pass": sum(r["status"] == "PASS" for r in rows),
            "fail": sum(r["status"] == "FAIL" for r in rows),
            "error": sum(r["status"] == "ERROR" for r in rows),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"]))
    return 0 if result["summary"]["fail"] == result["summary"]["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
