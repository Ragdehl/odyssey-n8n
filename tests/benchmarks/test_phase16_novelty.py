"""Focused deterministic checks for the Phase 16.2A novelty benchmark helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.run_phase16_novelty import (
    cosine_similarity,
    load_cases,
    normalize_exact_duplicate,
    percentile,
    threshold_analysis,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_dataset_is_small_labelled_and_covers_required_risk_categories() -> None:
    """Keep the synthetic evidence reviewable while preserving required risk coverage."""
    data = load_cases(REPOSITORY_ROOT / "benchmarks/phase16_novelty_cases.json")
    categories = {case["category"] for case in data["cases"]}

    assert 50 <= len(data["cases"]) <= 80
    assert {"OVERLAP", "INDEPENDENT"} == {case["expected"] for case in data["cases"]}
    assert {
        "exact_duplicate",
        "paraphrase_duplicate",
        "correction_contradiction",
        "temporal_update",
        "negation",
        "independent_fact",
        "related_distinct_conservative",
        "short_fact",
        "cross_language_overlap",
        "cross_language_independent",
        "date_number_change",
        "same_topic_independent",
    } <= categories


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Marta vive en Toulouse.  ", "Marta vive en Toulouse."),
        ("- Marta   vive\n en Toulouse.", "Marta vive en Toulouse."),
        ("Marta no trabaja en Airbus.", "Marta no trabaja en Airbus."),
    ],
)
def test_exact_normalization_only_removes_presentation_noise(raw: str, expected: str) -> None:
    """Allow harmless whitespace/list rendering while retaining semantic wording exactly."""
    assert normalize_exact_duplicate(raw) == expected
    assert normalize_exact_duplicate("Marta trabaja en Airbus.") != normalize_exact_duplicate(
        "Marta no trabaja en Airbus."
    )
    assert normalize_exact_duplicate("Marta trabaja en Airbus.") != normalize_exact_duplicate(
        "Marta es empleada de Airbus."
    )


def test_cosine_similarity_normalizes_runtime_vectors() -> None:
    """Use true cosine even when the embedding runtime returns non-unit vectors."""
    assert cosine_similarity([3.0, 4.0], [6.0, 8.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 2.0]) == pytest.approx(0.0)
    with pytest.raises(ValueError, match="dimensions"):
        cosine_similarity([1.0], [1.0, 0.0])


def test_threshold_analysis_reports_dangerous_overlap_false_negatives() -> None:
    """Prioritize overlap recall and expose unsafe append candidates by case ID."""
    measured = [
        {"id": "O", "expected": "OVERLAP", "similarity": 0.35},
        {"id": "I-low", "expected": "INDEPENDENT", "similarity": 0.20},
        {"id": "I-high", "expected": "INDEPENDENT", "similarity": 0.80},
    ]

    result = threshold_analysis(measured, [0.40])[0]

    assert result["overlap_recall"] == 0
    assert result["dangerous_false_negative_ids"] == ["O"]
    assert result["independent_unnecessarily_escalated_ids"] == ["I-high"]
    assert result["candidate_local_append_share"] == pytest.approx(2 / 3)


def test_percentile_is_deterministic_for_small_distributions() -> None:
    """Keep summary percentiles stable without a third-party statistics dependency."""
    assert percentile([0.1, 0.5, 0.9], 25) == pytest.approx(0.3)
