"""Strict four-case semantic gate for Selection-before-Operation prompting."""

from __future__ import annotations

import json
from typing import Any

from odyssey_core.request_planning import (
    DelegateAction,
    RequestPlanningError,
    RetrieveAction,
    SelectionCriteria,
    validate_request_plan,
)

from .benchmark import BENCHMARK_DIR, BenchmarkContractError

TARGETED_RESULTS_DIR = BENCHMARK_DIR / "targeted_results"


def load_targeted_cases() -> list[dict[str, str]]:
    """Load the four frozen targeted Selection-before-Operation cases.

    Returns:
        Ordered complete case dictionaries T01 through T04.

    Raises:
        BenchmarkContractError: If the targeted case fixture is malformed or changed in size.
    """
    try:
        cases = json.loads((BENCHMARK_DIR / "targeted_cases.json").read_text(encoding="utf-8"))[
            "cases"
        ]
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise BenchmarkContractError("Cannot load Phase 15.3 targeted cases") from error
    if (
        not isinstance(cases, list)
        or len(cases) != 4
        or any(set(case) != {"id", "request", "expect"} for case in cases)
        or [case["id"] for case in cases] != ["T01", "T02", "T03", "T04"]
    ):
        raise BenchmarkContractError("Targeted benchmark must contain frozen T01 through T04")
    return cases


def _related(selection: SelectionCriteria | None) -> bool:
    """Return whether selection is the canonical direct one-hop neighborhood around Marta."""
    if selection is None or selection.entity is not None or selection.filters:
        return False
    scope = selection.link_scope
    return bool(
        scope is not None
        and scope.anchor.entity == "Marta"
        and scope.anchor.type == "person"
        and not scope.anchor.filters
        and scope.direction == "both"
        and scope.max_depth == 1
    )


def evaluate_targeted(
    expectation: str, payload: Any, schema: dict[str, Any]
) -> tuple[str, list[str]]:
    """Evaluate one targeted output against an explicit fail-closed semantic oracle."""
    try:
        plan = validate_request_plan(payload, schema)
    except RequestPlanningError as error:
        return "INVALID", [f"invalid_plan:{error}"]
    findings: list[str] = []
    if expectation == "direct_marta":
        if len(plan.actions) != 1 or not isinstance(plan.actions[0], RetrieveAction):
            findings.append("direct_retrieve_required")
        else:
            selection = plan.actions[0].plan
            if (
                selection.entity != "Marta"
                or selection.type != "person"
                or selection.filters
                or selection.link_scope is not None
            ):
                findings.append("direct_marta_selection_wrong")
    elif expectation == "related_retrieve":
        if len(plan.actions) != 1 or not isinstance(plan.actions[0], RetrieveAction):
            findings.append("related_retrieve_required")
        elif not _related(plan.actions[0].plan):
            findings.append("related_retrieve_link_scope_wrong")
    elif expectation == "related_delegate":
        if len(plan.actions) != 1 or not isinstance(plan.actions[0], DelegateAction):
            findings.append("related_delegate_required")
        elif not _related(plan.actions[0].selection):
            findings.append("related_delegate_link_scope_wrong")
    elif expectation == "ordinary_delegate":
        if len(plan.actions) != 1 or not isinstance(plan.actions[0], DelegateAction):
            findings.append("ordinary_delegate_required")
        else:
            action = plan.actions[0]
            retained = action.request.casefold()
            if not all(term in retained for term in ("compr", "carrefour")) or not (
                "cuánt" in retained or "cont" in retained
            ):
                findings.append("ordinary_delegate_request_lost")
            if action.selection is not None and action.selection.link_scope is not None:
                findings.append("ordinary_delegate_invented_link_scope")
    else:
        return "FAIL", ["unknown_expectation"]
    return ("FAIL" if findings else "PASS"), findings
