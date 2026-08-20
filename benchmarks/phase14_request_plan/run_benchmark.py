#!/usr/bin/env python3
"""Run the approved future Phase 14 v2 experiment; never invoked during design."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
    sanitize_error,
    sha256_file,
    validate_output,
)
from benchmarks.phase14_request_plan.evaluate import evaluate_plan  # noqa: E402

RESULTS_DIR = BENCHMARK_DIR / "results"
DEFAULT_CONFIGURATIONS = (("gpt-5.6-terra", "low"),)


def _append(path: Path, row: dict[str, Any]) -> None:
    """Append one completed, non-secret request record and fsync it for resumability."""
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _metadata(configurations: list[tuple[str, str]], sdk_version: str) -> dict[str, Any]:
    """Freeze all versioned inputs before any future provider request."""
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_version": load_json(CASES_PATH)["benchmark_version"],
        "oracle_version": load_json(ORACLE_PATH)["oracle_version"],
        "configurations": [{"model": m, "reasoning_effort": e} for m, e in configurations],
        "openai_sdk_version": sdk_version,
        "api": "OpenAI Responses API",
        "store": False,
        "structured_outputs": True,
        "independent_request_per_case": True,
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


def run(run_id: str, configurations: list[tuple[str, str]]) -> None:
    """Execute one new or resumable append-only benchmark run after explicit approval.

    Args:
        run_id: Unique immutable evidence directory name.
        configurations: Approved model/effort configurations to execute.
    """
    assert_schema_alignment()
    try:
        from openai import OpenAI
        from openai import __version__ as sdk_version
    except ImportError as error:
        raise BenchmarkContractError("Install benchmark requirements before running") from error
    directory = RESULTS_DIR / run_id
    directory.mkdir(parents=True, exist_ok=True)
    metadata_path, raw_path = directory / "metadata.json", directory / "raw_results.jsonl"
    metadata = _metadata(configurations, sdk_version)
    if metadata_path.exists():
        existing_metadata = load_json(metadata_path)
        expected_metadata = dict(metadata)
        expected_metadata["created_at"] = existing_metadata.get("created_at")
        if existing_metadata != expected_metadata:
            raise BenchmarkContractError("Refusing to alter historical run metadata")
    else:
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    completed = (
        {
            (row["model"], row["reasoning_effort"], row["test_id"])
            for row in (
                json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()
            )
        }
        if raw_path.exists()
        else set()
    )
    client, prompt, oracle, pricing = (
        OpenAI(),
        PROMPT_PATH.read_text(encoding="utf-8"),
        load_json(ORACLE_PATH),
        load_json(PRICING_PATH),
    )
    indexed = {row["id"]: row for row in oracle["cases"]}
    for model, effort in configurations:
        for case in load_cases():
            if (model, effort, case["id"]) in completed:
                continue
            started = time.perf_counter()
            try:
                response = client.responses.create(
                    **build_api_payload(model, effort, prompt, case["request"])
                )
                payload = json.loads(response.output_text)
                validate_output(payload)
                usage = response.usage.model_dump(mode="json") if response.usage else {}
                counters = {
                    "input_tokens": usage.get("input_tokens", 0),
                    "cached_input_tokens": usage.get("input_tokens_details", {}).get(
                        "cached_tokens", 0
                    ),
                    "cache_write_tokens": usage.get("input_tokens_details", {}).get(
                        "cache_write_tokens", 0
                    ),
                    "output_tokens": usage.get("output_tokens", 0),
                    "reasoning_tokens": usage.get("output_tokens_details", {}).get(
                        "reasoning_tokens", 0
                    ),
                }
                status, findings = evaluate_plan(payload, indexed[case["id"]])
                row = {
                    "record_type": "request",
                    "test_id": case["id"],
                    "request": case["request"],
                    "model": model,
                    "reasoning_effort": effort,
                    "success": True,
                    "latency_seconds": finite_latency(time.perf_counter() - started),
                    "usage": counters,
                    "estimated_cost_usd": estimated_cost(model, counters, pricing),
                    "parsed_output": payload,
                    "status": status,
                    "findings": findings,
                }
            except Exception as error:
                row = {
                    "record_type": "request",
                    "test_id": case["id"],
                    "request": case["request"],
                    "model": model,
                    "reasoning_effort": effort,
                    "success": False,
                    "latency_seconds": finite_latency(time.perf_counter() - started),
                    "api_error": sanitize_error(error),
                }
            _append(raw_path, row)


def main() -> None:
    """Parse explicit future-run arguments and start no unapproved configurations."""
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--include-sol", action="store_true")
    args = parser.parse_args()
    configurations = list(DEFAULT_CONFIGURATIONS)
    if args.include_sol:
        configurations.append(("gpt-5.6-sol", "low"))
    run(args.run_id, configurations)


if __name__ == "__main__":
    main()
