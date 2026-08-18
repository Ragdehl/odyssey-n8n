"""Run the bounded Phase 11B.2 production-evidence Sol parity checkpoint."""

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
    ContextualResolutionExample,
    ContextualResolutionRequest,
    OpenAIContextualReasoner,
    validate_contextual_decision,
)
from odyssey_core.notes import Note, validate_note
from odyssey_core.resolution import build_provider_evidence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PHASE11A_CASES = REPOSITORY_ROOT / "benchmarks/phase11a_contextual_resolution_cases.json"
STRONG_EVIDENCE = REPOSITORY_ROOT / "benchmarks/phase11a_strong_reasoner_cases.json"
SCHEMA_PATH = REPOSITORY_ROOT / "config/note-schema.json"
DEFAULT_CACHE = Path("/data/odyssey/runtime/phase11a-benchmark/embedding-cache")
MODEL = "gpt-5.6-sol"
MAX_REQUESTS = 12
MODEL_PRICES_PER_MILLION = {"input": 5.00, "cached_input": 0.50, "output": 30.00}

SELECTED_CASE_IDS = (
    "en-wife-school",
    "en-climbing-xavi",
    "en-not-discount-balma",
    "en-xavi-client-or-friend",
    "es-esposa-hijos",
    "es-vecino-bicis",
    "es-xavi-sin-contexto",
    "es-mercurio-astronomia",
    "fr-compagne-xavi",
    "fr-clara-comptes",
    "fr-marc",
    "fr-veterinaire",
)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Persist safe benchmark state without ever storing request or response content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _synthetic_note(note_definition: dict[str, Any], schema: dict[str, Any]) -> Note:
    """Reconstruct one validated canonical synthetic note from frozen benchmark prose."""
    lines = note_definition["text"].splitlines()
    aliases: list[str] = []
    note_type = ""
    body: list[str] = []
    for line in lines[1:]:
        if line.startswith("Aliases: "):
            aliases = [item.strip() for item in line.removeprefix("Aliases: ").split(",")]
        elif line.startswith("Type: "):
            note_type = line.removeprefix("Type: ")
        else:
            body.append(line)
    metadata: dict[str, object] = {
        "id": note_definition["id"],
        "type": note_type,
        "created_at": "2026-08-16T12:00:00Z",
        "updated_at": "2026-08-16T12:00:00Z",
        "created_by": "phase11b2-synthetic",
        "updated_by": "phase11b2-synthetic",
        "revision": 1,
        "schema_version": 1,
    }
    if aliases:
        metadata["aliases"] = aliases
    note = Note(metadata=metadata, content="\n".join(body))  # type: ignore[arg-type]
    validate_note(note, schema)
    return note


def _load_ranked_cases(cache_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load frozen candidates using the established Phase 11B.1 ranking path."""
    from benchmarks.run_phase11b1_openai import load_blocking_cases

    base = json.loads(PHASE11A_CASES.read_text(encoding="utf-8"))
    ranked = load_blocking_cases(cache_dir)
    selected = select_cases(ranked)
    notes = {note["id"]: note for note in base["notes"]}
    return list(selected), notes


def select_cases(cases: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Return exactly the frozen ordered evaluation set and reject any other request count."""
    if len(SELECTED_CASE_IDS) != MAX_REQUESTS:
        raise ValueError("Phase 11B.2 selected case set is not exactly twelve cases")
    by_id = {case["id"]: case for case in cases}
    missing = [case_id for case_id in SELECTED_CASE_IDS if case_id not in by_id]
    if missing:
        raise ValueError(f"Frozen Phase 11B.2 cases are missing: {missing}")
    selected = tuple(by_id[case_id] for case_id in SELECTED_CASE_IDS)
    if any(case["split"] != "evaluation" for case in selected):
        raise ValueError("Phase 11B.2 parity cases must all be evaluation cases")
    return selected


def _production_request(
    case: dict[str, Any], note_definitions: dict[str, dict[str, Any]], schema: dict[str, Any]
) -> ContextualResolutionRequest:
    """Build one production request by routing every candidate through provider evidence."""
    candidates = []
    for candidate in case["candidates"]:
        note_definition = note_definitions[candidate["id"]]
        note = _synthetic_note(note_definition, schema)
        primary_name = note_definition["text"].splitlines()[0].removeprefix("Name: ")
        evidence = build_provider_evidence(note, f"synthetic/{primary_name}.md")
        candidates.append(ContextualCandidate(candidate["id"], evidence))
    return ContextualResolutionRequest(
        reference=case["reference"],
        context=case["context"],
        entity_type=case["type"],
        candidates=tuple(candidates),
    )


def _calibration_examples(
    cache_dir: Path, note_definitions: dict[str, dict[str, Any]], schema: dict[str, Any]
) -> tuple[ContextualResolutionExample, ...]:
    """Build the accepted ten calibration turns through the production evidence boundary."""
    from benchmarks.run_phase11a_contextual_resolution import build_phase10_candidates

    base = json.loads(PHASE11A_CASES.read_text(encoding="utf-8"))
    calibration = [case for case in base["cases"] if case["split"] == "calibration"]
    ranked = build_phase10_candidates({"notes": base["notes"], "cases": calibration}, cache_dir)
    examples = []
    for case in ranked:
        request = _production_request(case, note_definitions, schema)
        decision = ContextualResolutionDecision(
            case["expected"], case.get("expected_id") if case["expected"] == "RESOLVED" else None
        )
        examples.append(ContextualResolutionExample(request, decision))
    return tuple(examples)


def estimated_cost_from_tokens(tokens: Counter[str]) -> float:
    """Estimate cost using the documented historical Sol price methodology."""
    ordinary = max(0, tokens["input_tokens"] - tokens["cached_input_tokens"])
    return round(
        (
            ordinary * MODEL_PRICES_PER_MILLION["input"]
            + tokens["cached_input_tokens"] * MODEL_PRICES_PER_MILLION["cached_input"]
            + tokens["output_tokens"] * MODEL_PRICES_PER_MILLION["output"]
        )
        / 1_000_000,
        6,
    )


def run_benchmark(cache_dir: Path, output: Path) -> None:
    """Run one no-retry twelve-request synthetic production-evidence checkpoint."""
    if output.exists():
        raise ValueError(f"Refusing to overwrite benchmark result: {output}")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    selected, note_definitions = _load_ranked_cases(cache_dir)
    examples = _calibration_examples(cache_dir, note_definitions, schema)
    reasoner = OpenAIContextualReasoner(MODEL, reasoning_effort="medium", examples=examples)
    result: dict[str, Any] = {
        "phase": "11B.2",
        "run_id": "sol-production-parity-12",
        "synthetic_only": True,
        "model": MODEL,
        "reasoning_effort": "medium",
        "store": False,
        "prompt_cache_enabled": False,
        "case_ids": list(SELECTED_CASE_IDS),
        "projected_max_cost_usd": 0.217483,
        "requests_attempted": 0,
        "requests_completed": 0,
        "cases": [],
    }
    tokens: Counter[str] = Counter()
    for case in selected:
        request = _production_request(case, note_definitions, schema)
        started = time.perf_counter()
        result["requests_attempted"] += 1
        try:
            output_data, usage = reasoner.resolve(request)
        except (ContextualProviderError, RuntimeError) as error:
            result["failure"] = {"type": type(error).__name__}
            write_json_atomic(output, result)
            raise
        latency = time.perf_counter() - started
        candidate_ids = {candidate.id for candidate in request.candidates}
        decision = validate_contextual_decision(output_data, candidate_ids)
        expected_id = case.get("expected_id") if case["expected"] == "RESOLVED" else None
        correct = decision.outcome == case["expected"] and decision.id == expected_id
        row = {
            "case_id": case["id"],
            "language": case["language"],
            "category": case["category"],
            "outcome": decision.outcome,
            "selected_id": decision.id,
            "schema_valid": True,
            "correct": correct,
            "false_resolved": decision.outcome == "RESOLVED" and not correct,
            "latency_seconds": round(latency, 6),
            **usage,
        }
        result["cases"].append(row)
        result["requests_completed"] += 1
        tokens.update({key: int(value) for key, value in usage.items() if key.endswith("tokens")})
        result["token_usage"] = dict(tokens)
        result["estimated_cost_usd"] = estimated_cost_from_tokens(tokens)
        write_json_atomic(output, result)
    outcomes = Counter(row["outcome"] for row in result["cases"])
    result["outcome_counts"] = dict(outcomes)
    result["correct_count"] = sum(row["correct"] for row in result["cases"])
    result["clear_false_resolved"] = sum(
        row["false_resolved"] and row["case_id"] != "en-toulouse-supermarket"
        for row in result["cases"]
    )
    result["pass"] = (
        result["requests_completed"] == MAX_REQUESTS
        and result["correct_count"] == MAX_REQUESTS
        and result["clear_false_resolved"] == 0
    )
    result["latency_seconds"] = {
        "mean": round(statistics.mean(row["latency_seconds"] for row in result["cases"]), 6)
    }
    write_json_atomic(output, result)


def main() -> None:
    """Parse the one authorized synthetic parity-run command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--embedding-cache-dir", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    run_benchmark(args.embedding_cache_dir, args.output)


if __name__ == "__main__":
    main()
