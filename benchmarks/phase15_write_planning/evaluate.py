"""Small deterministic Phase 15 oracle; natural-language equivalence stays reviewable."""

from __future__ import annotations

import unicodedata
from typing import Any

from benchmarks.phase15_write_planning.benchmark import BenchmarkContractError, validate_output


def _normalized(value: str) -> str:
    """Normalize user-language text for conservative token-group diagnostics."""
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    )


def _finding(severity: str, code: str) -> dict[str, str]:
    """Create one stable compact oracle finding."""
    return {"severity": severity, "code": code}


def _contains_group(text: str, group: list[str]) -> bool:
    """Return whether normalized text includes any acceptable required term."""
    normalized = _normalized(text)
    return any(_normalized(term) in normalized for term in group)


def evaluate_plan(candidate: Any, oracle: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Score only demonstrable structural/safety failures and wording review signals.

    Args:
        candidate: Parsed model output.
        oracle: One frozen expectation row.

    Returns:
        Overall status and deterministic findings.
    """
    try:
        plan = validate_output(candidate)
    except BenchmarkContractError:
        return "CRITICAL", [_finding("CRITICAL", "invalid_plan")]
    expected = oracle["actions"]
    actual = plan["actions"]
    if plan["limitations"] != oracle.get("limitations", []):
        return "CRITICAL", [_finding("CRITICAL", "incorrect_limitation")]
    if [item["kind"] for item in actual] != [item["kind"] for item in expected]:
        return "CRITICAL", [_finding("CRITICAL", "lost_or_extra_action")]
    findings: list[dict[str, str]] = []
    for candidate_action, expected_action in zip(actual, expected, strict=True):
        if candidate_action["kind"] == "retrieve":
            findings.extend(_retrieve_findings(candidate_action["plan"], expected_action))
        else:
            findings.extend(_write_findings(candidate_action, expected_action))
    if any(action["kind"] == "write" for action in actual):
        findings.append(_finding("HUMAN REVIEW", "write_semantic_review_required"))
    status = "CRITICAL" if any(item["severity"] == "CRITICAL" for item in findings) else "PASS"
    if status == "PASS" and findings:
        status = "HUMAN REVIEW"
    return status, findings


def _retrieve_findings(plan: dict[str, Any], expected: dict[str, Any]) -> list[dict[str, str]]:
    """Compare retrieval safety constraints while retaining recall-first missing-filter behavior."""
    actual_filters = {(item["field"], item["op"], repr(item["value"])) for item in plan["filters"]}
    expected_filters = {
        (field, op, repr(value)) for field, op, value in expected.get("filters", [])
    }
    findings = []
    if plan["type"] != expected.get("type"):
        findings.append(_finding("CRITICAL", "retrieval_type_regression"))
    if actual_filters - expected_filters:
        findings.append(_finding("CRITICAL", "unexpected_hard_filter"))
    if expected_filters - actual_filters:
        findings.append(_finding("MAJOR", "missing_safe_filter"))
    for group in expected.get("query_groups", []):
        if not _contains_group(plan["query"], group):
            findings.append(_finding("HUMAN REVIEW", "retrieval_query_wording"))
    return findings


def _write_findings(action: dict[str, Any], expected: dict[str, Any]) -> list[dict[str, str]]:
    """Compare unit count, intent, references, and minimally required semantic groups."""
    units, expected_units = action["units"], expected["units"]
    if len(units) != len(expected_units):
        return [_finding("CRITICAL", "lost_or_extra_knowledge_unit")]
    findings = []
    for _index, (unit, expectation) in enumerate(zip(units, expected_units, strict=True)):
        if unit["intent"] != expectation["intent"]:
            findings.append(_finding("CRITICAL", "incorrect_mutation_intent"))
        if "type" in expectation and unit["type"] != expectation["type"]:
            findings.append(_finding("CRITICAL", "invalid_or_invented_canonical_type"))
        if "fact_count" in expectation and len(unit["facts"]) != expectation["fact_count"]:
            findings.append(_finding("CRITICAL", "unexpected_or_missing_fact"))
        for group in expectation.get("subject_groups", []):
            if not _contains_group(unit["subject"], group):
                findings.append(_finding("HUMAN REVIEW", "subject_wording"))
        fact_text = " ".join(unit["facts"])
        for group in expectation.get("fact_groups", []):
            if not _contains_group(fact_text, group):
                findings.append(_finding("CRITICAL", "lost_knowledge_fact"))
    for source, target, role_group in expected.get("units", [{}])[-1].get("references", []):
        matching = [
            item
            for item in units[source]["references"]
            if item["target_index"] == target and _contains_group(item["role"], role_group)
        ]
        if not matching:
            findings.append(_finding("CRITICAL", "lost_or_malformed_reference"))
    return findings
