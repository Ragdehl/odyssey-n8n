"""Offline preparation tests for the Phase 15 incremental benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.phase15_write_planning.benchmark import (
    load_cases,
    load_contract,
    load_oracle,
    load_planner_capabilities,
    render_prompt,
    validate_output,
)
from benchmarks.phase15_write_planning.evaluate import evaluate_plan
from benchmarks.phase15_write_planning.run_benchmark import CONFIGURATIONS
from odyssey_core.planner_capabilities import build_planner_capabilities
from odyssey_core.request_planning import render_request_planner_prompt


def retrieve(query: str) -> dict:
    """Build one safe retrieval action fixture for mixed benchmark checks."""
    return {"kind": "retrieve", "plan": {"query": query, "type": None, "filters": []}}


def unit(subject: str, intent: str = "record", **extra: object) -> dict:
    """Build one valid knowledge-unit fixture with optional explicit fields."""
    return {
        "subject": subject,
        "type": None,
        "intent": intent,
        "facts": ["Fact."],
        "references": [],
    } | extra


def test_incremental_case_set_is_frozen_and_sol_only() -> None:
    """Keep seven retrieval regressions, eleven write cases, and one future Sol pass."""
    cases = load_cases()
    assert [case["id"] for case in cases[:7]] == [f"R{index:02}" for index in range(1, 8)]
    assert [case["id"] for case in cases[7:]] == [f"W{index:02}" for index in range(1, 12)]
    assert len(load_oracle()) == 18 and CONFIGURATIONS == {"sol": ("gpt-5.6-sol", "low")}
    assert "Decompose write knowledge semantically" in render_prompt()
    assert load_oracle()["W05"]["actions"][0]["units"][0]["type"] == "project"
    assert load_oracle()["W05"]["actions"][0]["units"][0]["fact_count"] == 0
    assert load_oracle()["W10"]["actions"][0]["units"][0]["fact_groups"] == [["20:30"]]


def test_oracle_reference_plans_cover_all_contract_shapes() -> None:
    """Exercise deterministic evaluation for grouping, mixed planning, and references."""
    grouped = {
        "actions": [{"kind": "write", "units": [unit("Carrefour", facts=["20:30", "parking"])]}],
        "limitations": [],
    }
    status, _ = evaluate_plan(
        grouped,
        {
            "actions": [
                {
                    "kind": "write",
                    "units": [{"intent": "record", "fact_groups": [["20:30"], ["parking"]]}],
                }
            ]
        },
    )
    assert status == "HUMAN REVIEW"
    mixed = {
        "actions": [
            retrieve("compras Carrefour"),
            {"kind": "write", "units": [unit("Carrefour", "amend", facts=["20:30"])]},
        ],
        "limitations": [],
    }
    assert (
        evaluate_plan(
            mixed,
            {
                "actions": [
                    {"kind": "retrieve", "query_groups": [["carrefour"]]},
                    {"kind": "write", "units": [{"intent": "amend", "fact_groups": [["20:30"]]}]},
                ]
            },
        )[0]
        == "HUMAN REVIEW"
    )


def test_oracle_fails_closed_on_physical_fields_bad_intent_and_bad_references() -> None:
    """Classify persistence authority and unsafe write structures as critical failures."""
    invalid = [
        {
            "actions": [{"kind": "write", "units": [unit("Carrefour", operation="UPDATE")]}],
            "limitations": [],
        },
        {"actions": [{"kind": "write", "units": [unit("Carrefour", "create")]}], "limitations": []},
        {
            "actions": [
                {
                    "kind": "write",
                    "units": [unit("Carrefour", references=[{"target_index": 0, "role": "store"}])],
                }
            ],
            "limitations": [],
        },
    ]
    for payload in invalid:
        status, _ = evaluate_plan(payload, {"actions": []})
        assert status == "CRITICAL"


def test_frozen_contract_matches_current_canonical_types() -> None:
    """Detect type-vocabulary drift before any later paid benchmark execution."""
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "config/note-schema.json").read_text(encoding="utf-8"))
    assert [item["id"] for item in schema["types"]] == load_contract()["canonical_types"]
    assert validate_output(
        {"actions": [{"kind": "write", "units": [unit("Carrefour")]}], "limitations": []}
    )


def test_phase15_capability_snapshot_matches_current_production_projection() -> None:
    """Freeze Phase 15 capabilities from current production, not Phase 14 evidence."""
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "config/note-schema.json").read_text(encoding="utf-8"))
    expected = build_planner_capabilities(
        schema,
        current_context={"date": "2026-08-20", "time": "10:30", "timezone": "Europe/Madrid"},
    )
    assert load_planner_capabilities() == expected
    assert expected["filters"]["relationship_to_user"]["operators"] == ["eq", "in"]


def test_frozen_prompt_has_production_contract_parity() -> None:
    """Prevent frozen prompt drift from critical production write-planning semantics."""
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "config/note-schema.json").read_text(encoding="utf-8"))
    context = {"date": "2026-08-20", "time": "10:30", "timezone": "Europe/Madrid"}
    production, frozen = (
        render_request_planner_prompt(schema, context).lower(),
        render_prompt().lower(),
    )
    requirements = (
        "compatible",
        "different intents for the same subject produce separate knowledgeunits",
        "record, amend, remove, and delete",
        "amend requires concrete facts",
        "remove requires concrete facts",
        "delete uses facts: []",
        "record normally contains facts",
        "resolve identity",
        "create versus update",
        "generate ids, paths, markdown",
        "execute retrieval, persistence, or entity resolution",
    )
    for requirement in requirements:
        assert requirement in production
        assert requirement in frozen


def test_oracle_rejects_extra_facts_and_allows_factless_reference_targets() -> None:
    """Guard deterministic fact counts while permitting only valid empty-fact units."""
    extra_fact = {
        "actions": [{"kind": "write", "units": [unit("Carrefour", facts=["20:30", "parking"])]}],
        "limitations": [],
    }
    assert (
        evaluate_plan(
            extra_fact,
            {"actions": [{"kind": "write", "units": [{"intent": "record", "fact_count": 1}]}]},
        )[0]
        == "CRITICAL"
    )
    reference_only = {
        "actions": [
            {
                "kind": "write",
                "units": [
                    unit("Carrefour", facts=[]),
                    unit(
                        "Purchase",
                        facts=["Today."],
                        references=[{"target_index": 0, "role": "store"}],
                    ),
                    unit("Old purchase", intent="delete", facts=[]),
                ],
            }
        ],
        "limitations": [],
    }
    assert validate_output(reference_only)
    assert (
        evaluate_plan(
            {
                "actions": [
                    {"kind": "write", "units": [unit("Old", intent="delete", facts=["filler"])]}
                ],
                "limitations": [],
            },
            {"actions": [{"kind": "write", "units": [{"intent": "delete", "fact_count": 0}]}]},
        )[0]
        == "CRITICAL"
    )
    assert (
        evaluate_plan(
            {"actions": [retrieve("Odyssey")], "limitations": []},
            {"actions": [{"kind": "retrieve", "query_groups": [["odyssey"]]}]},
        )[0]
        == "PASS"
    )
