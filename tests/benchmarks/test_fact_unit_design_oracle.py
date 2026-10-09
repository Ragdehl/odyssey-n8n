"""Non-executable architecture oracles for future atomic Router segmentation.

These checks validate design fixture hygiene only. They do not prove current Router
or production Luna behavior and must never overwrite the frozen Router-v0 matrix.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "benchmarks/application_router/fact_units_v1.design.json"
EXPECTED_COUNTS = (3, 3, 2, 2, 2, 2, 2, 2, 2, 1, 2, 2, 3, 3, 3, 2, 2, 2, 1, 2, 2, 3)
ROLES = {
    "participants",
    "subject",
    "predicate",
    "predicate_relation",
    "object",
    "date",
    "date_scope",
    "time",
    "time_approx",
    "time_relation",
    "location",
    "polarity",
    "condition",
    "modality",
    "order",
    "transaction",
    "reference",
    "replacement",
}
KINDS = {
    "occurrence",
    "property",
    "relationship",
    "purchase_item",
    "plan",
    "negative",
    "conditional",
    "task",
}


def test_accepted_fact_candidate_design_examples_are_frozen_and_source_grounded() -> None:
    """All proposed candidate excerpts and role scopes must cite literal user source."""
    data = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert set(data) == {"version", "status", "cases"}
    assert data["version"] == 1
    assert data["status"] == "non_executable_design_oracle"
    cases = data["cases"]
    assert [case["id"] for case in cases] == [f"F{i:02d}" for i in range(1, 23)]
    assert tuple(len(case["expected_units"]) for case in cases) == EXPECTED_COUNTS
    assert sum(EXPECTED_COUNTS) == 48

    for case in cases:
        assert set(case) == {"id", "source", "expected_units", "safety_oracle"}
        assert isinstance(case["source"], str) and case["source"].strip()
        assert isinstance(case["safety_oracle"], str) and case["safety_oracle"].strip()
        for unit_index, unit in enumerate(case["expected_units"], start=1):
            assert set(unit) == {
                "reading",
                "kind",
                "source_anchors",
                "inheritance",
                "scoped_source",
                "state",
            }
            assert unit["kind"] in KINDS
            assert unit["state"] in {"candidate", "ambiguous_identity"}
            assert isinstance(unit["reading"], str) and unit["reading"].strip()
            assert unit["source_anchors"]
            assert all(
                isinstance(text, str) and text.strip() and text in case["source"]
                for text in unit["source_anchors"]
            ), (case["id"], unit_index)
            for scope in unit["scoped_source"]:
                assert set(scope) == {"role", "text"}
                assert scope["role"] in ROLES
                assert scope["text"] in case["source"], (case["id"], unit_index, scope)
            for dependency in unit["inheritance"]:
                assert set(dependency) == {"role", "from_unit"}
                assert dependency["role"] in ROLES
                # This design fixture uses older semantic units for its inheritance
                # sentinels. The future runtime must ALSO allow later lexical scopes.
                assert isinstance(dependency["from_unit"], int)
                assert not isinstance(dependency["from_unit"], bool)
                assert 1 <= dependency["from_unit"] < unit_index


def test_design_oracles_keep_non_equivalent_fact_sharing_cases_distinct() -> None:
    """Property, symmetric relation, transaction, correction, and ambiguity differ."""
    cases = {case["id"]: case for case in json.loads(MATRIX.read_text(encoding="utf-8"))["cases"]}
    assert {item["kind"] for item in cases["F09"]["expected_units"]} == {"property"}
    assert len(cases["F10"]["expected_units"]) == 1
    assert cases["F10"]["expected_units"][0]["kind"] == "relationship"
    assert [item["kind"] for item in cases["F11"]["expected_units"]] == [
        "purchase_item",
        "purchase_item",
    ]
    assert len(cases["F19"]["expected_units"]) == 1
    assert cases["F19"]["expected_units"][0]["kind"] == "plan"
    assert cases["F14"]["expected_units"][2]["state"] == "ambiguous_identity"
    assert all(item["kind"] == "conditional" for item in cases["F20"]["expected_units"])
    assert all(item["kind"] == "task" for item in cases["F22"]["expected_units"])
    # One later textual clock expression may scope *earlier* semantic units.
    assert all(
        any(scope["text"] == "a las 18h" for scope in unit["scoped_source"])
        for unit in cases["F21"]["expected_units"]
    )
