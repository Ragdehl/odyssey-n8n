"""Run the frozen MiniLM-selected-context Luna benchmark without provider retries."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from benchmarks.phase16_3_writer_benchmark.benchmark import (
    BENCHMARK_DIR,
    render_prompt,
    render_request,
    writer_json_schema,
)
from benchmarks.phase16_3_writer_benchmark.evaluate import evaluate_output
from benchmarks.phase16_3_writer_benchmark.minilm_cases import load_pipeline_cases
from benchmarks.phase16_3_writer_benchmark.minilm_retrieval import (
    render_retrieved_context,
    retrieve,
    target_rank,
)
from benchmarks.phase16_3_writer_benchmark.run_benchmark import MODELS, _cost, _usage
from odyssey_core.semantic import FastEmbedTextEmbedder


def run(run_id: str, *, cache_dir: Path, client: Any | None = None) -> Path:
    """Embed frozen cases locally, then append the predeclared Luna TOP_3 provider calls."""
    directory = BENCHMARK_DIR / "results" / run_id
    if directory.exists():
        raise ValueError("Refusing to alter existing benchmark evidence")
    primary, extra = load_pipeline_cases()
    embedder = FastEmbedTextEmbedder(cache_dir=cache_dir, local_files_only=True)
    retrieval = {
        case["id"]: {f"TOP_{k}": retrieve(case, embedder, limit=k) for k in (3, 5)}
        for case in primary + extra
    }
    directory.mkdir(parents=True)
    (directory / "retrieval.json").write_text(
        json.dumps(retrieval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (directory / "metadata.json").write_text(
        json.dumps(
            {
                "suite": "minilm-retrieval",
                "model": MODELS["luna"],
                "reasoning_effort": "low",
                "store": False,
                "planned_top_3_calls": len(primary),
                "planned_top_5_calls": "conditional",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required")
        from openai import OpenAI

        client = OpenAI()
    with (directory / "raw_results.jsonl").open("x", encoding="utf-8") as stream:
        for case in primary:
            _call(stream, client, case, "TOP_3", retrieval[case["id"]]["TOP_3"])
            rank = target_rank(case, retrieval[case["id"]]["TOP_3"])
            if rank is not None and 3 < rank <= 5:
                _call(stream, client, case, "TOP_5", retrieval[case["id"]]["TOP_5"])
    return directory


def _call(
    stream: Any, client: Any, case: dict[str, Any], strategy: str, retrieval: dict[str, Any]
) -> None:
    """Make one Luna call against exact automatically retrieved source fragments."""
    context = render_retrieved_context(case, retrieval)
    response = client.responses.create(
        model=MODELS["luna"],
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
    raw = response.output_text
    try:
        parsed = json.loads(raw)
        status, checks = evaluate_output(parsed, case, context=context)
    except (TypeError, json.JSONDecodeError):
        parsed, status, checks = (
            None,
            "CRITICAL",
            [{"severity": "CRITICAL", "code": "invalid_json"}],
        )
    usage = _usage(response)
    stream.write(
        json.dumps(
            {
                "case_id": case["id"],
                "context_strategy": strategy,
                "model": MODELS["luna"],
                "current_note": case["current_body"],
                "retrieved_context": context,
                "facts": case["facts"],
                "raw_output": raw,
                "parsed_operations": parsed,
                "deterministic_status": status,
                "deterministic_checks": checks,
                "usage": usage,
                "estimated_cost_usd": _cost(usage, MODELS["luna"]),
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    stream.flush()
