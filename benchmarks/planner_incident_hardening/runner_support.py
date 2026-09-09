"""Shared bounded evidence plumbing for authorization-gated planner-only runners."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from odyssey_core.request_planning import (
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    DelegateAction,
    PlannerClarification,
    RequestPlan,
    RetrieveAction,
    WriteAction,
)

_EVENT_DATE_QUERY_PATTERN = re.compile(r"\b(?:july|julio|2026-07)\b", re.IGNORECASE)


class Planner(Protocol):
    """Describe the bounded planner state retained by live evidence runners."""

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
        """Return a planner-only result without executing any returned action."""


def evaluate(result: RequestPlan | PlannerClarification, expected: str) -> bool:
    """Check the smallest frozen semantic outcome needed by a focused live gate."""
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


def run_cases(planner: Planner, cases: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    """Attempt each supplied frozen case once and retain bounded evidence only.

    Args:
        planner: Planner boundary; its returned action objects remain unexecuted.
        cases: Frozen case objects selected by the owning closed runner.

    Returns:
        One safe success or failure row for every attempted case.
    """
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


def write_rows(rows: Sequence[dict[str, Any]], output_path: Path) -> None:
    """Persist bounded evidence exclusively so an authorized gate cannot overwrite a prior run."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as output_file:
        output_file.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
