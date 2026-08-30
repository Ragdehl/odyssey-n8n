"""Offline tests for the frozen Phase 14 RequestPlan v3 contract."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from benchmarks.phase14_request_plan_v3.benchmark import (
    BenchmarkContractError,
    assert_schema_alignment,
    load_cases,
    load_oracle,
    load_planner_capabilities,
    render_prompt,
    structured_output_schema,
    validate_output,
)
from benchmarks.phase14_request_plan_v3.evaluate import evaluate_plan
from benchmarks.phase14_request_plan_v3.run_benchmark import run
from benchmarks.phase14_retrieval_plan.benchmark import load_json
from odyssey_core.planner_capabilities import LIMITATIONS, build_planner_capabilities


def retrieve(
    query: str = "Odyssey", *, note_type: str | None = None, filters: list[dict] | None = None
) -> dict:
    """Build a v3 retrieval fixture without planner tags."""
    return {
        "kind": "retrieve",
        "plan": {"query": query, "type": note_type, "filters": filters or []},
    }


def output(*actions: dict, limitations: list[str] | None = None) -> dict:
    """Build a complete v3 RequestPlan fixture."""
    return {"actions": list(actions), "limitations": limitations or []}


def reference_plan(expected: dict) -> dict:
    """Materialize an oracle-compatible plan for structural regression checks."""
    actions = []
    for branch in expected["retrieve"]:
        types = branch.get("types", branch.get("type", []))
        filters = [
            {"field": field, "op": op, "value": value}
            for field, op, value in branch.get("filters", [])
        ]
        if len(types) > 1:
            filters.insert(0, {"field": "type", "op": "in", "value": types})
        actions.append(
            retrieve(
                " ".join(group[0] for group in branch.get("query_groups", [])) or "retrieval",
                note_type=types[0] if len(types) == 1 else None,
                filters=filters,
            )
        )
    actions.extend(
        {
            "kind": "create_note",
            "content": " ".join(group[0] for group in expected.get("create_content_groups", []))
            or "content",
        }
        for _ in range(expected["create_count"])
    )
    if expected.get("action_kinds") == ["create_note", "retrieve"]:
        actions.sort(key=lambda action: action["kind"] != "create_note")
    return output(*actions, limitations=expected["limitations"])


def test_frozen_contract_uses_only_schema_derived_v3_capabilities() -> None:
    contract = assert_schema_alignment()
    assert "tags" not in contract["retrieval_contract"]["filterable_fields"]
    rendered = render_prompt()
    assert '"types"' in rendered and '"operators"' in rendered and '"applies_to"' in rendered
    assert "retrieval_guidance" in rendered and "retrieval_examples" in rendered
    assert (
        "created_at" in rendered
        and "updated_at" in rendered
        and "entry_date" in rendered
        and "birth_date" in rendered
    )
    assert "tags" not in json.loads(rendered.split("\n\n")[-1])["filters"]


def test_frozen_capabilities_remain_historical_after_production_operator_fix() -> None:
    """Keep the frozen snapshot independent when Core's safe operator projection improves."""
    production = build_planner_capabilities(
        load_json(Path("config/note-schema.json")),
        current_context={"date": "2026-08-20", "time": "10:30", "timezone": "Europe/Madrid"},
    )
    frozen = load_planner_capabilities()
    assert frozen["filters"]["relationship_to_user"]["operators"] == [
        "eq",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
    ]
    assert "relationship_to_user" not in production["filters"]
    rendered = render_prompt()
    assert (
        '"current_context":{"date":"2026-08-20","time":"10:30","timezone":"Europe/Madrid"}'
        in rendered
    )
    assert json.loads(rendered.split("\n\n")[-1])["limitations"] == LIMITATIONS


def test_structured_output_and_local_contract_reject_tags() -> None:
    schema = structured_output_schema(assert_schema_alignment())
    plan = schema["properties"]["actions"]["items"]["anyOf"][0]["properties"]["plan"]
    assert "required_tags" not in plan["properties"]
    with pytest.raises(BenchmarkContractError):
        validate_output(
            {
                "actions": [
                    {
                        "kind": "retrieve",
                        "plan": {
                            "query": "ideas",
                            "type": None,
                            "required_tags": [],
                            "filters": [],
                        },
                    }
                ],
                "limitations": [],
            }
        )


def test_all_24_reference_plans_pass() -> None:
    assert len(load_cases()) == len(load_oracle()) == 24
    for oracle in load_oracle().values():
        assert evaluate_plan(reference_plan(oracle["expected"]), oracle) == ("PASS", []), oracle[
            "id"
        ]


def test_semantic_ideas_do_not_require_concept_or_tags() -> None:
    plan = output(retrieve("ideas sobre Odyssey para revisar"))
    assert validate_output(plan)
    assert evaluate_plan(plan, load_oracle()["S03"])[0] == "PASS"
    assert (
        evaluate_plan(output(retrieve("ideas Odyssey", note_type="concept")), load_oracle()["S03"])[
            0
        ]
        == "CRITICAL"
    )


def test_date_regressions_remain_recall_first() -> None:
    yesterday = [
        {"field": "created_at", "op": "gte", "value": "2026-08-19T00:00:00+02:00"},
        {"field": "created_at", "op": "lt", "value": "2026-08-20T00:00:00+02:00"},
    ]
    assert (
        evaluate_plan(
            output(retrieve("niños", note_type="journal_entry", filters=yesterday)),
            load_oracle()["S02"],
        )[0]
        == "PASS"
    )
    assert (
        evaluate_plan(
            output(
                retrieve(
                    "niños",
                    note_type="journal_entry",
                    filters=[{"field": "created_at", "op": "gte", "value": "2026-08-19T00:00:00"}],
                )
            ),
            load_oracle()["S02"],
        )[0]
        == "CRITICAL"
    )


def test_received_invalid_output_is_critical_evidence_not_transport_retry(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("benchmarks.phase14_request_plan_v3.run_benchmark.RESULTS_DIR", tmp_path)
    response = MagicMock(output_text='{"actions": []}', usage=None)
    fake_openai = MagicMock(responses=MagicMock(create=MagicMock(return_value=response)))
    with patch.dict(
        "sys.modules",
        {"openai": MagicMock(OpenAI=MagicMock(return_value=fake_openai), __version__="test")},
    ):
        run("invalid", ["terra"], case_ids={"S01"})
    row = json.loads((tmp_path / "invalid" / "raw_results.jsonl").read_text())
    assert row["success"] is True and row["status"] == "CRITICAL" and "validation_error" in row
    assert "failure_kind" not in row
