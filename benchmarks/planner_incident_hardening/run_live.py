"""Run the authorization-gated focused Sol/low planner hardening evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from odyssey_core.request_planning import (  # noqa: E402
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    DelegateAction,
    OpenAIRequestPlanner,
    PlannerClarification,
    RequestPlan,
    RetrieveAction,
    WriteAction,
)

CASES = Path(__file__).with_name("cases.json")
OUTPUT = ROOT / "benchmarks" / ".live-results" / "planner-incident-hardening.jsonl"
_EVENT_DATE_QUERY_PATTERN = re.compile(r"\b(?:july|julio|2026-07)\b", re.IGNORECASE)


def evaluate(result: RequestPlan | PlannerClarification, expected: str) -> bool:
    """Check the smallest frozen semantic outcome needed by this focused live gate."""
    if expected == "clarify":
        return isinstance(result, PlannerClarification)
    if not isinstance(result, RequestPlan):
        return False
    if expected == "event_date_retrieve":
        if len(result.actions) != 1 or not isinstance(result.actions[0], RetrieveAction):
            return False
        selection = result.actions[0].plan
        if selection.type != "purchase" or not _EVENT_DATE_QUERY_PATTERN.search(selection.query):
            return False
        if "unsupported_domain_date" not in result.limitations:
            return False
        filters = list(selection.filters)
        if selection.link_scope is not None:
            filters.extend(selection.link_scope.anchor.filters)
        return all(item.field not in {"created_at", "updated_at"} for item in filters)
    if expected == "mixed_retrieve_write":
        return len(result.actions) == 2 and {type(action) for action in result.actions} == {
            RetrieveAction,
            WriteAction,
        }
    expected_type = {
        "retrieve": RetrieveAction,
        "write": WriteAction,
        "delegate": DelegateAction,
    }[expected]
    return len(result.actions) == 1 and isinstance(result.actions[0], expected_type)


def main() -> int:
    """Run planner-only frozen cases after explicit authorization and confirmation.

    The returned plans are evaluated structurally and are never passed to application execution,
    so the mixed request's write action cannot mutate a vault.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args()
    if not args.confirm_live_provider_calls:
        parser.error("live provider calls require --confirm-live-provider-calls")
    if OUTPUT.exists():
        parser.error("output path already exists")

    schema = json.loads((ROOT / "config" / "note-schema.json").read_text(encoding="utf-8"))
    cases: list[dict[str, str]] = json.loads(CASES.read_text(encoding="utf-8"))
    context = {"date": "2026-09-08", "time": "12:00", "timezone": "Europe/Paris"}
    planner = OpenAIRequestPlanner.from_environment(schema, context)
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = planner.plan(case["request"])
            rows.append(
                {
                    "id": case["id"],
                    "model": PLANNER_MODEL,
                    "reasoning_effort": PLANNER_REASONING_EFFORT,
                    "expected": case["expect"],
                    "passed": evaluate(result, case["expect"]),
                    "result": asdict(result),
                    "response_id": planner.last_response_id,
                    "provider_status": planner.last_provider_status,
                    "usage": planner.last_usage,
                    "result_counts": planner.last_result_counts,
                }
            )
        except Exception as error:
            rows.append(
                {
                    "id": case["id"],
                    "model": PLANNER_MODEL,
                    "reasoning_effort": PLANNER_REASONING_EFFORT,
                    "expected": case["expect"],
                    "passed": False,
                    "error_category": planner.last_error_category or type(error).__name__,
                    "provider_status": planner.last_provider_status,
                    "incomplete_reason": planner.last_incomplete_reason,
                    "usage": planner.last_usage,
                }
            )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("x", encoding="utf-8") as output_file:
        output_file.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
