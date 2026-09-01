"""Benchmark-only Luna relevance reduction over persisted Combined rankings."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from benchmarks.phase17e_retrieval.benchmark import build_corpus, load_cases, query_cases

MODEL = "gpt-5.6-luna"
REASONING = "none"


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


def run_live(
    artifact: Path, cases_path: Path, schema_path: Path, scale_size: int
) -> dict[str, Any]:
    """Run the cheapest Luna selector across the frozen cases and preserve audit evidence."""
    from openai import OpenAI

    artifact_data = json.loads(artifact.read_text(encoding="utf-8"))
    ranking_data = artifact_data["strategies"][0]["rankings"]
    data = load_cases(cases_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    corpus = build_corpus(data, schema, scale_size=scale_size)
    cases = query_cases(data, scale_size=scale_size)
    client = OpenAI(max_retries=0)
    rows = []
    for case, ranking in zip(cases, ranking_data, strict=True):
        candidates = grounded_candidates(ranking[:500], corpus)
        supplied = {item["locator"] for item in candidates}
        payload = {"query": case.query, "candidates": candidates}
        started = time.perf_counter()
        error = None
        try:
            response = client.responses.create(
                model=MODEL,
                reasoning={"effort": REASONING},
                store=False,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a relevance filter only. Retain ALL supplied facts that may be "
                            "needed to answer the query. Remove only facts you can safely judge irrelevant. "
                            "Do not answer, summarize, rewrite, infer, resolve identity, or mutate anything. "
                            "If safe reduction is uncertain, return ESCALATE with an empty locator list. "
                            "Never choose a target number of facts."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
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
            raw = json.loads(response.output_text)
            selection = validate_selection(raw, supplied)
            usage = response.usage
        except Exception as exc:  # Provider and validation failures are benchmark escalation.
            selection = {"decision": "ESCALATE", "locators": []}
            usage = None
            error = type(exc).__name__
        selected = [item for item in candidates if item["locator"] in selection["locators"]]
        required = set(case.expected_facts)
        selected_facts = {item["fact"] for item in selected}
        rows.append(
            {
                "case": case.id,
                "query": case.query,
                "model": MODEL,
                "reasoning": REASONING,
                "candidate_count": len(candidates),
                "candidate_fact_tokens": _tokens("\n".join(item["fact"] for item in candidates)),
                "selection": selection,
                "selected_count": len(selected),
                "selected_fact_tokens": _tokens("\n".join(item["fact"] for item in selected)),
                "required_fact_count": len(required),
                "required_any": bool(required & selected_facts) if required else True,
                "required_all": required.issubset(selected_facts),
                "dropped_without_escalation": bool(required - selected_facts)
                and selection["decision"] == "SELECT",
                "latency_seconds": round(time.perf_counter() - started, 3),
                "usage": getattr(usage, "model_dump", lambda: None)() if usage else None,
                "error": error,
            }
        )
    return {"model": MODEL, "reasoning": REASONING, "rows": rows}


def main() -> None:
    """Run the benchmark selector and write machine-readable evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale-size", type=int, default=1000)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).parents[2] / "config/note-schema.json"
    )
    args = parser.parse_args()
    result = run_live(args.artifact, args.cases, args.schema, args.scale_size)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = result["rows"]
    print(
        json.dumps(
            {
                "cases": len(rows),
                "escalations": sum(r["selection"]["decision"] == "ESCALATE" for r in rows),
            }
        )
    )


if __name__ == "__main__":
    main()
