"""Regression coverage for frozen Phase 16.3 writer benchmark mechanics."""

from __future__ import annotations

import json

from benchmarks.phase16_3_writer_benchmark.adjudication import canonical_records
from benchmarks.phase16_3_writer_benchmark.benchmark import load_cases, writer_json_schema
from benchmarks.phase16_3_writer_benchmark.evaluate import evaluate_output
from benchmarks.phase16_3_writer_benchmark.minilm_cases import load_pipeline_cases
from benchmarks.phase16_3_writer_benchmark.minilm_retrieval import (
    classify_pipeline,
    exact_body_units,
    render_retrieved_context,
)
from benchmarks.phase16_3_writer_benchmark.run_benchmark import _planned_call_metadata
from benchmarks.phase16_3_writer_benchmark.supplemental import load_supplemental_cases


def test_frozen_cases_cover_cost_first_experiment_shape() -> None:
    """Keep the benchmark at sixty synthetic cases with twelve reduced-context probes."""
    cases = load_cases()
    assert len(cases) == 60
    assert len([case for case in cases if case["mode"] == "CREATE"]) == 15
    assert len([case for case in cases if "reduced_context" in case]) == 12


def test_update_requires_an_exact_non_oversized_anchor() -> None:
    """Reject paraphrased or broad replacement spans even if a model schema validates them."""
    case = next(case for case in load_cases() if case["id"] == "U04_employer_update")
    status, findings = evaluate_output(
        {
            "operations": [
                {
                    "op": "REPLACE",
                    "old": "Marta es empleada de Airbus.",
                    "new": "Marta trabaja en Thales desde enero.",
                }
            ]
        },
        case,
    )
    assert status == "CRITICAL"
    assert findings[0]["code"] == "unsafe_missing_exact_anchor"


def test_no_change_cannot_be_combined_with_a_mutation() -> None:
    """Keep no-op semantics unambiguous for later Core application."""
    case = next(case for case in load_cases() if case["id"] == "U01_exact_duplicate")
    status, findings = evaluate_output(
        {"operations": [{"op": "NO_CHANGE"}, {"op": "APPEND", "text": "- Incorrecto."}]}, case
    )
    assert status == "CRITICAL"
    assert "no_change_combined" in {item["code"] for item in findings}


def test_closed_schema_exposes_only_bounded_operations() -> None:
    """Ensure the provider cannot receive an unconstrained whole-note rewrite alternative."""
    encoded = str(writer_json_schema())
    assert "CREATE_BODY" in encoded
    assert "whole_note" not in encoded


def test_supplemental_suite_is_frozen_long_context_coverage() -> None:
    """Keep the separately frozen suite at twelve cases with genuine long-note coverage."""
    cases = load_supplemental_cases()
    factual = [case for case in cases if case["id"].startswith("L")]
    very_long = [case for case in cases if case["id"].startswith("VL")]
    assert len(cases) == 12
    assert len(factual) >= 8
    assert all(40 <= case["factual_unit_count"] <= 60 for case in factual[:8])
    assert [case["word_count"] for case in very_long] == [2783, 2808]
    assert {case["target_position"] for case in cases} >= {
        "beginning",
        "25_percent",
        "50_percent",
        "75_percent",
        "near_end",
    }
    assert len([case for case in cases if "reduced_context" in case]) == 8


def test_integrity_preserves_malformed_and_duplicate_spend(tmp_path) -> None:
    """Select the first valid call while retaining malformed and duplicate accounting evidence."""
    rows = [
        {
            "case_id": "L01",
            "context_strategy": "FULL_NOTE",
            "usage": {"input_tokens": 4},
            "estimated_cost_usd": 0.1,
        },
        {
            "case_id": "L01",
            "context_strategy": "FULL_NOTE",
            "usage": {"input_tokens": 5},
            "estimated_cost_usd": 0.2,
        },
    ]
    raw = tmp_path / "raw.jsonl"
    raw.write_text("\n".join(json.dumps(row) for row in rows) + "\nnot-json\n")
    selected, metadata = canonical_records(raw)
    assert len(selected) == 1
    assert metadata["malformed_raw_lines"] == [3]
    assert metadata["duplicate_effective_calls"][0]["line"] == 2
    assert metadata["actual_cost"]["input_tokens"] == 9
    assert metadata["actual_cost"]["estimated_cost_usd"] == 0.3


def test_future_luna_metadata_counts_full_and_reduced_calls() -> None:
    """Expose every planned Luna context variant instead of silently counting full notes only."""
    plan = _planned_call_metadata(load_cases(), "luna")
    assert plan["planned_full_note_calls"] == 60
    assert plan["planned_reduced_context_calls"] == 12
    assert plan["planned_total_calls"] == 72
    assert plan["context_strategies"] == ["FULL_NOTE", "REDUCED_CONTEXT"]


def test_minilm_fragments_preserve_exact_authoritative_anchor_and_hide_oracle() -> None:
    """Keep exact mutation spans separate from label-free retrieval input fields."""
    primary, _ = load_pipeline_cases()
    case = next(item for item in primary if item["id"] == "L03_buried_update_end")
    assert case["target_fragment"] in exact_body_units(case["current_body"])
    assert "target_fragment" not in {"current_body", "facts", "identity", "note_type"}
    context = render_retrieved_context(
        case,
        {"fragments": [{"exact_text": "- Diego trabaja en Airbus en planificación industrial."}]},
    )
    assert context == case["target_fragment"]


def test_pipeline_stage_separates_missing_evidence_from_writer_contract() -> None:
    """Do not attribute a missing required fragment to Luna's semantic writer."""
    assert (
        classify_pipeline(
            {"target_fragment": "x"},
            rank=6,
            semantic_status="MATERIAL_FAIL",
            taxonomy="C. SEMANTIC_RELATION",
        )
        == "RETRIEVAL_FAIL"
    )
    assert (
        classify_pipeline(
            {"target_fragment": "x"},
            rank=1,
            semantic_status="MATERIAL_FAIL",
            taxonomy="A. OPERATION_CONTRACT",
        )
        == "CONTRACT_FAIL"
    )
