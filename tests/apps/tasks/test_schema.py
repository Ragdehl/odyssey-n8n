"""Tasks-owned schema extension contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.schema_extensions import (
    ApplicationSchemaError,
    ApplicationSchemaExtension,
    compose_application_schema,
)
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION, TASK_STATUS_VALUES
from odyssey_core.schema_types import ordinary_type_ids

ROOT = Path(__file__).resolve().parents[3]


def base_schema() -> dict:
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def test_tasks_registers_domain_type_without_granting_ordinary_core_authority() -> None:
    schema = compose_application_schema(base_schema(), (TASK_SCHEMA_EXTENSION,))
    task = next(item for item in schema["types"] if item["id"] == "task")
    assert task["managed_by"] == "tasks"
    assert "task" not in ordinary_type_ids(schema)
    properties = {item["id"]: item for item in task["properties"]}
    assert properties["status"]["constraints"]["enum"] == list(TASK_STATUS_VALUES)
    assert properties["target_date"]["value_type"] == "date"
    assert properties["planned_start_at"]["constraints"]["format"] == "date-time"
    assert properties["deadline_at"]["constraints"]["format"] == "temporal-anchor"
    assert properties["completed_at"]["constraints"]["format"] == "date-time"


def test_application_schema_rejects_type_collision_and_wrong_owner() -> None:
    duplicate = ApplicationSchemaExtension(
        "tasks",
        (
            {
                "id": "person",
                "name": "Bad",
                "description": "bad",
                "examples": [],
                "managed_by": "tasks",
                "properties": [],
            },
        ),
    )
    with pytest.raises(ApplicationSchemaError, match="conflicts"):
        compose_application_schema(base_schema(), (duplicate,))

    with pytest.raises(ApplicationSchemaError, match="managed by"):
        ApplicationSchemaExtension(
            "tasks",
            (
                {
                    "id": "task",
                    "name": "Task",
                    "description": "bad owner",
                    "examples": [],
                    "managed_by": "calendar",
                    "properties": [],
                },
            ),
        )


def test_task_values_use_core_generic_validation_and_controlled_status() -> None:
    from odyssey_core.notes import Note, NoteValidationError, validate_note
    from odyssey_core.schema_types import planning_schema_for_capability

    schema = compose_application_schema(base_schema(), (TASK_SCHEMA_EXTENSION,))
    planning = planning_schema_for_capability(schema, "tasks")
    assert "task" in ordinary_type_ids(planning)
    assert "task" not in ordinary_type_ids(schema)

    metadata = {
        "id": "task-1",
        "name": "Call the bank",
        "type": "task",
        "created_at": "2026-10-04T21:00:00+02:00",
        "updated_at": "2026-10-04T21:00:00+02:00",
        "created_by": {"human": "user-1", "app": "tasks"},
        "updated_by": {"human": "user-1", "app": "tasks"},
        "revision": 1,
        "schema_version": 3,
        "status": "pending",
        "target_date": "2026-10-06",
        "planned_start_at": "2026-10-06T14:00:00+02:00",
        "planned_end_at": "2026-10-06T16:00:00+02:00",
        "deadline_at": "2026-10-09",
    }
    validate_note(Note(metadata, "- Call the bank.\n"), schema)
    metadata["deadline_at"] = "2026-10-09T17:30:00+02:00"
    validate_note(Note(metadata, "- Call the bank.\n"), schema)

    bad = dict(metadata, status="done")
    with pytest.raises(NoteValidationError, match="controlled value"):
        validate_note(Note(bad, "- Call the bank.\n"), schema)

    bad_deadline = dict(metadata, deadline_at="2026-10-09T17:30:00")
    with pytest.raises(NoteValidationError, match="temporal anchor"):
        validate_note(Note(bad_deadline, "- Call the bank.\n"), schema)


def test_task_domain_projection_changes_only_app_owned_creation_authority() -> None:
    from odyssey_core.domain_interpretation import DomainInterpretation
    from odyssey_core.experimental_luna_planning import luna_experimental_result_json_schema
    from odyssey_core.schema_types import planning_schema_for_capability

    schema = compose_application_schema(base_schema(), (TASK_SCHEMA_EXTENSION,))
    ordinary = planning_schema_for_capability(schema, None)
    temporal = planning_schema_for_capability(schema, "temporal")
    tasks = planning_schema_for_capability(schema, "tasks")
    assert ordinary == temporal == schema
    assert "task" not in ordinary_type_ids(ordinary)
    assert "task" in ordinary_type_ids(tasks)

    interpretation = DomainInterpretation("tasks", "Tengo que llamar al banco", "CREATE")
    provider = luna_experimental_result_json_schema(tasks, interpretation)
    semantic_identity = provider["$defs"]["semantic_identity"]
    note_types = semantic_identity["properties"]["note_type"]["anyOf"][1]["enum"]
    assert "task" in note_types
