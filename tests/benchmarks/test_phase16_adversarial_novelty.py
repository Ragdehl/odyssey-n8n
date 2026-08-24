"""Focused deterministic checks for the Phase 16.2A.2 adversarial benchmark."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.run_phase16_adversarial_novelty import adjacent_blocks, body_units, load_cases

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_adversarial_dataset_is_separate_and_covers_required_risks() -> None:
    """Keep the larger adversarial evidence synthetic, labelled, and reviewable."""
    data = load_cases(REPOSITORY_ROOT / "benchmarks/phase16_adversarial_novelty_cases.json")
    categories = {item["category"] for item in data["scenarios"]}

    assert 40 <= len(data["scenarios"]) <= 70
    assert {"OVERLAP", "INDEPENDENT"} == {item["expected"] for item in data["scenarios"]}
    assert {
        "buried_exact_duplicate",
        "buried_value_update",
        "same_topic_independent",
        "cross_language_independent",
        "raw_request_update",
        "raw_request_multiple",
    } <= categories
    assert any(item.get("raw_request") for item in data["scenarios"])


def test_body_units_keep_simple_facts_and_ignore_heading_presentation() -> None:
    """Use only deterministic list, paragraph, and plain-line body projections."""
    markdown = (
        "# Marta\n\n- Vive en Toulouse.\n- Trabaja en Airbus.\n\nTiene un perro\nllamado Sol."
    )

    assert body_units(markdown) == [
        "Vive en Toulouse.",
        "Trabaja en Airbus.",
        "Tiene un perro llamado Sol.",
    ]


def test_adjacent_blocks_use_only_two_source_ordered_units() -> None:
    """Make the block strategy inspect adjacent two-unit windows without chunking machinery."""
    assert adjacent_blocks(["uno", "dos", "tres"]) == ["uno\ndos", "dos\ntres"]
    assert adjacent_blocks(["uno"]) == ["uno"]
    assert adjacent_blocks([]) == []


def test_body_units_reject_non_text_input() -> None:
    """Fail clearly rather than coercing an invalid Markdown body."""
    with pytest.raises(TypeError, match="Markdown body"):
        body_units(None)  # type: ignore[arg-type]
