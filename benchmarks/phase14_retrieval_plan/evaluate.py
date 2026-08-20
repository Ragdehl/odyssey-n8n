#!/usr/bin/env python3
"""Deterministically evaluate Phase 14 RetrievalPlans against the locked oracle."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.phase14_retrieval_plan.benchmark import (  # noqa: E402
    PRICING_PATH,
    BenchmarkContractError,
    assert_schema_alignment,
    canonical_filter,
    concepts_present,
    effective_required_tags,
    effective_types,
    estimated_cost,
    load_cases,
    load_json,
    load_oracle,
    regular_filters,
    validate_output,
)

SEVERITIES = ("PASS", "MINOR", "MAJOR", "CRITICAL")
SEVERITY_RANK = {value: index for index, value in enumerate(SEVERITIES)}


def finding(severity: str, code: str, message: str) -> dict[str, str]:
    """Build one stable machine-readable oracle finding."""
    return {"severity": severity, "code": code, "message": message}


def evaluate_plan(output: Any, oracle: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Evaluate one generated output by retrieval semantics rather than wording.

    Args:
        output: Parsed model output from one successful API request.
        oracle: Predeclared semantic invariants for the corresponding case.

    Returns:
        Overall severity and every deterministic finding.
    """
    try:
        validated = validate_output(output)
    except BenchmarkContractError as error:
        return "CRITICAL", [finding("CRITICAL", "invalid_plan", str(error))]
    expected = oracle["expected"]
    plan = validated["plan"]
    findings: list[dict[str, str]] = []

    actual_types = effective_types(plan)
    expected_types = None if expected["types"] is None else set(expected["types"])
    if expected_types is None and actual_types is not None:
        findings.append(
            finding(
                "CRITICAL",
                "false_type_filter",
                f"Unexpected type restriction can exclude valid notes: {sorted(actual_types)}",
            )
        )
    elif expected_types is not None:
        if actual_types is None:
            findings.append(
                finding(
                    "MAJOR",
                    "missing_type_filter",
                    f"Missing requested types: {sorted(expected_types)}",
                )
            )
        else:
            missing_types = expected_types - actual_types
            extra_types = actual_types - expected_types
            if missing_types:
                findings.append(
                    finding(
                        "CRITICAL",
                        "excluded_requested_type",
                        f"Type restriction excludes requested types: {sorted(missing_types)}",
                    )
                )
            if extra_types:
                findings.append(
                    finding(
                        "MAJOR",
                        "extra_candidate_type",
                        f"Type restriction includes unrequested types: {sorted(extra_types)}",
                    )
                )

    actual_tags = effective_required_tags(plan)
    expected_tags = set(expected["required_tags"])
    extra_tags = actual_tags - expected_tags
    missing_tags = expected_tags - actual_tags
    if extra_tags:
        findings.append(
            finding(
                "CRITICAL",
                "false_required_tag",
                f"Unexpected ANDed tags can exclude valid notes: {sorted(extra_tags)}",
            )
        )
    if missing_tags:
        findings.append(
            finding(
                "MAJOR",
                "missing_required_tag",
                f"Safe requested deterministic tags were omitted: {sorted(missing_tags)}",
            )
        )

    actual_filter_counts = Counter(canonical_filter(item) for item in regular_filters(plan))
    expected_candidates = [expected["filters"], *expected.get("filter_alternatives", [])]
    expected_filter_counts = min(
        (
            Counter(canonical_filter(item) for item in candidate)
            for candidate in expected_candidates
        ),
        key=lambda candidate: (
            sum((actual_filter_counts - candidate).values()),
            sum((candidate - actual_filter_counts).values()),
        ),
    )
    for signature, count in (expected_filter_counts - actual_filter_counts).items():
        findings.append(
            finding(
                "MAJOR",
                "missing_safe_filter",
                f"Safe requested filter was omitted ({count}x): {signature!r}",
            )
        )
    for signature, count in (actual_filter_counts - expected_filter_counts).items():
        findings.append(
            finding(
                "CRITICAL",
                "unexpected_hard_filter",
                f"Unjustified hard filter can reduce recall ({count}x): {signature!r}",
            )
        )

    missing_query = concepts_present(plan["query"], expected["query_groups"])
    for group in missing_query:
        findings.append(
            finding(
                "CRITICAL",
                "lost_semantic_concept",
                f"Meaningful topic/entity missing from semantic query: {group!r}",
            )
        )

    unrepresented_text = "\n".join(validated["unrepresented_constraints"])
    missing_unrepresented = concepts_present(unrepresented_text, expected["unrepresented_groups"])
    for group in missing_unrepresented:
        findings.append(
            finding(
                "MAJOR",
                "silent_structural_limitation",
                f"Material unsupported structural constraint was not reported: {group!r}",
            )
        )
    if not expected["unrepresented_groups"] and validated["unrepresented_constraints"]:
        findings.append(
            finding(
                "MINOR",
                "unnecessary_unrepresented_constraint",
                "Plan reports an unsupported constraint where semantic retrieval or filters suffice",
            )
        )

    if oracle.get("needs_human_review"):
        findings.append(finding("MAJOR", "needs_human_review", oracle["needs_human_review"]))
        return "HUMAN REVIEW", findings
    severity = max((item["severity"] for item in findings), key=SEVERITY_RANK.get, default="PASS")
    return severity, findings


def load_raw_rows(path: Path) -> list[dict[str, Any]]:
    """Load preserved JSONL responses and reject malformed experiment history."""
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise BenchmarkContractError(f"Malformed raw result at line {line_number}") from error
        if not isinstance(row, dict):
            raise BenchmarkContractError(f"Raw result at line {line_number} is not an object")
        if row.get("record_type", "request") == "request":
            rows.append(row)
    return rows


def logical_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    """Return the model/effort/case/repetition identity for retry collapsing."""
    return row["model"], row["reasoning_effort"], row["test_id"], row["repetition"]


def evaluate_rows(
    rows: list[dict[str, Any]], oracle: dict[str, dict[str, Any]], pricing: dict[str, Any]
) -> list[dict[str, Any]]:
    """Collapse retries and evaluate every latest logical request result."""
    latest: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for row in rows:
        latest[logical_key(row)] = row
    evaluated = []
    for key in sorted(latest):
        row = latest[key]
        if not row["success"]:
            evaluated.append(
                {
                    "test_id": row["test_id"],
                    "model": row["model"],
                    "reasoning_effort": row["reasoning_effort"],
                    "repetition": row["repetition"],
                    "status": "API_ERROR",
                    "findings": [],
                    "plan": None,
                    "api_error": row["api_error"],
                    "latency_seconds": row["latency_seconds"],
                    "usage": None,
                    "estimated_cost_usd": None,
                }
            )
            continue
        status, findings = evaluate_plan(row["parsed_output"], oracle[row["test_id"]])
        evaluated.append(
            {
                "test_id": row["test_id"],
                "model": row["model"],
                "reasoning_effort": row["reasoning_effort"],
                "repetition": row["repetition"],
                "status": status,
                "findings": findings,
                "plan": row["parsed_output"],
                "api_error": None,
                "latency_seconds": row["latency_seconds"],
                "usage": row["usage"],
                "estimated_cost_usd": estimated_cost(row["model"], row["usage"], pricing),
            }
        )
    return evaluated


def worst_status(rows: list[dict[str, Any]]) -> str:
    """Return a case's worst observed model-quality status across repetitions."""
    statuses = [row["status"] for row in rows]
    if not statuses:
        return "NOT RUN"
    if "API_ERROR" in statuses:
        return "API ERROR"
    if "HUMAN REVIEW" in statuses:
        return "HUMAN REVIEW"
    return max(statuses, key=SEVERITY_RANK.get)


def summarize_configuration(rows: list[dict[str, Any]], total_cases: int) -> dict[str, Any]:
    """Aggregate stability, severity, latency, tokens, and cost for one configuration."""
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[row["test_id"]].append(row)
    case_statuses = Counter(worst_status(case_rows) for case_rows in by_case.values())
    successful = [row for row in rows if row["status"] != "API_ERROR"]
    usage_fields = (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "output_tokens",
        "reasoning_tokens",
    )
    totals = {
        field: sum((row["usage"] or {}).get(field, 0) for row in rows) for field in usage_fields
    }
    costs = [row["estimated_cost_usd"] for row in successful]
    latencies = [row["latency_seconds"] for row in rows]
    return {
        "tests_expected": total_cases,
        "tests_observed": len(by_case),
        "requests": len(rows),
        "api_errors": sum(row["status"] == "API_ERROR" for row in rows),
        "pass": case_statuses["PASS"],
        "minor": case_statuses["MINOR"],
        "major": case_statuses["MAJOR"],
        "critical": case_statuses["CRITICAL"],
        "human_review": case_statuses["HUMAN REVIEW"],
        "complete": len(by_case) == total_cases
        and not any(row["status"] == "API_ERROR" for row in rows),
        "mean_latency_seconds": round(statistics.fmean(latencies), 6) if latencies else None,
        "median_latency_seconds": round(statistics.median(latencies), 6) if latencies else None,
        "tokens": totals,
        "estimated_cost_usd": round(sum(costs), 9) if costs else None,
        "mean_cost_per_request_usd": round(statistics.fmean(costs), 9) if costs else None,
        "median_cost_per_request_usd": round(statistics.median(costs), 9) if costs else None,
    }


def select_recommendation(summaries: dict[str, dict[str, Any]]) -> str | None:
    """Select the cheapest complete zero-critical configuration by the approved tie-breakers."""
    eligible = [
        (key, value)
        for key, value in summaries.items()
        if value["complete"] and value["critical"] == 0 and value["human_review"] == 0
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda item: (
            item[1]["major"],
            item[1]["minor"],
            item[1]["estimated_cost_usd"],
            item[1]["mean_latency_seconds"],
        ),
    )[0]


def render_summary(
    metadata: dict[str, Any],
    evaluated: list[dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    oracle: dict[str, dict[str, Any]],
) -> str:
    """Render the decision-oriented human summary required by the benchmark specification."""
    configurations = [
        (item["model"], item["reasoning_effort"]) for item in metadata["configurations"]
    ]
    lines = [
        "# Phase 14 retrieval-plan benchmark summary",
        "",
        f"Run: `{metadata['run_id']}`",
        f"Git SHA: `{metadata['git_sha']}`",
        f"Fixed context: `{json.dumps(metadata['fixed_context'], ensure_ascii=False)}`",
        "",
    ]
    if metadata.get("execution_status"):
        lines.extend(
            [
                f"Execution status: `{metadata['execution_status']}`",
                f"Blocker: `{metadata.get('blocker', 'none')}`",
                f"Paid API requests: `{metadata.get('paid_requests', 0)}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Configuration overview",
            "",
            "| Model | Effort | Tests | Critical | Major | Minor | Avg latency | Tokens | Estimated cost |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for model, effort in configurations:
        key = f"{model}:{effort}"
        summary = summaries.get(key)
        if summary is None:
            lines.append(f"| `{model}` | {effort} | 0/45 | — | — | — | — | — | not run |")
            continue
        token_total = summary["tokens"]["input_tokens"] + summary["tokens"]["output_tokens"]
        if summary["requests"] == 0:
            cost = "not run"
        elif summary["estimated_cost_usd"] is not None:
            cost = f"${summary['estimated_cost_usd']:.6f}"
        else:
            cost = "unresolved"
        latency = (
            f"{summary['mean_latency_seconds']:.3f}s"
            if summary["mean_latency_seconds"] is not None
            else "—"
        )
        lines.append(
            f"| `{model}` | {effort} | {summary['tests_observed']}/45 | "
            f"{summary['critical']} | {summary['major']} | {summary['minor']} | "
            f"{latency} | {token_total} | {cost} |"
        )

    lines.extend(
        [
            "",
            "API failures are reported separately and are not counted as model-quality failures.",
            "Total measured API usage: "
            + f"{sum(item['requests'] for item in summaries.values())} requests; "
            + f"${sum(item['estimated_cost_usd'] or 0 for item in summaries.values()):.9f} estimated.",
            "",
            "## Per-test comparison",
            "",
            "| Test | "
            + " | ".join(f"{model}/{effort}" for model, effort in configurations)
            + " |",
            "| --- | " + " | ".join("---" for _ in configurations) + " |",
        ]
    )
    by_config_case: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in evaluated:
        by_config_case[(row["model"], row["reasoning_effort"], row["test_id"])].append(row)
    for case in load_cases():
        statuses = [
            worst_status(by_config_case[(model, effort, case["id"])])
            for model, effort in configurations
        ]
        lines.append(f"| {case['id']} | " + " | ".join(statuses) + " |")

    serious_ids = sorted(
        {
            row["test_id"]
            for row in evaluated
            if row["status"] in {"CRITICAL", "MAJOR", "HUMAN REVIEW"}
        }
    )
    case_by_id = {case["id"]: case for case in load_cases()}
    lines.extend(["", "## Critical and major differences", ""])
    if not serious_ids:
        lines.append("None in the available evaluated results.")
    for case_id in serious_ids:
        lines.extend(
            [
                f"### {case_id}",
                "",
                "Question:",
                "",
                case_by_id[case_id]["request"],
                "",
                "Expected safe behavior:",
                "",
                "```json",
                json.dumps(oracle[case_id]["expected"], indent=2, ensure_ascii=False),
                "```",
                "",
            ]
        )
        for model, effort in configurations:
            rows = by_config_case[(model, effort, case_id)]
            if not rows:
                rendered = "not run"
            else:
                rendered = json.dumps(rows[-1]["plan"], ensure_ascii=False, separators=(",", ":"))
            lines.extend([f"{model}/{effort}:", "", f"`{rendered}`", ""])
        explanations = sorted(
            {
                item["message"]
                for row in evaluated
                if row["test_id"] == case_id
                for item in row["findings"]
                if item["severity"] in {"CRITICAL", "MAJOR"}
            }
        )
        lines.extend(
            [
                "Why a result is unsafe or inferior:",
                "",
                "; ".join(explanations) if explanations else "Human review is required.",
                "",
            ]
        )

    recommended = select_recommendation(summaries)
    lines.extend(["## Final recommendation", ""])
    if recommended is None:
        lines.append(
            "No configuration can yet be recommended: no complete evaluated configuration has "
            "demonstrated zero critical errors."
        )
    else:
        lines.append(
            f"Cheapest recall-safe configuration under the approved ordering: `{recommended}`."
        )
    quality_key = next(
        (key for key in summaries if key.startswith("gpt-5.6-sol:") and summaries[key]["complete"]),
        None,
    )
    lines.append(
        f"Quality reference: `{quality_key}`."
        if quality_key
        else "Quality reference remains unavailable until a complete Sol run exists."
    )
    lines.extend(
        [
            "",
            "A more articulate explanation is not evidence of better retrieval. The recommendation "
            "uses hard-filter safety and preservation of semantic recall first, then major/minor "
            "errors, actual estimated cost, and latency.",
            "",
        ]
    )
    return "\n".join(lines)


def write_derived(path: Path, content: str, *, replace: bool) -> None:
    """Write a derived result atomically while protecting historical artifacts by default."""
    if path.exists() and not replace:
        raise BenchmarkContractError(f"Refusing to overwrite {path}; pass --replace-derived")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def parser() -> argparse.ArgumentParser:
    """Build the deterministic evaluator CLI."""
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("run_dir", type=Path, help="Existing immutable benchmark result directory")
    value.add_argument(
        "--replace-derived",
        action="store_true",
        help="Regenerate evaluation.json and summary.md after intentional resumed requests",
    )
    return value


def main() -> int:
    """Evaluate one run and write machine-readable and human-readable conclusions."""
    args = parser().parse_args()
    assert_schema_alignment()
    metadata = load_json(args.run_dir / "metadata.json")
    oracle = load_oracle()
    pricing = load_json(PRICING_PATH)
    rows = load_raw_rows(args.run_dir / "raw_results.jsonl")
    evaluated = evaluate_rows(rows, oracle, pricing)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evaluated:
        grouped[f"{row['model']}:{row['reasoning_effort']}"].append(row)
    summaries = {}
    for configuration in metadata["configurations"]:
        key = f"{configuration['model']}:{configuration['reasoning_effort']}"
        summaries[key] = summarize_configuration(grouped[key], total_cases=45)
    payload = {
        "run_id": metadata["run_id"],
        "oracle_version": metadata["oracle_version"],
        "evaluated_requests": evaluated,
        "configurations": summaries,
        "recommendation": select_recommendation(summaries),
    }
    write_derived(
        args.run_dir / "evaluation.json",
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        replace=args.replace_derived,
    )
    write_derived(
        args.run_dir / "summary.md",
        render_summary(metadata, evaluated, summaries, oracle),
        replace=args.replace_derived,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BenchmarkContractError as error:
        print(f"evaluation error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
