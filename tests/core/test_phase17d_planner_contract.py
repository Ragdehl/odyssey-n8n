"""Provider-free planner contract regressions for append-first Phase 17D."""

import json
from pathlib import Path

from odyssey_core.request_planning import (
    RequestPlan,
    WriteAction,
    plan_fact_ordinals,
    validate_request_plan,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def _plan(units: list[dict]) -> object:
    """Validate a minimal provider-shaped write plan."""
    return validate_request_plan(
        {"actions": [{"kind": "write", "units": units}], "limitations": []}, SCHEMA
    )


def _unit(
    facts: list[str], *, properties: list[dict] | None = None, intent: str = "record"
) -> dict:
    """Build one Marta write unit for structured-output contract tests."""
    return {
        "target": {
            "entity": "Marta",
            "query": "Marta",
            "type": "person",
            "filters": [],
            "link_scope": None,
        },
        "cardinality": "one",
        "destination_type": None,
        "intent": intent,
        "properties": properties or [],
        "tag_changes": [],
        "facts": facts,
        "references": [],
    }


def test_atomic_split_contract_accepts_three_independent_facts() -> None:
    """Keep independent knowledge as three ordered facts rather than one compound entry."""
    action = _plan(
        [
            _unit(
                [
                    "Marta trabaja en Thales.",
                    "Marta tiene dos hijos.",
                    "Marta se va a mudar a Lyon.",
                ]
            )
        ]
    )
    assert isinstance(action.actions[0], WriteAction)
    assert action.actions[0].units[0].facts == (
        "Marta trabaja en Thales.",
        "Marta tiene dos hijos.",
        "Marta se va a mudar a Lyon.",
    )


def test_property_conversational_fact_and_unregistered_concept_contracts() -> None:
    """Retain registered conversational knowledge while leaving employer unregistered."""
    action = _plan(
        [
            _unit(
                ["Ahora es mi jefa."],
                properties=[{"field": "relationship_to_user", "op": "set", "value": "jefa"}],
            )
        ]
    )
    unit = action.actions[0].units[0]
    assert unit.facts == ("Ahora es mi jefa.",) and unit.properties[0].value == "jefa"
    unregistered = _plan([_unit(["Marta ahora trabaja en Thales."])])
    assert unregistered.actions[0].units[0].properties == ()


def test_correction_and_explicit_remove_use_existing_write_units() -> None:
    """Represent correction as ordered remove plus amend, without a new operation kind."""
    action = _plan(
        [
            _unit(["Marta no trabaja en Airbus."], intent="remove"),
            _unit(["Marta trabaja en Thales."], intent="amend"),
        ]
    )
    assert isinstance(action.actions[0], WriteAction)
    assert [unit.intent for unit in action.actions[0].units] == ["remove", "amend"]


def test_plan_ordinals_ignore_nonwrite_actions_and_execution_outcomes() -> None:
    """Keep later fact ordinals stable regardless of retrieval ordering or failed execution."""
    first = _plan([_unit(["first"])])
    second = _plan([_unit(["second", "third"])])
    combined = RequestPlan(first.actions + second.actions, ())
    assert plan_fact_ordinals(combined) == ((0,), (1, 2))
