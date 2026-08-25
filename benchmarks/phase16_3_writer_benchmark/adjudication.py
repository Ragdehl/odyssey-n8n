"""Create append-only semantic reviews and auditable run-integrity summaries."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def canonical_records(raw_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select the first parseable record per case/context and retain every spend-bearing call.

    Args:
        raw_path: Append-only JSONL provider evidence, which may contain damaged fragments.

    Returns:
        Canonical records and metadata describing malformed lines, duplicate calls, and costs.
    """
    canonical: list[dict[str, Any]] = []
    malformed: list[int] = []
    duplicates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    all_records: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw_path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed.append(line_number)
            continue
        all_records.append(record)
        key = (record.get("case_id", ""), record.get("context_strategy", ""))
        if key in seen:
            duplicates.append({"line": line_number, "case_id": key[0], "context_strategy": key[1]})
            continue
        seen.add(key)
        canonical.append(record)
    totals = _cost_totals(all_records)
    return canonical, {
        "raw_record_lines": len(raw_path.read_text(encoding="utf-8").splitlines()),
        "malformed_raw_lines": malformed,
        "duplicate_effective_calls": duplicates,
        "canonical_selection": "first_parseable_record_by_case_id_and_context_strategy",
        "canonical_evaluation_record_count": len(canonical),
        "actual_provider_record_count": len(all_records),
        "all_provider_calls_count_toward_actual_cost": True,
        "actual_cost": totals,
    }


def write_review(directory: Path, findings_by_case: dict[str, dict[str, str]]) -> Path:
    """Write one immutable semantic adjudication row for each canonical provider result.

    Args:
        directory: Result directory containing append-only raw evidence.
        findings_by_case: Reviewed status, taxonomy, and concise rationale keyed by case ID.

    Returns:
        New `review.jsonl` path.

    Raises:
        ValueError: If a review already exists or a canonical record lacks an adjudication.
    """
    review_path = directory / "review.jsonl"
    if review_path.exists():
        raise ValueError("Refusing to rewrite semantic review evidence")
    records, _ = canonical_records(directory / "raw_results.jsonl")
    rows = []
    for record in records:
        finding = findings_by_case.get(record["case_id"])
        if finding is None:
            raise ValueError(f"Missing semantic adjudication for {record['case_id']}")
        rows.append({**record, "semantic_status": finding["status"], "findings": [finding]})
    review_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    return review_path


def write_integrity(directory: Path, extra: dict[str, Any] | None = None) -> Path:
    """Persist deterministic run-integrity metadata without changing raw provider evidence."""
    path = directory / "integrity.json"
    if path.exists():
        raise ValueError("Refusing to rewrite run-integrity evidence")
    _, metadata = canonical_records(directory / "raw_results.jsonl")
    path.write_text(json.dumps({**metadata, **(extra or {})}, indent=2) + "\n", encoding="utf-8")
    return path


def _cost_totals(records: list[dict[str, Any]]) -> dict[str, float | int]:
    """Sum token and USD fields across every parseable provider record, including duplicates."""
    totals: defaultdict[str, float] = defaultdict(float)
    for record in records:
        usage = record.get("usage", {})
        for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
            totals[key] += int(usage.get(key, 0))
        totals["estimated_cost_usd"] += float(record.get("estimated_cost_usd", 0))
    return {key: round(value, 8) for key, value in totals.items()}
