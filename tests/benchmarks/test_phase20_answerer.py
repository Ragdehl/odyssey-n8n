"""Deterministic tests for the Phase 20.1 grounded-answerer benchmark."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from benchmarks.phase20_answerer.benchmark import (
    PROMPT_VERSION,
    REPOSITORY_ROOT,
    AnswerCase,
    aggregate_rows,
    answer_schema,
    answer_system_prompt,
    checkpoint_identity,
    contract_identity,
    estimate_cost_usd,
    evaluate_case,
    load_cases,
    load_checkpoint,
    load_pricing_snapshot,
    normalize_usage,
    repository_path,
    select_cases,
    validate_answer,
    write_checkpoint,
)

CASES_PATH = Path("benchmarks/phase20_answerer/cases.json")


def test_frozen_suite_covers_required_case_families() -> None:
    """The compact suite preserves every Phase 20.1 grounding sentinel family."""
    cases = load_cases(CASES_PATH)
    ids = {case.id for case in cases}
    assert len(cases) == 12
    assert {
        "simple-single-note-es",
        "distractors-es",
        "split-evidence-es",
        "empty-retrieval-es",
        "nonempty-insufficient-es",
        "partial-usable-es",
        "french-simple",
        "exact-domain-term-fr",
        "missing-fact-no-invention-es",
        "conjunctive-person-es",
        "misleading-date-distractor-es",
        "partial-insufficient-fr",
    } == ids


def test_answer_schema_and_prompt_are_closed_and_grounded() -> None:
    """The benchmark contract stays closed and explicitly forbids outside knowledge."""
    schema = answer_schema()
    prompt = answer_system_prompt()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "outcome",
        "answer",
        "supporting_item_ids",
        "limitations",
    }
    assert "only from the supplied Odyssey evidence" in prompt
    assert "never use outside knowledge" in prompt
    assert "PARTIAL_RESULT" in prompt
    assert PROMPT_VERSION == "phase20.1-v1"


def test_valid_answer_requires_supplied_support() -> None:
    """An answer may cite only supplied evidence IDs and needs at least one citation."""
    value = validate_answer(
        {
            "outcome": "ANSWER",
            "answer": "Marta trabaja en Thales.",
            "supporting_item_ids": ["marta"],
            "limitations": [],
        },
        {"marta"},
    )
    assert value["supporting_item_ids"] == ["marta"]

    with pytest.raises(ValueError, match="unknown supporting"):
        validate_answer(
            {
                "outcome": "ANSWER",
                "answer": "x",
                "supporting_item_ids": ["invented"],
                "limitations": [],
            },
            {"marta"},
        )
    with pytest.raises(ValueError, match="requires at least one"):
        validate_answer(
            {
                "outcome": "ANSWER",
                "answer": "x",
                "supporting_item_ids": [],
                "limitations": [],
            },
            {"marta"},
        )


def test_invalid_duplicate_and_insufficient_support_fail_closed() -> None:
    """Duplicate citations and citations on insufficient outcomes are rejected."""
    with pytest.raises(ValueError, match="duplicate supporting"):
        validate_answer(
            {
                "outcome": "ANSWER",
                "answer": "x",
                "supporting_item_ids": ["marta", "marta"],
                "limitations": [],
            },
            {"marta"},
        )
    with pytest.raises(ValueError, match="cannot cite"):
        validate_answer(
            {
                "outcome": "INSUFFICIENT_EVIDENCE",
                "answer": "No hay evidencia suficiente.",
                "supporting_item_ids": ["marta"],
                "limitations": [],
            },
            {"marta"},
        )


def test_simple_case_oracle_passes_and_wrong_fragment_fails() -> None:
    """Required answer fragments and support IDs make simple regressions deterministic."""
    case = next(case for case in load_cases(CASES_PATH) if case.id == "simple-single-note-es")
    good = {
        "outcome": "ANSWER",
        "answer": "Marta trabaja en Thales.",
        "supporting_item_ids": ["marta"],
        "limitations": [],
    }
    assert evaluate_case(case, good)["passed"]

    wrong = {**good, "answer": "Marta trabaja en Airbus."}
    evaluation = evaluate_case(case, wrong)
    assert not evaluation["passed"]
    assert not evaluation["checks"]["required_fragments"]


def test_partial_cases_require_explicit_partial_limitation() -> None:
    """A usable partial result cannot silently look like a fully complete Odyssey result."""
    case = next(case for case in load_cases(CASES_PATH) if case.id == "partial-usable-es")
    response = {
        "outcome": "ANSWER",
        "answer": "Marta trabaja en Thales.",
        "supporting_item_ids": ["marta"],
        "limitations": [],
    }
    assert not evaluate_case(case, response)["checks"]["partial_limitation"]
    response["limitations"] = ["PARTIAL_RESULT"]
    assert evaluate_case(case, response)["passed"]


def test_insufficient_case_passes_without_support() -> None:
    """Empty evidence succeeds only through the explicit insufficient-evidence path."""
    case = next(case for case in load_cases(CASES_PATH) if case.id == "empty-retrieval-es")
    response = validate_answer(
        {
            "outcome": "INSUFFICIENT_EVIDENCE",
            "answer": "No tengo evidencia suficiente en Odyssey.",
            "supporting_item_ids": [],
            "limitations": [],
        },
        set(),
    )
    assert evaluate_case(case, response)["passed"]


def test_case_filter_preserves_frozen_order_and_rejects_unknown_ids() -> None:
    """Focused paid runs cannot silently reorder cases or accept a typo."""
    cases = load_cases(CASES_PATH)
    selected = select_cases(cases, ("french-simple", "simple-single-note-es"))
    assert [case.id for case in selected] == ["simple-single-note-es", "french-simple"]
    with pytest.raises(ValueError, match="unknown benchmark case ids"):
        select_cases(cases, ("missing",))


def test_loader_rejects_oracle_support_that_was_not_supplied() -> None:
    """A fixture typo cannot make invented evidence look like a valid benchmark oracle."""
    payload = {
        "cases": [
            {
                "id": "bad",
                "description": "bad oracle",
                "input": {
                    "request": "x",
                    "status": "completed",
                    "retrieval_query": "x",
                    "items": [],
                },
                "oracle": {
                    "expected_outcome": "ANSWER",
                    "required_supporting_item_ids": ["missing"],
                    "forbidden_supporting_item_ids": [],
                    "required_answer_fragments": ["x"],
                    "forbidden_answer_fragments": [],
                    "require_partial_limitation": false,
                },
            }
        ]
    }
    with TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
        path = Path(directory) / "bad-cases.json"
        path.write_text(__import__("json").dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="unknown evidence ids"):
            load_cases(path)


def test_checkpoint_identity_and_round_trip_fail_closed_on_config_change() -> None:
    """Paid rows resume only for the same cases, prompt contract, model, and reasoning."""
    with TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
        root = Path(directory)
        cases = root / "cases.json"
        output = root / "answers.json"
        cases.write_text('{"cases": []}', encoding="utf-8")
        identity = checkpoint_identity(cases, "gpt-test", "low", ("q1",))
        row = {"case": "q1", "evaluation": {"passed": True}}
        write_checkpoint(output, identity, [row], "CHECKPOINT")
        assert load_checkpoint(output, identity) == {"q1": row}

        other_model = checkpoint_identity(cases, "other-model", "low", ("q1",))
        with pytest.raises(ValueError, match="incompatible"):
            load_checkpoint(output, other_model)


def test_contract_identity_is_stable_sha256() -> None:
    """Prompt/schema identity is stable and suitable for paid-checkpoint compatibility."""
    identity = contract_identity()
    assert len(identity) == 64
    assert identity == contract_identity()


def test_normalize_usage_keeps_unavailable_metrics_explicit() -> None:
    """Provider counters are bounded and absent details remain None rather than fabricated zeroes."""
    usage = normalize_usage(
        SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            input_tokens_details=SimpleNamespace(cached_tokens=10),
            output_tokens_details=SimpleNamespace(reasoning_tokens=5),
        )
    )
    assert usage == {
        "input_tokens": 100,
        "cached_input_tokens": 10,
        "output_tokens": 20,
        "reasoning_tokens": 5,
    }
    assert normalize_usage(None) is None


def test_pricing_cost_uses_cached_rate_and_refuses_incomplete_usage() -> None:
    """Cost uses a dated external rate snapshot and stays unavailable if usage is incomplete."""
    pricing = {
        "as_of": "2026-09-06",
        "source": "official",
        "models": {
            "model": {
                "input_per_million": 0.2,
                "cached_input_per_million": 0.02,
                "output_per_million": 1.2,
            }
        },
    }
    usage = {
        "input_tokens": 1000,
        "cached_input_tokens": 200,
        "output_tokens": 100,
        "reasoning_tokens": 10,
    }
    assert estimate_cost_usd(usage, pricing, "model") == 0.000284
    assert estimate_cost_usd({**usage, "cached_input_tokens": None}, pricing, "model") is None
    assert estimate_cost_usd(usage, pricing, "missing") is None


def test_pricing_snapshot_validation_and_repository_boundary() -> None:
    """Pricing files are bounded repository inputs and malformed rate snapshots fail closed."""
    with TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
        root = Path(directory)
        pricing_path = root / "pricing.json"
        pricing_path.write_text(
            """{
  "as_of": "2026-09-06",
  "source": "official",
  "models": {
    "model": {
      "input_per_million": 0.2,
      "cached_input_per_million": 0.02,
      "output_per_million": 1.2
    }
  }
}""",
            encoding="utf-8",
        )
        assert load_pricing_snapshot(pricing_path)["models"]["model"]["output_per_million"] == 1.2

    with pytest.raises(ValueError, match="inside the repository"):
        repository_path(Path("/tmp/outside-phase20-benchmark.json"))


def test_aggregates_do_not_turn_missing_usage_or_cost_into_zero() -> None:
    """Aggregate reporting preserves unavailable provider metrics explicitly."""
    rows = [
        {
            "case": "a",
            "evaluation": {"passed": True},
            "latency_seconds": 1.0,
            "usage": None,
            "estimated_cost_usd": None,
        },
        {
            "case": "b",
            "evaluation": {"passed": False},
            "latency_seconds": 3.0,
            "usage": None,
            "estimated_cost_usd": None,
        },
    ]
    aggregate = aggregate_rows(rows)
    assert aggregate["case_count"] == 2
    assert aggregate["passed"] == 1
    assert aggregate["pass_rate"] == 0.5
    assert aggregate["average_latency_seconds"] == 2.0
    assert aggregate["total_input_tokens"] is None
    assert aggregate["total_estimated_cost_usd"] is None


def test_answer_case_dataclass_is_frozen() -> None:
    """Frozen cases cannot be mutated accidentally during benchmark iteration."""
    case = AnswerCase("id", "description", {}, {})
    with pytest.raises(AttributeError):
        case.id = "changed"  # type: ignore[misc]
