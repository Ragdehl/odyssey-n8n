"""Run the benchmark-only persisted Luna decision -> grounded evidence -> Sol path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from benchmarks.phase17e_retrieval.benchmark import build_corpus, load_cases, query_cases
from benchmarks.phase17e_retrieval.reduction import grounded_candidates, select_cases

MODEL = "gpt-5.6-sol"
REASONING = "low"


def checkpoint_identity(
    answer_artifact: Path,
    ranking_artifact: Path,
    reasoning: str = REASONING,
    case_ids: tuple[str, ...] = (),
) -> dict[str, str]:
    """Return stable identities for the persisted selector and ranking inputs."""

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    return {
        "model": MODEL,
        "reasoning": reasoning,
        "cases": ",".join(case_ids),
        "luna_artifact": str(answer_artifact.resolve()),
        "luna_artifact_sha256": digest(answer_artifact),
        "ranking_artifact": str(ranking_artifact.resolve()),
        "ranking_artifact_sha256": digest(ranking_artifact),
    }


def write_checkpoint(
    output: Path, identity: dict[str, str], rows: list[dict[str, Any]], status: str
) -> None:
    """Atomically persist completed answer rows so interruption loses no paid results."""
    payload = {"phase_status": status, "checkpoint_identity": identity, "rows": rows}
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, output)


def load_checkpoint(output: Path, identity: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Load and validate a compatible checkpoint, failing closed on mismatch."""
    if not output.exists():
        return {}
    payload = json.loads(output.read_text(encoding="utf-8"))
    if payload.get("checkpoint_identity") != identity or not isinstance(payload.get("rows"), list):
        raise ValueError("answer-path checkpoint is incompatible with current inputs")
    rows = payload["rows"]
    if any(not isinstance(row, dict) or not isinstance(row.get("case"), str) for row in rows):
        raise ValueError("answer-path checkpoint contains invalid rows")
    if len({row["case"] for row in rows}) != len(rows):
        raise ValueError("answer-path checkpoint contains duplicate cases")
    return {row["case"]: row for row in rows}


def map_rankings(all_cases: tuple[Any, ...], rankings: list[Any]) -> dict[str, Any]:
    """Associate each persisted ranking with its full frozen case ordering."""
    return dict(zip((case.id for case in all_cases), rankings, strict=True))


def answer_schema() -> dict[str, Any]:
    """Return Sol's closed answer and supporting-locator schema."""
    return {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "minLength": 1},
            "supporting_locators": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["answer", "supporting_locators"],
        "additionalProperties": False,
    }


def validate_answer(value: object, supplied_locators: set[str]) -> dict[str, Any]:
    """Validate Sol's answer and ensure support cites supplied unique locators."""
    if (
        not isinstance(value, dict)
        or set(value) != {"answer", "supporting_locators"}
        or not isinstance(value["answer"], str)
        or not value["answer"].strip()
        or not isinstance(value["supporting_locators"], list)
        or any(not isinstance(locator, str) for locator in value["supporting_locators"])
        or any(locator not in supplied_locators for locator in value["supporting_locators"])
        or len(value["supporting_locators"]) != len(set(value["supporting_locators"]))
        or (supplied_locators and not value["supporting_locators"])
    ):
        raise ValueError("answer schema is invalid")
    return value


def evaluate_support(
    response: dict[str, Any], grounded_by_locator: dict[str, str], expected_facts: tuple[str, ...]
) -> bool:
    """Measure whether cited grounded evidence covers every required benchmark fact."""
    supported_facts = {grounded_by_locator[locator] for locator in response["supporting_locators"]}
    return set(expected_facts).issubset(supported_facts)


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
            "correct": sum(row["required_evidence_supported"] for row in group),
            "correctness": sum(row["required_evidence_supported"] for row in group) / len(group),
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
    output: Path,
    reasoning: str = REASONING,
    case_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Send persisted decisions and re-grounded evidence to Sol, never to Luna."""
    from openai import OpenAI

    identity = checkpoint_identity(answer_artifact, ranking_artifact, reasoning, case_ids)
    completed = load_checkpoint(output, identity)
    data = load_cases(cases_path)
    corpus = build_corpus(
        data, json.loads(schema_path.read_text(encoding="utf-8")), scale_size=scale_size
    )
    all_cases = query_cases(data, scale_size=scale_size)
    cases = select_cases(all_cases, case_ids)
    decisions = {
        row["case"]: row for row in json.loads(answer_artifact.read_text(encoding="utf-8"))["rows"]
    }
    ranking = json.loads(ranking_artifact.read_text(encoding="utf-8"))["strategies"][0]["rankings"]
    rankings = map_rankings(all_cases, ranking)
    client = OpenAI(max_retries=0)
    rows = [completed[case.id] for case in cases if case.id in completed]
    for index, case in enumerate(cases, 1):
        if case.id in completed:
            print(f"[{index}/{len(cases)}] {case.id} (resumed)", file=sys.stderr)
            continue
        print(f"[{index}/{len(cases)}] {case.id}", file=sys.stderr)
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
        try:
            response = client.responses.create(
                model=MODEL,
                reasoning={"effort": reasoning},
                store=False,
                input=[
                    {
                        "role": "system",
                        "content": "Answer only from supplied grounded evidence. Do not retrieve or infer unsupported knowledge. Return a compact answer and cite every supplied locator that supports it in supporting_locators.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"query": case.query, "evidence": selected}, ensure_ascii=False
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
        except Exception:
            write_checkpoint(output, identity, rows, "PROVIDER_ERROR")
            raise
        response_value = validate_answer(
            json.loads(response.output_text), {item["locator"] for item in selected}
        )
        grounded_by_locator = {item["locator"]: item["fact"] for item in selected}
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
                "answer": response_value["answer"],
                "supporting_locators": response_value["supporting_locators"],
                "required_evidence_supported": evaluate_support(
                    response_value, grounded_by_locator, case.expected_facts
                ),
                "usage": usage,
            }
        )
        write_checkpoint(output, identity, rows, "CHECKPOINT")
    return {
        "phase_status": "LIVE_SOL_EVIDENCE_OBTAINED",
        "model": MODEL,
        "reasoning": reasoning,
        "luna_artifact": str(answer_artifact),
        "ranking_artifact": str(ranking_artifact),
        "checkpoint_identity": identity,
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
    parser.add_argument("--reasoning", choices=("low", "medium", "high"), default=REASONING)
    parser.add_argument("--case", dest="case_ids", action="append", default=[])
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).parents[2] / "config/note-schema.json"
    )
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(
            run_live(
                args.luna_artifact,
                args.ranking_artifact,
                args.cases,
                args.schema,
                args.scale_size,
                args.output,
                args.reasoning,
                tuple(args.case_ids),
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
