"""Focused deterministic contract tests for generic Phase 15.3 delegation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.request_planning import (
    DelegateAction,
    LinkScope,
    RequestPlanningError,
    RetrieveAction,
    WriteAction,
    render_request_planner_prompt,
    request_plan_json_schema,
    validate_request_plan,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema used by request planning."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def selection(query: str = "Marta") -> dict:
    """Build one complete Phase 15.2 shared selection fixture."""
    return {"entity": "Marta", "query": query, "type": "person", "filters": [], "link_scope": None}


def delegate(
    request: str = "Cuenta las notas de Marta", selection_value: dict | None = None
) -> dict:
    """Build one raw generic delegated action fixture."""
    return {"kind": "delegate", "request": request, "selection": selection_value}


def output(*actions: dict) -> dict:
    """Build one complete RequestPlan fixture."""
    return {"actions": list(actions), "limitations": []}


def test_delegate_action_accepts_optional_shared_selection(schema: dict) -> None:
    """Keep generic delegated work small and reuse the established selection contract."""
    plan = validate_request_plan(output(delegate(selection_value=selection())), schema)
    action = plan.actions[0]
    assert isinstance(action, DelegateAction)
    assert action.request == "Cuenta las notas de Marta"
    assert action.selection is not None and action.selection.entity == "Marta"


def test_delegate_action_rejects_empty_unknown_and_invalid_selection_shapes(schema: dict) -> None:
    """Fail closed before app IDs, unknown fields, or malformed selections reach later routing."""
    invalid = [
        delegate(request="   "),
        delegate() | {"app_id": "analytics"},
        delegate(selection_value={"query": "Marta"}),
    ]
    for action in invalid:
        with pytest.raises(RequestPlanningError):
            validate_request_plan(output(action), schema)


def test_delegate_branch_is_closed_in_structured_outputs(schema: dict) -> None:
    """Expose only the generic delegate shape to the one planner Structured Outputs call."""
    alternatives = request_plan_json_schema(schema)["properties"]["actions"]["items"]["anyOf"]
    branch = next(
        item for item in alternatives if item["properties"]["kind"]["enum"] == ["delegate"]
    )
    assert branch["required"] == ["kind", "request", "selection"]
    assert branch["additionalProperties"] is False
    assert "app_id" not in branch["properties"]


def test_delegate_preserves_order_with_direct_actions(schema: dict) -> None:
    """Retain independent ordered retrieve, delegate, and write work without execution."""
    retrieve = {"kind": "retrieve", "plan": selection("Marta")}
    write = {
        "kind": "write",
        "units": [
            {
                "target": selection("presupuesto"),
                "intent": "record",
                "properties": [],
                "tag_changes": [],
                "facts": ["Quiero revisar mi presupuesto."],
                "references": [],
            }
        ],
    }
    plan = validate_request_plan(output(retrieve, delegate(), write), schema)
    assert [type(action) for action in plan.actions] == [
        RetrieveAction,
        DelegateAction,
        WriteAction,
    ]


def test_delegate_reuses_link_scope_and_filters_without_changing_direct_note_semantics(
    schema: dict,
) -> None:
    """Preserve shared graph candidate-set restrictions for direct and delegated work."""
    related = {
        "entity": None,
        "query": "notas relacionadas con Marta",
        "type": None,
        "filters": [{"field": "tags", "op": "contains", "value": "review"}],
        "link_scope": {
            "anchor": {"entity": "Marta", "query": "Marta", "type": "person", "filters": []},
            "direction": "both",
            "max_depth": 1,
        },
    }
    direct = validate_request_plan(output({"kind": "retrieve", "plan": related}), schema)
    delegated = validate_request_plan(output(delegate(selection_value=related)), schema)
    assert isinstance(direct.actions[0], RetrieveAction)
    assert isinstance(direct.actions[0].plan.link_scope, LinkScope)
    assert delegated.actions[0].selection == direct.actions[0].plan
    direct_note = validate_request_plan(output({"kind": "retrieve", "plan": selection()}), schema)
    assert direct_note.actions[0].plan.link_scope is None


def test_prompt_keeps_representable_selection_when_specialized_work_is_delegated(
    schema: dict,
) -> None:
    """Keep the production instruction aligned with the shared selection contract."""
    prompt = render_request_planner_prompt(
        schema, {"date": "2026-08-24", "time": "10:00", "timezone": "Europe/Paris"}
    )
    selection_position = prompt.index("FIRST identify the Odyssey knowledge candidate set")
    operation_position = prompt.index("THEN choose what operation")
    action_position = prompt.index("Use DelegateAction only")
    assert selection_position < operation_position < action_position
    assert "A non-null DelegateAction.selection obeys those same SelectionCriteria rules" in prompt
    assert "retaining that graph meaning only in query is insufficient" in prompt
    assert (
        "it may be null only when the request has no safely representable Odyssey knowledge "
        "candidate set" in prompt
    )
