"""Run the authorization-gated focused Sol/low planner hardening evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.planner_incident_hardening.runner_support import (  # noqa: E402
    evaluate,  # noqa: F401
    run_cases,
    write_rows,
)
from odyssey_core.request_planning import OpenAIRequestPlanner  # noqa: E402

CASES = Path(__file__).with_name("cases.json")
OUTPUT = ROOT / "benchmarks" / ".live-results" / "planner-incident-hardening.jsonl"


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
    rows = run_cases(planner, cases)
    write_rows(rows, OUTPUT)
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
