"""Run the focused production Sol/low Phase 16.7A cardinality benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
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
    if "units" in expectation and len(units) != expectation["units"]:
        failures.append(f"expected {expectation.get('units')} units, got {len(units)}")
    if "min_units" in expectation and len(units) < expectation["min_units"]:
        failures.append(f"expected at least {expectation['min_units']} units, got {len(units)}")
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
    if units and "intents" in expectation and units[0].intent not in expectation["intents"]:
        failures.append(f"expected intent in {expectation['intents']!r}, got {units[0].intent!r}")
    if units and "filters" in expectation:
        actual_filters = [asdict(item) for item in units[0].target.filters]
        if actual_filters != expectation["filters"]:
            failures.append(f"expected filters {expectation['filters']!r}, got {actual_filters!r}")
    if units and "query_contains" in expectation:
        query = units[0].target.query or ""
        for fragment in expectation["query_contains"]:
            if fragment not in query:
                failures.append(f"expected target query to contain {fragment!r}, got {query!r}")
    if units and "tag_changes" in expectation:
        actual_tags = [asdict(item) for item in units[0].tag_changes]
        if expectation.get("all_units_one"):
            actual_tags = [asdict(item) for item in units[0].tag_changes]
            if any(
                [asdict(item) for item in unit.tag_changes] != expectation["tag_changes"]
                for unit in units
            ):
                failures.append(
                    "independent units did not preserve the exact requested tag mutation"
                )
        elif actual_tags != expectation["tag_changes"]:
            failures.append(
                f"expected tag_changes {expectation['tag_changes']!r}, got {actual_tags!r}"
            )
    if units and "references_required" in expectation:
        if not any(unit.references for unit in units):
            failures.append("expected semantic reference occurrences")
    if units and "properties" in expectation:
        actual_properties = [asdict(item) for item in units[0].properties]
        if actual_properties != expectation["properties"]:
            failures.append(
                f"expected properties {expectation['properties']!r}, got {actual_properties!r}"
            )
    if units and "reference_pairs" in expectation:
        actual_pairs: list[dict[str, str]] = []
        for unit in units:
            for reference in unit.references:
                if not 0 <= reference.target_index < len(units):
                    failures.append("reference target index is out of range")
                    continue
                actual_pairs.append(
                    {
                        "mention": reference.mention,
                        "target_query": units[reference.target_index].target.query,
                    }
                )
        if actual_pairs != expectation["reference_pairs"]:
            failures.append(
                f"expected reference pairs {expectation['reference_pairs']!r}, got {actual_pairs!r}"
            )
    if units and "no_reference_mentions" in expectation:
        actual_mentions = [reference.mention for unit in units for reference in unit.references]
        if any(mention in actual_mentions for mention in expectation["no_reference_mentions"]):
            failures.append("target-identifying names were incorrectly emitted as references")
    return failures


def provider_diagnostic(error: BaseException) -> dict[str, str]:
    """Extract a sanitized root provider error without exposing request data or credentials."""
    root = error
    while root.__cause__ is not None:
        root = root.__cause__
    message = str(root)
    for secret_marker in ("sk-", "Bearer ", "api_key="):
        if secret_marker in message:
            message = message.split(secret_marker, 1)[0] + "[REDACTED]"
    lowered = message.lower()
    if type(root).__name__ == "RequestPlanningError" and "provider call failed" not in lowered:
        category = "request/schema incompatibility"
    elif "auth" in lowered or "401" in lowered or "403" in lowered:
        category = "authentication/access"
    elif "model" in lowered or "permission" in lowered:
        category = "model availability/permissions"
    elif "schema" in lowered or "400" in lowered:
        category = "request/schema incompatibility"
    elif "connect" in lowered or "dns" in lowered or "resolve" in lowered:
        category = "networking/transport"
    else:
        category = "HTTP/provider failure"
    return {
        "root_error_type": type(root).__name__,
        "root_error_message": message[:500],
        "root_error_category": category,
    }


def create_default_output_path() -> Path:
    """Create a private temporary result path for an omitted benchmark output.

    Returns:
        An exclusively-created temporary JSON path that the benchmark can report
        and populate after execution.
    """
    with tempfile.NamedTemporaryFile(
        prefix="phase16-7a-sol-low-results-", suffix=".json", delete=False
    ) as temporary:
        return Path(temporary.name)


def main() -> int:
    """Execute all frozen cases with gpt-5.6-sol, low reasoning, and store=false."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    args = parser.parse_args()
    if args.output is None:
        args.output = create_default_output_path()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if args.case_ids:
        cases = [case for case in cases if case["id"] in set(args.case_ids)]
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
                    **provider_diagnostic(error),
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
    print(f"output={args.output}")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0 if payload["summary"]["fail"] == 0 and payload["summary"]["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
