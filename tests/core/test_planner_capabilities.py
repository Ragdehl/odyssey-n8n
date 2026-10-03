"""Schema-derived retrieval and write capability tests."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from odyssey_core.planner_capabilities import build_planner_capabilities, build_write_capabilities

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema used by planner capability projections."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def test_write_capabilities_are_schema_driven(schema: dict) -> None:
    """Expose canonical writable properties without hard-coded type/property branches."""
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
                }
            ],
        }
    )

    capabilities = build_write_capabilities(changed)

    assert capabilities["types"]["car"]["properties"]["registration_number"] == {
        "value_type": "string",
        "required": False,
        "description": "Vehicle registration number.",
        "constraints": {},
    }
    assert (
        capabilities["types"]["car"]["properties"]["registration_number"]["value_type"] == "string"
    )


def test_write_capabilities_fail_closed_on_unsupported_property_semantics(schema: dict) -> None:
    """Reject new technical value/constraint semantics until generic Core support exists."""
    unsupported_type = deepcopy(schema)
    unsupported_type["types"][0]["properties"].append(
        {
            "id": "confidence",
            "value_type": "number",
            "required": False,
            "description": "Confidence score.",
        }
    )
    with pytest.raises(ValueError, match="Unsupported writable property value type"):
        build_write_capabilities(unsupported_type)

    unsupported_constraint = deepcopy(schema)
    unsupported_constraint["types"][0]["properties"].append(
        {
            "id": "code",
            "value_type": "string",
            "required": False,
            "description": "External code.",
            "constraints": {"pattern": "^[A-Z]+$"},
        }
    )
    with pytest.raises(ValueError, match="unsupported constraints"):
        build_write_capabilities(unsupported_constraint)


def test_compatible_same_id_filter_fields_merge_type_scope(schema: dict) -> None:
    """Accumulate applies_to for compatible type properties instead of last-write-wins."""
    changed = deepcopy(schema)
    shared = {
        "id": "domain_status",
        "value_type": "string",
        "required": False,
        "description": "Domain status.",
        "filterable": True,
    }
    changed["types"][0]["properties"].append(deepcopy(shared))
    changed["types"][1]["properties"].append(deepcopy(shared))

    capabilities = build_planner_capabilities(changed)

    assert capabilities["filters"]["domain_status"]["applies_to"] == ["concept", "project"]


def test_incompatible_same_id_filter_fields_fail_closed(schema: dict) -> None:
    """Reject ambiguous same-ID filter definitions rather than silently overwriting one."""
    changed = deepcopy(schema)
    changed["types"][0]["properties"].append(
        {
            "id": "domain_status",
            "value_type": "string",
            "required": False,
            "description": "Domain status.",
            "filterable": True,
        }
    )
    changed["types"][1]["properties"].append(
        {
            "id": "domain_status",
            "value_type": "integer",
            "required": False,
            "description": "Domain status.",
            "filterable": True,
        }
    )

    with pytest.raises(ValueError, match="conflicting filter field"):
        build_planner_capabilities(changed)


def test_application_managed_types_are_hidden_from_generic_planner(schema: dict) -> None:
    """Keep Calendar-owned canonical types out of ordinary retrieval/write planning."""
    without_managed = deepcopy(schema)
    without_managed["types"] = [
        item for item in without_managed["types"] if "managed_by" not in item
    ]

    retrieval = build_planner_capabilities(schema)
    writes = build_write_capabilities(schema)

    assert "calendar_day" not in retrieval["types"]
    assert "calendar_day" not in retrieval["filters"]["type"]["controlled_values"]
    assert "calendar_day" not in writes["types"]
    assert retrieval == build_planner_capabilities(without_managed)
    assert writes == build_write_capabilities(without_managed)


def test_managed_type_filter_properties_do_not_leak_to_planner(schema: dict) -> None:
    """Exclude application-owned properties even if they later become internally filterable."""
    changed = deepcopy(schema)
    calendar_day = next(item for item in changed["types"] if item["id"] == "calendar_day")
    calendar_day["properties"][0]["filterable"] = True

    capabilities = build_planner_capabilities(changed)

    assert "date" not in capabilities["filters"]


def test_concept_description_is_positive_not_fallback(schema: dict) -> None:
    """Keep concept as a reusable abstraction rather than an underclassification escape hatch."""
    concept = next(item for item in schema["types"] if item["id"] == "concept")
    assert "semantic identity of its own" in concept["description"]
    assert "not a generic fallback" in concept["description"]


def test_journal_write_target_semantics_are_schema_declared_and_projected(schema: dict) -> None:
    """Expose date-bound journal destination semantics through generic write capabilities."""
    journal = next(item for item in schema["types"] if item["id"] == "journal_entry")
    entry_date = next(item for item in journal["properties"] if item["id"] == "entry_date")

    assert "constrain target selection by entry_date equal to that date" in journal["description"]
    assert "Never repurpose an entry from another date" in journal["description"]
    assert "preserve its entry_date" in entry_date["description"]
    assert "different date belongs to a different journal_entry" in entry_date["description"]

    projected = build_write_capabilities(schema)["types"]["journal_entry"]
    assert projected["description"] == journal["description"]
    assert projected["properties"]["entry_date"]["description"] == entry_date["description"]
