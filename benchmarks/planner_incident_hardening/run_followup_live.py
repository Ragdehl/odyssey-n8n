"""Run the closed four-case planner diagnostic follow-up after explicit authorization."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.planner_incident_hardening.run_live import evaluate  # noqa: E402
from odyssey_core.request_planning import (  # noqa: E402
    PLANNER_AUTOMATIC_RETRIES,
    PLANNER_MAX_OUTPUT_TOKENS,
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    OpenAIRequestPlanner,
    PlannerClarification,
    RequestPlan,
)

CASES = Path(__file__).with_name("cases.json")
OUTPUT = ROOT / "benchmarks" / ".live-results" / "planner-incident-hardening-followup.jsonl"
FOLLOW_UP_IDS = (
    "normal_retrieval",
    "normal_write",
    "legitimate_delegation",
    "legitimate_mixed",
)
_FOLLOW_UP_EXPECTATIONS = {
    "normal_retrieval": "retrieve",
    "normal_write": "write",
    "legitimate_delegation": "delegate",
    "legitimate_mixed": "mixed_retrieve_write",
}


class Planner(Protocol):
    """Describe the bounded planner state retained by the follow-up evidence runner."""

    last_response_id: str | None
    last_provider_status: str | None
    last_usage: dict[str, int] | None
    last_parse_status: str | None
    last_validation_stage: str | None
    last_validation_code: str | None
    last_result_counts: dict[str, int] | None
    last_error_category: str | None
    last_incomplete_reason: str | None
    last_output_text_chars: int | None
    last_output_text_bytes: int | None

    def plan(self, request: str) -> RequestPlan | PlannerClarification:
        """Return a planner-only result without executing any action."""


def validate_followup_configuration() -> None:
    """Refuse a follow-up run unless it retains the reviewed production planner limits."""
    if PLANNER_MAX_OUTPUT_TOKENS != 4096 or PLANNER_AUTOMATIC_RETRIES != 0:
        raise RuntimeError("follow-up runner requires the reviewed planner limits")


def load_followup_cases(cases_path: Path = CASES) -> list[dict[str, str]]:
    """Load exactly the unresolved frozen cases without copying their request text.

    Args:
        cases_path: Canonical frozen case registry shared with the original eight-case gate.

    Returns:
        The four selected frozen case objects in the fixed follow-up order.

    Raises:
        ValueError: If the registry is malformed, missing a target, duplicates a target, or maps a
            target ID to an unexpected expectation.
    """
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
        if case_id not in FOLLOW_UP_IDS:
            continue
        if case_id in selected:
            raise ValueError("frozen follow-up case is duplicated")
        request, expected = case.get("request"), case.get("expect")
        if (
            not isinstance(request, str)
            or not request.strip()
            or expected != _FOLLOW_UP_EXPECTATIONS[case_id]
        ):
            raise ValueError("frozen follow-up case mapping is invalid")
        selected[case_id] = {"id": case_id, "request": request, "expect": expected}

    if set(selected) != set(FOLLOW_UP_IDS) or len(selected) != len(FOLLOW_UP_IDS):
        raise ValueError("frozen follow-up case set is incomplete")
    return [selected[case_id] for case_id in FOLLOW_UP_IDS]


def run_followup_cases(planner: Planner, cases: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    """Run every already-selected case exactly once and retain bounded evidence only.

    Args:
        planner: Injected planner boundary; returned plans are never passed to execution.
        cases: Exactly the four cases returned by ``load_followup_cases``.

    Returns:
        One bounded evidence row per attempted case, including failures.

    Raises:
        ValueError: If callers bypass the closed loader with a different case set.
    """
    if [case.get("id") for case in cases] != list(FOLLOW_UP_IDS):
        raise ValueError("follow-up cases must use the fixed unresolved ID order")

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
                    "parse_status": planner.last_parse_status,
                    "validation_stage": planner.last_validation_stage,
                    "validation_code": planner.last_validation_code,
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
                    "response_id": planner.last_response_id,
                    "parse_status": planner.last_parse_status,
                    "output_text_chars": planner.last_output_text_chars,
                    "output_text_bytes": planner.last_output_text_bytes,
                    "validation_stage": planner.last_validation_stage,
                    "validation_code": planner.last_validation_code,
                }
            )
    return rows


def write_followup_rows(rows: Sequence[dict[str, Any]], output_path: Path = OUTPUT) -> None:
    """Persist follow-up evidence once without touching the original live-gate JSONL.

    Args:
        rows: Bounded rows produced by the closed follow-up case loop.
        output_path: Fixed, gitignored follow-up evidence location.

    Raises:
        FileExistsError: If follow-up evidence already exists.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as output_file:
        output_file.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the closed follow-up gate only after explicit human authorization."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_live_provider_calls:
        parser.error("live provider calls require --confirm-live-provider-calls")
    if OUTPUT.exists():
        parser.error("follow-up output path already exists")

    validate_followup_configuration()
    cases = load_followup_cases()
    schema = json.loads((ROOT / "config" / "note-schema.json").read_text(encoding="utf-8"))
    context = {"date": "2026-09-08", "time": "12:00", "timezone": "Europe/Paris"}
    planner = OpenAIRequestPlanner.from_environment(schema, context)
    rows = run_followup_cases(planner, cases)
    write_followup_rows(rows)
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
