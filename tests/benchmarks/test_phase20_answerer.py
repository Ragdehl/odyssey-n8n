"""Deterministic tests for the Phase 20.1 grounded-answerer benchmark."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from benchmarks.phase20_answerer.benchmark import (
    PROMPT_VERSION,
    REPOSITORY_ROOT,
    aggregate_rows,
    answer_schema,
    answer_system_prompt,
    contract_identity,
    estimate_cost_usd,
    evaluate_case,
    load_cases,
    load_pricing_snapshot,
    normalize_usage,
    provider_request,
    repository_path,
    run_identity,
    select_cases,
    validate_answer,
)

CASES_PATH = Path("benchmarks/phase20_answerer/cases.json")


def test_frozen_suite_covers_required_case_families() -> None:
    """The compact suite preserves every Phase 20.1 grounding sentinel family."""
    ids = {case.id for case in load_cases(CASES_PATH)}
    assert ids == {
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
    }


def test_answer_schema_and_prompt_are_closed_and_grounded() -> None:
    """The model contract stays closed and explicitly forbids outside knowledge."""
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


def test_provider_request_is_provider_neutral_and_never_stores() -> None:
    """20.1A freezes the exact request payload without calling a provider."""
    case = next(case for case in load_cases(CASES_PATH) if case.id == "simple-single-note-es")
    payload = provider_request(case)
    assert payload["store"] is False
    assert payload["input"][0] == {"role": "system", "content": answer_system_prompt()}
    assert json.loads(payload["input"][1]["content"]) == case.input
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"] == answer_schema()


def test_answer_validation_requires_known_unique_support() -> None:
    """Answers need supplied support while invented or duplicate IDs fail closed."""
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


def test_insufficient_evidence_cannot_cite_support() -> None:
    """The explicit insufficient path cannot disguise a grounded factual answer."""
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


def test_case_oracles_cover_fragments_distractors_and_partial_status() -> None:
    """Frozen oracles detect wrong content, distractor support, and lost partial state."""
    cases = {case.id: case for case in load_cases(CASES_PATH)}
    simple = {
        "outcome": "ANSWER",
        "answer": "Marta trabaja en Thales.",
        "supporting_item_ids": ["marta"],
        "limitations": [],
    }
    assert evaluate_case(cases["simple-single-note-es"], simple)["passed"]
    assert not evaluate_case(
        cases["simple-single-note-es"], {**simple, "answer": "Marta trabaja en Airbus."}
    )["passed"]

    partial = {**simple, "limitations": []}
    assert not evaluate_case(cases["partial-usable-es"], partial)["passed"]
    partial["limitations"] = ["PARTIAL_RESULT"]
    assert evaluate_case(cases["partial-usable-es"], partial)["passed"]

    conjunctive = {
        "outcome": "ANSWER",
        "answer": "Marta.",
        "supporting_item_ids": ["marta", "alice"],
        "limitations": [],
    }
    assert not evaluate_case(cases["conjunctive-person-es"], conjunctive)["checks"][
        "forbidden_support"
    ]


def test_empty_evidence_passes_only_as_explicit_insufficient() -> None:
    """Empty retrieval has a deterministic safe outcome with no evidence citations."""
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


def test_case_filter_preserves_order_and_rejects_unknown_ids() -> None:
    """Focused live runs cannot silently reorder cases or accept a typo."""
    cases = load_cases(CASES_PATH)
    selected = select_cases(cases, ("french-simple", "simple-single-note-es"))
    assert [case.id for case in selected] == ["simple-single-note-es", "french-simple"]
    with pytest.raises(ValueError, match="unknown benchmark case ids"):
        select_cases(cases, ("missing",))


def test_loader_rejects_oracle_support_and_duplicate_paths() -> None:
    """Fixture mistakes cannot violate stable note identity or invent benchmark evidence."""
    base = {
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
            "require_partial_limitation": False,
        },
    }
    with TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
        path = Path(directory) / "bad-cases.json"
        path.write_text(json.dumps({"cases": [base]}), encoding="utf-8")
        with pytest.raises(ValueError, match="unknown evidence ids"):
            load_cases(path)

        duplicate_path = json.loads(json.dumps(base))
        duplicate_path["input"]["items"] = [
            {"id": "a", "type": "person", "path": "people/A.md", "content": "A."},
            {"id": "b", "type": "person", "path": "people/A.md", "content": "B."},
        ]
        duplicate_path["oracle"]["required_supporting_item_ids"] = ["a"]
        path.write_text(json.dumps({"cases": [duplicate_path]}), encoding="utf-8")
        with pytest.raises(ValueError, match="duplicate canonical note paths"):
            load_cases(path)


def test_run_identity_changes_with_model_config_and_contract() -> None:
    """20.1B can key paid evidence to exact cases, model, reasoning, and prompt/schema."""
    first = run_identity("gpt-test", "low", ("simple-single-note-es",))
    assert first["contract_sha256"] == contract_identity()
    assert len(first["cases_sha256"]) == 64
    assert first != run_identity("other-model", "low", ("simple-single-note-es",))
    assert first != run_identity("gpt-test", "medium", ("simple-single-note-es",))


def test_contract_identity_is_stable_sha256() -> None:
    """Prompt/schema identity is stable and suitable for live-evidence compatibility."""
    identity = contract_identity()
    assert len(identity) == 64
    assert identity == contract_identity()


def test_usage_and_cost_keep_unavailable_values_explicit() -> None:
    """Token counters and cost never manufacture provider metrics that were not supplied."""
    usage = normalize_usage(
        SimpleNamespace(
            input_tokens=1000,
            output_tokens=100,
            input_tokens_details=SimpleNamespace(cached_tokens=200),
            output_tokens_details=SimpleNamespace(reasoning_tokens=10),
        )
    )
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
    assert usage == {
        "input_tokens": 1000,
        "cached_input_tokens": 200,
        "output_tokens": 100,
        "reasoning_tokens": 10,
    }
    assert estimate_cost_usd(usage, pricing, "model") == 0.000284
    assert estimate_cost_usd({**usage, "cached_input_tokens": None}, pricing, "model") is None
    assert normalize_usage(None) is None


def test_pricing_snapshot_and_repository_path_fail_closed() -> None:
    """Pricing is dated benchmark input and internal test paths cannot escape the repository."""
    with TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
        path = Path(directory) / "pricing.json"
        path.write_text(
            json.dumps(
                {
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
            ),
            encoding="utf-8",
        )
        snapshot = load_pricing_snapshot(path)
        assert snapshot is not None
        assert snapshot["models"]["model"]["output_per_million"] == 1.2

    with pytest.raises(ValueError, match="inside the repository"):
        repository_path(Path("/tmp/outside-phase20-benchmark.json"))


def test_aggregates_keep_missing_usage_and_cost_as_none() -> None:
    """Aggregate reporting preserves unavailable metrics instead of treating them as zero."""
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
