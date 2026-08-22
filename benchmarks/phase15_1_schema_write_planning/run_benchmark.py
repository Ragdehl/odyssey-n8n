#!/usr/bin/env python3
"""Run the one-pass Phase 15.1 Sol/low benchmark without hidden retries."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.phase15_1_schema_write_planning.benchmark import (
    BENCHMARK_DIR,
    BenchmarkContractError,
    load_cases,
    load_json,
    production_request,
)
from benchmarks.phase15_1_schema_write_planning.evaluate import evaluate

RESULTS_DIR = BENCHMARK_DIR / "results"
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "low"


def _append(path: Path, row: dict[str, Any]) -> None:
    """Durably append one result row after every provider attempt.

    Args:
        path: Append-only JSON Lines evidence file.
        row: Non-secret request/result evidence.
    """
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _usage(response: Any) -> dict[str, int]:
    """Extract available provider usage counters without assuming optional fields exist."""
    raw = response.usage.model_dump(mode="json") if getattr(response, "usage", None) else {}
    details = raw.get("input_tokens_details", {})
    return {
        "input_tokens": raw.get("input_tokens", 0),
        "cached_input_tokens": details.get("cached_tokens", 0),
        "cache_write_tokens": details.get("cache_write_tokens", 0),
        "output_tokens": raw.get("output_tokens", 0),
        "reasoning_tokens": raw.get("output_tokens_details", {}).get("reasoning_tokens", 0),
    }


def _estimated_cost(usage: dict[str, int]) -> float:
    """Estimate USD cost from the frozen standard short-context pricing snapshot."""
    rates = load_json(BENCHMARK_DIR / "pricing.json")["models"][MODEL]
    ordinary = usage["input_tokens"] - usage["cached_input_tokens"] - usage["cache_write_tokens"]
    if ordinary < 0:
        raise BenchmarkContractError("Provider usage counters overlap beyond total input tokens")
    return (
        ordinary * rates["input"]
        + usage["cached_input_tokens"] * rates["cached_input"]
        + usage["cache_write_tokens"] * rates["cache_write"]
        + usage["output_tokens"] * rates["output"]
    ) / 1_000_000


def run(run_id: str, client: Any | None = None, case_ids: set[str] | None = None) -> Path:
    """Execute one Sol/low call for every selected not-yet-recorded frozen case.

    Args:
        run_id: New immutable evidence directory name.
        client: Optional Responses-compatible client used only by deterministic tests.
        case_ids: Optional explicit focused follow-up case IDs. ``None`` runs the complete benchmark.

    Returns:
        Created evidence directory.

    Raises:
        BenchmarkContractError: If historical inputs are inconsistent, a run is complete, or the SDK
            is unavailable.
    """
    directory = RESULTS_DIR / run_id
    if client is None:
        try:
            from openai import OpenAI
            from openai import __version__ as sdk_version
        except ImportError as error:
            raise BenchmarkContractError("Install the OpenAI SDK before execution") from error
        client = OpenAI(max_retries=0)
    else:
        sdk_version = "test-client"
    all_cases = load_cases()
    unknown = (case_ids or set()) - {case["id"] for case in all_cases}
    if unknown:
        raise BenchmarkContractError(f"Unknown focused case IDs: {sorted(unknown)!r}")
    cases = [case for case in all_cases if case_ids is None or case["id"] in case_ids]
    raw_path = directory / "raw_results.jsonl"
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_version": load_json(BENCHMARK_DIR / "cases.json")["benchmark_version"],
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "store": False,
        "structured_outputs": "production request_plan_json_schema",
        "prompt": "production render_request_planner_prompt",
        "planned_calls": len(cases),
        "automatic_retries": False,
        "openai_sdk_version": sdk_version,
    }
    if directory.exists():
        if not raw_path.exists() or not (directory / "metadata.json").exists():
            raise BenchmarkContractError(
                "Existing benchmark run is incomplete before any request row"
            )
        existing = load_json(directory / "metadata.json")
        metadata["created_at"] = existing.get("created_at")
        if existing != metadata:
            raise BenchmarkContractError("Refusing to alter benchmark metadata")
        rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
        completed = [row.get("test_id") for row in rows]
        expected_ids = [case["id"] for case in cases]
        if len(completed) != len(set(completed)) or not set(completed) <= set(expected_ids):
            raise BenchmarkContractError(
                "Existing benchmark rows are not a valid prefix-free record"
            )
        if len(completed) == len(cases):
            raise BenchmarkContractError("Benchmark run is already complete")
    else:
        directory.mkdir(parents=True)
        (directory / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        completed = []
    for case in cases:
        if case["id"] in completed:
            continue
        api_request, schema = production_request(case)
        started = time.perf_counter()
        base = {
            "test_id": case["id"],
            "request": case["request"],
            "current_context": case["current_context"],
            "schema_selector": case["schema"],
            "schema": schema,
            "api_request": api_request,
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "store": False,
        }
        try:
            response = client.responses.create(**api_request)
        except Exception as error:
            _append(
                raw_path,
                base
                | {
                    "provider_success": False,
                    "classification": "INVALID",
                    "failure_kind": "provider",
                    "error": str(error)[:500],
                    "latency_seconds": time.perf_counter() - started,
                },
            )
            continue
        row = base | {
            "provider_success": True,
            "latency_seconds": time.perf_counter() - started,
            "usage": _usage(response),
            "raw_model_output": getattr(response, "output_text", None),
        }
        try:
            row["estimated_cost_usd"] = _estimated_cost(row["usage"])
            payload = json.loads(row["raw_model_output"])
        except (BenchmarkContractError, TypeError, json.JSONDecodeError) as error:
            row |= {"classification": "INVALID", "error": str(error)[:500]}
        else:
            classification, findings = evaluate(case["id"], payload, schema)
            row |= {
                "parsed_output": payload,
                "validated_output": payload if classification != "INVALID" else None,
                "classification": classification,
                "oracle_findings": findings,
            }
        _append(raw_path, row)
    return directory


def main() -> None:
    """Parse a new run ID; no selective case execution or retry option is exposed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--case-id", action="append", dest="case_ids")
    arguments = parser.parse_args()
    run(arguments.run_id, case_ids=set(arguments.case_ids) if arguments.case_ids else None)


if __name__ == "__main__":
    main()
