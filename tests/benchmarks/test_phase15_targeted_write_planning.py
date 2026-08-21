"""Offline contract tests for the five-case Phase 15 targeted follow-up."""

from __future__ import annotations

from benchmarks.phase15_write_planning.targeted.benchmark import load_cases
from benchmarks.phase15_write_planning.targeted.evaluate import evaluate_plan
from benchmarks.phase15_write_planning.targeted.run_benchmark import CONFIGURATIONS


def _retrieve(query: str, *, type: str | None = None, filters: list[dict] | None = None) -> dict:
    """Build a retrieval fixture with only the frozen RequestPlan fields."""
    return {"kind": "retrieve", "plan": {"query": query, "type": type, "filters": filters or []}}


def _unit(subject: str, intent: str, facts: list[str]) -> dict:
    """Build one valid targeted knowledge-unit fixture."""
    return {"subject": subject, "type": None, "intent": intent, "facts": facts, "references": []}


def _plan(*actions: dict) -> dict:
    """Build a valid RequestPlan fixture with no limitations."""
    return {"actions": list(actions), "limitations": []}


def test_targeted_case_set_is_exactly_the_approved_five_sol_low_calls() -> None:
    """Freeze the focused R06/W10 follow-up and its three regression sentinels."""
    assert [case["id"] for case in load_cases()] == ["T01", "T02", "T03", "T04", "T05"]
    assert CONFIGURATIONS == {"sol": ("gpt-5.6-sol", "low")}


def test_targeted_oracle_keeps_semantic_before_out_of_lifecycle_filters() -> None:
    """Reject the R06 recall loss while preserving a semantic earlier-thinking query."""
    candidate = _plan(
        {"kind": "write", "units": [_unit("Phase 15", "record", ["Use Sol."])]},
        _retrieve("qué había pensado antes sobre esto"),
    )
    assert evaluate_plan("T01", candidate)[0] == "HUMAN REVIEW"
    unsafe = _plan(
        {"kind": "write", "units": [_unit("Phase 15", "record", ["Use Sol."])]},
        _retrieve(
            "qué había pensado antes sobre esto",
            filters=[{"field": "created_at", "op": "lt", "value": "2026-08-20T10:30:00+02:00"}],
        ),
    )
    assert evaluate_plan("T01", unsafe)[0] == "CRITICAL"


def test_targeted_oracle_keeps_explicit_metadata_and_or_recall_behavior() -> None:
    """Require explicit diary timing and both independent 1990/2000 candidate sets."""
    yesterday = _plan(
        _retrieve(
            "niños",
            type="journal_entry",
            filters=[
                {"field": "created_at", "op": "gte", "value": "2026-08-19T00:00:00+02:00"},
                {"field": "created_at", "op": "lt", "value": "2026-08-20T00:00:00+02:00"},
            ],
        )
    )
    assert evaluate_plan("T03", yesterday)[0] == "PASS"
    born = _plan(
        _retrieve(
            "personas nacidas en 1990",
            type="person",
            filters=[
                {"field": "birth_date", "op": "gte", "value": "1990-01-01"},
                {"field": "birth_date", "op": "lt", "value": "1991-01-01"},
            ],
        ),
        _retrieve(
            "personas nacidas en 2000",
            type="person",
            filters=[
                {"field": "birth_date", "op": "gte", "value": "2000-01-01"},
                {"field": "birth_date", "op": "lt", "value": "2001-01-01"},
            ],
        ),
    )
    assert evaluate_plan("T04", born)[0] == "PASS"


def test_targeted_oracle_separates_write_existence_from_genuine_mixed_retrieval() -> None:
    """Reject an existence lookup while allowing a user-requested purchase-history lookup."""
    amend = {
        "kind": "write",
        "units": [_unit("tienda de la esquina", "amend", ["Cierra a las 20:30."])],
    }
    assert evaluate_plan("T02", _plan(amend))[0] == "HUMAN REVIEW"
    assert evaluate_plan("T02", _plan(_retrieve("tienda de la esquina"), amend))[0] == "CRITICAL"
    mixed = _plan(
        _retrieve("qué compré la última vez en Carrefour Balma"),
        {"kind": "write", "units": [_unit("Carrefour Balma", "amend", ["Cierra a las 20:30."])]},
    )
    assert evaluate_plan("T05", mixed)[0] == "HUMAN REVIEW"
