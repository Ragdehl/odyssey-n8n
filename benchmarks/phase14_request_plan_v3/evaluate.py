"""Deterministically evaluate RequestPlan candidate-set safety, not prose quality.

The evaluator proves only a small coverage subset: one generated branch may broaden
several oracle branches, and finite type sets may be partitioned across otherwise
equivalent branches. Other unions are deliberately left conservative.
"""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Any

from benchmarks.phase14_request_plan_v3.benchmark import (
    BenchmarkContractError,
    assert_schema_alignment,
    validate_output,
)

SEVERITY_RANK = {"PASS": 0, "HUMAN REVIEW": 1, "MINOR": 2, "MAJOR": 3, "CRITICAL": 4}
RANGE_FIELDS = {"created_at", "updated_at", "birth_date", "entry_date"}


def _finding(severity: str, code: str, detail: str) -> dict[str, str]:
    """Create one evaluator finding with a stable machine-oriented code."""
    return {"severity": severity, "code": code, "detail": detail}


def _effective_types(plan: dict[str, Any]) -> set[str] | None:
    """Return intersected Phase 13 type restrictions, or None when unrestricted."""
    universe = set(assert_schema_alignment()["retrieval_contract"]["canonical_types"])
    restrictions = [{plan["type"]}] if plan["type"] is not None else []
    restrictions.extend(
        set(item["value"] if isinstance(item["value"], list) else [item["value"]])
        for item in plan["filters"]
        if item["field"] == "type"
    )
    return set.intersection(universe, *restrictions) if restrictions else None


def _expected_types(branch: dict[str, Any]) -> set[str] | None:
    """Read a branch's optional expected type set."""
    return set(branch.get("types", branch.get("type", []))) or None


def _branch_filters(plan: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """Group non-type filters by candidate dimension."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for item in plan["filters"]:
        if item["field"] != "type":
            grouped.setdefault(item["field"], []).append((item["op"], item["value"]))
    return grouped


def _expected_filters(branch: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """Group oracle deterministic filters by candidate dimension."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for field, operator, value in branch.get("filters", []):
        if field != "type":
            grouped.setdefault(field, []).append((operator, value))
    return grouped


def _as_value(field: str, value: str) -> date | datetime:
    """Parse one validated date/date-time value for ordered containment comparison."""
    return (
        datetime.fromisoformat(value)
        if field in {"created_at", "updated_at"}
        else date.fromisoformat(value)
    )


def _interval(
    field: str, predicates: list[tuple[str, str]]
) -> tuple[tuple[Any, bool] | None, tuple[Any, bool] | None] | None:
    """Return an intersection interval, or None when predicates are not a single interval."""
    lower: tuple[Any, bool] | None = None
    upper: tuple[Any, bool] | None = None
    for operator, raw in predicates:
        if operator == "in":
            return None
        value = _as_value(field, raw)
        if operator == "eq":
            candidate_lower, candidate_upper = (value, True), (value, True)
        elif operator in {"gt", "gte"}:
            candidate_lower, candidate_upper = (value, operator == "gte"), None
        elif operator in {"lt", "lte"}:
            candidate_lower, candidate_upper = None, (value, operator == "lte")
        else:
            return None
        if candidate_lower and (
            lower is None
            or candidate_lower[0] > lower[0]
            or (candidate_lower[0] == lower[0] and not candidate_lower[1])
        ):
            lower = candidate_lower
        if candidate_upper and (
            upper is None
            or candidate_upper[0] < upper[0]
            or (candidate_upper[0] == upper[0] and not candidate_upper[1])
        ):
            upper = candidate_upper
    return lower, upper


def _contains_endpoint(
    actual: tuple[Any, bool] | None, expected: tuple[Any, bool] | None, *, lower: bool
) -> bool:
    """Return whether one interval endpoint is no stricter than its expected endpoint."""
    if actual is None:
        return True
    if expected is None:
        return False
    if lower:
        return actual[0] < expected[0] or (
            actual[0] == expected[0] and (actual[1] or not expected[1])
        )
    return actual[0] > expected[0] or (actual[0] == expected[0] and (actual[1] or not expected[1]))


def _set_predicates(predicates: list[tuple[str, str]]) -> set[str] | None:
    """Return allowed scalar values for eq/in predicates, when they are set-like."""
    values: set[str] | None = None
    for operator, value in predicates:
        if operator not in {"eq", "in"}:
            return None
        current = set(value if isinstance(value, list) else [value])
        values = current if values is None else values & current
    return values


def _field_findings(
    field: str, actual: list[tuple[str, str]] | None, expected: list[tuple[str, str]]
) -> list[dict[str, str]]:
    """Compare one deterministic field with recall-first containment semantics."""
    if actual is None:
        return [_finding("MAJOR", "missing_safe_filter", f"Requested {field} filter was omitted.")]
    if field in RANGE_FIELDS:
        actual_interval, expected_interval = _interval(field, actual), _interval(field, expected)
        if actual_interval is not None and expected_interval is not None:
            contains = _contains_endpoint(
                actual_interval[0], expected_interval[0], lower=True
            ) and _contains_endpoint(actual_interval[1], expected_interval[1], lower=False)
            if contains:
                if actual_interval == expected_interval:
                    return []
                return [
                    _finding(
                        "MAJOR",
                        "broader_range_filter",
                        f"{field} interval safely broadens candidates.",
                    )
                ]
            return [
                _finding(
                    "CRITICAL",
                    "narrow_range_filter",
                    f"{field} interval excludes requested candidates.",
                )
            ]
    actual_values, expected_values = _set_predicates(actual), _set_predicates(expected)
    if actual_values is not None and expected_values is not None:
        if actual_values == expected_values:
            return []
        if expected_values <= actual_values:
            return [
                _finding(
                    "MAJOR",
                    "broader_value_filter",
                    f"{field} allowed values safely broaden candidates.",
                )
            ]
        return [
            _finding(
                "CRITICAL",
                "narrow_value_filter",
                f"{field} allowed values exclude requested candidates.",
            )
        ]
    if actual == expected:
        return []
    return [
        _finding("CRITICAL", "changed_hard_filter", f"{field} predicate can exclude candidates.")
    ]


def _branch_findings(
    plan: dict[str, Any], branch: dict[str, Any], *, types: bool = True
) -> list[dict[str, str]]:
    """Compare one generated branch with one expected candidate set."""
    findings: list[dict[str, str]] = []
    if types:
        universe = set(assert_schema_alignment()["retrieval_contract"]["canonical_types"])
        actual, expected = _effective_types(plan) or universe, _expected_types(branch) or universe
        if actual != expected:
            findings.append(
                _finding(
                    "MAJOR" if expected <= actual else "CRITICAL",
                    "type_restriction",
                    "Type restriction safely broadens candidates."
                    if expected <= actual
                    else "Type restriction excludes requested candidates.",
                )
            )
    actual_filters, expected_filters = _branch_filters(plan), _expected_filters(branch)
    for field in actual_filters.keys() - expected_filters.keys():
        findings.append(
            _finding(
                "CRITICAL",
                "unexpected_hard_filter",
                f"Unexpected {field} filter can exclude candidates.",
            )
        )
    for field, expected_predicates in expected_filters.items():
        findings.extend(_field_findings(field, actual_filters.get(field), expected_predicates))
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
        if not any(_normalize(term) in query for term in group)
    ]


def _critical(findings: list[dict[str, str]]) -> bool:
    """Return whether deterministic comparison proves recall loss."""
    return any(item["severity"] == "CRITICAL" for item in findings)


def evaluate_plan(candidate: Any, oracle: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Score retrieval union coverage plus ordered mixed actions.

    A generated action can cover multiple expected branches. An expected finite type set
    can be covered by several actions with equivalent non-type constraints. Other
    unions are not inferred: unexplained coverage remains conservative, not magical.
    """
    try:
        validated = validate_output(candidate)
    except BenchmarkContractError as error:
        return "CRITICAL", [_finding("CRITICAL", "invalid_plan", str(error))]
    expected, findings = oracle["expected"], []
    plans = [action["plan"] for action in validated["actions"] if action["kind"] == "retrieve"]
    used: set[int] = set()
    for branch in expected["retrieve"]:
        direct = [(index, _branch_findings(plan, branch)) for index, plan in enumerate(plans)]
        safe = [(index, result) for index, result in direct if not _critical(result)]
        if safe:
            index, result = min(
                safe,
                key=lambda item: max((SEVERITY_RANK[f["severity"]] for f in item[1]), default=0),
            )
            used.add(index)
            findings.extend(result)
            findings.extend(_semantic_findings(plans[index], branch))
            continue
        base_safe = [
            (index, _branch_findings(plan, branch, types=False)) for index, plan in enumerate(plans)
        ]
        base_safe = [(index, result) for index, result in base_safe if not _critical(result)]
        expected_types = _expected_types(branch)
        covered_types = (
            set().union(*(_effective_types(plans[index]) or set() for index, _ in base_safe))
            if base_safe
            else set()
        )
        if expected_types and expected_types <= covered_types:
            for index, result in base_safe:
                used.add(index)
                findings.extend(result)
            findings.append(
                _finding(
                    "MAJOR",
                    "partitioned_retrieval",
                    "Several actions partition one intended retrieval branch.",
                )
            )
            for index, _ in base_safe:
                findings.extend(_semantic_findings(plans[index], branch))
            continue
        if direct:
            findings.extend(
                min(direct, key=lambda item: max(SEVERITY_RANK[f["severity"]] for f in item[1]))[1]
            )
        findings.append(
            _finding(
                "CRITICAL",
                "missing_retrieval_coverage",
                "No generated action union proves coverage of this requested candidate region.",
            )
        )
    for index, _plan in enumerate(plans):
        if index not in used:
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
                    "Create content may omit requested knowledge.",
                )
            )
    if (expected_order := expected.get("action_kinds")) is not None and [
        action["kind"] for action in validated["actions"]
    ] != expected_order:
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
