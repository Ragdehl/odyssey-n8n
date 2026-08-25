"""Deterministic safety checks for Phase 16.3 bounded writer results."""

from __future__ import annotations

import re
from typing import Any

from benchmarks.phase16_3_writer_benchmark.benchmark import BenchmarkContractError

_FORBIDDEN = (
    "[[",
    "http://",
    "https://",
    "id:",
    "path:",
    "schema_version",
    "created_at",
    "updated_at",
)


def evaluate_output(
    candidate: Any, case: dict[str, Any], *, context: str | None = None
) -> tuple[str, list[dict[str, str]]]:
    """Check schema, anchor containment, minimal spans, and frozen operation families.

    Semantic faithfulness intentionally remains a separate human-review decision.  A `CRITICAL`
    result is automatically material; `PASS` means only deterministic checks passed.
    """
    findings: list[dict[str, str]] = []
    if (
        not isinstance(candidate, dict)
        or set(candidate) != {"operations"}
        or not isinstance(candidate["operations"], list)
        or not candidate["operations"]
    ):
        return "CRITICAL", [_finding("invalid_schema")]
    operations = candidate["operations"]
    names = [
        operation.get("op") if isinstance(operation, dict) else None for operation in operations
    ]
    if "NO_CHANGE" in names and len(operations) != 1:
        findings.append(_finding("no_change_combined"))
    if case["mode"] == "CREATE":
        if names != ["CREATE_BODY"]:
            findings.append(_finding("invalid_create_operation"))
        elif not _valid_create_operation(operations[0]):
            findings.append(_finding("invalid_create_operation"))
    else:
        if "CREATE_BODY" in names:
            findings.append(_finding("create_operation_on_existing_note"))
        body = case["current_body"] if context is None else context
        for operation in operations:
            findings.extend(_operation_findings(operation, body))
        expected = set(case["expected_families"])
        if not expected.issubset(set(names)) or any(
            name not in {"NO_CHANGE", "APPEND", "REPLACE", "REMOVE", "INSERT_AFTER"}
            for name in names
        ):
            findings.append(_finding("incorrect_operation_family"))
    text = "\n".join(
        str(value)
        for operation in operations
        if isinstance(operation, dict)
        for value in operation.values()
        if isinstance(value, str)
    )
    if any(term.casefold() in text.casefold() for term in _FORBIDDEN):
        findings.append(_finding("forbidden_metadata_or_link"))
    return ("CRITICAL" if findings else "PASS"), findings


def _operation_findings(operation: Any, body: str) -> list[dict[str, str]]:
    """Return deterministic findings for one bounded operation against its exact body."""
    if not isinstance(operation, dict) or not isinstance(operation.get("op"), str):
        return [_finding("invalid_operation")]
    op = operation["op"]
    required = {
        "NO_CHANGE": {"op"},
        "APPEND": {"op", "text"},
        "REPLACE": {"op", "old", "new"},
        "REMOVE": {"op", "old"},
        "INSERT_AFTER": {"op", "anchor", "text"},
    }
    provider_shape = {"op", "text", "old", "new", "anchor", "content"}
    if set(operation) == provider_shape:
        operation = {key: value for key, value in operation.items() if value is not None}
    if (
        op not in required
        or set(operation) != required[op]
        or any(
            not isinstance(value, str) or not value.strip()
            for key, value in operation.items()
            if key != "op"
        )
    ):
        return [_finding("invalid_operation")]
    findings = []
    anchor = operation.get("old", operation.get("anchor"))
    if anchor is not None:
        if anchor not in body:
            findings.append(_finding("unsafe_missing_exact_anchor"))
        elif len(anchor) > max(240, len(body) // 2):
            findings.append(_finding("oversized_anchor"))
    if op == "REPLACE" and operation["old"] == operation["new"]:
        findings.append(_finding("identity_replacement"))
    return findings


def _valid_create_operation(operation: Any) -> bool:
    """Return whether one create result has only a non-empty Markdown body field."""
    if not isinstance(operation, dict):
        return False
    if set(operation) == {"op", "text", "old", "new", "anchor", "content"}:
        operation = {key: value for key, value in operation.items() if value is not None}
    return (
        set(operation) == {"op", "content"}
        and operation.get("op") == "CREATE_BODY"
        and isinstance(operation.get("content"), str)
        and bool(operation["content"].strip())
    )


def apply_operations(body: str, operations: list[dict[str, str]]) -> str:
    """Apply validated operations in sequence for optional human semantic inspection.

    Raises:
        BenchmarkContractError: If an exact replacement or removal span is absent.
    """
    result = body
    for operation in operations:
        if operation["op"] == "APPEND":
            result += ("\n" if result and not result.endswith("\n") else "") + operation["text"]
        elif operation["op"] == "REPLACE":
            if operation["old"] not in result:
                raise BenchmarkContractError("Cannot apply absent replacement span")
            result = result.replace(operation["old"], operation["new"], 1)
        elif operation["op"] == "REMOVE":
            if operation["old"] not in result:
                raise BenchmarkContractError("Cannot apply absent removal span")
            result = result.replace(operation["old"], "", 1)
        elif operation["op"] == "INSERT_AFTER":
            if operation["anchor"] not in result:
                raise BenchmarkContractError("Cannot apply absent insertion anchor")
            result = result.replace(operation["anchor"], operation["anchor"] + operation["text"], 1)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def _finding(code: str) -> dict[str, str]:
    """Build one compact deterministic finding."""
    return {"severity": "CRITICAL", "code": code}
