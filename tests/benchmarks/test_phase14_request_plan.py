"""Offline tests for the proposed Phase 14 RequestPlan contract and v2 evaluator."""

from __future__ import annotations

import pytest

from benchmarks.phase14_request_plan.benchmark import (
    BenchmarkContractError,
    assert_schema_alignment,
    build_api_payload,
    load_cases,
    load_oracle,
    render_prompt,
    structured_output_schema,
    validate_output,
)
from benchmarks.phase14_request_plan.evaluate import _effective_types, evaluate_plan


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
    alternatives = schema["properties"]["actions"]["items"]["oneOf"][0]["properties"]["plan"][
        "properties"
    ]["filters"]["items"]["oneOf"]
    aliases = [item for item in alternatives if item["properties"]["field"]["const"] == "aliases"]
    assert [item["properties"]["op"]["const"] for item in aliases] == ["contains"]
    assert load_oracle()["S01"]["expected"]


def test_every_locked_oracle_case_has_a_valid_passing_reference_plan() -> None:
    for oracle in load_oracle().values():
        expected = oracle["expected"]
        retrievals = []
        for branch in expected["retrieve"]:
            types = branch.get("types", branch.get("type", []))
            filters = [
                {"field": field, "op": op, "value": value}
                for field, op, value in branch.get("filters", [])
            ]
            note_type = types[0] if len(types) == 1 else None
            if len(types) > 1:
                filters.insert(0, {"field": "type", "op": "in", "value": types})
            retrievals.append(
                retrieve(
                    " ".join(group[0] for group in branch.get("query_groups", [])) or "retrieval",
                    note_type=note_type,
                    tags=branch.get("tags", []),
                    filters=filters,
                )
            )
        creates = [
            create(
                " ".join(group[0] for group in expected.get("create_content_groups", []))
                or "content"
            )
            for _ in range(expected["create_count"])
        ]
        actions = retrievals + creates
        if expected.get("action_kinds") == ["create_note", "retrieve"]:
            actions = creates + retrievals
        assert evaluate_plan(output(*actions, limitations=expected["limitations"]), oracle) == (
            "PASS",
            [],
        ), oracle["id"]


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


def test_b02_uses_journal_entry_date_not_note_creation_time() -> None:
    oracle = load_oracle()["B02"]
    person = retrieve(
        note_type="person", filters=[{"field": "birth_date", "op": "gt", "value": "1990-12-31"}]
    )
    journal = retrieve(
        note_type="journal_entry",
        filters=[
            {"field": "entry_date", "op": "gte", "value": "2026-08-01"},
            {"field": "entry_date", "op": "lt", "value": "2026-09-01"},
        ],
    )
    assert evaluate_plan(output(person, journal), oracle)[0] == "PASS"
    wrong_date_field = retrieve(
        note_type="journal_entry",
        filters=[
            {"field": "created_at", "op": "gte", "value": "2026-08-01T00:00:00+02:00"},
            {"field": "created_at", "op": "lt", "value": "2026-09-01T00:00:00+02:00"},
        ],
    )
    assert evaluate_plan(output(person, wrong_date_field), oracle)[0] == "CRITICAL"


def test_a02_keeps_shared_types_filters_and_topic_in_one_action() -> None:
    today = [
        {"field": "type", "op": "in", "value": ["person", "project"]},
        {"field": "created_at", "op": "gte", "value": "2026-08-20T00:00:00+02:00"},
        {"field": "created_at", "op": "lt", "value": "2026-08-21T00:00:00+02:00"},
    ]
    oracle = load_oracle()["A02"]
    assert evaluate_plan(output(retrieve("Toulouse", filters=today)), oracle)[0] == "PASS"
    split = output(
        retrieve("Toulouse", note_type="person", filters=today[1:]),
        retrieve("Toulouse", note_type="project", filters=today[1:]),
    )
    assert evaluate_plan(split, oracle)[0] == "CRITICAL"


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
        "unexpected_hard_filter",
    }


def test_omitted_safe_filter_is_major_not_critical() -> None:
    status, findings = evaluate_plan(
        output(retrieve("niños", note_type="journal_entry")), load_oracle()["S02"]
    )
    assert status == "MAJOR"
    assert {item["code"] for item in findings} == {"missing_safe_filter"}


def test_effective_types_intersect_instead_of_unioning_restrictions() -> None:
    plan = retrieve(
        note_type="person", filters=[{"field": "type", "op": "in", "value": ["person", "project"]}]
    )["plan"]
    assert _effective_types(plan) == {"person"}
    assert (
        evaluate_plan(
            output(
                retrieve(
                    "Toulouse",
                    note_type="person",
                    filters=[
                        {"field": "type", "op": "in", "value": ["person", "project"]},
                        {"field": "created_at", "op": "gte", "value": "2026-08-20T00:00:00+02:00"},
                        {"field": "created_at", "op": "lt", "value": "2026-08-21T00:00:00+02:00"},
                    ],
                )
            ),
            load_oracle()["A02"],
        )[0]
        == "CRITICAL"
    )


def test_recall_first_candidate_set_scoring_distinguishes_broad_and_narrow() -> None:
    expected_person = {
        "expected": {"retrieve": [{"types": ["person"]}], "create_count": 0, "limitations": []}
    }
    assert evaluate_plan(output(retrieve("personas")), expected_person)[0] == "MAJOR"
    assert (
        evaluate_plan(output(retrieve("personas", note_type="project")), expected_person)[0]
        == "CRITICAL"
    )
    expected_tag = {
        "expected": {"retrieve": [{"tags": ["idea"]}], "create_count": 0, "limitations": []}
    }
    assert evaluate_plan(output(retrieve("ideas")), expected_tag)[0] == "MAJOR"
    assert evaluate_plan(output(retrieve("ideas", tags=["review"])), expected_tag)[0] == "CRITICAL"


def test_extra_retrieval_is_major_but_extra_create_is_critical() -> None:
    oracle = load_oracle()["S01"]
    assert evaluate_plan(output(retrieve("Odyssey"), retrieve("n8n")), oracle)[0] == "MAJOR"
    assert (
        evaluate_plan(output(retrieve("Odyssey"), create("no solicitado")), oracle)[0] == "CRITICAL"
    )


def test_wrong_hard_filter_value_is_critical() -> None:
    candidate = output(
        retrieve(
            "niños",
            note_type="journal_entry",
            filters=[
                {"field": "created_at", "op": "gte", "value": "2026-08-18T00:00:00+02:00"},
                {"field": "created_at", "op": "lt", "value": "2026-08-20T00:00:00+02:00"},
            ],
        )
    )
    assert evaluate_plan(candidate, load_oracle()["S02"])[0] == "CRITICAL"


def test_create_content_groups_queue_human_review_without_structural_failure() -> None:
    status, findings = evaluate_plan(
        output(create("guardar una preferencia")), load_oracle()["C01"]
    )
    assert status == "HUMAN REVIEW"
    assert {item["code"] for item in findings} == {"create_content_review"}
    assert (
        evaluate_plan(output(create("probar Terra y revisar los tickets")), load_oracle()["MC01"])[
            0
        ]
        == "PASS"
    )


def test_unsupported_domain_dates_stay_semantic_and_human_reviewable() -> None:
    purchase = output(
        retrieve("Carrefour en julio", note_type="purchase"),
        limitations=["unsupported_domain_date"],
    )
    assert evaluate_plan(purchase, load_oracle()["U02"])[0] == "PASS"
    missing_month = output(
        retrieve("Carrefour", note_type="purchase"), limitations=["unsupported_domain_date"]
    )
    assert evaluate_plan(missing_month, load_oracle()["U02"])[0] == "HUMAN REVIEW"


def test_mixed_action_order_is_major_but_not_execution_dependency() -> None:
    candidate = output(retrieve("modelos"), create("vamos a probar Terra para Phase 14"))
    status, findings = evaluate_plan(candidate, load_oracle()["M01"])
    assert status == "MAJOR"
    assert {item["code"] for item in findings} == {"logical_action_order"}


def test_type_specific_filters_require_compatible_type_candidates() -> None:
    with pytest.raises(BenchmarkContractError, match="entry_date"):
        validate_output(
            output(
                retrieve(
                    note_type="project",
                    filters=[{"field": "entry_date", "op": "eq", "value": "2026-08-20"}],
                )
            )
        )
    with pytest.raises(BenchmarkContractError, match="birth_date"):
        validate_output(
            output(
                retrieve(
                    filters=[
                        {"field": "type", "op": "in", "value": ["person", "project"]},
                        {"field": "birth_date", "op": "lt", "value": "2000-01-01"},
                    ]
                )
            )
        )


def test_unregistered_subtypes_remain_invalid_in_schema_and_local_validation() -> None:
    schema = structured_output_schema(assert_schema_alignment())
    alternatives = schema["properties"]["actions"]["items"]["oneOf"][0]["properties"]["plan"][
        "properties"
    ]["filters"]["items"]["oneOf"]
    assert "subtype" not in {item["properties"]["field"]["const"] for item in alternatives}
    with pytest.raises(BenchmarkContractError, match="unregistered"):
        validate_output(
            output(retrieve(filters=[{"field": "subtype", "op": "eq", "value": "system"}]))
        )


def test_rendered_prompt_contains_schema_derived_capabilities() -> None:
    prompt = render_prompt()
    assert "Timestamp when Odyssey created the note." in prompt
    assert "Date the journal entry refers to." in prompt
    assert "{{RETRIEVAL_CAPABILITIES}}" not in prompt


def test_semantic_wording_mismatch_is_human_review_not_critical() -> None:
    status, findings = evaluate_plan(output(retrieve("asuntos")), load_oracle()["S01"])
    assert status == "HUMAN REVIEW"
    assert all(item["severity"] != "CRITICAL" for item in findings)


def test_limitations_are_closed_and_evaluated() -> None:
    assert (
        evaluate_plan(
            output(retrieve("Odyssey sin revisar", tags=["idea"]), limitations=["not_supported"]),
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
