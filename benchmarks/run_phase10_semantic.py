"""Run the non-CI Phase 10 multilingual semantic retrieval benchmark."""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np
from fastembed import TextEmbedding

DEFAULT_MODELS = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)


def load_cases(path: Path) -> dict[str, Any]:
    """Load the synthetic benchmark dataset from JSON.

    Args:
        path: JSON file containing note projections and expected query targets.

    Returns:
        Parsed benchmark object.

    Raises:
        OSError: If the dataset cannot be read.
        json.JSONDecodeError: If the dataset is not valid JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def run_model(model_name: str, cases: dict[str, Any], *, limit: int) -> dict[str, Any]:
    """Measure expected-target recall and runtime for one local embedding model.

    Args:
        model_name: FastEmbed supported model identifier.
        cases: Synthetic benchmark notes and queries.
        limit: Number of highest-scoring candidates counted as a hit.

    Returns:
        Machine-readable metrics and individual ranked query results.
    """
    started = time.perf_counter()
    model = TextEmbedding(model_name=model_name)
    loaded_seconds = time.perf_counter() - started

    notes = cases["notes"]
    queries = cases["queries"]
    started = time.perf_counter()
    note_vectors = np.asarray(list(model.embed([note["text"] for note in notes])))
    query_texts = [
        f"Reference: {query['reference']}\nContext: {query['context']}" for query in queries
    ]
    query_vectors = np.asarray(list(model.query_embed(query_texts)))
    execution_seconds = time.perf_counter() - started

    rankings = []
    hits = 0
    for query, vector in zip(queries, query_vectors, strict=True):
        scores = note_vectors @ vector
        order = sorted(
            range(len(notes)), key=lambda index: (-float(scores[index]), notes[index]["id"])
        )
        top_ids = [notes[index]["id"] for index in order[:limit]]
        hit = query["expected_id"] in top_ids
        hits += hit
        rankings.append(
            {
                "reference": query["reference"],
                "expected_id": query["expected_id"],
                "top_ids": top_ids,
                "hit": hit,
            }
        )

    return {
        "model": model_name,
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "limit": limit,
        "hits": hits,
        "queries": len(queries),
        "recall_at_n": hits / len(queries),
        "model_load_seconds": loaded_seconds,
        "embed_and_query_seconds": execution_seconds,
        "rankings": rankings,
    }


def main() -> None:
    """Parse CLI arguments, run selected models, and print JSON results."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("phase10_semantic_cases.json"),
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    cases = load_cases(args.cases)
    results = [run_model(name, cases, limit=args.limit) for name in args.models or DEFAULT_MODELS]
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
