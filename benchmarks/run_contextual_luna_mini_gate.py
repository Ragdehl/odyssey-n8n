"""Run the bounded Luna/medium contextual-reasoner replacement gate."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from benchmarks.run_phase11b1_openai import (
    DEFAULT_CACHE,
    blind_request,
    estimated_cost,
    load_blocking_cases,
    load_calibration_examples,
    score_case,
    write_json_atomic,
)
from odyssey_core.contextual import ContextualProviderError, OpenAIContextualReasoner

MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "medium"
MAX_REQUESTS = 8
SELECTED_CASE_IDS = (
    "A02",  # resolved person, English
    "A09",  # resolved project, Spanish
    "A11",  # resolved store, French
    "A19",  # historical Luna clear false RESOLVED: mandatory regression sentinel
    "A22",  # ambiguous store, Spanish
    "A28",  # ambiguous project, French
    "A31",  # unresolved project, English
    "A34",  # unresolved person, Spanish
)


def select_cases(cases: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Select exactly the frozen eight-case replacement gate in deterministic order."""
    if len(SELECTED_CASE_IDS) != MAX_REQUESTS:
        raise ValueError("Contextual Luna mini-gate must contain exactly eight cases")
    by_id = {case["id"]: case for case in cases}
    missing = [case_id for case_id in SELECTED_CASE_IDS if case_id not in by_id]
    if missing:
        raise ValueError(f"Contextual Luna mini-gate cases are missing: {missing}")
    return tuple(by_id[case_id] for case_id in SELECTED_CASE_IDS)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the frozen safety/quality gate to compact per-case evidence."""
    clear_false_resolved = sum(bool(row["false_resolved"]) for row in rows)
    invalid = sum(not bool(row["schema_valid"]) for row in rows)
    correct = sum(bool(row["correct"]) for row in rows)
    a19 = next((row for row in rows if row["case_id"] == "A19"), None)
    a19_safe = bool(
        a19
        and a19["schema_valid"]
        and a19["outcome"] == "AMBIGUOUS"
        and a19["id"] is None
    )
    totals: Counter[str] = Counter()
    for row in rows:
        for key, value in row.items():
            if key.endswith("tokens") and isinstance(value, int):
                totals[key] += value
    gate = {
        "all_eight_completed": len(rows) == MAX_REQUESTS,
        "clear_false_resolved_zero": clear_false_resolved == 0,
        "invalid_zero": invalid == 0,
        "frozen_labels_eight_of_eight": correct == MAX_REQUESTS,
        "a19_ambiguous": a19_safe,
    }
    return {
        "cases": len(rows),
        "correct": correct,
        "clear_false_resolved": clear_false_resolved,
        "invalid": invalid,
        "a19_safe": a19_safe,
        "token_usage": dict(totals),
        "estimated_cost_usd": estimated_cost(MODEL, totals),
        "quality_gate": gate,
        "pass": all(gate.values()),
    }


def run_benchmark(output: Path, cache_dir: Path) -> None:
    """Run exactly eight Luna/medium calls with the frozen production prompt and no retries."""
    if output.exists():
        raise ValueError(f"Refusing to overwrite benchmark result: {output}")
    all_cases = load_blocking_cases(cache_dir)
    selected = select_cases(all_cases)
    examples = load_calibration_examples(cache_dir)
    reasoner = OpenAIContextualReasoner(
        MODEL,
        reasoning_effort=REASONING_EFFORT,
        examples=examples,
    )
    result: dict[str, Any] = {
        "phase": "20.2G",
        "synthetic_only": True,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "store": False,
        "prompt_variant": "frozen-few-shot",
        "calibration_examples": len(examples),
        "case_ids": list(SELECTED_CASE_IDS),
        "attempts": 0,
        "cases": [],
    }
    for index, case in enumerate(selected, start=1):
        started = time.perf_counter()
        try:
            output_data, usage = reasoner.resolve(blind_request(case))
        except ContextualProviderError:
            write_json_atomic(output, result)
            raise
        result["attempts"] += 1
        result["cases"].append(
            score_case(case, output_data, time.perf_counter() - started, usage)
        )
        write_json_atomic(output, result)
        print(f"{index}/{MAX_REQUESTS} {case['id']}", flush=True)
    result["summary"] = summarize(result["cases"])
    write_json_atomic(output, result)
    print(json.dumps(result["summary"], indent=2), flush=True)


def main() -> None:
    """Parse the explicitly authorized bounded Luna mini-gate command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--embedding-cache-dir", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    run_benchmark(args.output, args.embedding_cache_dir)


if __name__ == "__main__":
    main()
