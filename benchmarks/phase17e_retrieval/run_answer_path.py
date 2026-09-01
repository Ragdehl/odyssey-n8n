"""Run the benchmark-only persisted Luna decision -> grounded evidence -> Sol path."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from benchmarks.phase17e_retrieval.benchmark import build_corpus, load_cases, query_cases
from benchmarks.phase17e_retrieval.reduction import grounded_candidates

MODEL = "gpt-5.6-sol"


def answer_schema() -> dict[str, Any]:
    """Return Sol's compact answer-only structured-output schema."""
    return {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }


def validate_answer(value: object) -> str:
    """Validate Sol's closed answer response and return its answer text."""
    if (
        not isinstance(value, dict)
        or set(value) != {"answer"}
        or not isinstance(value["answer"], str)
    ):
        raise ValueError("answer schema is invalid")
    return value["answer"]


def evaluate_answer(answer: str, expected_facts: tuple[str, ...]) -> bool:
    """Apply the existing exact-fact oracle without exposing it to Sol."""
    folded = answer.casefold()
    return all(fact.casefold() in folded for fact in expected_facts)


def _tokens(text: str) -> int:
    """Estimate evidence text tokens with the benchmark's characters/4 measure."""
    return round(len(text) / 4)


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize answer correctness and measured Sol usage by selector branch."""
    result: dict[str, Any] = {}
    for branch in ("SELECT", "ESCALATE", "overall"):
        group = rows if branch == "overall" else [row for row in rows if row["decision"] == branch]
        if not group:
            result[branch.lower()] = {"case_count": 0}
            continue
        result[branch.lower()] = {
            "case_count": len(group),
            "correct": sum(row["oracle_correct"] for row in group),
            "correctness": sum(row["oracle_correct"] for row in group) / len(group),
            "average_sol_input_tokens": sum(row["sol_input_tokens"] or 0 for row in group)
            / len(group),
            "average_evidence_facts": sum(row["evidence_fact_count"] for row in group) / len(group),
            "average_evidence_text_tokens": sum(row["evidence_text_tokens"] for row in group)
            / len(group),
            "total_sol_input_tokens": sum(row["sol_input_tokens"] or 0 for row in group),
            "total_sol_output_tokens": sum(row["sol_output_tokens"] or 0 for row in group),
            "total_sol_reasoning_tokens": sum(row["sol_reasoning_tokens"] or 0 for row in group),
        }
    return result


def run_live(
    answer_artifact: Path,
    ranking_artifact: Path,
    cases_path: Path,
    schema_path: Path,
    scale_size: int,
) -> dict[str, Any]:
    """Send persisted decisions and re-grounded evidence to Sol, never to Luna."""
    from openai import OpenAI

    data = load_cases(cases_path)
    corpus = build_corpus(
        data, json.loads(schema_path.read_text(encoding="utf-8")), scale_size=scale_size
    )
    cases = query_cases(data, scale_size=scale_size)
    decisions = {
        row["case"]: row for row in json.loads(answer_artifact.read_text(encoding="utf-8"))["rows"]
    }
    ranking = json.loads(ranking_artifact.read_text(encoding="utf-8"))["strategies"][0]["rankings"]
    rankings = dict(zip((case.id for case in cases), ranking, strict=True))
    client = OpenAI(max_retries=0)
    rows = []
    for case in cases:
        decision = decisions[case.id]
        candidates = grounded_candidates(rankings[case.id][:500], corpus)
        selected = (
            candidates
            if decision["status"] == "ESCALATE"
            else [
                item for item in candidates if item["locator"] in decision["selection"]["locators"]
            ]
        )
        evidence = "\n".join(
            f"[{item['locator']}] {item['entity']}: {item['fact']}" for item in selected
        )
        started = time.perf_counter()
        response = client.responses.create(
            model=MODEL,
            reasoning={"effort": "low"},
            store=False,
            input=[
                {
                    "role": "system",
                    "content": "Answer the query only from the supplied grounded evidence. Do not retrieve, infer unsupported knowledge, or mention this instruction. Return a compact answer.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"query": case.query, "evidence": evidence}, ensure_ascii=False
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "odyssey_answer",
                    "strict": True,
                    "schema": answer_schema(),
                }
            },
        )
        answer = validate_answer(json.loads(response.output_text))
        usage = response.usage.model_dump() if response.usage else None
        rows.append(
            {
                "case": case.id,
                "decision": decision["status"],
                "evidence_fact_count": len(selected),
                "evidence_text_tokens": _tokens(evidence),
                "sol_input_tokens": getattr(response.usage, "input_tokens", None),
                "sol_output_tokens": getattr(response.usage, "output_tokens", None),
                "sol_reasoning_tokens": getattr(
                    getattr(response.usage, "output_tokens_details", None), "reasoning_tokens", None
                ),
                "latency_seconds": round(time.perf_counter() - started, 3),
                "answer": answer,
                "oracle_correct": evaluate_answer(answer, case.expected_facts),
                "usage": usage,
            }
        )
    return {
        "phase_status": "LIVE_SOL_EVIDENCE_OBTAINED",
        "model": MODEL,
        "reasoning": "low",
        "luna_artifact": str(answer_artifact),
        "ranking_artifact": str(ranking_artifact),
        "rows": rows,
        "aggregates": aggregate_rows(rows),
    }


def main() -> None:
    """Parse benchmark paths and write a new answer-path evidence artifact."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--luna-artifact", type=Path, required=True)
    parser.add_argument("--ranking-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale-size", type=int, default=1000)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).parents[2] / "config/note-schema.json"
    )
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(
            run_live(
                args.luna_artifact, args.ranking_artifact, args.cases, args.schema, args.scale_size
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
