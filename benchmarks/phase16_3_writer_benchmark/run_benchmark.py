"""Execute the frozen cost-first Phase 16.3 writer benchmark without semantic retries."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.phase16_3_writer_benchmark.benchmark import (
    BENCHMARK_DIR,
    load_cases,
    render_prompt,
    render_request,
    writer_json_schema,
)
from benchmarks.phase16_3_writer_benchmark.evaluate import evaluate_output

RESULTS_DIR = BENCHMARK_DIR / "results"
MODELS = {"luna": "gpt-5.6-luna", "terra": "gpt-5.6-terra", "sol": "gpt-5.6-sol"}


def run(run_id: str, stage: str, *, resume: bool = False, client: Any | None = None) -> Path:
    """Run one frozen staged provider pass and append one raw record per effective call.

    Args:
        run_id: New, filesystem-safe evidence directory name.
        stage: `luna`, `terra`, or `sol`; later stages select only material failures.
        resume: Continue an interrupted append-only run without repeating persisted calls.
        client: Optional compatible Responses client for deterministic tests.

    Returns:
        Newly created evidence directory.

    Raises:
        ValueError: If the stage is invalid, input evidence is absent, or run state is inconsistent.
        RuntimeError: If a live call is requested without SDK/API configuration.
    """
    if stage not in MODELS or not run_id or Path(run_id).name != run_id:
        raise ValueError("Invalid writer benchmark stage or run ID")
    directory = RESULTS_DIR / run_id
    if directory.exists() and not resume:
        raise ValueError("Refusing to alter existing benchmark evidence")
    cases = _stage_cases(stage)
    if client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for a live writer benchmark")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("Install the OpenAI SDK before executing the benchmark") from error
        client = OpenAI()
    completed: set[tuple[str, str]] = set()
    if resume:
        metadata_path = directory / "metadata.json"
        raw_path = directory / "raw_results.jsonl"
        if not metadata_path.exists() or not raw_path.exists():
            raise ValueError("Resume requires an existing append-only writer run")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("stage") != stage or metadata.get("model") != MODELS[stage]:
            raise ValueError("Resume stage does not match existing writer evidence")
        completed = set()
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # A supervisor can terminate a process between write() and fsync(). Preserve the
                # damaged append-only fragment as harness evidence, but do not mistake it for a
                # completed call when resuming.
                continue
            if row.get("case_id") and row.get("context_strategy"):
                completed.add((row["case_id"], row["context_strategy"]))
    else:
        directory.mkdir(parents=True)
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_version": "1.0.0",
        "stage": stage,
        "model": MODELS[stage],
        "reasoning_effort": "low",
        "store": False,
        "semantic_retries": False,
        "planned_calls": len(cases),
        "context_strategies": ["FULL_NOTE"],
    }
    if not resume:
        (directory / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
    with (directory / "raw_results.jsonl").open("a" if resume else "x", encoding="utf-8") as stream:
        for case, strategy, context in _calls(cases, stage):
            if (case["id"], strategy) in completed:
                continue
            response = client.responses.create(
                model=MODELS[stage],
                reasoning={"effort": "low"},
                store=False,
                input=[
                    {"role": "system", "content": render_prompt()},
                    {"role": "user", "content": render_request(case, context=context)},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_bounded_writer",
                        "strict": True,
                        "schema": writer_json_schema(),
                    }
                },
            )
            raw = getattr(response, "output_text", None)
            try:
                parsed = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                parsed, status, findings = (
                    None,
                    "CRITICAL",
                    [{"severity": "CRITICAL", "code": "invalid_json"}],
                )
            else:
                status, findings = evaluate_output(parsed, case, context=context)
            record = {
                "case_id": case["id"],
                "context_strategy": strategy,
                "model": MODELS[stage],
                "current_note": case.get("current_body"),
                "facts": case["facts"],
                "expected": case.get("expected_families", ["CREATE_BODY"]),
                "raw_output": raw,
                "parsed_operations": parsed,
                "deterministic_status": status,
                "deterministic_checks": findings,
                "semantic_status": "PENDING_HUMAN_REVIEW",
                "findings": [],
                "usage": _usage(response),
                "estimated_cost_usd": _cost(_usage(response), MODELS[stage]),
            }
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return directory


def _stage_cases(stage: str) -> list[dict[str, Any]]:
    """Select all Luna cases or only frozen material failures from the prior stage."""
    if stage == "luna":
        return load_cases()
    prior = "luna" if stage == "terra" else "terra"
    prior_runs = sorted(RESULTS_DIR.glob("*/metadata.json"), key=lambda path: path.stat().st_mtime)
    matches = [
        path.parent
        for path in prior_runs
        if json.loads(path.read_text(encoding="utf-8")).get("stage") == prior
    ]
    if not matches:
        raise ValueError(f"{stage} requires completed {prior} evidence")
    review_path = matches[-1] / "review.jsonl"
    if not review_path.exists():
        raise ValueError(f"{stage} requires human-reviewed {prior} evidence")
    failed_ids = set()
    for line in review_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if (
            record.get("semantic_status") == "MATERIAL_FAIL"
            and record.get("context_strategy") == "FULL_NOTE"
        ):
            failed_ids.add(record["case_id"])
    if not failed_ids:
        raise ValueError(f"No {prior} material failures exist; do not call {stage}")
    return [case for case in load_cases() if case["id"] in failed_ids]


def _calls(cases: list[dict[str, Any]], stage: str):
    """Yield effective calls, adding Luna-only frozen reduced-context probes."""
    for case in cases:
        yield case, "FULL_NOTE", None
    if stage == "luna":
        probes = [case for case in cases if case.get("reduced_context")][:12]
        for case in probes:
            yield case, "REDUCED_CONTEXT", case["reduced_context"]


def _usage(response: Any) -> dict[str, int]:
    """Normalize Responses token counters without retaining provider response internals."""
    usage = getattr(response, "usage", None)
    getter = (
        (lambda key, default=0: getattr(usage, key, default))
        if usage is not None
        else (lambda key, default=0: default)
    )
    details = getter("input_tokens_details", None)
    return {
        "input_tokens": int(getter("input_tokens")),
        "cached_input_tokens": int(getattr(details, "cached_tokens", 0) if details else 0),
        "output_tokens": int(getter("output_tokens")),
        "reasoning_tokens": int(
            getattr(getter("output_tokens_details", None), "reasoning_tokens", 0) or 0
        ),
    }


def _cost(usage: dict[str, int], model: str) -> float:
    """Estimate standard short-context USD cost from the frozen pricing artifact."""
    prices = json.loads((BENCHMARK_DIR / "pricing.json").read_text(encoding="utf-8"))["models"][
        model
    ]
    uncached = usage["input_tokens"] - usage["cached_input_tokens"]
    return round(
        (
            uncached * prices["input"]
            + usage["cached_input_tokens"] * prices["cached_input"]
            + usage["output_tokens"] * prices["output"]
        )
        / 1_000_000,
        8,
    )


def main() -> None:
    """Parse an explicit one-stage benchmark invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage", required=True, choices=sorted(MODELS))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.run_id, args.stage, resume=args.resume)


if __name__ == "__main__":
    main()
