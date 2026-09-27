"""Provider-free checks for the prepared semantic self-clarification Luna gate."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.semantic_set_planner.v8_gate import (
    MAX_COST_USD,
    MAX_PROVIDER_CALLS,
    evaluate_v8_result,
    evaluate_v8_selector_result,
    load_v8_registry,
    load_v8_selector_registry,
    v8_preflight,
)
from odyssey_core.request_planning import RequestPlan, RetrieveAction, SelectionCriteria
from odyssey_core.semantic_sets import SetEvidenceSelection, SetMemberOccurrence

ROOT = Path(__file__).resolve().parents[2]


def test_v8_gate_is_frozen_and_preflights_the_reviewed_luna_ceiling() -> None:
    """Prepare the later live gate without constructing a provider client."""
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    cases, oracles = load_v8_registry()

    preflight = v8_preflight(schema, cases)

    assert preflight["maximum_provider_calls"] == MAX_PROVIDER_CALLS == 25
    assert preflight["conservative_no_cache_maximum_usd"] == str(MAX_COST_USD)
    assert preflight["model"] == "gpt-5.6-luna"
    assert preflight["reasoning"] == "low"
    assert preflight["retries"] == 0


def test_v8_selector_rows_are_frozen_and_require_all_relevant_fact_evidence() -> None:
    """Keep the new relational selector false-negative sentinel provider-free and exact."""
    cases, oracles = load_v8_selector_registry()
    assert [item["id"] for item in cases["cases"]] == [
        "RELSEL_CORROBORATE",
        "RELSEL_CONFLICT",
        "RELSEL_MULTI_TARGET",
        "RELSEL_SEMANTIC",
    ]
    conflict = cases["cases"][1]
    passing = SetEvidenceSelection(
        ("relational-0", "relational-1"),
        (
            SetMemberOccurrence("relational-0", "literal", 0, 2),
            SetMemberOccurrence("relational-1", "link", 12, 20),
        ),
    )
    assert (
        evaluate_v8_selector_result(passing, conflict, oracles["RELSEL_CONFLICT"]).classification
        == "PASS"
    )
    omitted = SetEvidenceSelection(
        ("relational-0",), (SetMemberOccurrence("relational-0", "literal", 0, 2),)
    )
    assert (
        evaluate_v8_selector_result(omitted, conflict, oracles["RELSEL_CONFLICT"]).classification
        == "FAIL"
    )


def test_v8_oracle_requires_the_new_collection_subject_bit() -> None:
    """Reject a collection that drops the explicit Core-bound self/query distinction."""
    _cases, oracles = load_v8_registry()
    self_plan = RequestPlan(
        (
            RetrieveAction(
                SelectionCriteria(
                    None,
                    "¿Quiénes son las personas de mi familia?",
                    None,
                    (),
                    None,
                    collection_subject="self",
                ),
                result_shape="collection",
            ),
        ),
        (),
    )
    query_plan = RequestPlan(
        (
            RetrieveAction(
                SelectionCriteria(
                    None,
                    "¿Qué piezas incluye mi kit básico para la bici?",
                    None,
                    (),
                    None,
                    collection_subject="query",
                ),
                result_shape="collection",
            ),
        ),
        (),
    )

    assert evaluate_v8_result(self_plan, oracles["SSET01"]).classification == "PASS"
    assert evaluate_v8_result(query_plan, oracles["SSET02"]).classification == "PASS"
