"""Deterministically evaluate RequestPlan candidate-set safety, not prose quality."""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from benchmarks.phase14_request_plan.benchmark import BenchmarkContractError, validate_output

SEVERITY_RANK = {"PASS": 0, "HUMAN REVIEW": 1, "MINOR": 2, "MAJOR": 3, "CRITICAL": 4}


def _finding(severity: str, code: str, detail: str) -> dict[str, str]:
    """Create one evaluator finding with a stable machine-oriented code."""
    return {"severity": severity, "code": code, "detail": detail}


def _effective_types(plan: dict[str, Any]) -> set[str] | None:
    """Return an action's type restriction across Phase 13-compatible representations."""
    values: set[str] = {plan["type"]} if plan["type"] else set()
    for item in plan["filters"]:
        if item["field"] == "type":
            values.update(item["value"] if isinstance(item["value"], list) else [item["value"]])
    return values or None


def _filters(plan: dict[str, Any]) -> set[tuple[str, str, str]]:
    """Normalize non-type filters for order-independent structural comparison."""
    return {
        (item["field"], item["op"], json.dumps(item["value"], sort_keys=True))
        for item in plan["filters"]
        if item["field"] != "type"
    }


def _expected_filters(branch: dict[str, Any]) -> set[tuple[str, str, str]]:
    """Normalize an oracle branch's required filters."""
    return {
        (field, op, json.dumps(value, sort_keys=True))
        for field, op, value in branch.get("filters", [])
    }


def _matches_branch(plan: dict[str, Any], branch: dict[str, Any]) -> bool:
    """Return whether deterministic restrictions preserve one required candidate branch."""
    expected_types = set(branch.get("types", branch.get("type", []))) or None
    actual_types = _effective_types(plan)
    if expected_types != actual_types:
        return False
    expected_tags = set(branch.get("tags", []))
    if set(plan["required_tags"]) != expected_tags:
        return False
    return _filters(plan) == _expected_filters(branch)


def _normalize(text: str) -> str:
    """Normalize text only to flag semantic review candidates, never safety errors."""
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(char) != "Mn"
    )


def evaluate_plan(candidate: Any, oracle: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Score one output using unordered retrieval-branch candidate-set semantics.

    Invalid shapes and recall-threatening restrictions are CRITICAL.  Free-text query and
    create-content fidelity are intentionally reported only for human review.
    """
    try:
        validated = validate_output(candidate)
    except BenchmarkContractError as error:
        return "CRITICAL", [_finding("CRITICAL", "invalid_plan", str(error))]
    expected = oracle["expected"]
    findings: list[dict[str, str]] = []
    plans = [action["plan"] for action in validated["actions"] if action["kind"] == "retrieve"]
    unmatched = list(plans)
    for branch in expected["retrieve"]:
        match = next((plan for plan in unmatched if _matches_branch(plan, branch)), None)
        if match is None:
            expected_types = set(branch.get("types", branch.get("type", []))) or None
            expected_tags = set(branch.get("tags", []))
            compatible = next(
                (
                    plan
                    for plan in plans
                    if _effective_types(plan) == expected_types
                    and set(plan["required_tags"]) == expected_tags
                ),
                None,
            )
            if compatible in unmatched:
                unmatched.remove(compatible)
            severity = (
                "CRITICAL"
                if compatible and _filters(compatible) > _expected_filters(branch)
                else "MAJOR"
                if compatible
                else "CRITICAL"
            )
            findings.append(
                _finding(
                    severity,
                    "missing_retrieval_branch",
                    "A requested candidate branch is absent or lacks its safe constraints.",
                )
            )
        else:
            unmatched.remove(match)
            for group in branch.get("query_groups", []):
                if not any(term in _normalize(match["query"]) for term in group):
                    findings.append(
                        _finding(
                            "HUMAN REVIEW",
                            "semantic_query_review",
                            "Query wording may omit requested meaning.",
                        )
                    )
    for _plan in unmatched:
        findings.append(
            _finding(
                "CRITICAL",
                "unexpected_retrieval_branch",
                "An extra retrieval branch can impose an unrequested candidate restriction.",
            )
        )
    create_actions = [action for action in validated["actions"] if action["kind"] == "create_note"]
    if len(create_actions) < expected["create_count"]:
        findings.append(
            _finding("MAJOR", "missing_create_action", "A requested create intent is absent.")
        )
    if len(create_actions) > expected["create_count"]:
        findings.append(
            _finding(
                "MAJOR",
                "extra_create_action",
                "The request did not establish independent extra create intent.",
            )
        )
    if expected["create_count"] and any(not action["content"].strip() for action in create_actions):
        findings.append(
            _finding(
                "HUMAN REVIEW", "create_content_review", "Create content requires semantic review."
            )
        )
    if set(validated["limitations"]) != set(expected["limitations"]):
        findings.append(
            _finding(
                "MAJOR",
                "limitation_mismatch",
                "Limitations differ from remaining unsupported semantics.",
            )
        )
    return max(
        (item["severity"] for item in findings), key=SEVERITY_RANK.get, default="PASS"
    ), findings
