"""Offline tests for the proposed Phase 14 RequestPlan contract and v2 evaluator."""

from __future__ import annotations

import pytest

from benchmarks.phase14_request_plan.benchmark import (
    BenchmarkContractError,
    assert_schema_alignment,
    build_api_payload,
    load_cases,
    load_oracle,
    structured_output_schema,
    validate_output,
)
from benchmarks.phase14_request_plan.evaluate import evaluate_plan


def retrieve(
    query: str = "Odyssey",
    *,
    note_type: str | None = None,
    tags: list[str] | None = None,
    filters: list[dict] | None = None,
) -> dict:
    """Build one valid retrieval fixture with a Phase 13-compatible nested plan."""
    return {
        "kind": "retrieve",
        "plan": {
            "query": query,
            "type": note_type,
            "required_tags": tags or [],
            "filters": filters or [],
        },
    }


def create(content: str = "prefiero Terra") -> dict:
    """Build one deliberately minimal create-intent fixture."""
    return {"kind": "create_note", "content": content}


def output(*actions: dict, limitations: list[str] | None = None) -> dict:
    """Build a complete RequestPlan fixture."""
    return {"actions": list(actions), "limitations": limitations or []}


def test_frozen_v2_schema_cases_oracle_and_strict_schema_align() -> None:
    contract = assert_schema_alignment()
    assert len(load_cases()) == 24
    assert len(load_oracle()) == 24
    schema = structured_output_schema(contract)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["actions"]["items"]["oneOf"][0]["additionalProperties"] is False


def test_one_retrieve_action_is_valid() -> None:
    assert validate_output(output(retrieve()))["actions"][0]["kind"] == "retrieve"


def test_multiple_independent_retrieval_actions_are_valid() -> None:
    candidate = output(
        retrieve(
            "Odyssey",
            filters=[{"field": "updated_at", "op": "gte", "value": "2026-08-20T00:00:00+02:00"}],
        ),
        retrieve(
            "n8n",
            filters=[{"field": "created_at", "op": "gte", "value": "2026-08-19T00:00:00+02:00"}],
        ),
    )
    assert len(validate_output(candidate)["actions"]) == 2


def test_equivalent_branch_order_passes() -> None:
    oracle = load_oracle()["B01"]
    today = [
        {"field": "updated_at", "op": "gte", "value": "2026-08-20T00:00:00+02:00"},
        {"field": "updated_at", "op": "lt", "value": "2026-08-21T00:00:00+02:00"},
    ]
    yesterday = [
        {"field": "created_at", "op": "gte", "value": "2026-08-19T00:00:00+02:00"},
        {"field": "created_at", "op": "lt", "value": "2026-08-20T00:00:00+02:00"},
    ]
    assert (
        evaluate_plan(
            output(retrieve("n8n", filters=yesterday), retrieve("Odyssey", filters=today)), oracle
        )[0]
        == "PASS"
    )


def test_unsafe_global_conjunction_instead_of_branches_is_critical() -> None:
    oracle = load_oracle()["B03"]
    candidate = output(
        retrieve(
            "Odyssey",
            filters=[
                {"field": "created_at", "op": "gte", "value": "2026-08-19T00:00:00+02:00"},
                {"field": "created_at", "op": "lt", "value": "2026-08-20T00:00:00+02:00"},
                {"field": "updated_at", "op": "gte", "value": "2026-08-20T00:00:00+02:00"},
                {"field": "updated_at", "op": "lt", "value": "2026-08-21T00:00:00+02:00"},
            ],
        )
    )
    assert evaluate_plan(candidate, oracle)[0] == "CRITICAL"


def test_thematic_or_stays_one_semantic_action() -> None:
    assert evaluate_plan(output(retrieve("n8n o LangGraph")), load_oracle()["N01"])[0] == "PASS"


def test_shared_types_and_filters_stay_one_action() -> None:
    filters = [
        {"field": "type", "op": "in", "value": ["project", "task", "concept"]},
        {"field": "created_at", "op": "gte", "value": "2026-08-20T00:00:00+02:00"},
        {"field": "created_at", "op": "lt", "value": "2026-08-21T00:00:00+02:00"},
    ]
    assert (
        evaluate_plan(output(retrieve("Odyssey", filters=filters)), load_oracle()["N03"])[0]
        == "PASS"
    )


def test_create_only_and_mixed_request_are_valid() -> None:
    assert (
        evaluate_plan(output(create("prefiero Terra para esta prueba")), load_oracle()["C01"])[0]
        == "PASS"
    )
    assert (
        evaluate_plan(
            output(create("probar Terra para Phase 14"), retrieve("modelos anteriores")),
            load_oracle()["M01"],
        )[0]
        == "PASS"
    )


def test_no_model_generated_stable_id_or_persistence_fields() -> None:
    with pytest.raises(BenchmarkContractError):
        validate_output(
            {"actions": [{"kind": "create_note", "content": "x", "id": "bad"}], "limitations": []}
        )
    with pytest.raises(BenchmarkContractError):
        validate_output(
            {"actions": [{"kind": "create_note", "content": "x", "write": True}], "limitations": []}
        )


def test_false_hard_filter_is_critical() -> None:
    status, findings = evaluate_plan(
        output(
            retrieve(
                "Odyssey",
                filters=[
                    {"field": "created_at", "op": "gte", "value": "2026-08-20T00:00:00+02:00"}
                ],
            )
        ),
        load_oracle()["S01"],
    )
    assert status == "CRITICAL"
    assert {item["code"] for item in findings} == {
        "missing_retrieval_branch",
    }


def test_omitted_safe_filter_is_major_not_critical() -> None:
    status, findings = evaluate_plan(
        output(retrieve("niños", note_type="journal_entry")), load_oracle()["S02"]
    )
    assert status == "MAJOR"
    assert {item["code"] for item in findings} == {"missing_retrieval_branch"}


def test_semantic_wording_mismatch_is_human_review_not_critical() -> None:
    status, findings = evaluate_plan(output(retrieve("asuntos")), load_oracle()["S01"])
    assert status == "HUMAN REVIEW"
    assert all(item["severity"] != "CRITICAL" for item in findings)


def test_limitations_are_closed_and_evaluated() -> None:
    assert (
        evaluate_plan(
            output(retrieve("Odyssey", tags=["idea"]), limitations=["not_supported"]),
            load_oracle()["U01"],
        )[0]
        == "PASS"
    )
    with pytest.raises(BenchmarkContractError):
        validate_output(output(retrieve(), limitations=["tag_or"]))


def test_api_payload_is_v2_and_only_allows_staged_models() -> None:
    payload = build_api_payload("gpt-5.6-terra", "low", "common", "request")
    assert payload["store"] is False
    assert payload["text"]["format"]["name"] == "odyssey_request_plan_v2"
    with pytest.raises(BenchmarkContractError):
        build_api_payload("gpt-5.6-luna", "low", "common", "request")
