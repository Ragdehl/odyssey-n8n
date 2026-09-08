"""Provider-free checks for the frozen planner incident-hardening live gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.planner_incident_hardening.run_live import evaluate
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


@pytest.mark.parametrize("field", ("created_at", "updated_at"))
def test_event_date_evaluator_rejects_note_lifecycle_filters(field: str) -> None:
    """Keep a real-world purchase month distinct from note creation or update time."""
    semantic = RequestPlan(
        (RetrieveAction(SelectionCriteria(None, "purchases in July", "purchase", (), None)),), ()
    )
    lifecycle = RequestPlan(
        (
            RetrieveAction(
                SelectionCriteria(
                    None,
                    "purchases in July",
                    "purchase",
                    (ContextFilter(field, "gte", "2026-07-01T00:00:00+02:00"),),
                    None,
                )
            ),
        ),
        (),
    )

    assert evaluate(semantic, "event_date_retrieve")
    assert not evaluate(lifecycle, "event_date_retrieve")
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
