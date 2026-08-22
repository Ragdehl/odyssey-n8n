"""Focused Phase 15.1 tests for schema-driven selection reuse."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from odyssey_core.request_planning import RetrieveAction, WriteAction, validate_request_plan

ROOT = Path(__file__).resolve().parents[2]


def _schema_with_filterable_car_property() -> dict:
    """Return the canonical schema extended with one synthetic filterable car property."""
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    changed = deepcopy(schema)
    changed["types"].append(
        {
            "id": "car",
            "name": "Car",
            "description": "Reusable vehicle identity.",
            "examples": ["Family car"],
            "subtypes": [],
            "properties": [
                {
                    "id": "registration_number",
                    "value_type": "string",
                    "required": False,
                    "description": "Vehicle registration number.",
                    "filterable": True,
                }
            ],
        }
    )
    return changed


def test_synthetic_filterable_property_is_reused_by_retrieve_and_write_target() -> None:
    """Expose one schema-added filter through both selection surfaces without code branches."""
    schema = _schema_with_filterable_car_property()
    registration_filter = {
        "field": "registration_number",
        "op": "eq",
        "value": "1234-ABC",
    }
    payload = {
        "actions": [
            {
                "kind": "retrieve",
                "plan": {
                    "query": "our car",
                    "type": "car",
                    "filters": [registration_filter],
                },
            },
            {
                "kind": "write",
                "units": [
                    {
                        "target": {
                            "query": "our car",
                            "type": "car",
                            "filters": [registration_filter],
                        },
                        "intent": "amend",
                        "properties": [
                            {
                                "field": "registration_number",
                                "op": "set",
                                "value": "5678-XYZ",
                            }
                        ],
                        "facts": [],
                        "references": [],
                    }
                ],
            },
        ],
        "limitations": [],
    }

    plan = validate_request_plan(payload, schema)

    retrieve = plan.actions[0]
    write = plan.actions[1]
    assert isinstance(retrieve, RetrieveAction)
    assert isinstance(write, WriteAction)
    assert retrieve.plan.filters[0].field == "registration_number"
    assert write.units[0].target.filters[0].field == "registration_number"
    assert write.units[0].properties[0].field == "registration_number"
