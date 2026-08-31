"""Deterministic contract tests for the Phase 17E retrieval benchmark."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from benchmarks.phase17e_retrieval.benchmark import (
    TIER_TARGETS,
    QueryCase,
    _metric_table,
    build_corpus,
    load_cases,
    query_cases,
    run_strategy,
    validate_scale_oracles,
)

ROOT = Path(__file__).resolve().parents[2]


class KeywordEmbedder:
    """Map benchmark vocabulary to a stable vector space without model downloads."""

    model_name = "tests/phase17e-keywords"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed document projections using deterministic keyword dimensions."""
        return [self._embed(text) for text in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed query text using the same deterministic keyword dimensions."""
        return [self._embed(text) for text in texts]

    @staticmethod
    def _embed(text: str) -> list[float]:
        """Produce a small normalized-compatible vector for fixture assertions."""
        value = text.casefold()
        return [
            float("thales" in value),
            float("airbus" in value),
            float("lyon" in value),
            float("paris" in value),
            float("xavi" in value),
            float("maps" in value),
            float("markdown" in value),
            float("balma" in value),
            float("claire" in value),
            0.1,
        ]


def test_corpus_is_schema_valid_and_whole_projection_is_production_projection() -> None:
    """Build all frozen notes and preserve the exact current context projection contract."""
    data = load_cases(ROOT / "benchmarks/phase17e_retrieval/cases.json")
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    corpus = build_corpus(data, schema)
    assert len(corpus) == 8
    assert all("Name: " in item.whole_text and "Type: " in item.whole_text for item in corpus)
    assert all(item.facts for item in corpus)
    assert "Fact:" not in corpus[0].whole_text


def test_fact_projection_retains_identity_and_entity_metrics_deduplicate_units() -> None:
    """Fact ranking exposes multiple units while entity recall counts each note once."""
    data = load_cases(ROOT / "benchmarks/phase17e_retrieval/cases.json")
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    corpus = build_corpus(data, schema)
    cases = query_cases(data)
    result = run_strategy(corpus, cases, KeywordEmbedder(), "fact_level")
    assert result["unit_count"] > result["entity_count"]
    assert result["metrics"]["entity"]["20"] == 1.0
    assert result["metrics"]["fact"]["20"] == 1.0
    assert result["vector_count"] == result["unit_count"]
    assert all(item["fact"] for item in result["rankings"][0][:5])


def test_three_strategy_outputs_are_comparable_and_fusion_is_deterministic() -> None:
    """Use the same cases and model boundary for all arms with stable fused ordering."""
    data = load_cases(ROOT / "benchmarks/phase17e_retrieval/cases.json")
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    corpus = build_corpus(data, schema)
    cases = query_cases(data)
    whole = run_strategy(corpus, cases, KeywordEmbedder(), "whole_note")
    first = run_strategy(corpus, cases, KeywordEmbedder(), "combined")
    second = run_strategy(corpus, cases, KeywordEmbedder(), "combined")
    assert whole["unit_count"] == whole["entity_count"] == 8
    assert first["rankings"] == second["rankings"]
    assert first["metrics"]["entity"]["20"] == 1.0


def test_unique_entity_top_k_scans_past_repeated_fact_units_and_fact_oracle_is_optional() -> None:
    """Separate raw-unit Top-K from true unique-entity Top-K and omit unlabelled facts."""
    case = QueryCase("q", "q", ("target",), (), "test", "short")
    ranking = [
        [("same", "a"), ("same", "b"), ("same", "c"), ("same", "d"), ("same", "e"), ("target", "f")]
    ]
    metrics = _metric_table(ranking, (case,))
    assert metrics["unit"]["5"] == 0.0
    assert metrics["entity"]["5"] == 1.0
    assert metrics["fact"]["5"] is None


def test_scale_corpus_has_meaningful_cutoffs_and_controlled_dilution_tiers() -> None:
    """Keep the stress corpus schema-valid and exercise note/fact length tiers."""
    data = load_cases(ROOT / "benchmarks/phase17e_retrieval/cases.json")
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    corpus = build_corpus(data, schema, scale_size=1000)
    assert len(corpus) == 1000
    assert [len(corpus[index].facts) for index in (8, 9, 10)] == [21, 51, 101]
    lengths = [len(TIER_TARGETS[tier].split()) for tier in ("medium", "long", "very-long")]
    assert lengths[0] >= 40 and lengths[1] >= 80 and lengths[2] >= 150
    validate_scale_oracles(corpus, query_cases(data, scale_size=1000))
