#!/usr/bin/env python3
"""Run focused Phase 15.2 Sol/low evidence with one call per case and no retries."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.phase15_2_selection_anchors.benchmark import (
    BENCHMARK_DIR,
    BenchmarkContractError,
    load_cases,
    production_request,
)
from benchmarks.phase15_2_selection_anchors.evaluate import evaluate

RESULTS_DIR = BENCHMARK_DIR / "results"


def _append(path: Path, row: dict[str, Any]) -> None:
    """Durably append one complete evidence row after a provider attempt."""
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _usage(response: Any) -> dict[str, Any]:
    """Extract available provider usage without assuming every optional field exists."""
    usage = getattr(response, "usage", None)
    return usage.model_dump(mode="json") if usage is not None else {}


def run(run_id: str, client: Any | None = None) -> Path:
    """Run every frozen Phase 15.2 case exactly once into a new append-only directory.

    Args:
        run_id: New immutable evidence-directory name.
        client: Optional Responses-compatible client used by deterministic harness tests.

    Returns:
        The newly created evidence directory.

    Raises:
        BenchmarkContractError: If evidence already exists, inputs are invalid, or SDK setup fails.
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
    cases = load_cases()
    raw_path = directory / "raw_results.jsonl"
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_version": "1.0.0",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "low",
        "store": False,
        "planned_calls": len(cases),
        "automatic_retries": False,
        "production_prompt": "render_request_planner_prompt",
        "production_structured_outputs": "request_plan_json_schema",
        "openai_sdk_version": sdk_version,
    }
    if directory.exists():
        try:
            existing_metadata = json.loads(
                (directory / "metadata.json").read_text(encoding="utf-8")
            )
            rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
        except (OSError, json.JSONDecodeError) as error:
            raise BenchmarkContractError("Existing benchmark evidence is incomplete") from error
        metadata["created_at"] = existing_metadata.get("created_at")
        if existing_metadata != metadata:
            raise BenchmarkContractError("Refusing to alter benchmark metadata")
        completed = [row.get("test_id") for row in rows]
        expected_ids = [case["id"] for case in cases]
        if len(completed) != len(set(completed)) or not set(completed) <= set(expected_ids):
            raise BenchmarkContractError(
                "Existing benchmark rows are not a valid append-only record"
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
        api_request, effective, digests = production_request(case)
        started = time.perf_counter()
        base = {
            "test_id": case["id"],
            "expectation": case["expect"],
            "request": case["request"],
            "current_context": effective["capabilities"]["selection"]["current_context"],
            "effective_schema": effective["schema"],
            "effective_capabilities": effective["capabilities"],
            "identity_digests": digests,
            "api_request": api_request,
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
        raw_output = getattr(response, "output_text", None)
        row = base | {
            "provider_success": True,
            "latency_seconds": time.perf_counter() - started,
            "usage": _usage(response),
            "raw_model_output": raw_output,
        }
        try:
            payload = json.loads(raw_output)
        except (TypeError, json.JSONDecodeError) as error:
            row |= {"classification": "INVALID", "error": str(error)[:500]}
        else:
            classification, findings = evaluate(case["expect"], payload, effective["schema"])
            row |= {
                "parsed_output": payload,
                "validated_output": payload if classification != "INVALID" else None,
                "classification": classification,
                "oracle_findings": findings,
            }
        _append(raw_path, row)
    return directory


def main() -> None:
    """Run a fresh named benchmark evidence set without case selection or retries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    arguments = parser.parse_args()
    run(arguments.run_id)


if __name__ == "__main__":
    main()
