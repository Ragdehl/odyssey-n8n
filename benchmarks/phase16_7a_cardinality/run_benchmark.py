"""Run the focused production Sol/low Phase 16.7A cardinality benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "config/note-schema.json"
CASES_PATH = Path(__file__).with_name("cases.json")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from odyssey_core.request_planning import OpenAIRequestPlanner  # noqa: E402


def evaluate(plan: Any, expectation: dict[str, Any]) -> list[str]:
    """Return explicit expectation failures for one validated RequestPlan."""
    writes = [action for action in plan.actions if action.kind == "write"]
    units = [unit for action in writes for unit in action.units]
    failures: list[str] = []
    if expectation.get("not_all_matching"):
        if any(unit.cardinality == "all_matching" for unit in units):
            failures.append("partial subset was classified as all_matching")
        return failures
    if len(units) != expectation.get("units"):
        failures.append(f"expected {expectation.get('units')} units, got {len(units)}")
    if expectation.get("all_units_one") and any(unit.cardinality != "one" for unit in units):
        failures.append("independent named targets were not all cardinality one")
    if (
        units
        and "cardinality" in expectation
        and units[0].cardinality != expectation["cardinality"]
    ):
        failures.append(f"expected cardinality {expectation['cardinality']}")
    if units and "type" in expectation and units[0].target.type != expectation["type"]:
        failures.append(f"expected type {expectation['type']!r}")
    if units and "intent" in expectation and units[0].intent != expectation["intent"]:
        failures.append(f"expected intent {expectation['intent']!r}")
    if units and "fields" in expectation:
        actual = {item.field for item in units[0].target.filters}
        if not set(expectation["fields"]).issubset(actual):
            failures.append(
                f"expected deterministic fields {expectation['fields']!r}, got {sorted(actual)!r}"
            )
    if (
        units
        and "filters" in expectation
        and len(units[0].target.filters) != expectation["filters"]
    ):
        failures.append("semantic-only case invented deterministic filters")
    return failures


def main() -> int:
    """Execute all frozen cases with gpt-5.6-sol, low reasoning, and store=false."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/phase16-7a-sol-low-results.json"))
    args = parser.parse_args()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    planner = OpenAIRequestPlanner.from_environment(
        schema,
        {"date": "2026-08-27", "time": "10:00", "timezone": "Europe/Paris"},
    )
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            plan = planner.plan(case["request"])
            failures = evaluate(plan, case["expect"])
            rows.append(
                {
                    "id": case["id"],
                    "request": case["request"],
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
                    "status": "ERROR",
                    "failures": [type(error).__name__],
                    "error": str(error)[:300],
                }
            )
    payload = {
        "model": "gpt-5.6-sol",
        "reasoning": "low",
        "store": False,
        "model_selection": False,
        "token_usage": None,
        "cases": rows,
        "summary": {
            "pass": sum(row["status"] == "PASS" for row in rows),
            "fail": sum(row["status"] == "FAIL" for row in rows),
            "error": sum(row["status"] == "ERROR" for row in rows),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0 if payload["summary"]["fail"] == 0 and payload["summary"]["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
