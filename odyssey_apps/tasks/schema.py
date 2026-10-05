"""Canonical schema contribution owned by the Tasks application."""

from __future__ import annotations

from odyssey_apps.schema_extensions import ApplicationSchemaExtension

TASK_TYPE = "task"
WORK_SESSION_TYPE = "work_session"
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
            "repeatable_identity": True,
            "notes_visible": True,
            "referenceable": True,
            "content_writable": True,
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
                    "calendar_role": "target",
                },
                {
                    "id": "planned_start_at",
                    "value_type": "string",
                    "required": False,
                    "description": "Exact offset-aware instant when planned task work starts.",
                    "constraints": {"format": "date-time"},
                    "filterable": True,
                    "calendar_role": "planned_start",
                },
                {
                    "id": "planned_end_at",
                    "value_type": "string",
                    "required": False,
                    "description": "Exact offset-aware instant when planned task work ends.",
                    "constraints": {"format": "date-time"},
                    "filterable": True,
                    "calendar_role": "planned_end",
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
                    "calendar_role": "deadline",
                },
                {
                    "id": "completed_at",
                    "value_type": "string",
                    "required": False,
                    "description": "Exact offset-aware instant when the task became completed.",
                    "constraints": {"format": "date-time"},
                    "filterable": True,
                    "calendar_role": "completed",
                },
            ],
        },
        {
            "id": WORK_SESSION_TYPE,
            "name": "Work Session",
            "description": (
                "Tasks-owned occurrence recording actual work performed on one canonical Task. "
                "It is hidden from ordinary Notes and edited only through Tasks operations."
            ),
            "examples": ["Work session for Prepare the apartment inventory"],
            "managed_by": "tasks",
            "repeatable_identity": True,
            "notes_visible": False,
            "referenceable": False,
            "content_writable": False,
            "properties": [
                {
                    "id": "task_id",
                    "value_type": "string",
                    "required": True,
                    "description": "Stable canonical Task ID owning this Work Session.",
                    "filterable": False,
                },
                {
                    "id": "started_at",
                    "value_type": "string",
                    "required": True,
                    "description": "Exact offset-aware instant when actual work started.",
                    "constraints": {"format": "date-time"},
                    "filterable": False,
                },
                {
                    "id": "ended_at",
                    "value_type": "string",
                    "required": False,
                    "description": "Exact offset-aware instant when actual work ended; absent while active.",
                    "constraints": {"format": "date-time"},
                    "filterable": False,
                },
            ],
        },
    ),
)
