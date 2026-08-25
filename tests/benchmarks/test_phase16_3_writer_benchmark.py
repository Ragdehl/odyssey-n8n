"""Regression coverage for frozen Phase 16.3 writer benchmark mechanics."""

from __future__ import annotations

from benchmarks.phase16_3_writer_benchmark.benchmark import load_cases, writer_json_schema
from benchmarks.phase16_3_writer_benchmark.evaluate import evaluate_output


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
