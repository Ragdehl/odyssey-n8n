#!/usr/bin/env python3
"""Run the approved future Phase 14 v2 experiment; never invoked during design."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.phase14_request_plan.benchmark import (  # noqa: E402
    BENCHMARK_DIR,
    CASES_PATH,
    ORACLE_PATH,
    PRICING_PATH,
    PROMPT_PATH,
    SCHEMA_CONTRACT_PATH,
    BenchmarkContractError,
    assert_schema_alignment,
    build_api_payload,
    estimated_cost,
    finite_latency,
    load_cases,
    load_json,
    render_prompt,
    sanitize_error,
    sha256_file,
    validate_output,
)
from benchmarks.phase14_request_plan.evaluate import evaluate_plan  # noqa: E402

RESULTS_DIR = BENCHMARK_DIR / "results"
PLANNED_CONFIGURATIONS = {
    "terra": ("gpt-5.6-terra", "low"),
    "sol": ("gpt-5.6-sol", "low"),
}
MAX_REPETITIONS = 4


def _append(path: Path, row: dict[str, Any]) -> None:
    """Append one completed, non-secret request record and fsync it for resumability."""
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _metadata(sdk_version: str) -> dict[str, Any]:
    """Freeze experiment design and versioned inputs before provider requests."""
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_version": load_json(CASES_PATH)["benchmark_version"],
        "oracle_version": load_json(ORACLE_PATH)["oracle_version"],
        "planned_configurations": [
            {"name": name, "model": model, "reasoning_effort": effort}
            for name, (model, effort) in PLANNED_CONFIGURATIONS.items()
        ],
        "openai_sdk_version": sdk_version,
        "api": "OpenAI Responses API",
        "store": False,
        "structured_outputs": True,
        "independent_request_per_case": True,
        "caching_strategy": "Independent requests retain a stable shared system prompt/schema prefix; provider counters are recorded without assuming a cache hit or write.",
        "prompt_cache_key": "odyssey-phase14-request-plan-v2",
        "artifact_sha256": {
            name: sha256_file(path)
            for name, path in {
                "prompt.md": PROMPT_PATH,
                "cases.json": CASES_PATH,
                "oracle.json": ORACLE_PATH,
                "schema_contract.json": SCHEMA_CONTRACT_PATH,
                "pricing.json": PRICING_PATH,
            }.items()
        },
    }


def logical_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    """Return the identity of one quality repetition, excluding API retry attempts."""
    return row["model"], row["reasoning_effort"], row["test_id"], row["repetition"]


def effective_attempts(
    rows: Iterable[dict[str, Any]],
) -> dict[tuple[str, str, str, int], dict[str, Any]]:
    """Select each logical request's latest success, else its latest failure."""
    grouped: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("record_type") == "request":
            grouped.setdefault(logical_key(row), []).append(row)
    return {
        key: max(
            (row for row in attempts if row.get("success")),
            key=lambda row: row["attempt"],
            default=max(attempts, key=lambda row: row["attempt"]),
        )
        for key, attempts in grouped.items()
    }


def summarize_attempts(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize transport attempts separately from logical quality repetitions.

    Retries increase ``api_attempt_count`` only. Stability is keyed without attempt,
    so a successful retry of repetition one cannot appear as repetition two.
    """
    attempts = [row for row in rows if row.get("record_type") == "request"]
    effective = effective_attempts(attempts)
    stability: dict[tuple[str, str, str], list[int]] = {}
    for model, effort, test_id, repetition in effective:
        stability.setdefault((model, effort, test_id), []).append(repetition)
    return {
        "api_attempt_count": len(attempts),
        "logical_request_count": len(effective),
        "successful_logical_count": sum(row.get("success", False) for row in effective.values()),
        "failed_logical_count": sum(not row.get("success", False) for row in effective.values()),
        "successful_repetitions": sorted(
            key for key, row in effective.items() if row.get("success", False)
        ),
        "stability_repetitions": {str(key): sorted(value) for key, value in stability.items()},
    }


def pending_requests(
    rows: Iterable[dict[str, Any]],
    configurations: list[tuple[str, str]],
    cases: Iterable[dict[str, str]],
    target_repetitions: int,
    retry_failures: bool,
) -> list[tuple[str, str, dict[str, str], int, int]]:
    """Return missing or explicitly retryable logical requests with their next attempt.

    Ordinary resume never reruns a failure; ``retry_failures`` retries it append-only.
    A retry retains its repetition number and therefore never becomes new stability data.
    """
    if not 1 <= target_repetitions <= MAX_REPETITIONS:
        raise BenchmarkContractError(f"target repetitions must be 1..{MAX_REPETITIONS}")
    grouped: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("record_type") == "request":
            grouped.setdefault(logical_key(row), []).append(row)
    pending = []
    for model, effort in configurations:
        for case in cases:
            for repetition in range(1, target_repetitions + 1):
                attempts = grouped.get((model, effort, case["id"], repetition), [])
                if any(row.get("success") for row in attempts):
                    continue
                if attempts and not retry_failures:
                    continue
                pending.append(
                    (
                        model,
                        effort,
                        case,
                        repetition,
                        max((row["attempt"] for row in attempts), default=0) + 1,
                    )
                )
    return pending


def _rows(path: Path) -> list[dict[str, Any]]:
    """Load append-only request evidence without changing it."""
    return (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if path.exists()
        else []
    )


def run(
    run_id: str,
    configuration_names: list[str],
    target_repetitions: int = 1,
    case_ids: set[str] | None = None,
    retry_failures: bool = False,
) -> None:
    """Execute selected planned configurations after explicit human approval."""
    assert_schema_alignment()
    try:
        from openai import OpenAI
        from openai import __version__ as sdk_version
    except ImportError as error:
        raise BenchmarkContractError("Install benchmark requirements before running") from error
    configurations = [PLANNED_CONFIGURATIONS[name] for name in configuration_names]
    directory = RESULTS_DIR / run_id
    directory.mkdir(parents=True, exist_ok=True)
    metadata_path, raw_path = directory / "metadata.json", directory / "raw_results.jsonl"
    metadata = _metadata(sdk_version)
    if metadata_path.exists():
        existing = load_json(metadata_path)
        expected = dict(metadata)
        expected["created_at"] = existing.get("created_at")
        if existing != expected:
            raise BenchmarkContractError("Refusing to alter historical run metadata")
    else:
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    selected_cases = [case for case in load_cases() if case_ids is None or case["id"] in case_ids]
    unknown = (case_ids or set()) - {case["id"] for case in load_cases()}
    if unknown:
        raise BenchmarkContractError(f"Unknown case IDs: {sorted(unknown)!r}")
    client, prompt, oracle, pricing = (
        OpenAI(),
        render_prompt(),
        load_json(ORACLE_PATH),
        load_json(PRICING_PATH),
    )
    indexed = {row["id"]: row for row in oracle["cases"]}
    for model, effort, case, repetition, attempt in pending_requests(
        _rows(raw_path), configurations, selected_cases, target_repetitions, retry_failures
    ):
        started = time.perf_counter()
        base = {
            "record_type": "request",
            "test_id": case["id"],
            "request": case["request"],
            "model": model,
            "reasoning_effort": effort,
            "repetition": repetition,
            "attempt": attempt,
        }
        try:
            response = client.responses.create(
                **build_api_payload(model, effort, prompt, case["request"])
            )
            payload = json.loads(response.output_text)
            validate_output(payload)
            usage = response.usage.model_dump(mode="json") if response.usage else {}
            details = usage.get("input_tokens_details", {})
            counters = {
                "input_tokens": usage.get("input_tokens", 0),
                "cached_input_tokens": details.get("cached_tokens", 0),
                "cache_write_tokens": details.get("cache_write_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "reasoning_tokens": usage.get("output_tokens_details", {}).get(
                    "reasoning_tokens", 0
                ),
            }
            status, findings = evaluate_plan(payload, indexed[case["id"]])
            row = base | {
                "success": True,
                "latency_seconds": finite_latency(time.perf_counter() - started),
                "usage": counters,
                "estimated_cost_usd": estimated_cost(model, counters, pricing),
                "parsed_output": payload,
                "status": status,
                "findings": findings,
            }
        except Exception as error:
            row = base | {
                "success": False,
                "latency_seconds": finite_latency(time.perf_counter() - started),
                "api_error": sanitize_error(error),
            }
        _append(raw_path, row)


def main() -> None:
    """Parse explicit future-run arguments and start no unapproved configuration."""
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--configuration", choices=PLANNED_CONFIGURATIONS, default="terra")
    parser.add_argument("--target-repetitions", type=int, default=1)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--retry-failures", action="store_true")
    args = parser.parse_args()
    run(
        args.run_id,
        [args.configuration],
        args.target_repetitions,
        set(args.case_ids) if args.case_ids else None,
        args.retry_failures,
    )


if __name__ == "__main__":
    main()
