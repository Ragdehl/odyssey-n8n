"""Run the fixed six-case planner gate after the nested envelope fix."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.planner_incident_hardening.runner_support import (  # noqa: E402
    Planner,
    run_cases,
    write_rows,
)
from odyssey_core.request_planning import (  # noqa: E402
    PLANNER_AUTOMATIC_RETRIES,
    PLANNER_MAX_OUTPUT_TOKENS,
    OpenAIRequestPlanner,
)

CASES = Path(__file__).with_name("cases.json")
OUTPUT = ROOT / "benchmarks" / ".live-results" / "planner-incident-hardening-post-envelope.jsonl"
POST_ENVELOPE_IDS = (
    "incident_bdbd",
    "normal_retrieval",
    "normal_write",
    "legitimate_delegation",
    "event_date_not_lifecycle",
    "legitimate_mixed",
)
EXPECTATIONS = {
    "incident_bdbd": "clarify",
    "normal_retrieval": "retrieve",
    "normal_write": "write",
    "legitimate_delegation": "delegate",
    "event_date_not_lifecycle": "event_date_retrieve",
    "legitimate_mixed": "mixed_retrieve_write",
}


def load_post_envelope_cases(cases_path: Path = CASES) -> list[dict[str, str]]:
    """Load exactly the six reviewed cases in their fail-fast order."""
    try:
        raw_cases = json.loads(cases_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("frozen planner cases are unavailable") from error
    if not isinstance(raw_cases, list):
        raise ValueError("frozen planner cases must be a list")
    selected: dict[str, dict[str, str]] = {}
    for case in raw_cases:
        if not isinstance(case, dict):
            raise ValueError("frozen planner case is invalid")
        case_id = case.get("id")
        if case_id not in POST_ENVELOPE_IDS:
            continue
        if case_id in selected:
            raise ValueError("post-envelope case is duplicated")
        request, expected = case.get("request"), case.get("expect")
        if not isinstance(request, str) or not request.strip() or expected != EXPECTATIONS[case_id]:
            raise ValueError("post-envelope case mapping is invalid")
        selected[case_id] = {"id": case_id, "request": request, "expect": expected}
    if set(selected) != set(POST_ENVELOPE_IDS) or len(selected) != 6:
        raise ValueError("post-envelope case set is incomplete")
    return [selected[case_id] for case_id in POST_ENVELOPE_IDS]


def run_post_envelope_cases(
    planner: Planner, cases: Sequence[dict[str, str]]
) -> list[dict[str, Any]]:
    """Evaluate each selected plan once without executing any returned action."""
    if [case.get("id") for case in cases] != list(POST_ENVELOPE_IDS):
        raise ValueError("post-envelope cases must use the fixed approved order")
    rows: list[dict[str, Any]] = []
    for case in cases:
        row = run_cases(planner, [case])[0]
        rows.append(row)
        if (
            case["id"] in {"incident_bdbd", "normal_retrieval"}
            and row.get("provider_status") != "completed"
        ):
            break
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the post-envelope gate only after explicit authorization."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_live_provider_calls:
        parser.error("live provider calls require --confirm-live-provider-calls")
    if OUTPUT.exists():
        parser.error("post-envelope output path already exists")
    if PLANNER_MAX_OUTPUT_TOKENS != 4096 or PLANNER_AUTOMATIC_RETRIES != 0:
        parser.error("post-envelope runner requires max_output_tokens=4096 and max_retries=0")
    cases = load_post_envelope_cases()
    schema = json.loads((ROOT / "config" / "note-schema.json").read_text(encoding="utf-8"))
    planner = OpenAIRequestPlanner.from_environment(
        schema, {"date": "2026-09-08", "time": "12:00", "timezone": "Europe/Paris"}
    )
    rows = run_post_envelope_cases(planner, cases)
    write_rows(rows, OUTPUT)
    return 0 if len(rows) == 6 and all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
