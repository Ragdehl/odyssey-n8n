"""Deterministic tests for the Phase 15.2 benchmark oracle."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from benchmarks.phase15_2_selection_anchors.benchmark import load_cases
from benchmarks.phase15_2_selection_anchors.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[2]
RESULTS = (
    ROOT
    / "benchmarks/phase15_2_selection_anchors/results/phase15-2-sol-low-20260823/raw_results.jsonl"
)


def _saved_rows() -> dict[str, dict]:
    """Load saved model outputs without contacting a provider."""
    return {
        row["test_id"]: row
        for row in (json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines())
    }


def _schema() -> dict:
    """Load the canonical schema used by the saved benchmark."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def _payload(case_id: str) -> dict:
    """Return a mutable copy of one saved parsed model output."""
    return copy.deepcopy(_saved_rows()[case_id]["parsed_output"])


def test_every_frozen_expectation_has_a_passing_strict_oracle() -> None:
    """Require one explicit oracle handler for every saved case and preserve all passes."""
    cases = load_cases()
    rows = _saved_rows()
    assert {case["id"] for case in cases} == set(rows)
    assert all(
        evaluate(case["expect"], rows[case["id"]]["parsed_output"], _schema()) == ("PASS", [])
        for case in cases
    )


def test_graph_anchor_and_result_restrictions_fail_when_moved_or_weakened() -> None:
    """Reject G02/G03 outputs that lose direction, anchor filters, or independent result filters."""
    g02 = _payload("G02")
    scope = g02["actions"][0]["plan"]["link_scope"]
    g02["actions"][0]["plan"]["type"] = "person"
    scope["anchor"]["filters"], g02["actions"][0]["plan"]["filters"] = (
        [],
        scope["anchor"]["filters"],
    )
    assert evaluate("property_anchor", g02, _schema())[0] == "FAIL"

    g02_direction = _payload("G02")
    g02_direction["actions"][0]["plan"]["link_scope"]["direction"] = "both"
    assert evaluate("property_anchor", g02_direction, _schema())[0] == "FAIL"

    g02_entity = _payload("G02")
    g02_entity["actions"][0]["plan"]["link_scope"]["anchor"]["entity"] = "Marta"
    assert evaluate("property_anchor", g02_entity, _schema())[0] == "FAIL"

    g03 = _payload("G03")
    g03["actions"][0]["plan"]["filters"] = []
    assert evaluate("independent_filters", g03, _schema())[0] == "FAIL"

    g03_leak = _payload("G03")
    outer = g03_leak["actions"][0]["plan"]
    outer["type"] = "person"
    outer["filters"] = [{"field": "birth_date", "op": "eq", "value": "1990-05-03"}]
    assert evaluate("independent_filters", g03_leak, _schema())[0] == "FAIL"


def test_entity_direct_and_depth_regressions_fail() -> None:
    """Reject accidental entity promotion, concept fallback, graph traversal, and depth collapse."""
    e03 = _payload("E03")
    e03["actions"][0]["units"][0]["target"]["entity"] = "Marta"
    assert evaluate("contextual_person", e03, _schema())[0] == "FAIL"

    e05 = _payload("E05")
    e05["actions"][0]["plan"]["type"] = "concept"
    assert evaluate("n8n_direct", e05, _schema())[0] == "FAIL"

    g04 = _payload("G04")
    g04["actions"][0]["plan"]["link_scope"]["max_depth"] = 1
    assert evaluate("two_hops", g04, _schema())[0] == "FAIL"


def test_tag_and_property_regressions_fail() -> None:
    """Reject implicit tags, missing explicit tags, broken tag ordering, and fact-only dates."""
    t01 = _payload("T01")
    t01["actions"][0]["plan"]["filters"] = [{"field": "tags", "op": "contains", "value": "idea"}]
    assert evaluate("semantic_no_tags", t01, _schema())[0] == "FAIL"

    t02 = _payload("T02")
    t02["actions"][0]["plan"]["filters"] = []
    assert evaluate("tag_retrieval", t02, _schema())[0] == "FAIL"

    t03 = _payload("T03")
    t03["actions"][0]["units"] = [t03["actions"][0]["units"][0]]
    assert evaluate("tag_mutations", t03, _schema())[0] == "FAIL"

    r01 = _payload("R01")
    r01["actions"][0]["units"][0]["properties"] = []
    r01["actions"][0]["units"][0]["facts"] = ["Nació en 1990."]
    assert evaluate("property_regression", r01, _schema())[0] == "FAIL"


def test_mixed_retrieval_write_and_unknown_expectation_fail_closed() -> None:
    """Reject collapsed mixed actions and expectations without a registered oracle handler."""
    r02 = _payload("R02")
    r02["actions"].pop(0)
    assert evaluate("mixed_regression", r02, _schema())[0] == "FAIL"

    valid = _payload("E01")
    assert evaluate("not-implemented-expectation", valid, _schema()) == (
        "FAIL",
        ["unknown_expectation"],
    )
