"""No-provider tests for the unexecuted combined planner-shape successor gate."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from benchmarks.semantic_set_planner.v7_gate import (
    CASE_ORDER,
    CLASSIFIER_ORDER,
    evaluate_v7_result,
    load_classifier_cases,
    load_v7_registry,
    run_classifier_cases,
    v7_preflight,
)
from odyssey_core.experimental_luna_planning import _complete_example_selections
from odyssey_core.request_planning import (
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
)

ROOT = Path(__file__).resolve().parents[2]


def _selection(query: str) -> SelectionCriteria:
    """Build a direct-free query for frozen planner-shape evaluation."""
    return SelectionCriteria(None, query, None, (), None)


def test_v7_preserves_six_requests_and_adds_two_shape_sentinels() -> None:
    """Versioning changes no historical six-case request wording or order."""
    cases, oracles = load_v7_registry()
    previous = json.loads((ROOT / "benchmarks/semantic_set_planner/v6_cases.json").read_text())
    assert cases["cases"][:6] == previous["cases"]
    assert tuple(oracles) == CASE_ORDER
    assert CASE_ORDER[-2:] == ("NOTE01", "SINGLE01")


def test_preflight_is_luna_low_zero_retry_and_cost_bounded() -> None:
    """Future provider use remains explicit and limited before any client construction."""
    cases, _oracles = load_v7_registry()
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    preflight = v7_preflight(schema, cases)
    assert preflight["maximum_provider_calls"] == 12
    assert preflight["model"] == "gpt-5.6-luna"
    assert preflight["reasoning"] == "low"
    assert preflight["retries"] == 0
    assert preflight["conservative_no_cache_maximum_usd"] == "0.1388288"
    assert preflight["case_order"] == CASE_ORDER + CLASSIFIER_ORDER


def test_collection_note_set_and_single_shapes_are_distinct() -> None:
    """Multiple semantic values and multiple Notes each retain their own planner mode."""
    _cases, oracles = load_v7_registry()
    collection = RequestPlan(
        (RetrieveAction(_selection("personas de mi familia"), result_shape="collection"),), ()
    )
    note_set = RequestPlan(
        (RetrieveAction(_selection("notas sobre viajes")),), (), presentation_intent="note_set"
    )
    single = RequestPlan(
        (RetrieveAction(SelectionCriteria("Italia", "nota de Italia", None, (), None)),),
        (),
    )
    assert evaluate_v7_result(collection, oracles["SSET01"]).classification == "PASS"
    assert evaluate_v7_result(note_set, oracles["NOTE01"]).classification == "PASS"
    assert evaluate_v7_result(single, oracles["SINGLE01"]).classification == "PASS"
    assert evaluate_v7_result(single, oracles["SSET01"]).classification == "FAIL"
    assert evaluate_v7_result(collection, oracles["NOTE01"]).classification == "FAIL"
    assert evaluate_v7_result(note_set, oracles["SINGLE01"]).classification == "FAIL"


@pytest.mark.parametrize("case_id", ("SSET01", "SSET02", "SSET03", "SSET04"))
def test_collection_requires_material_query_meaning(case_id: str) -> None:
    """A shape marker without the useful semantic request is not a passing plan."""
    _cases, oracles = load_v7_registry()
    result = RequestPlan((RetrieveAction(_selection("something"), result_shape="collection"),), ())
    assert evaluate_v7_result(result, oracles[case_id]).findings == (
        "lossless_query_meaning_dropped",
    )


def test_explicit_teaching_shape_is_not_rewritten_by_legacy_completion() -> None:
    """A collection teaching contract remains a collection after shared field completion."""
    example = {
        "actions": [
            {
                "kind": "retrieve",
                "result_shape": "collection",
                "plan": {
                    "entity": None,
                    "query": "all current values",
                    "type": None,
                    "filters": [],
                    "link_scope": None,
                    "self_target": None,
                },
            }
        ]
    }
    projected = _complete_example_selections(example)
    assert projected["actions"][0]["result_shape"] == "collection"
    assert projected["actions"][0]["plan"]["relational_reference"] is None
    assert example["actions"][0]["plan"].get("relational_reference") is None


def test_classifier_gate_flushes_and_stops_on_first_non_pass() -> None:
    """Only bounded decisions reach evidence, never the synthetic reply or provider body."""
    cases = load_classifier_cases()

    class FakeClassifier:
        """Provide local outcomes and safe metadata without a network call."""

        model = "gpt-5.6-luna"
        reasoning_effort = "low"
        last_called = True
        last_usage = {"input_tokens": 1, "output_tokens": 1}
        last_error_category = None
        last_response_id = "fake-response"

        def classify(self, reply, original_request, options):
            """Pass the first case and fail the second without continuing."""
            return "marta-lyon" if reply == "The one in Lyon." else "UNRESOLVED"

    evidence = StringIO()
    rows = run_classifier_cases(FakeClassifier(), cases, evidence)
    assert [row["case_id"] for row in rows] == ["CLAR01", "CLAR02"]
    assert [row["classification"] for row in rows] == ["PASS", "FAIL"]
    assert len(evidence.getvalue().splitlines()) == 2
    assert "Where is my bike?" not in evidence.getvalue()
    assert "Tell me about Marta" not in evidence.getvalue()
