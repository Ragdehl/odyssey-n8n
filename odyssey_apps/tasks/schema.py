"""Canonical schema contribution owned by the Tasks application."""

from __future__ import annotations

from odyssey_apps.schema_extensions import ApplicationSchemaExtension

TASK_TYPE = "task"
TASK_STATUS_VALUES = ("pending", "in_progress", "completed", "cancelled")

TASK_SCHEMA_EXTENSION = ApplicationSchemaExtension(
    capability_id="tasks",
    types=(
        {
            "id": TASK_TYPE,
            "name": "Task",
            "description": (
                "Actionable commitment with a Tasks-owned lifecycle. It may accumulate ordinary "
                "knowledge, references, and context while Tasks owns status and scheduling semantics."
            ),
            "examples": ["Call the bank", "Prepare the apartment inventory"],
            "managed_by": "tasks",
            "properties": [
                {
                    "id": "status",
                    "value_type": "string",
                    "required": True,
                    "description": "Tasks-owned lifecycle state.",
                    "constraints": {"enum": list(TASK_STATUS_VALUES)},
                    "filterable": True,
                },
                {
                    "id": "target_date",
                    "value_type": "date",
                    "required": False,
                    "description": (
                        "Calendar day on which the user intends to address the task; not a deadline."
                    ),
                    "filterable": True,
                },
                {
                    "id": "planned_start_at",
                    "value_type": "string",
                    "required": False,
                    "description": "Exact offset-aware instant when planned task work starts.",
                    "constraints": {"format": "date-time"},
                    "filterable": True,
                },
                {
                    "id": "planned_end_at",
                    "value_type": "string",
                    "required": False,
                    "description": "Exact offset-aware instant when planned task work ends.",
                    "constraints": {"format": "date-time"},
                    "filterable": True,
                },
                {
                    "id": "deadline_at",
                    "value_type": "string",
                    "required": False,
                    "description": (
                        "Hard task deadline as either an exact date or offset-aware exact date-time."
                    ),
                    "constraints": {"format": "temporal-anchor"},
                    "filterable": True,
                },
                {
                    "id": "completed_at",
                    "value_type": "string",
                    "required": False,
                    "description": "Exact offset-aware instant when the task became completed.",
                    "constraints": {"format": "date-time"},
                    "filterable": True,
                },
            ],
        },
    ),
)
