"""Offline preparation tests for the Phase 15 incremental benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.phase15_write_planning.benchmark import (
    load_cases,
    load_contract,
    load_oracle,
    render_prompt,
    validate_output,
)
from benchmarks.phase15_write_planning.evaluate import evaluate_plan
from benchmarks.phase15_write_planning.run_benchmark import CONFIGURATIONS


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
    """Keep seven retrieval regressions, ten new write cases, and one future Sol pass."""
    cases = load_cases()
    assert [case["id"] for case in cases[:7]] == [f"R{index:02}" for index in range(1, 8)]
    assert [case["id"] for case in cases[7:]] == [f"W{index:02}" for index in range(1, 11)]
    assert len(load_oracle()) == 17 and CONFIGURATIONS == {"sol": ("gpt-5.6-sol", "low")}
    assert "decompose semantically" in render_prompt()


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
    assert status == "PASS"
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
        == "PASS"
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
