"""Measure the existing local MiniLM's conservative free-text novelty evidence.

This Phase 16.2A checkpoint is deliberately not a production write gate.  It embeds synthetic,
fact-like body units through the existing ``TextEmbedder`` boundary and records where a later,
human-reviewed threshold might safely fail closed to a semantic writer.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odyssey_core.semantic import FastEmbedTextEmbedder, _normalized_vector

EXPECTED_CLASSES = frozenset({"OVERLAP", "INDEPENDENT"})
DEFAULT_THRESHOLDS = (0.30, 0.40, 0.50, 0.60, 0.70)


def normalize_exact_duplicate(text: str) -> str:
    """Normalize only presentation differences that cannot change a fact's wording.

    Surrounding whitespace, repeated internal whitespace, and one conventional unordered-list
    marker are ignored. Case, punctuation, accents, negation, word choice, and grammar remain
    unchanged. For example, ``" -  Marta vive en Toulouse. "`` becomes
    ``"Marta vive en Toulouse."``.

    Args:
        text: Candidate body unit to compare exactly.

    Returns:
        Conservative canonical text for exact-duplicate equality.

    Raises:
        TypeError: If ``text`` is not a string.
    """
    if not isinstance(text, str):
        raise TypeError("exact duplicate normalization requires text")
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] in "-*+" and stripped[1].isspace():
        stripped = stripped[2:].lstrip()
    return " ".join(stripped.split())


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity after rejecting malformed embedding vectors.

    Args:
        left: First finite non-zero embedding.
        right: Second finite non-zero embedding of the same dimension.

    Returns:
        Dot product of the two normalized vectors.

    Raises:
        ValueError: If the vectors have different dimensions.
        SemanticIndexError: If an embedding is invalid, propagated from normalization.
    """
    normalized_left = _normalized_vector(left)
    normalized_right = _normalized_vector(right)
    if len(normalized_left) != len(normalized_right):
        raise ValueError("embedding dimensions do not match")
    return sum(
        first * second for first, second in zip(normalized_left, normalized_right, strict=True)
    )


def load_cases(path: Path) -> dict[str, Any]:
    """Load and validate the reviewable synthetic Phase 16.2A dataset.

    Args:
        path: JSON dataset containing labelled pairs and Markdown probes.

    Returns:
        Parsed dataset with unique IDs and supported expected classes.

    Raises:
        ValueError: If the dataset is malformed or has an unsupported label.
        OSError: If the dataset cannot be read.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format_version") != 1 or not isinstance(data.get("cases"), list):
        raise ValueError("Phase 16 novelty dataset has an unsupported format")
    identifiers = []
    for case in data["cases"]:
        if not isinstance(case, dict) or case.get("expected") not in EXPECTED_CLASSES:
            raise ValueError("every novelty case needs a supported expected class")
        if not all(
            isinstance(case.get(key), str) and case[key]
            for key in ("id", "category", "existing", "proposed")
        ):
            raise ValueError("every novelty case needs non-empty text fields")
        identifiers.append(case["id"])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("novelty case IDs must be unique")
    return data


def percentile(values: Sequence[float], percent: float) -> float:
    """Return a deterministic linear-interpolated percentile for non-empty scores.

    Args:
        values: Numeric scores to summarize.
        percent: Percentile in the inclusive range 0 through 100.

    Returns:
        The requested interpolated percentile.

    Raises:
        ValueError: If no values exist or the requested percentile is invalid.
    """
    if not values or not 0 <= percent <= 100:
        raise ValueError("percentile requires values and a percentage from 0 through 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(values: Sequence[float]) -> dict[str, float]:
    """Summarize one labelled similarity distribution for benchmark review.

    Args:
        values: Non-empty cosine similarities from one expected class.

    Returns:
        Minimum, maximum, median, and 10th/25th/75th/90th percentile scores.
    """
    return {
        "minimum": min(values),
        "maximum": max(values),
        "median": statistics.median(values),
        "p10": percentile(values, 10),
        "p25": percentile(values, 25),
        "p75": percentile(values, 75),
        "p90": percentile(values, 90),
    }


def threshold_analysis(
    cases: Sequence[dict[str, Any]], thresholds: Sequence[float]
) -> list[dict[str, Any]]:
    """Measure conservative escalation outcomes for candidate similarity thresholds.

    A score below a threshold is the only candidate local-append path. Every score at or above
    the threshold escalates. This intentionally reports dangerous overlap false negatives rather
    than optimizing aggregate classification accuracy.

    Args:
        cases: Labelled benchmark records with cosine similarities.
        thresholds: Candidate escalation thresholds in ascending order.

    Returns:
        Per-threshold overlap recall, false-negative IDs, unnecessary independent escalations,
        and synthetic candidate-append share.
    """
    overlap = [case for case in cases if case["expected"] == "OVERLAP"]
    independent = [case for case in cases if case["expected"] == "INDEPENDENT"]
    results = []
    for threshold in thresholds:
        dangerous = [case for case in overlap if case["similarity"] < threshold]
        escalated = [case for case in independent if case["similarity"] >= threshold]
        append_candidates = [case for case in cases if case["similarity"] < threshold]
        safe_independent = [case for case in independent if case["similarity"] < threshold]
        results.append(
            {
                "threshold": threshold,
                "overlap_recall": (len(overlap) - len(dangerous)) / len(overlap),
                "dangerous_false_negative_count": len(dangerous),
                "dangerous_false_negative_ids": [case["id"] for case in dangerous],
                "independent_unnecessarily_escalated_count": len(escalated),
                "independent_unnecessarily_escalated_ids": [case["id"] for case in escalated],
                "candidate_local_append_count": len(append_candidates),
                "candidate_local_append_share": len(append_candidates) / len(cases),
                "known_independent_local_append_count": len(safe_independent),
                "known_independent_local_append_share": len(safe_independent) / len(cases),
            }
        )
    return results


def run_benchmark(data: dict[str, Any], embedder: FastEmbedTextEmbedder) -> dict[str, Any]:
    """Embed every synthetic pair and derive reviewable novelty-gate evidence.

    Args:
        data: Validated synthetic dataset.
        embedder: Existing local FastEmbed/TextEmbedder implementation.

    Returns:
        Machine-readable cases, Markdown probes, class distributions, and threshold analysis.

    Raises:
        ValueError: If the embedding runtime returns the wrong vector count.
    """
    cases = data["cases"]
    texts = [text for case in cases for text in (case["existing"], case["proposed"])]
    vectors = list(embedder.embed_documents(texts))
    if len(vectors) != len(texts):
        raise ValueError("embedding runtime returned the wrong number of novelty vectors")
    measured = []
    for index, case in enumerate(cases):
        measured.append(
            {
                **case,
                "similarity": cosine_similarity(vectors[index * 2], vectors[index * 2 + 1]),
                "exact_normalized_match": normalize_exact_duplicate(case["existing"])
                == normalize_exact_duplicate(case["proposed"]),
            }
        )
    probes = data.get("markdown_probes", [])
    probe_vectors = list(
        embedder.embed_documents(
            [text for probe in probes for text in (probe["left"], probe["right"])]
        )
    )
    if len(probe_vectors) != len(probes) * 2:
        raise ValueError("embedding runtime returned the wrong number of Markdown-probe vectors")
    measured_probes = [
        {
            **probe,
            "similarity": cosine_similarity(probe_vectors[index * 2], probe_vectors[index * 2 + 1]),
        }
        for index, probe in enumerate(probes)
    ]
    classes = {
        expected: [case for case in measured if case["expected"] == expected]
        for expected in sorted(EXPECTED_CLASSES)
    }
    return {
        "format_version": 1,
        "model_name": embedder.model_name,
        "model_version": embedder.model_version,
        "cases": measured,
        "category_counts": dict(sorted(Counter(case["category"] for case in measured).items())),
        "class_counts": {expected: len(items) for expected, items in classes.items()},
        "distributions": {
            expected: summarize([case["similarity"] for case in items])
            for expected, items in classes.items()
        },
        "lowest_similarity_overlap": sorted(
            classes["OVERLAP"], key=lambda case: case["similarity"]
        )[:5],
        "highest_similarity_independent": sorted(
            classes["INDEPENDENT"], key=lambda case: case["similarity"], reverse=True
        )[:5],
        "markdown_probes": measured_probes,
        "threshold_analysis": threshold_analysis(measured, DEFAULT_THRESHOLDS),
    }


def main() -> None:
    """Run the local-only Phase 16.2A benchmark and write deterministic JSON evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases", type=Path, default=Path(__file__).with_name("phase16_novelty_cases.json")
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("phase16_novelty_results.json")
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
