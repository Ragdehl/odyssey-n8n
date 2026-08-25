"""Measure adversarial local MiniLM novelty evidence against Markdown note bodies.

This Phase 16.2A.2 benchmark is evidence only.  It compares a planner-style atomic fact against
the whole note body, individual deterministic body units, and adjacent two-unit blocks.  It does
not make, expose, or authorize any production writing decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.run_phase16_novelty import (
    EXPECTED_CLASSES,
    cosine_similarity,
    normalize_exact_duplicate,
    summarize,
    threshold_analysis,
)
from odyssey_core.semantic import FastEmbedTextEmbedder, TextEmbedder

DEFAULT_THRESHOLDS = (0.15, 0.18, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50)


def load_cases(path: Path) -> dict[str, Any]:
    """Load the reviewable Phase 16.2A.2 adversarial Markdown dataset.

    Args:
        path: JSON file containing labelled Markdown-note scenarios.

    Returns:
        Parsed data with unique scenario identifiers.

    Raises:
        ValueError: If required fields, expected classes, or IDs are invalid.
        OSError: If the dataset cannot be read.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format_version") != 1 or not isinstance(data.get("scenarios"), list):
        raise ValueError("Phase 16 adversarial novelty dataset has an unsupported format")
    identifiers = []
    for scenario in data["scenarios"]:
        if not isinstance(scenario, dict) or scenario.get("expected") not in EXPECTED_CLASSES:
            raise ValueError("every adversarial scenario needs a supported expected class")
        if not all(
            isinstance(scenario.get(key), str) and scenario[key]
            for key in ("id", "category", "note_body", "proposed")
        ):
            raise ValueError("every adversarial scenario needs non-empty text fields")
        if "raw_request" in scenario and not isinstance(scenario["raw_request"], str):
            raise ValueError("raw_request must be a string when supplied")
        identifiers.append(scenario["id"])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("adversarial scenario IDs must be unique")
    return data


def body_units(markdown: str) -> list[str]:
    """Project simple Markdown bodies into deterministic small factual comparison units.

    Unordered list items and non-empty plain lines become individual units. Consecutive prose
    lines form one paragraph unit; Markdown headings are presentation and are excluded. This is
    intentionally not a Markdown AST or semantic parser.

    Args:
        markdown: Markdown note body to project.

    Returns:
        Non-empty plain-text units in source order.

    Raises:
        TypeError: If ``markdown`` is not a string.
    """
    if not isinstance(markdown, str):
        raise TypeError("Markdown body must be text")
    units: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        """Append the pending prose paragraph when one exists."""
        if paragraph:
            units.append(" ".join(paragraph))
            paragraph.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
        elif line.startswith("#") and line.lstrip("#").startswith(" "):
            flush_paragraph()
        elif len(line) >= 2 and line[0] in "-*+" and line[1].isspace():
            flush_paragraph()
            units.append(normalize_exact_duplicate(line))
        else:
            paragraph.append(line)
    flush_paragraph()
    return units


def adjacent_blocks(units: Sequence[str]) -> list[str]:
    """Build source-ordered adjacent two-unit blocks for the small-block strategy.

    Args:
        units: Existing deterministic body units.

    Returns:
        One joined block per adjacent pair, or the only unit when the body has one unit.
    """
    if len(units) < 2:
        return list(units)
    return [f"{units[index]}\n{units[index + 1]}" for index in range(len(units) - 1)]


def _measure(texts: Sequence[str], embedder: TextEmbedder) -> list[Sequence[float]]:
    """Embed texts and reject runtimes that lose source-order cardinality.

    Args:
        texts: Non-empty texts to embed.
        embedder: Existing local embedding boundary.

    Returns:
        One vector per text in the original order.

    Raises:
        ValueError: If the runtime returns the wrong number of vectors.
    """
    vectors = list(embedder.embed_documents(texts))
    if len(vectors) != len(texts):
        raise ValueError("embedding runtime returned the wrong number of vectors")
    return vectors


def _best_match(
    proposed_vector: Sequence[float],
    candidates: Sequence[str],
    candidate_vectors: Sequence[Sequence[float]],
) -> tuple[float, str]:
    """Return the greatest proposed-fact similarity and its source unit or block.

    Args:
        proposed_vector: Embedding for the new atomic fact.
        candidates: Units or blocks corresponding to ``candidate_vectors``.
        candidate_vectors: Existing unit or block embeddings.

    Returns:
        Highest cosine similarity and its deterministic source text.

    Raises:
        ValueError: If no candidate exists.
    """
    if not candidates:
        raise ValueError("a Markdown note must yield at least one body unit")
    scores = [cosine_similarity(proposed_vector, vector) for vector in candidate_vectors]
    best_index = max(range(len(scores)), key=scores.__getitem__)
    return scores[best_index], candidates[best_index]


def run_benchmark(data: dict[str, Any], embedder: TextEmbedder) -> dict[str, Any]:
    """Run all whole-note, unit-MAX, and block-MAX adversarial comparisons.

    Args:
        data: Validated adversarial benchmark dataset.
        embedder: Existing local MiniLM/FastEmbed runtime.

    Returns:
        Per-scenario evidence, distributions, and threshold analysis for every strategy.
    """
    scenarios = data["scenarios"]
    projections = [(body_units(item["note_body"]), item) for item in scenarios]
    all_texts = [
        text
        for units, item in projections
        for text in [item["note_body"], item["proposed"], *units, *adjacent_blocks(units)]
        + ([item["raw_request"]] if item.get("raw_request") else [])
    ]
    vectors = iter(_measure(all_texts, embedder))
    measured = []
    for units, item in projections:
        note_vector = next(vectors)
        proposed_vector = next(vectors)
        unit_vectors = [next(vectors) for _ in units]
        blocks = adjacent_blocks(units)
        block_vectors = [next(vectors) for _ in blocks]
        whole_similarity = cosine_similarity(proposed_vector, note_vector)
        unit_similarity, highest_unit = _best_match(proposed_vector, units, unit_vectors)
        block_similarity, highest_block = _best_match(proposed_vector, blocks, block_vectors)
        record = {
            **item,
            "body_units": units,
            "whole_note_similarity": whole_similarity,
            "max_unit_similarity": unit_similarity,
            "highest_scoring_unit": highest_unit,
            "max_block_similarity": block_similarity,
            "highest_scoring_block": highest_block,
            "exact_normalized_unit_match": any(
                normalize_exact_duplicate(unit) == normalize_exact_duplicate(item["proposed"])
                for unit in units
            ),
        }
        if item.get("raw_request"):
            raw_vector = next(vectors)
            raw_unit_similarity, raw_highest_unit = _best_match(raw_vector, units, unit_vectors)
            record.update(
                {
                    "raw_request_whole_note_similarity": cosine_similarity(raw_vector, note_vector),
                    "raw_request_max_unit_similarity": raw_unit_similarity,
                    "raw_request_highest_scoring_unit": raw_highest_unit,
                }
            )
        measured.append(record)

    strategies = {
        "whole_note": "whole_note_similarity",
        "unit_max": "max_unit_similarity",
        "block_max": "max_block_similarity",
    }
    analysis = {}
    distributions = {}
    for name, field in strategies.items():
        scored = [{**item, "similarity": item[field]} for item in measured]
        analysis[name] = threshold_analysis(scored, DEFAULT_THRESHOLDS)
        distributions[name] = {
            expected: summarize([item[field] for item in measured if item["expected"] == expected])
            for expected in sorted(EXPECTED_CLASSES)
        }
    return {
        "format_version": 1,
        "model_name": embedder.model_name,
        "model_version": embedder.model_version,
        "scenario_count": len(measured),
        "category_counts": dict(sorted(Counter(item["category"] for item in measured).items())),
        "class_counts": {
            expected: sum(item["expected"] == expected for item in measured)
            for expected in sorted(EXPECTED_CLASSES)
        },
        "scenarios": measured,
        "distributions": distributions,
        "threshold_analysis": analysis,
    }


def main() -> None:
    """Run the offline adversarial benchmark and write reviewable JSON evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("phase16_adversarial_novelty_cases.json"),
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("phase16_adversarial_novelty_results.json"),
    )
    args = parser.parse_args()
    results = run_benchmark(
        load_cases(args.cases),
        FastEmbedTextEmbedder(cache_dir=args.cache_dir, local_files_only=True),
    )
    args.output.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
