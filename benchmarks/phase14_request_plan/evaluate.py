"""Deterministically evaluate RequestPlan candidate-set safety, not prose quality."""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from benchmarks.phase14_request_plan.benchmark import (
    BenchmarkContractError,
    assert_schema_alignment,
    validate_output,
)

SEVERITY_RANK = {"PASS": 0, "HUMAN REVIEW": 1, "MINOR": 2, "MAJOR": 3, "CRITICAL": 4}


def _finding(severity: str, code: str, detail: str) -> dict[str, str]:
    """Create one evaluator finding with a stable machine-oriented code."""
    return {"severity": severity, "code": code, "detail": detail}


def _effective_types(plan: dict[str, Any]) -> set[str] | None:
    """Return intersected Phase 13 type restrictions, or None when unrestricted."""
    universe = set(assert_schema_alignment()["retrieval_contract"]["canonical_types"])
    restrictions = []
    if plan["type"] is not None:
        restrictions.append({plan["type"]})
    for item in plan["filters"]:
        if item["field"] == "type":
            restrictions.append(
                set(item["value"] if isinstance(item["value"], list) else [item["value"]])
            )
    return set.intersection(universe, *restrictions) if restrictions else None


def _effective_tags(plan: dict[str, Any]) -> set[str]:
    """Return all-of tag restrictions across equivalent Phase 13 representations."""
    tags = set(plan["required_tags"])
    tags.update(item["value"] for item in plan["filters"] if item["field"] == "tags")
    return tags


def _filters(plan: dict[str, Any]) -> set[tuple[str, str, str]]:
    """Normalize ordinary filters after extracting type and tag restrictions."""
    return {
        (item["field"], item["op"], json.dumps(item["value"], sort_keys=True))
        for item in plan["filters"]
        if item["field"] not in {"type", "tags"}
    }


def _expected_types(branch: dict[str, Any]) -> set[str] | None:
    """Read a branch's optional expected type set."""
    return set(branch.get("types", branch.get("type", []))) or None


def _expected_filters(branch: dict[str, Any]) -> set[tuple[str, str, str]]:
    """Normalize an oracle branch's required filters."""
    return {
        (field, op, json.dumps(value, sort_keys=True))
        for field, op, value in branch.get("filters", [])
    }


def _restriction_severity(
    actual: set[str] | None, expected: set[str] | None
) -> tuple[str, str] | None:
    """Compare candidate types while distinguishing recall loss from safe broadening."""
    universe = set(assert_schema_alignment()["retrieval_contract"]["canonical_types"])
    actual_values = universe if actual is None else actual
    expected_values = universe if expected is None else expected
    if actual_values == expected_values:
        return None
    if actual_values <= expected_values:
        return "CRITICAL", "candidate restriction excludes requested values"
    if expected_values <= actual_values:
        return "MAJOR", "candidate restriction safely broadens requested values"
    return "CRITICAL", "candidate restriction changes and excludes requested values"


def _branch_findings(plan: dict[str, Any], branch: dict[str, Any]) -> list[dict[str, str]]:
    """Compare one generated branch with one expected candidate set."""
    findings = []
    type_difference = _restriction_severity(_effective_types(plan), _expected_types(branch))
    if type_difference:
        findings.append(_finding(type_difference[0], "type_restriction", type_difference[1]))
    actual_tags, expected_tags = _effective_tags(plan), set(branch.get("tags", []))
    if actual_tags - expected_tags:
        findings.append(
            _finding("CRITICAL", "false_required_tag", "An extra all-of tag excludes candidates.")
        )
    if expected_tags - actual_tags:
        findings.append(
            _finding("MAJOR", "missing_required_tag", "A requested tag restriction was omitted.")
        )
    actual_filters, expected_filters = _filters(plan), _expected_filters(branch)
    if actual_filters - expected_filters:
        findings.append(
            _finding(
                "CRITICAL", "unexpected_hard_filter", "An extra hard filter can exclude candidates."
            )
        )
    if expected_filters - actual_filters:
        findings.append(
            _finding("MAJOR", "missing_safe_filter", "A requested safe filter was omitted.")
        )
    return findings


def _normalize(text: str) -> str:
    """Normalize text only to flag semantic review candidates, never safety errors."""
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(char) != "Mn"
    )


def _semantic_findings(plan: dict[str, Any], branch: dict[str, Any]) -> list[dict[str, str]]:
    """Return human-review-only diagnostics for semantic retrieval wording."""
    query = _normalize(plan["query"])
    return [
        _finding(
            "HUMAN REVIEW", "semantic_query_review", "Query wording may omit requested meaning."
        )
        for group in branch.get("query_groups", [])
        if not any(term in query for term in group)
    ]


def _worst_severity(findings: list[dict[str, str]]) -> int:
    """Return a branch finding rank for simple best-candidate matching."""
    return max((SEVERITY_RANK[item["severity"]] for item in findings), default=0)


def evaluate_plan(candidate: Any, oracle: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Score unordered retrieval branches and logically ordered mixed actions."""
    try:
        validated = validate_output(candidate)
    except BenchmarkContractError as error:
        return "CRITICAL", [_finding("CRITICAL", "invalid_plan", str(error))]
    expected = oracle["expected"]
    findings: list[dict[str, str]] = []
    plans = [action["plan"] for action in validated["actions"] if action["kind"] == "retrieve"]
    unmatched = list(plans)
    for branch in expected["retrieve"]:
        if not unmatched:
            findings.append(
                _finding(
                    "CRITICAL",
                    "missing_retrieval_branch",
                    "A requested candidate branch is absent.",
                )
            )
            continue
        selected = min(unmatched, key=lambda plan: _worst_severity(_branch_findings(plan, branch)))
        unmatched.remove(selected)
        findings.extend(_branch_findings(selected, branch))
        findings.extend(_semantic_findings(selected, branch))
    for _plan in unmatched:
        findings.append(
            _finding(
                "MAJOR",
                "extra_retrieval_branch",
                "An unrequested retrieval adds noise and cost but no side effect.",
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
                "CRITICAL",
                "extra_create_action",
                "An unrequested create action is a future side effect.",
            )
        )
    create_text = _normalize(" ".join(action["content"] for action in create_actions))
    for group in expected.get("create_content_groups", []):
        if not any(term in create_text for term in group):
            findings.append(
                _finding(
                    "HUMAN REVIEW",
                    "create_content_review",
                    "Create content may omit explicitly requested knowledge.",
                )
            )
    expected_order = expected.get("action_kinds")
    actual_order = [action["kind"] for action in validated["actions"]]
    if expected_order is not None and actual_order != expected_order:
        findings.append(
            _finding(
                "MAJOR",
                "logical_action_order",
                "Action order does not preserve the request's conversational structure.",
            )
        )
    if set(validated["limitations"]) != set(expected["limitations"]):
        findings.append(
            _finding("MAJOR", "limitation_mismatch", "Limitations differ from expected semantics.")
        )
    return max(
        (item["severity"] for item in findings), key=SEVERITY_RANK.get, default="PASS"
    ), findings
