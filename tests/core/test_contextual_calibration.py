"""Tests for the canonical contextual few-shot configuration boundary."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from odyssey_core.contextual import (
    ContextualCandidate,
    ContextualResolutionRequest,
    build_openai_payload,
)
from odyssey_core.contextual_calibration import load_contextual_calibration_examples
from odyssey_runtime import composition


def test_canonical_calibration_has_exact_frozen_ten_and_a22_a19_labels() -> None:
    """The shared configuration preserves the historical ordered examples and abstentions."""
    examples = load_contextual_calibration_examples()

    assert len(examples) == 10
    assert examples[-1].request.reference == "Carrefour"
    assert examples[-1].decision.outcome == "AMBIGUOUS"
    assert examples[-1].decision.id is None
    assert any(
        example.request.reference == "Beatriz" and example.decision.outcome == "AMBIGUOUS"
        for example in examples
    )


def test_a19_and_a22_frozen_labels_remain_ambiguous() -> None:
    """Parity work must not weaken either the historical safety or collision oracle."""
    cases = json.loads(
        (
            Path(__file__).resolve().parents[2] / "benchmarks/phase11a_strong_reasoner_cases.json"
        ).read_text(encoding="utf-8")
    )["phase11a3"]["cases"]
    selected = {case["case_id"]: case for case in cases if case["case_id"] in {"A19", "A22"}}

    assert selected["A19"]["expected"] == "AMBIGUOUS"
    assert selected["A22"]["expected"] == "AMBIGUOUS"
    assert {
        candidate.id for candidate in load_contextual_calibration_examples()[-1].request.candidates
    } >= {"carrefour-balma", "carrefour-labege", "carrefour-market-capitole"}


def test_production_and_benchmark_load_the_same_calibration_source() -> None:
    """The benchmark adapter returns the same canonical examples used by production."""
    from benchmarks.run_phase11b1_openai import load_calibration_examples

    assert load_calibration_examples.__module__ == "benchmarks.run_phase11b1_openai"
    assert load_calibration_examples(None) == load_contextual_calibration_examples()
    assert "benchmarks" not in inspect.getsource(composition._build_contextual_reasoner)


def test_production_contextual_default_and_override_keep_medium_reasoning(monkeypatch) -> None:
    """Production defaults to Luna/medium while retaining the environment model override."""
    captured: list[tuple[str, str, int]] = []

    class FakeReasoner:
        def __init__(self, model, *, reasoning_effort, examples):
            captured.append((model, reasoning_effort, len(examples)))

    monkeypatch.setattr(composition, "OpenAIContextualReasoner", FakeReasoner)
    monkeypatch.delenv("ODYSSEY_CONTEXTUAL_MODEL", raising=False)
    composition._build_contextual_reasoner()
    monkeypatch.setenv("ODYSSEY_CONTEXTUAL_MODEL", "gpt-5.6-sol")
    composition._build_contextual_reasoner()

    assert captured == [("gpt-5.6-luna", "medium", 10), ("gpt-5.6-sol", "medium", 10)]


def test_shared_examples_preserve_historical_provider_payload_controls() -> None:
    """The shared prefix keeps strict output, store false, and medium reasoning semantics."""
    request = ContextualResolutionRequest(
        "Carrefour",
        "Voy a comprar comida.",
        "store",
        (ContextualCandidate("carrefour-balma", "Name: Carrefour Balma\nType: store"),),
    )
    payload = build_openai_payload(
        request,
        "gpt-5.6-sol",
        reasoning_effort="medium",
        examples=load_contextual_calibration_examples(),
    )

    assert payload["store"] is False
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["text"]["format"]["strict"] is True
    assert len(payload["input"]) == 22
