#!/usr/bin/env python3
"""Run independent, resumable OpenAI requests for the Phase 14 benchmark."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.phase14_retrieval_plan.benchmark import (  # noqa: E402
    BENCHMARK_DIR,
    CASES_PATH,
    ORACLE_PATH,
    PRICING_PATH,
    PROMPT_PATH,
    REPOSITORY_ROOT,
    SCHEMA_CONTRACT_PATH,
    BenchmarkContractError,
    assert_schema_alignment,
    build_api_payload,
    finite_latency,
    load_cases,
    load_json,
    sanitize_error,
    sha256_file,
    validate_output,
)

RESULTS_DIR = BENCHMARK_DIR / "results"
DEFAULT_CONFIGURATIONS = (
    ("gpt-5.6-luna", "none"),
    ("gpt-5.6-luna", "low"),
    ("gpt-5.6-terra", "low"),
    ("gpt-5.6-sol", "low"),
)


def parse_configuration(value: str) -> tuple[str, str]:
    """Parse one exact `model:effort` CLI configuration.

    Args:
        value: CLI value containing one colon separator.

    Returns:
        Exact model ID and reasoning effort.

    Raises:
        argparse.ArgumentTypeError: If the configuration is unsupported or malformed.
    """
    try:
        model, effort = value.rsplit(":", 1)
    except ValueError as error:
        raise argparse.ArgumentTypeError("configuration must be MODEL:EFFORT") from error
    pricing = load_json(PRICING_PATH)
    if model not in pricing["models"]:
        raise argparse.ArgumentTypeError(f"model is not in the approved benchmark matrix: {model}")
    if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise argparse.ArgumentTypeError(f"unsupported reasoning effort: {effort}")
    return model, effort


def git_sha() -> str:
    """Return the exact repository commit recorded for a benchmark run."""
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write one benchmark metadata JSON document.

    Args:
        path: Final artifact path.
        payload: JSON-compatible metadata.
    """
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Durably append one completed request record for resumability.

    Args:
        path: Raw JSONL result path.
        payload: One request result containing no secret material.
    """
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Load existing resumable rows, rejecting partial or malformed history."""
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise BenchmarkContractError(
                f"Malformed raw result at {path}:{line_number}; preserve and repair before resuming"
            ) from error
        if not isinstance(row, dict):
            raise BenchmarkContractError(f"Non-object raw result at {path}:{line_number}")
        rows.append(row)
    return rows


def request_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    """Return the logical resumability key for one model/case repetition."""
    return row["model"], row["reasoning_effort"], row["test_id"], row["repetition"]


def usage_from_response(raw: dict[str, Any]) -> dict[str, int]:
    """Normalize all exposed Responses API token counters.

    Args:
        raw: JSON-compatible official SDK response dump.

    Returns:
        Input, cached input, cache-write, output, and reasoning token counts.
    """
    usage = raw.get("usage") or {}
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    return {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "cached_input_tokens": int(input_details.get("cached_tokens", 0)),
        "cache_write_tokens": int(input_details.get("cache_write_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "reasoning_tokens": int(output_details.get("reasoning_tokens", 0)),
    }


def create_metadata(
    run_id: str, configurations: list[tuple[str, str]], sdk_version: str
) -> dict[str, Any]:
    """Build immutable experiment identity before the first provider request."""
    cases_document = load_json(CASES_PATH)
    oracle_document = load_json(ORACLE_PATH)
    return {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha(),
        "benchmark_version": cases_document["benchmark_version"],
        "oracle_version": oracle_document["oracle_version"],
        "fixed_context": cases_document["fixed_context"],
        "configurations": [
            {"model": model, "reasoning_effort": effort} for model, effort in configurations
        ],
        "openai_sdk_version": sdk_version,
        "api": "OpenAI Responses API",
        "structured_outputs": True,
        "store": False,
        "independent_request_per_case": True,
        "prompt_cache_key": "odyssey-phase14-retrieval-plan-v1",
        "artifact_sha256": {
            "prompt.md": sha256_file(PROMPT_PATH),
            "cases.json": sha256_file(CASES_PATH),
            "oracle.json": sha256_file(ORACLE_PATH),
            "schema_contract.json": sha256_file(SCHEMA_CONTRACT_PATH),
            "pricing.json": sha256_file(PRICING_PATH),
        },
        "pricing": load_json(PRICING_PATH),
    }


def prepare_run(
    run_id: str, configurations: list[tuple[str, str]], sdk_version: str
) -> tuple[Path, dict[str, Any]]:
    """Create a new run directory or validate a compatible resumable run.

    Raises:
        BenchmarkContractError: If a historical run would be overwritten or changed.
    """
    run_dir = RESULTS_DIR / run_id
    metadata_path = run_dir / "metadata.json"
    if metadata_path.exists():
        metadata = load_json(metadata_path)
        known = {(item["model"], item["reasoning_effort"]) for item in metadata["configurations"]}
        if not set(configurations) <= known:
            raise BenchmarkContractError(
                "Existing run metadata does not contain every requested configuration"
            )
        current_hashes = {
            "prompt.md": sha256_file(PROMPT_PATH),
            "cases.json": sha256_file(CASES_PATH),
            "oracle.json": sha256_file(ORACLE_PATH),
            "schema_contract.json": sha256_file(SCHEMA_CONTRACT_PATH),
            "pricing.json": sha256_file(PRICING_PATH),
        }
        if metadata["artifact_sha256"] != current_hashes:
            raise BenchmarkContractError("Benchmark inputs changed; start a new run ID")
        return run_dir, metadata
    if run_dir.exists() and any(run_dir.iterdir()):
        raise BenchmarkContractError(
            "Refusing to overwrite a non-empty historical result directory"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = create_metadata(run_id, configurations, sdk_version)
    write_json_atomic(metadata_path, metadata)
    return run_dir, metadata


def execute_request(
    client: Any,
    *,
    model: str,
    effort: str,
    case: dict[str, str],
    repetition: int,
    retry_index: int,
    prompt: str,
) -> dict[str, Any]:
    """Execute and locally validate one independent benchmark request.

    Provider failures are returned explicitly and are not converted into model-quality failures.
    """
    started = time.perf_counter()
    base = {
        "record_type": "request",
        "test_id": case["id"],
        "request": case["request"],
        "model": model,
        "reasoning_effort": effort,
        "repetition": repetition,
        "retry_index": retry_index,
        "requested_at": datetime.now(UTC).isoformat(),
    }
    try:
        payload = build_api_payload(model, effort, prompt, case["request"])
        response = client.responses.create(**payload)
        latency = finite_latency(time.perf_counter() - started)
        raw = response.model_dump(mode="json")
        output_text = response.output_text
        parsed = json.loads(output_text)
        validate_output(parsed)
        if raw.get("status") != "completed":
            raise BenchmarkContractError("OpenAI response did not complete")
        return {
            **base,
            "success": True,
            "latency_seconds": latency,
            "response_id": raw.get("id"),
            "parsed_output": parsed,
            "raw_output_text": output_text,
            "usage": usage_from_response(raw),
            "api_error": None,
            "raw_response": raw,
        }
    except Exception as error:  # Provider and SDK exceptions must remain visible in raw results.
        return {
            **base,
            "success": False,
            "latency_seconds": finite_latency(time.perf_counter() - started),
            "response_id": None,
            "parsed_output": None,
            "raw_output_text": None,
            "usage": None,
            "api_error": sanitize_error(error),
            "raw_response": None,
        }


def parser() -> argparse.ArgumentParser:
    """Build the documented benchmark runner CLI."""
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument(
        "--configuration",
        action="append",
        type=parse_configuration,
        help="MODEL:EFFORT; repeat for each candidate (defaults to the cost-conscious matrix)",
    )
    value.add_argument(
        "--run-id", help="Immutable result directory name; defaults to UTC timestamp"
    )
    value.add_argument("--case-id", action="append", help="Run only this case; repeat as needed")
    value.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="Target repetitions per selected case/configuration; existing successful rows are skipped",
    )
    value.add_argument(
        "--retry-failures",
        action="store_true",
        help="Retry logical requests whose latest stored row is an API/local-validation failure",
    )
    value.add_argument(
        "--timeout", type=float, default=120.0, help="Per-request timeout in seconds"
    )
    return value


def main() -> int:
    """Run the requested staged matrix without leaking credentials or overwriting history."""
    args = parser().parse_args()
    if args.repetitions < 1:
        raise BenchmarkContractError("--repetitions must be positive")
    if not os.environ.get("OPENAI_API_KEY"):
        raise BenchmarkContractError("OPENAI_API_KEY is required for paid benchmark execution")
    assert_schema_alignment()
    load_oracle = load_json(ORACLE_PATH)
    if load_oracle.get("locked_before_model_calls") is not True:
        raise BenchmarkContractError("Oracle must be explicitly locked before API execution")
    try:
        import openai
        from openai import OpenAI
    except ImportError as error:
        raise BenchmarkContractError(
            "Official OpenAI SDK is missing; install benchmarks/phase14_retrieval_plan/requirements.txt"
        ) from error

    configurations = list(dict.fromkeys(args.configuration or DEFAULT_CONFIGURATIONS))
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir, _ = prepare_run(run_id, configurations, openai.__version__)
    raw_path = run_dir / "raw_results.jsonl"
    existing = [
        row for row in load_rows(raw_path) if row.get("record_type", "request") == "request"
    ]
    latest: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for row in existing:
        latest[request_key(row)] = row

    cases = load_cases()
    if args.case_id:
        requested_ids = set(args.case_id)
        unknown = requested_ids - {case["id"] for case in cases}
        if unknown:
            raise BenchmarkContractError(f"Unknown benchmark case IDs: {sorted(unknown)}")
        cases = [case for case in cases if case["id"] in requested_ids]
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=args.timeout, max_retries=0)
    completed = 0
    skipped = 0
    for model, effort in configurations:
        for case in cases:
            for repetition in range(1, args.repetitions + 1):
                key = (model, effort, case["id"], repetition)
                previous = latest.get(key)
                if previous is not None and (previous["success"] or not args.retry_failures):
                    skipped += 1
                    continue
                retry_index = 0 if previous is None else int(previous["retry_index"]) + 1
                row = execute_request(
                    client,
                    model=model,
                    effort=effort,
                    case=case,
                    repetition=repetition,
                    retry_index=retry_index,
                    prompt=prompt,
                )
                append_jsonl(raw_path, row)
                latest[key] = row
                completed += 1
                status = "ok" if row["success"] else "error"
                print(f"{model}:{effort} {case['id']} r{repetition} {status}", flush=True)
    print(f"run_id={run_id} completed={completed} skipped={skipped}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BenchmarkContractError as error:
        print(f"benchmark error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
