"""Tests for the deterministic Phase 14 retrieval-plan benchmark harness."""

from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks.phase14_retrieval_plan.benchmark import (
    PRICING_PATH,
    BenchmarkContractError,
    assert_schema_alignment,
    build_api_payload,
    estimated_cost,
    load_cases,
    load_json,
    load_oracle,
    sanitize_error,
    structured_output_schema,
    validate_output,
)
from benchmarks.phase14_retrieval_plan.evaluate import evaluate_plan, select_recommendation


def output(
    *,
    query: str = "Odyssey",
    note_type: str | None = None,
    tags: list[str] | None = None,
    filters: list[dict] | None = None,
    unrepresented: list[str] | None = None,
) -> dict:
    """Build one complete generated-output fixture with explicit safe defaults."""
    return {
        "plan": {
            "query": query,
            "type": note_type,
            "required_tags": tags or [],
            "filters": filters or [],
        },
        "unrepresented_constraints": unrepresented or [],
    }


def test_frozen_schema_cases_and_oracle_are_complete() -> None:
    contract = assert_schema_alignment()
    assert contract["canonical_subtypes"] == []
    assert set(contract["filterable_fields"]) == {
        "type",
        "subtype",
        "created_at",
        "updated_at",
        "aliases",
        "tags",
        "birth_date",
        "relationship_to_user",
        "entry_date",
    }
    assert len(load_cases()) == 45
    assert len(load_oracle()) == 45


def test_structured_schema_is_strict_and_uses_op() -> None:
    schema = structured_output_schema(assert_schema_alignment())
    filter_schema = schema["properties"]["plan"]["properties"]["filters"]["items"]
    assert filter_schema["additionalProperties"] is False
    assert filter_schema["required"] == ["field", "op", "value"]
    assert "operator" not in filter_schema["properties"]


def test_local_validation_rejects_invalid_operator_and_unregistered_subtype() -> None:
    invalid_operator = output(filters=[{"field": "created_at", "op": "contains", "value": "x"}])
    with pytest.raises(BenchmarkContractError, match="Unsupported operator"):
        validate_output(invalid_operator)
    invalid_subtype = output(filters=[{"field": "subtype", "op": "eq", "value": "system"}])
    with pytest.raises(BenchmarkContractError, match="No canonical subtype"):
        validate_output(invalid_subtype)


def test_t11_correct_created_at_plan_passes() -> None:
    oracle = load_oracle()["T11"]
    candidate = output(
        query="niños",
        note_type="journal_entry",
        filters=[
            {"field": "created_at", "op": "gte", "value": "2026-08-19T00:00:00+02:00"},
            {"field": "created_at", "op": "lt", "value": "2026-08-20T00:00:00+02:00"},
        ],
    )
    assert evaluate_plan(candidate, oracle) == ("PASS", [])


def test_every_oracle_expectation_is_executable_and_self_consistent() -> None:
    for oracle in load_oracle().values():
        expected = oracle["expected"]
        type_values = expected["types"]
        note_type = type_values[0] if type_values is not None and len(type_values) == 1 else None
        filters = deepcopy(expected["filters"])
        if type_values is not None and len(type_values) > 1:
            filters.append({"field": "type", "op": "in", "value": type_values})
        candidate = output(
            query=" | ".join(group[0] for group in expected["query_groups"]) or "retrieval",
            note_type=note_type,
            tags=expected["required_tags"],
            filters=filters,
            unrepresented=[" | ".join(group[0] for group in expected["unrepresented_groups"])]
            if expected["unrepresented_groups"]
            else [],
        )
        assert evaluate_plan(candidate, oracle) == ("PASS", []), oracle["id"]


def test_t11_wrong_entry_date_is_critical() -> None:
    oracle = load_oracle()["T11"]
    candidate = output(
        query="niños",
        note_type="journal_entry",
        filters=[{"field": "entry_date", "op": "eq", "value": "2026-08-19"}],
    )
    status, findings = evaluate_plan(candidate, oracle)
    assert status == "CRITICAL"
    assert "unexpected_hard_filter" in {item["code"] for item in findings}


def test_equivalent_date_filter_alternative_passes() -> None:
    oracle = load_oracle()["T12"]
    candidate = output(
        query="niños",
        note_type="journal_entry",
        filters=[
            {"field": "entry_date", "op": "gte", "value": "2026-08-19"},
            {"field": "entry_date", "op": "lt", "value": "2026-08-20"},
        ],
    )
    assert evaluate_plan(candidate, oracle) == ("PASS", [])


def test_missing_safe_filter_is_major_but_extra_tag_is_critical() -> None:
    oracle = load_oracle()["T05"]
    missing_status, _ = evaluate_plan(output(query="Odyssey Raspberry"), oracle)
    assert missing_status == "MAJOR"
    extra_status, findings = evaluate_plan(
        output(query="Odyssey Raspberry", tags=["review"]), oracle
    )
    assert extra_status == "CRITICAL"
    assert "false_required_tag" in {item["code"] for item in findings}


def test_equivalent_type_and_tag_filters_are_scored_semantically() -> None:
    oracle = load_oracle()["T38"]
    candidate = output(
        query="Odyssey",
        filters=[
            {"field": "tags", "op": "contains", "value": "question"},
            {"field": "tags", "op": "contains", "value": "review"},
        ],
    )
    assert evaluate_plan(candidate, oracle) == ("PASS", [])


def test_tag_or_converted_to_and_is_recall_threatening() -> None:
    oracle = load_oracle()["T15"]
    candidate = output(
        query="ideas y decisiones Odyssey",
        tags=["idea", "decision"],
        unrepresented=["tag idea OR tag decision no se puede representar"],
    )
    status, findings = evaluate_plan(candidate, oracle)
    assert status == "CRITICAL"
    assert "false_required_tag" in {item["code"] for item in findings}


def test_scoped_filter_applied_globally_is_critical() -> None:
    oracle = load_oracle()["T22"]
    candidate = output(
        query="documentos personas alquiler actualizados relacionados",
        filters=[
            {"field": "type", "op": "in", "value": ["person", "document"]},
            {"field": "updated_at", "op": "gte", "value": "2026-08-17T00:00:00+02:00"},
        ],
        unrepresented=["updated_at applies only to document branch"],
    )
    status, findings = evaluate_plan(candidate, oracle)
    assert status == "CRITICAL"
    assert "unexpected_hard_filter" in {item["code"] for item in findings}


def test_entity_name_cannot_become_alias_filter() -> None:
    oracle = load_oracle()["T30"]
    candidate = output(
        query="Ody", filters=[{"field": "aliases", "op": "contains", "value": "Ody"}]
    )
    assert evaluate_plan(candidate, oracle)[0] == "CRITICAL"


def test_payload_contains_exactly_one_case_and_stable_prompt_prefix() -> None:
    prompt = "stable common prompt"
    first = build_api_payload("gpt-5.6-luna", "none", prompt, "request one")
    second = build_api_payload("gpt-5.6-luna", "none", prompt, "request two")
    assert first["input"][0] == second["input"][0]
    assert first["input"][1]["content"] == "request one"
    assert second["input"][1]["content"] == "request two"
    assert len(first["input"]) == 2
    assert first["text"]["format"]["strict"] is True


def test_cost_uses_cached_and_cache_write_counters() -> None:
    pricing = load_json(PRICING_PATH)
    usage = {
        "input_tokens": 1000,
        "cached_input_tokens": 400,
        "cache_write_tokens": 200,
        "output_tokens": 100,
    }
    assert estimated_cost("gpt-5.6-luna", usage, pricing) == pytest.approx(0.000258)


def test_error_sanitization_removes_key_shaped_values() -> None:
    fake_key = "sk-" + "example_secret_123456789"
    rendered = sanitize_error(RuntimeError(f"authorization {fake_key} failed"))
    assert "sk-example" not in rendered
    assert "[REDACTED_API_KEY]" in rendered


def test_recommendation_obeys_safety_quality_cost_order() -> None:
    template = {
        "complete": True,
        "critical": 0,
        "human_review": 0,
        "major": 0,
        "minor": 0,
        "estimated_cost_usd": 1.0,
        "mean_latency_seconds": 1.0,
    }
    summaries = {
        "unsafe": {**template, "critical": 1, "estimated_cost_usd": 0.01},
        "more_major": {**template, "major": 1, "estimated_cost_usd": 0.1},
        "safe_cheap": {**template, "estimated_cost_usd": 0.2},
        "safe_expensive": {**template, "estimated_cost_usd": 2.0},
    }
    assert select_recommendation(deepcopy(summaries)) == "safe_cheap"
