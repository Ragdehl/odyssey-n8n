"""No-provider tests for the unexecuted combined planner-shape successor gate."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from benchmarks.semantic_set_planner.gate import Evaluation
from benchmarks.semantic_set_planner.run_live import run_cases
from benchmarks.semantic_set_planner.v7_gate import (
    CASE_ORDER,
    CLASSIFIER_ORDER,
    FINAL_CASE_ORDER,
    HISTORICAL_CASE_ORDER,
    MAX_PROVIDER_CALLS,
    PLANNER_ORDER,
    evaluate_historical_result,
    evaluate_v7_result,
    load_classifier_cases,
    load_historical_registry,
    load_v7_registry,
    run_classifier_cases,
    v7_planner_preflight,
    v7_preflight,
)
from odyssey_core.context import ContextFilter
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


def test_final_v7_gate_contains_every_expected_case_once_in_frozen_order() -> None:
    """The final authorization covers the existing cases, sentinels, and classifier rows once."""
    historical_cases, historical_oracles = load_historical_registry()
    assert PLANNER_ORDER == (
        "SSET01",
        "SSET02",
        "SSET03",
        "SSET04",
        "REG01",
        "REG02",
        "NOTE01",
        "SINGLE01",
        "HD03",
        "HO02",
        "SP02",
        "SW01",
        "SW02",
        "SD02",
        "SM01",
        "SC02",
        "SE01",
        "SA02",
    )
    assert tuple(case["id"] for case in historical_cases) == HISTORICAL_CASE_ORDER
    assert tuple(historical_oracles) == HISTORICAL_CASE_ORDER
    assert PLANNER_ORDER == CASE_ORDER + HISTORICAL_CASE_ORDER
    assert FINAL_CASE_ORDER == PLANNER_ORDER + CLASSIFIER_ORDER
    assert len(FINAL_CASE_ORDER) == MAX_PROVIDER_CALLS == 22
    assert len(set(FINAL_CASE_ORDER)) == len(FINAL_CASE_ORDER)


def test_historical_sentinels_reuse_existing_request_and_oracle_contracts() -> None:
    """Requests and meanings are reused except the explicit HD03 contract projection."""
    from benchmarks.semantic_set_planner.v3_regression_gate import load_v3_regression_registry

    old_cases, old_oracles = load_v3_regression_registry()
    cases, oracles = load_historical_registry()
    old_requests = {case["id"]: case["request"] for case in old_cases["cases"]}
    assert {case["id"]: case["request"] for case in cases} == {
        case_id: old_requests[case_id] for case_id in HISTORICAL_CASE_ORDER
    }
    assert old_oracles["HD03"]["plan"]["required_limitations"] == ["unsupported_domain_date"]
    for case_id in HISTORICAL_CASE_ORDER:
        if case_id != "HD03":
            assert oracles[case_id] == old_oracles[case_id]
    projected_hd03 = json.loads(json.dumps(old_oracles["HD03"]))
    projected_hd03["plan"].pop("required_limitations")
    projected_hd03["guards"] = []
    assert oracles["HD03"] == projected_hd03


def test_hd03_requires_may_in_lossless_query_without_lifecycle_filters() -> None:
    """Current HD03 accepts domain-date meaning in query, not invented lifecycle filters."""
    _cases, oracles = load_historical_registry()
    expected = RequestPlan(
        (
            RetrieveAction(
                SelectionCriteria(
                    None,
                    "Show journal entries describing trips I took in May.",
                    "journal_entry",
                    (),
                    None,
                )
            ),
        ),
        (),
    )
    dropped_may = RequestPlan(
        (
            RetrieveAction(
                SelectionCriteria(
                    None, "Show journal entries describing trips I took.", "journal_entry", (), None
                )
            ),
        ),
        (),
    )
    lifecycle_mapped = RequestPlan(
        (
            RetrieveAction(
                SelectionCriteria(
                    None,
                    "Show journal entries describing trips I took in May.",
                    "journal_entry",
                    (ContextFilter("entry_date", "eq", "May"),),
                    None,
                )
            ),
        ),
        (),
    )
    assert evaluate_historical_result("HD03", expected, oracles["HD03"]).classification == "PASS"
    assert evaluate_historical_result("HD03", dropped_may, oracles["HD03"]).classification == "FAIL"
    assert (
        evaluate_historical_result("HD03", lifecycle_mapped, oracles["HD03"]).classification
        == "FAIL"
    )


def test_preflight_is_luna_low_zero_retry_and_cost_bounded() -> None:
    """Future provider use remains explicit and limited before any client construction."""
    cases, _oracles = load_v7_registry()
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    preflight = v7_preflight(schema, cases)
    assert preflight["maximum_provider_calls"] == 22
    assert preflight["model"] == "gpt-5.6-luna"
    assert preflight["reasoning"] == "low"
    assert preflight["retries"] == 0
    assert preflight["conservative_no_cache_maximum_usd"] == "0.3034048"
    assert preflight["case_order"] == FINAL_CASE_ORDER


def test_planner_only_recheck_preflight_is_exactly_18_luna_calls() -> None:
    """The prepared planner-only successor excludes unchanged classifier work and cost."""
    cases, _oracles = load_v7_registry()
    historical_cases, _historical_oracles = load_historical_registry()
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    preflight = v7_planner_preflight(schema, cases)
    assert tuple(case["id"] for case in [*cases["cases"], *historical_cases]) == PLANNER_ORDER
    assert preflight["maximum_provider_calls"] == 18
    assert preflight["model"] == "gpt-5.6-luna"
    assert preflight["reasoning"] == "low"
    assert preflight["retries"] == 0
    assert preflight["conservative_no_cache_maximum_usd"] == "0.2962368"
    assert preflight["case_order"] == PLANNER_ORDER


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


def test_classifier_gate_flushes_safe_mismatch_and_continues() -> None:
    """A valid wrong option is a safe oracle FAIL and later clarification cases still run."""
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
            """Return a valid but wrong first choice, followed by expected decisions."""
            if reply == "The one in Lyon.":
                return "marta-madrid"
            if reply == "Where is my bike?":
                return "NEW_REQUEST"
            if reply == "Maybe that one.":
                return "UNRESOLVED"
            return "CANCEL"

    evidence = StringIO()
    rows = run_classifier_cases(FakeClassifier(), cases, evidence)
    assert [row["case_id"] for row in rows] == list(CLASSIFIER_ORDER)
    assert [row["classification"] for row in rows] == ["FAIL", "PASS", "PASS", "PASS"]
    assert len(evidence.getvalue().splitlines()) == 4
    assert "Where is my bike?" not in evidence.getvalue()
    assert "Tell me about Marta" not in evidence.getvalue()


@pytest.mark.parametrize("failure", ["out_of_bounds", "provider"])
def test_classifier_gate_stops_on_invalid_decision_or_provider_failure(failure: str) -> None:
    """Invalid bounded output and provider errors flush FAIL_CLOSED and skip later cases."""
    cases = load_classifier_cases()

    class FakeClassifier:
        """Return an invalid choice or raise a provider-like error without network access."""

        model = "gpt-5.6-luna"
        reasoning_effort = "low"
        last_called = True
        last_usage = None
        last_error_category = None
        last_response_id = None

        def classify(self, _reply, _original_request, _options):
            """Simulate only the requested local failure mode."""
            if failure == "provider":
                raise TimeoutError("provider detail must not be persisted")
            return "unlisted-option"

    evidence = StringIO()
    rows = run_classifier_cases(FakeClassifier(), cases, evidence)
    assert [row["case_id"] for row in rows] == ["CLAR01"]
    assert rows[0]["classification"] == "FAIL_CLOSED"
    assert rows[0]["decision"] == ("INVALID" if failure == "out_of_bounds" else "UNRESOLVED")
    assert len(evidence.getvalue().splitlines()) == 1
    assert "provider detail" not in evidence.getvalue()


class _FakePlanner:
    """Count deterministic local planner invocations for runner-stop behavior."""

    last_usage = None
    last_response_id = None
    last_provider_status = "completed"
    last_validation_stage = None
    last_validation_code = None
    last_parse_status = "parsed"
    last_error_category = None
    last_error_chain = None
    last_input_sizes = None

    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or RequestPlan((RetrieveAction(_selection("test query")),), ())
        self.error = error
        self.calls = 0

    def plan(self, _request: str):
        """Return a fixed local result or raise the configured provider failure."""
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def test_safe_semantic_fail_is_flushed_and_continues() -> None:
    """An oracle-only FAIL does not prevent later cases from being recorded."""
    planner = _FakePlanner()
    evidence = StringIO()
    rows = run_cases(
        planner,
        [{"id": f"CASE{i}", "request": "request"} for i in range(3)],
        {f"CASE{i}": {} for i in range(3)},
        evidence,
        evaluator=lambda _result, _oracle: Evaluation("FAIL", ("safe_semantic_mismatch",)),
        continue_on_safe_fail=True,
    )
    assert planner.calls == 3
    assert [row["classification"] for row in rows] == ["FAIL"] * 3
    assert len(evidence.getvalue().splitlines()) == 3


@pytest.mark.parametrize("classification", ["FAIL_CLOSED", "FAIL"])
def test_fail_closed_and_unsafe_authority_stop_immediately(classification: str) -> None:
    """Fail-closed outcomes and authority findings cannot use safe-failure continuation."""
    planner = _FakePlanner()
    evidence = StringIO()
    if classification == "FAIL_CLOSED":

        def evaluator(_result, _oracle):
            return Evaluation("FAIL_CLOSED", ("closed",))

    else:
        unsafe_result = RequestPlan((RetrieveAction(_selection("../../../private.md")),), ())
        planner = _FakePlanner(unsafe_result)
        evaluator = evaluate_v7_result
    rows = run_cases(
        planner,
        [{"id": "FIRST", "request": "request"}, {"id": "SECOND", "request": "request"}],
        {"FIRST": {"kind": "single"}, "SECOND": {"kind": "single"}},
        evidence,
        evaluator=evaluator,
        continue_on_safe_fail=True,
    )
    assert planner.calls == 1
    assert len(rows) == len(evidence.getvalue().splitlines()) == 1
    assert rows[0]["classification"] == "FAIL_CLOSED"


def test_provider_error_stops_immediately_even_with_safe_fail_continuation() -> None:
    """Provider exceptions are flushed as fail-closed and never followed by another call."""
    planner = _FakePlanner(error=TimeoutError("private provider detail"))
    evidence = StringIO()
    rows = run_cases(
        planner,
        [{"id": "FIRST", "request": "request"}, {"id": "SECOND", "request": "request"}],
        {},
        evidence,
        continue_on_safe_fail=True,
    )
    assert planner.calls == 1
    assert rows[0]["classification"] == "FAIL_CLOSED"
    assert "private provider detail" not in evidence.getvalue()
