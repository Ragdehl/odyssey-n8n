#!/usr/bin/env python3
"""Run append-only Phase 15.3 Sol/low evidence without corrective retries."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.phase15_3_capability_delegation.benchmark import (
    BENCHMARK_DIR,
    BenchmarkContractError,
    load_cases,
    production_request,
)
from benchmarks.phase15_3_capability_delegation.evaluate import evaluate

RESULTS_DIR = BENCHMARK_DIR / "results"


def _append(path: Path, row: dict[str, Any]) -> None:
    """Durably append one result after each provider attempt."""
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _completed_rows(raw_path: Path, expected_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Read valid append-only evidence and index its rows by completed case ID.

    Raises:
        BenchmarkContractError: If rows are malformed, duplicated, or outside the frozen case set.
    """
    try:
        rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkContractError("Existing benchmark evidence is incomplete") from error
    completed = [row.get("test_id") for row in rows]
    if (
        any(not isinstance(case_id, str) for case_id in completed)
        or len(completed) != len(set(completed))
        or not set(completed) <= expected_ids
    ):
        raise BenchmarkContractError("Existing benchmark rows are not a valid append-only record")
    return {row["test_id"]: row for row in rows}


def _validate_resume_contract(
    rows: Mapping[str, Mapping[str, Any]], cases: Sequence[Mapping[str, str]]
) -> None:
    """Require completed rows to match current frozen inputs and production digests.

    Raises:
        BenchmarkContractError: If a request, expectation, or production contract changed.
    """
    by_id = {case["id"]: case for case in cases}
    for case_id, row in rows.items():
        case = by_id[case_id]
        _, _, digests = production_request(dict(case))
        if (
            row.get("request") != case["request"]
            or row.get("expectation") != case["expect"]
            or row.get("identity_digests") != digests
        ):
            raise BenchmarkContractError(
                "Existing rows do not match the current benchmark contract"
            )


def run(
    run_id: str,
    client: Any | None = None,
    *,
    cases: list[dict[str, str]] | None = None,
    results_dir: Path | None = None,
    evaluator: Callable[[str, Any, dict[str, Any]], tuple[str, list[str]]] = evaluate,
    benchmark_version: str = "1.0.0",
) -> Path:
    """Call production Sol/low once per missing frozen case with no automatic retry.

    Args:
        run_id: Unique append-only evidence-directory name.
        client: Optional Responses-compatible client for deterministic tests.
        cases: Frozen cases; defaults to the full Phase 15.3 acceptance set.
        results_dir: Evidence root; defaults to the full benchmark results directory.
        evaluator: Strict semantic oracle for the supplied expectations.
        benchmark_version: Frozen evidence-contract version recorded in metadata.

    Returns:
        Evidence directory containing one row per completed unique case.

    Raises:
        BenchmarkContractError: If setup or existing evidence fails closed validation.
    """
    directory = (RESULTS_DIR if results_dir is None else results_dir) / run_id
    if client is None:
        try:
            from openai import OpenAI
            from openai import __version__ as sdk_version
        except ImportError as error:
            raise BenchmarkContractError("Install the OpenAI SDK before execution") from error
        client = OpenAI(max_retries=0)
    else:
        sdk_version = "test-client"
    cases = load_cases() if cases is None else cases
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_version": benchmark_version,
        "model": "gpt-5.6-sol",
        "reasoning_effort": "low",
        "store": False,
        "planned_calls": len(cases),
        "automatic_retries": False,
        "production_prompt": "render_request_planner_prompt",
        "production_structured_outputs": "request_plan_json_schema",
        "openai_sdk_version": sdk_version,
    }
    raw_path = directory / "raw_results.jsonl"
    expected_ids = {case["id"] for case in cases}
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".runner.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if (directory / "metadata.json").exists():
            try:
                existing = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise BenchmarkContractError("Existing benchmark metadata is incomplete") from error
            metadata["created_at"] = existing.get("created_at")
            if existing != metadata:
                raise BenchmarkContractError("Refusing to alter benchmark metadata")
            completed_rows = _completed_rows(raw_path, expected_ids)
            _validate_resume_contract(completed_rows, cases)
            completed = set(completed_rows)
        else:
            (directory / "metadata.json").write_text(
                json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
            )
            raw_path.touch()
            completed = set()
        if completed == expected_ids:
            return directory
        for case in cases:
            if case["id"] in completed:
                continue
            request, effective, digests = production_request(case)
            base = {
                "test_id": case["id"],
                "expectation": case["expect"],
                "request": case["request"],
                "current_context": effective["capabilities"]["selection"]["current_context"],
                "effective_schema": effective["schema"],
                "effective_capabilities": effective["capabilities"],
                "identity_digests": digests,
                "api_request": request,
            }
            started = time.perf_counter()
            try:
                response = client.responses.create(**request)
            except Exception as error:
                _append(
                    raw_path,
                    base
                    | {
                        "provider_success": False,
                        "classification": "INVALID",
                        "error": str(error)[:500],
                        "latency_seconds": time.perf_counter() - started,
                    },
                )
                completed.add(case["id"])
                continue
            raw = getattr(response, "output_text", None)
            row = base | {
                "provider_success": True,
                "raw_model_output": raw,
                "usage": response.usage.model_dump(mode="json")
                if getattr(response, "usage", None)
                else {},
                "latency_seconds": time.perf_counter() - started,
            }
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as error:
                row |= {"classification": "INVALID", "error": str(error)[:500]}
            else:
                status, findings = evaluator(case["expect"], payload, effective["schema"])
                row |= {
                    "parsed_output": payload,
                    "validated_output": payload if status != "INVALID" else None,
                    "classification": status,
                    "oracle_findings": findings,
                }
            _append(raw_path, row)
            completed.add(case["id"])
    return directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    run(parser.parse_args().run_id)
