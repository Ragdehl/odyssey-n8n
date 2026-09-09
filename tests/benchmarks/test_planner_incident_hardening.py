"""Provider-free checks for the frozen planner incident-hardening live gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.planner_incident_hardening.run_live import evaluate
from benchmarks.planner_incident_hardening.run_post_envelope_live import (
    OUTPUT as POST_ENVELOPE_OUTPUT,
)
from benchmarks.planner_incident_hardening.run_post_envelope_live import (
    POST_ENVELOPE_IDS,
    load_post_envelope_cases,
    run_post_envelope_cases,
)
from odyssey_core.context import ContextFilter
from odyssey_core.request_planning import (
    DelegateAction,
    KnowledgeUnit,
    PlannerClarification,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
)

ROOT = Path(__file__).resolve().parents[2]


def test_post_envelope_runner_selects_only_the_six_approved_cases() -> None:
    """Keep the post-envelope gate closed to passed-only or unrelated frozen cases."""
    cases = load_post_envelope_cases()
    assert [case["id"] for case in cases] == list(POST_ENVELOPE_IDS)
    assert "nonsense_letters" not in {case["id"] for case in cases}
    assert "nonsense_punctuation" not in {case["id"] for case in cases}
    assert POST_ENVELOPE_OUTPUT.name == "planner-incident-hardening-post-envelope.jsonl"


def test_post_envelope_runner_stops_after_early_provider_failure() -> None:
    """Stop before extra calls when the first schema-smoke case cannot complete."""

    class FakePlanner:
        last_response_id = None
        last_provider_status = None
        last_usage = None
        last_parse_status = None
        last_validation_stage = None
        last_validation_code = None
        last_result_counts = None
        last_error_category = "ProviderFailure"
        last_incomplete_reason = None
        last_output_text_chars = None
        last_output_text_bytes = None

        def __init__(self) -> None:
            self.calls = 0

        def plan(self, request: str) -> RequestPlan:
            self.calls += 1
            raise RuntimeError("provider unavailable")

    planner = FakePlanner()
    rows = run_post_envelope_cases(planner, load_post_envelope_cases())
    assert planner.calls == 1
    assert len(rows) == 1


def test_frozen_cases_cover_incident_and_normal_regressions() -> None:
    """Keep the future live run focused on abstention and bounded semantic regressions."""
    cases = json.loads(
        (ROOT / "benchmarks" / "planner_incident_hardening" / "cases.json").read_text(
            encoding="utf-8"
        )
    )

    assert {case["request"] for case in cases if case["expect"] == "clarify"} == {
        "Bdbd",
        "asdfgh",
        "???",
    }
    assert {case["expect"] for case in cases} == {
        "clarify",
        "retrieve",
        "write",
        "delegate",
        "event_date_retrieve",
        "mixed_retrieve_write",
    }
    assert (
        next(case for case in cases if case["id"] == "event_date_not_lifecycle")["request"]
        == "What purchases did I make in July?"
    )
    assert next(case for case in cases if case["id"] == "legitimate_mixed")["request"] == (
        "Remember that Marta works at Thales and tell me where she lives."
    )


def test_live_evaluator_distinguishes_clarification_from_every_action_kind() -> None:
    """Prevent legitimate delegation or ordinary plans from passing as abstention."""
    selection = SelectionCriteria(None, "Marta", None, (), None)
    clarify = PlannerClarification("UNRECOGNIZED_REQUEST")
    retrieve = RequestPlan((RetrieveAction(selection),), ())
    delegate = RequestPlan((DelegateAction("translate", selection),), ())
    write = RequestPlan(
        (WriteAction((KnowledgeUnit(selection, "record", (), (), ("fact",), ()),)),), ()
    )

    assert evaluate(clarify, "clarify")
    assert evaluate(retrieve, "retrieve")
    assert evaluate(write, "write")
    assert evaluate(delegate, "delegate")
    assert not evaluate(delegate, "clarify")


def event_date_plan(
    *,
    query: str = "purchases in July",
    note_type: str | None = "purchase",
    filters: tuple[ContextFilter, ...] = (),
    limitations: tuple[str, ...] = ("unsupported_domain_date",),
) -> RequestPlan:
    """Build the narrow U02/A01-compatible purchase-month regression result."""
    return RequestPlan(
        (RetrieveAction(SelectionCriteria(None, query, note_type, filters, None)),), limitations
    )


@pytest.mark.parametrize("query", ("purchases in July", "compras de julio", "purchases 2026-07"))
def test_event_date_evaluator_preserves_domain_month_in_semantic_query(query: str) -> None:
    """Accept the stable U02/A01 month equivalents without requiring exact prose."""
    assert evaluate(event_date_plan(query=query), "event_date_retrieve")


def test_event_date_evaluator_rejects_date_dropped_entirely() -> None:
    """Prevent a purchase-only retrieval from silently discarding the requested month."""
    assert not evaluate(event_date_plan(query="purchases"), "event_date_retrieve")


@pytest.mark.parametrize("field", ("created_at", "updated_at"))
def test_event_date_evaluator_rejects_note_lifecycle_filters(field: str) -> None:
    """Keep a real-world purchase month distinct from note creation or update time."""
    lifecycle = event_date_plan(filters=(ContextFilter(field, "gte", "2026-07-01T00:00:00+02:00"),))

    assert not evaluate(lifecycle, "event_date_retrieve")


def test_event_date_evaluator_requires_current_domain_date_limitation() -> None:
    """Require the canonical signal that purchase dates have no deterministic field."""
    assert not evaluate(event_date_plan(limitations=()), "event_date_retrieve")


def test_event_date_evaluator_requires_canonical_purchase_type() -> None:
    """Keep the event-date candidate set constrained to the current purchase type."""
    assert not evaluate(event_date_plan(note_type=None), "event_date_retrieve")
    assert not evaluate(PlannerClarification("UNRECOGNIZED_REQUEST"), "event_date_retrieve")


def test_mixed_evaluator_requires_retrieval_and_write_without_ordering_them() -> None:
    """Protect legitimate multi-intent planning without executing or imposing action order."""
    selection = SelectionCriteria("Marta", "Marta", "person", (), None)
    retrieve = RetrieveAction(selection)
    write = WriteAction(
        (KnowledgeUnit(selection, "record", (), (), ("Marta works at Thales.",), ()),)
    )

    assert evaluate(RequestPlan((write, retrieve), ()), "mixed_retrieve_write")
    assert evaluate(RequestPlan((retrieve, write), ()), "mixed_retrieve_write")
    assert not evaluate(RequestPlan((retrieve,), ()), "mixed_retrieve_write")
    assert not evaluate(
        RequestPlan((write, DelegateAction("lookup", selection)), ()),
        "mixed_retrieve_write",
    )
