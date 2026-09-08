"""Provider-free checks for the frozen planner incident-hardening live gate."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.planner_incident_hardening.run_live import evaluate
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
    """Keep the future live run focused on abstention and established action kinds."""
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
    assert {case["expect"] for case in cases} == {"clarify", "retrieve", "write", "delegate"}


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
