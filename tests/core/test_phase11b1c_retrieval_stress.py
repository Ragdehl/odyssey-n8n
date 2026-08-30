"""Deterministic guards for the bounded Phase 11B.1c retrieval stress fixture."""
# ruff: noqa: E402

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.skip(reason="Historical corpus fixture predates Phase 17E schema")

from benchmarks.run_phase11b1c_retrieval_stress import (
    NOTE_COUNT,
    create_vault,
    exact_unique_ids,
    generated_specs,
    metrics,
    rrf,
)
from odyssey_core.notes import parse_note, validate_note

ROOT = Path(__file__).resolve().parents[2]


def test_stress_corpus_is_deterministic_schema_valid_diverse_and_unique(tmp_path: Path) -> None:
    """Keep the generated corpus at 1,000 valid unique notes spanning every canonical type."""
    specs = create_vault(tmp_path)
    schema = json.loads((ROOT / "config" / "note-schema.json").read_text(encoding="utf-8"))
    markdown_paths = sorted(tmp_path.rglob("*.md"))

    assert len(specs) == NOTE_COUNT
    assert len(markdown_paths) == NOTE_COUNT
    assert len({spec.id for spec in specs}) == NOTE_COUNT
    assert {spec.type for spec in specs} == {definition["id"] for definition in schema["types"]}
    assert generated_specs() == specs
    for path in markdown_paths:
        validate_note(parse_note(path.read_text(encoding="utf-8")), schema)


def test_query_truth_is_frozen_and_targets_preexist_measurement() -> None:
    """Require the compact multilingual truth set to reference frozen generated targets."""
    fixture = json.loads(
        (ROOT / "benchmarks" / "phase11b1c_retrieval_queries.json").read_text(encoding="utf-8")
    )
    queries = fixture["queries"]
    target_ids = {spec.id for spec in generated_specs()}

    assert fixture["frozen_before_measurement"] is True
    assert len(queries) == 40
    assert len({query["id"] for query in queries}) == 40
    assert {query["language"] for query in queries} == {"en", "es", "fr"}
    assert {query["category"] for query in queries} == {
        "literal",
        "alias",
        "semantic_paraphrase",
        "synonym_mismatch",
        "polysemy",
    }
    assert all(query["expected_id"] in target_ids for query in queries)


def test_rrf_unions_sources_with_deterministic_ties() -> None:
    """Fuse evidence sources deterministically without losing source-only candidates."""
    assert rrf(["dense", "shared"], ["lexical", "shared"]) == [
        "shared",
        "dense",
        "lexical",
    ]


def test_contextual_only_partition_excludes_unique_exact_names_and_aliases() -> None:
    """Keep exact/alias short-circuits out of contextual retrieval measurements."""
    fixture = json.loads(
        (ROOT / "benchmarks" / "phase11b1c_retrieval_queries.json").read_text(encoding="utf-8")
    )
    contextual_only = [
        query
        for query in fixture["queries"]
        if exact_unique_ids(generated_specs(), query) != {query["expected_id"]}
    ]
    assert len(contextual_only) == 25
    assert {query["category"] for query in contextual_only} == {
        "polysemy",
        "semantic_paraphrase",
        "synonym_mismatch",
    }


def test_metrics_include_broad_recall_cutoffs() -> None:
    """Expose the broad retrieval cutoffs required by the viability experiment."""
    result = metrics(
        [
            {
                "expected_id": "target",
                "ranking": ["target"],
                "language": "en",
                "category": "literal",
                "mismatch": False,
            }
        ]
    )["overall"]
    assert result["recall_at_20"] == 1.0
    assert result["recall_at_50"] == 1.0
    assert result["recall_at_100"] == 1.0
