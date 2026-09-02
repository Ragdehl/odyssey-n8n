"""Benchmark-only Luna relevance reduction over persisted Combined rankings."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from benchmarks.phase17e_retrieval.benchmark import (
    build_corpus,
    load_cases,
    query_cases,
    required_evidence_pairs,
)

MODEL = "gpt-5.6-luna"
REASONING = "none"
REASONING_EFFORTS = ("none", "low", "medium", "high")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def repository_path(path: Path) -> Path:
    """Return a resolved benchmark path constrained to the repository tree.

    Parameters:
        path: CLI-provided or default path to use for benchmark input or output.

    Returns:
        The resolved path when it remains inside the repository.

    Raises:
        ValueError: If the path escapes the repository, including through a symlink.
    """
    resolved = path.resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise ValueError("benchmark paths must remain inside the repository") from exc
    return resolved


def _validated_output(path: Path) -> Path:
    """Return a writable repository-contained output path for a benchmark artifact.

    Parameters:
        path: Requested benchmark output path.

    Returns:
        A path using only the requested filename beneath the repository root.

    Raises:
        ValueError: If the output path escapes the repository tree.
    """
    name = path.name
    if not name or name in {".", ".."}:
        raise ValueError("benchmark output must have a filename")
    return REPOSITORY_ROOT / name


def selector_schema() -> dict[str, Any]:
    """Return the closed schema for high-recall supplied-locator selection."""
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["SELECT", "ESCALATE"]},
            "locators": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["decision", "locators"],
        "additionalProperties": False,
    }


def validate_selection(value: object, supplied: set[str]) -> dict[str, Any]:
    """Validate a Luna response and fail closed on malformed or unknown locators."""
    if not isinstance(value, dict) or set(value) != {"decision", "locators"}:
        raise ValueError("selector schema is invalid")
    decision, locators = value["decision"], value["locators"]
    if decision not in {"SELECT", "ESCALATE"} or not isinstance(locators, list):
        raise ValueError("selector decision or locator list is invalid")
    if any(not isinstance(locator, str) or locator not in supplied for locator in locators):
        raise ValueError("selector returned an unknown locator")
    if len(locators) != len(set(locators)):
        raise ValueError("selector returned duplicate locators")
    if decision == "ESCALATE" and locators:
        raise ValueError("ESCALATE must not contain locators")
    if decision == "SELECT" and not locators:
        raise ValueError("SELECT must retain at least one locator")
    return {"decision": decision, "locators": locators}


def _facts_and_locators(corpus: tuple[Any, ...]) -> dict[str, tuple[str, str]]:
    """Build stable locator-to-current-fact mappings from validated benchmark notes."""
    return {
        f"{note.id}#fact-{index}": (note.id, fact)
        for note in corpus
        for index, fact in enumerate(note.facts)
    }


def grounded_candidates(
    ranking: list[dict[str, str]], corpus: tuple[Any, ...]
) -> list[dict[str, str]]:
    """Re-ground ranked facts against current validated note content."""
    current = _facts_and_locators(corpus)
    by_fact = {(entity, fact): locator for locator, (entity, fact) in current.items()}
    result = []
    for item in ranking:
        locator = by_fact.get((item["entity"], item["fact"]))
        if locator is not None:
            result.append(
                {"locator": locator, "entity": item["entity"], "fact": current[locator][1]}
            )
    return result


def _tokens(text: str) -> int:
    """Estimate benchmark payload tokens using the established characters/4 planning measure."""
    return round(len(text) / 4)


def select_cases(all_cases: tuple[Any, ...], case_ids: tuple[str, ...] | None) -> tuple[Any, ...]:
    """Filter frozen cases by optional repeated CLI identifiers and reject unknown IDs."""
    requested = set(case_ids or ())
    known = {case.id for case in all_cases}
    unknown = requested - known
    if unknown:
        raise ValueError(f"unknown benchmark case ids: {sorted(unknown)!r}")
    return tuple(case for case in all_cases if not requested or case.id in requested)


def _call_selector(
    client: Any, query: str, candidates: list[dict[str, str]], reasoning: str
) -> tuple[dict[str, Any], Any]:
    """Call Luna once and validate its closed locator decision."""
    response = client.responses.create(
        model=MODEL,
        reasoning={"effort": reasoning},
        store=False,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a relevance filter only. Retain ALL supplied facts that may be "
                    "needed to answer the query. For conjunctive or multi-condition queries, "
                    "preserve evidence for EVERY material condition, not merely enough to identify "
                    "the answer entity. If the answer depends on A AND B AND C, retain evidence "
                    "supporting A, B, and C. If you cannot confidently preserve every condition, "
                    "return ESCALATE. Remove only facts you can safely judge irrelevant. "
                    "Do not answer, summarize, rewrite, infer, resolve identity, or mutate anything. "
                    "If safe reduction is uncertain, return ESCALATE with an empty locator list. "
                    "Never choose a target number of facts."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"query": query, "candidates": candidates}, ensure_ascii=False
                ),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "odyssey_relevance_selection",
                "strict": True,
                "schema": selector_schema(),
            }
        },
    )
    return validate_selection(
        json.loads(response.output_text), {item["locator"] for item in candidates}
    ), response.usage


def run_live(
    artifact: Path,
    cases_path: Path,
    schema_path: Path,
    scale_size: int,
    *,
    reasoning: str = REASONING,
    case_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Run the cheapest Luna selector across the frozen cases and preserve audit evidence."""
    from openai import APIError, OpenAI

    artifact_data = json.loads(artifact.read_text(encoding="utf-8"))
    ranking_data = artifact_data["strategies"][0]["rankings"]
    data = load_cases(cases_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    corpus = build_corpus(data, schema, scale_size=scale_size)
    all_cases = query_cases(data, scale_size=scale_size)
    rankings_by_case = dict(zip((case.id for case in all_cases), ranking_data, strict=True))
    cases = select_cases(all_cases, case_ids)
    client = OpenAI(max_retries=0)
    rows = []
    for case_index, case in enumerate(cases):
        ranking = rankings_by_case[case.id]
        candidates = grounded_candidates(ranking[:500], corpus)
        started = time.perf_counter()
        error = None
        status = "PROVIDER_ERROR"
        try:
            selection, usage = _call_selector(client, case.query, candidates, reasoning)
            status = selection["decision"]
        except (APIError, OSError, TypeError, ValueError, KeyError) as exc:
            selection = {"decision": "ESCALATE", "locators": []}
            usage = None
            error = type(exc).__name__
        selected = [item for item in candidates if item["locator"] in selection["locators"]]
        required = required_evidence_pairs(case)
        selected_facts = {(item["entity"], item["fact"]) for item in selected}
        rows.append(
            {
                "case": case.id,
                "query": case.query,
                "model": MODEL,
                "reasoning": reasoning,
                "candidate_count": len(candidates),
                "candidate_fact_tokens": _tokens("\n".join(item["fact"] for item in candidates)),
                "status": status,
                "evidence_status": "VALID" if status in {"SELECT", "ESCALATE"} else "NO_EVIDENCE",
                "selection": selection if status in {"SELECT", "ESCALATE"} else None,
                "selected_count": len(selected),
                "selected_fact_tokens": _tokens("\n".join(item["fact"] for item in selected)),
                "required_fact_count": len(required),
                "required_any": bool(required & selected_facts) if required else True,
                "required_all": required.issubset(selected_facts),
                "dropped_without_escalation": status == "SELECT"
                and bool(required - selected_facts),
                "latency_seconds": round(time.perf_counter() - started, 3),
                "usage": getattr(usage, "model_dump", lambda: None)() if usage else None,
                "error": error,
            }
        )
        if case_index == 0 and status == "PROVIDER_ERROR":
            return {
                "phase_status": "BLOCKED_ON_LIVE_PROVIDER_EVIDENCE",
                "model": MODEL,
                "reasoning": reasoning,
                "rows": rows,
            }
    return {
        "phase_status": "LIVE_EVIDENCE_OBTAINED",
        "model": MODEL,
        "reasoning": reasoning,
        "rows": rows,
    }


def main() -> None:
    """Run the benchmark selector and write machine-readable evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale-size", type=int, default=1000)
    parser.add_argument("--reasoning", choices=REASONING_EFFORTS, default=REASONING)
    parser.add_argument("--case", dest="case_ids", action="append", default=[])
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).parents[2] / "config/note-schema.json"
    )
    args = parser.parse_args()
    artifact = repository_path(args.artifact)
    cases = repository_path(args.cases)
    schema = repository_path(args.schema)
    output = _validated_output(args.output)
    result = run_live(
        artifact,
        cases,
        schema,
        args.scale_size,
        reasoning=args.reasoning,
        case_ids=tuple(args.case_ids),
    )
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = result["rows"]
    print(
        json.dumps(
            {
                "cases": len(rows),
                "semantic_escalations": sum(r["status"] == "ESCALATE" for r in rows),
                "provider_errors": sum(r["status"] == "PROVIDER_ERROR" for r in rows),
            }
        )
    )


if __name__ == "__main__":
    main()
