"""Small deterministic oracle for the five Phase 15 post-review sentinels."""

from __future__ import annotations

import unicodedata
from typing import Any

from benchmarks.phase14_request_plan_v3.benchmark import BenchmarkContractError
from benchmarks.phase15_write_planning.benchmark import validate_output


def _normalized(text: str) -> str:
    """Normalize text for conservative Spanish and English token matching."""
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(char) != "Mn"
    )


def _contains(text: str, *terms: str) -> bool:
    """Return whether a normalized string contains at least one required term."""
    normalized = _normalized(text)
    return any(_normalized(term) in normalized for term in terms)


def _finding(code: str, severity: str = "CRITICAL") -> dict[str, str]:
    """Create a stable result finding for the targeted evidence."""
    return {"severity": severity, "code": code}


def _facts_include(unit: dict[str, Any], term: str) -> bool:
    """Check that a semantic fact preserves a required concrete token."""
    return _contains(" ".join(unit["facts"]), term)


def evaluate_plan(case_id: str, candidate: Any) -> tuple[str, list[dict[str, str]]]:
    """Evaluate only the five approved regression properties.

    Args:
        case_id: Targeted case identifier from T01 through T05.
        candidate: Parsed model RequestPlan output.

    Returns:
        A deterministic status and concise findings. Write actions retain mandatory human review.
    """
    try:
        plan = validate_output(candidate)
    except BenchmarkContractError:
        return "CRITICAL", [_finding("invalid_plan")]
    findings = _case_findings(case_id, plan)
    if any(item["severity"] == "CRITICAL" for item in findings):
        return "CRITICAL", findings
    if any(action["kind"] == "write" for action in plan["actions"]):
        findings.append(_finding("write_semantic_review_required", "HUMAN REVIEW"))
        return "HUMAN REVIEW", findings
    return "PASS", findings


def _case_findings(case_id: str, plan: dict[str, Any]) -> list[dict[str, str]]:
    """Apply the intentionally narrow deterministic expectation for one targeted case."""
    actions = plan["actions"]
    if case_id == "T01":
        if [action["kind"] for action in actions] != ["write", "retrieve"]:
            return [_finding("wrong_action_boundary")]
        retrieve = actions[1]["plan"]
        if any(item["field"] in {"created_at", "updated_at"} for item in retrieve["filters"]):
            return [_finding("semantic_before_became_lifecycle_filter")]
        if not (
            _contains(retrieve["query"], "pens")
            and _contains(retrieve["query"], "antes", "anter", "previ")
        ):
            return [_finding("semantic_before_not_preserved")]
    elif case_id == "T02":
        if [action["kind"] for action in actions] != ["write"]:
            return [_finding("write_existence_lookup")]
        units = actions[0]["units"]
        if (
            len(units) != 1
            or units[0]["intent"] != "amend"
            or not _facts_include(units[0], "20:30")
        ):
            return [_finding("amendment_not_preserved")]
    elif case_id == "T03":
        if [action["kind"] for action in actions] != ["retrieve"]:
            return [_finding("explicit_metadata_retrieval_missing")]
        retrieve = actions[0]["plan"]
        filters = {(item["field"], item["op"], item["value"]) for item in retrieve["filters"]}
        expected = {
            ("created_at", "gte", "2026-08-19T00:00:00+02:00"),
            ("created_at", "lt", "2026-08-20T00:00:00+02:00"),
        }
        if retrieve["type"] != "journal_entry" or not expected.issubset(filters):
            return [_finding("explicit_metadata_filter_missing")]
    elif case_id == "T04":
        if [action["kind"] for action in actions] != ["retrieve", "retrieve"]:
            return [_finding("or_candidate_sets_lost")]
        branches = {
            tuple(
                sorted(
                    (item["field"], item["op"], item["value"]) for item in action["plan"]["filters"]
                )
            )
            for action in actions
            if action["plan"]["type"] == "person"
        }
        expected = {
            (("birth_date", "gte", "1990-01-01"), ("birth_date", "lt", "1991-01-01")),
            (("birth_date", "gte", "2000-01-01"), ("birth_date", "lt", "2001-01-01")),
        }
        if branches != expected:
            return [_finding("or_candidate_sets_lost")]
    elif case_id == "T05":
        if [action["kind"] for action in actions] != ["retrieve", "write"]:
            return [_finding("mixed_request_action_boundary")]
        retrieve, write = actions
        if not (
            _contains(retrieve["plan"]["query"], "compr")
            and _contains(retrieve["plan"]["query"], "carrefour")
        ):
            return [_finding("purchase_history_not_preserved")]
        units = write["units"]
        if (
            len(units) != 1
            or units[0]["intent"] != "amend"
            or not _facts_include(units[0], "20:30")
        ):
            return [_finding("mixed_request_amendment_not_preserved")]
    else:
        return [_finding("unknown_targeted_case")]
    return []
