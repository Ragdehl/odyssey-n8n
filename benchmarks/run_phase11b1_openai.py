"""Run the cost-gated Phase 11B.1 OpenAI contextual-resolution benchmark."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

from odyssey_core.contextual import (
    ContextualCandidate,
    ContextualProviderError,
    ContextualResolutionDecision,
    ContextualResolutionError,
    ContextualResolutionExample,
    ContextualResolutionRequest,
    OpenAIContextualReasoner,
    validate_contextual_decision,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PHASE11A_CASES = REPOSITORY_ROOT / "benchmarks/phase11a_contextual_resolution_cases.json"
STRONG_EVIDENCE = REPOSITORY_ROOT / "benchmarks/phase11a_strong_reasoner_cases.json"
DEFAULT_CACHE = Path("/data/odyssey/runtime/phase11a-benchmark/embedding-cache")
E13_CASE_ID = "en-toulouse-supermarket"
MODEL_PRICES_PER_MILLION = {
    # Historical benchmark inputs: OpenAI API prices effective 2026-07-30.
    # Cache writes cost 1.25x uncached input; do not treat these as live pricing.
    "gpt-5.6-luna": {"input": 0.20, "cached_input": 0.02, "output": 1.20},
    "gpt-5.6-terra": {"input": 2.00, "cached_input": 0.20, "output": 12.00},
    "gpt-5.6-sol": {"input": 5.00, "cached_input": 0.50, "output": 30.00},
}


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Replace a compact benchmark result without exposing a partial JSON document.

    Args:
        path: Final version-controlled result path.
        payload: JSON-compatible benchmark state.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_blocking_cases(cache_dir: Path) -> list[dict[str, Any]]:
    """Load only the 90 frozen synthetic strong-reasoner cases and Phase 10 candidates.

    Args:
        cache_dir: Existing local Phase 10 embedding-model cache.

    Returns:
        Phase 11A.2 and Phase 11A.3 cases with current Phase 10 Top-5 evidence.

    Raises:
        ValueError: If the frozen evidence no longer describes exactly 90 unique cases.
    """
    # Keep the optional Phase 10 runtime out of ordinary imports and Core-only CI tests.
    from benchmarks.run_phase11a_contextual_resolution import build_phase10_candidates

    base = json.loads(PHASE11A_CASES.read_text(encoding="utf-8"))
    evidence = json.loads(STRONG_EVIDENCE.read_text(encoding="utf-8"))
    phase11a2 = [
        case
        for case in base["cases"]
        if case["split"] == "evaluation" and not case.get("non_blocking", False)
    ]
    phase11a3 = [
        {
            "id": case["case_id"],
            "split": "evaluation",
            "language": "multilingual",
            "category": "phase11a3_adversarial",
            "reference": case["reference"],
            "context": case["context"],
            "type": case["entity_type"],
            "expected": case["expected"],
            "expected_id": case["expected_id"],
        }
        for case in evidence["phase11a3"]["cases"]
    ]
    combined = phase11a2 + phase11a3
    if len(combined) != 90 or len({case["id"] for case in combined}) != 90:
        raise ValueError("Phase 11B.1 requires exactly 90 unique frozen blocking cases")
    ranked = build_phase10_candidates(
        {"notes": base["notes"], "cases": combined}, cache_dir=cache_dir
    )
    missing = [
        case["id"]
        for case in ranked
        if case["expected"] == "RESOLVED"
        and case["expected_id"] not in {candidate["id"] for candidate in case["candidates"]}
    ]
    if missing:
        raise ValueError(f"Phase 10 omitted expected candidates for: {', '.join(missing)}")
    return ranked


def load_calibration_examples(cache_dir: Path) -> tuple[ContextualResolutionExample, ...]:
    """Load the ten pre-existing Phase 11A examples as compact labelled prompt turns.

    Args:
        cache_dir: Existing local Phase 10 embedding-model cache.

    Returns:
        Ten examples in their frozen dataset order, with no case IDs or scoring metadata.

    Raises:
        ValueError: If the frozen source no longer contains exactly ten valid examples.
    """
    from benchmarks.run_phase11a_contextual_resolution import build_phase10_candidates

    base = json.loads(PHASE11A_CASES.read_text(encoding="utf-8"))
    calibration = [case for case in base["cases"] if case["split"] == "calibration"]
    if len(calibration) != 10:
        raise ValueError("Phase 11B.1b requires exactly ten frozen calibration examples")
    ranked = build_phase10_candidates(
        {"notes": base["notes"], "cases": calibration}, cache_dir=cache_dir
    )
    examples = []
    for case in ranked:
        identity = case.get("expected_id") if case["expected"] == "RESOLVED" else None
        request = blind_request(case)
        decision = ContextualResolutionDecision(outcome=case["expected"], id=identity)
        validate_contextual_decision(
            {"outcome": decision.outcome, "id": decision.id},
            {candidate.id for candidate in request.candidates},
        )
        examples.append(ContextualResolutionExample(request=request, decision=decision))
    return tuple(examples)


def blind_request(case: dict[str, Any]) -> ContextualResolutionRequest:
    """Project one labelled benchmark row into the label-free provider contract.

    Args:
        case: Frozen case augmented with Phase 10 candidate evidence.

    Returns:
        Request containing no case ID, expected answer, labels, scores, or previous answers.
    """
    return ContextualResolutionRequest(
        reference=case["reference"],
        context=case["context"],
        entity_type=case["type"],
        candidates=tuple(
            ContextualCandidate(id=candidate["id"], evidence=candidate["text"])
            for candidate in case["candidates"]
        ),
    )


def score_case(
    case: dict[str, Any], output: object, latency_seconds: float, usage: dict[str, Any]
) -> dict[str, Any]:
    """Validate and score one response while preserving fail-closed invalid output.

    Args:
        case: Labelled benchmark case kept outside the provider request.
        output: Parsed provider output.
        latency_seconds: End-to-end request latency.
        usage: Compact provider token counters.

    Returns:
        Compact per-case result with correctness and safety evidence.
    """
    candidate_ids = {candidate["id"] for candidate in case["candidates"]}
    try:
        decision = validate_contextual_decision(output, candidate_ids)
    except ContextualResolutionError:
        return {
            "case_id": case["id"],
            "outcome": None,
            "id": None,
            "schema_valid": False,
            "correct": False,
            "false_resolved": False,
            "label_disputed": case["id"] == E13_CASE_ID,
            "latency_seconds": round(latency_seconds, 6),
            **usage,
        }
    correct = decision.outcome == case["expected"] and (
        decision.outcome != "RESOLVED" or decision.id == case.get("expected_id")
    )
    false_resolved = decision.outcome == "RESOLVED" and not correct
    return {
        "case_id": case["id"],
        "outcome": decision.outcome,
        "id": decision.id,
        "schema_valid": True,
        "correct": correct,
        "false_resolved": false_resolved,
        "label_disputed": case["id"] == E13_CASE_ID,
        "latency_seconds": round(latency_seconds, 6),
        **usage,
    }


def percentile(values: list[float], proportion: float) -> float:
    """Return a nearest-rank percentile for a non-empty latency sample."""
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * proportion + 0.999999) - 1))
    return ordered[index]


def estimated_cost(model: str, totals: Counter[str]) -> float:
    """Estimate standard API spend from actual token counters and dated list prices."""
    prices = MODEL_PRICES_PER_MILLION[model]
    cached = totals["cached_input_tokens"]
    cache_write = totals["cache_write_tokens"]
    ordinary = max(0, totals["input_tokens"] - cached - cache_write)
    dollars = (
        ordinary * prices["input"]
        + cached * prices["cached_input"]
        + cache_write * prices["input"] * 1.25
        + totals["output_tokens"] * prices["output"]
    ) / 1_000_000
    return round(dollars, 6)


def summarize(model: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the frozen quality gate, latency, coverage, and actual token usage."""
    valid = [row for row in rows if row["schema_valid"]]
    returned_counts = Counter(row["outcome"] for row in valid)
    correct_counts = Counter(row["outcome"] for row in valid if row["correct"])
    clear_false_resolved = sum(row["false_resolved"] and not row["label_disputed"] for row in rows)
    disputed_false_resolved = sum(row["false_resolved"] and row["label_disputed"] for row in rows)
    frozen_false_resolved = clear_false_resolved + disputed_false_resolved
    latencies = [row["latency_seconds"] for row in rows]
    token_fields = (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "output_tokens",
        "reasoning_tokens",
    )
    totals = Counter({field: sum(row[field] for row in rows) for field in token_fields})
    correct = sum(row["correct"] for row in rows)
    resolved_returned = returned_counts["RESOLVED"]
    correct_resolved = correct_counts["RESOLVED"]
    gate = {
        "clear_false_resolved_zero": clear_false_resolved == 0,
        "invalid_zero": len(valid) == 90,
        "correct_resolved_at_least_33_of_35": correct_resolved >= 33,
        "overall_accuracy_at_least_95_percent": correct / 90 >= 0.95,
    }
    return {
        "cases": len(rows),
        "correct_resolved": correct_resolved,
        "correct_ambiguous": correct_counts["AMBIGUOUS"],
        "correct_unresolved": correct_counts["UNRESOLVED"],
        "clear_false_resolved": clear_false_resolved,
        "disputed_e13_false_resolved": disputed_false_resolved,
        "frozen_label_false_resolved": frozen_false_resolved,
        "overall_accuracy": round(correct / 90, 6),
        "accuracy_when_resolved": round(correct_resolved / resolved_returned, 6)
        if resolved_returned
        else None,
        "coverage": round(resolved_returned / 90, 6),
        "invalid_or_malformed": 90 - len(valid),
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 6),
            "median": round(statistics.median(latencies), 6),
            "p95": round(percentile(latencies, 0.95), 6),
        },
        "token_usage": dict(totals),
        "estimated_cost_usd": estimated_cost(model, totals),
        "quality_gate": gate,
        "provisional_pass": all(gate.values()),
    }


def main() -> None:
    """Run exactly one explicitly selected model/run over all 90 frozen cases."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=tuple(MODEL_PRICES_PER_MILLION), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--prompt-variant", choices=("zero-shot", "frozen-few-shot"), default="zero-shot"
    )
    parser.add_argument("--embedding-cache-dir", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing benchmark run: {args.output}")

    cases = load_blocking_cases(args.embedding_cache_dir)
    examples = (
        load_calibration_examples(args.embedding_cache_dir)
        if args.prompt_variant == "frozen-few-shot"
        else ()
    )
    reasoner = OpenAIContextualReasoner(args.model, reasoning_effort="medium", examples=examples)
    result: dict[str, Any] = {
        "phase": "11B.1b" if examples else "11B.1a",
        "synthetic_only": True,
        "model": args.model,
        "reasoning_effort": "medium",
        "store": False,
        "prompt_variant": args.prompt_variant,
        "calibration_examples": len(examples),
        "run_id": args.run_id,
        "attempts": 0,
        "transient_retries": [],
        "cases": [],
    }
    for index, case in enumerate(cases, start=1):
        started = time.perf_counter()
        try:
            output, usage = reasoner.resolve(blind_request(case))
        except ContextualProviderError:
            # Do not silently turn provider failures into model-quality evidence or spend retries.
            write_json_atomic(args.output, result)
            raise
        latency = time.perf_counter() - started
        result["attempts"] += 1
        result["cases"].append(score_case(case, output, latency, usage))
        write_json_atomic(args.output, result)
        print(f"{index}/90 {case['id']}", flush=True)
    result["summary"] = summarize(args.model, result["cases"])
    write_json_atomic(args.output, result)
    print(json.dumps(result["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
