"""Deterministic checks for the optional Phase 16.2A.3 NLI benchmark helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.run_phase16_adversarial_novelty import body_units, load_cases
from benchmarks.run_phase16_nli import (
    ORACLE_UNIT_INDEX,
    aggregate,
    label_mapping,
    normalize_probabilities,
    policy_results,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_oracle_map_covers_the_reviewable_adversarial_dataset() -> None:
    """Keep every predeclared oracle index valid without downloading an NLI model."""
    scenarios = load_cases(REPOSITORY_ROOT / "benchmarks/phase16_adversarial_novelty_cases.json")[
        "scenarios"
    ]
    assert set(ORACLE_UNIT_INDEX) == {item["id"] for item in scenarios}
    assert all(
        ORACLE_UNIT_INDEX[item["id"]] < len(body_units(item["note_body"])) for item in scenarios
    )


def test_model_label_mapping_requires_the_real_nli_classes() -> None:
    """Reject generic classifier configurations instead of guessing an output-label order."""
    assert label_mapping({0: "entailment", 1: "neutral", 2: "contradiction"}) == {
        0: "entailment",
        1: "neutral",
        2: "contradiction",
    }
    with pytest.raises(ValueError, match="entailment"):
        label_mapping({0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"})


def test_probability_normalization_and_bidirectional_aggregation_are_explicit() -> None:
    """Retain all probabilities and aggregate conservatively across directions/candidates."""
    assert normalize_probabilities([0.2, 0.7, 0.1])["neutral"] == pytest.approx(0.7)
    with pytest.raises(ValueError, match="sum"):
        normalize_probabilities([0.2, 0.7, 0.2])
    result = aggregate(
        [
            {
                "max_entailment": 0.1,
                "max_contradiction": 0.2,
                "max_non_neutral": 0.2,
                "min_neutral": 0.8,
            },
            {
                "max_entailment": 0.3,
                "max_contradiction": 0.1,
                "max_non_neutral": 0.3,
                "min_neutral": 0.7,
            },
        ]
    )
    assert result == {
        "max_entailment": 0.3,
        "max_contradiction": 0.2,
        "max_non_neutral": 0.3,
        "min_neutral": 0.7,
    }


def test_policy_results_expose_dangerous_overlap_candidates() -> None:
    """Preserve safety-oriented IDs instead of reporting only aggregate accuracy."""
    records = [
        {
            "id": "O",
            "expected": "OVERLAP",
            "evidence": {"min_neutral": 0.9, "max_entailment": 0.01, "max_contradiction": 0.01},
        },
        {
            "id": "I",
            "expected": "INDEPENDENT",
            "evidence": {"min_neutral": 0.9, "max_entailment": 0.01, "max_contradiction": 0.01},
        },
    ]
    assert policy_results(records)[0]["dangerous_false_independent_ids"] == ["O"]


def test_benchmark_does_not_add_a_production_nli_import() -> None:
    """Keep optional Transformers use confined to the benchmark-local experiment file."""
    production = (REPOSITORY_ROOT / "odyssey_core/semantic.py").read_text(encoding="utf-8")
    assert "AutoModelForSequenceClassification" not in production
