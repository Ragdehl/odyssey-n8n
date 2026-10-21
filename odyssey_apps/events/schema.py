"""Events-owned canonical note registration; no alternative Writer or Temporal."""

from __future__ import annotations

from odyssey_apps.schema_extensions import ApplicationSchemaExtension

EVENT_TYPE = "event"
EVENT_STATUS_VALUES = ("scheduled", "cancelled")

EVENT_SCHEMA_EXTENSION = ApplicationSchemaExtension(
    capability_id="events",
    types=(
        {
            "id": EVENT_TYPE,
            "name": "Event",
            "description": (
                "A dated occurrence rather than an actionable Task. "
                "Calendar derives projections from canonical dates."
            ),
            "examples": ["School photo", "Summer camp"],
            "managed_by": "events",
            "repeatable_identity": True,
            "notes_visible": True,
            "referenceable": True,
            "content_writable": True,
            "calendar_projection": "occurrence",
            "properties": [
                {
                    "id": "event_status",
                    "value_type": "string",
                    "required": True,
                    "constraints": {"enum": list(EVENT_STATUS_VALUES)},
                    "description": "Explicit Events-owned lifecycle; cancelled occurrences are hidden from schedule.",
                    "filterable": True,
                },
                {
                    "id": "start_date",
                    "value_type": "date",
                    "required": True,
                    "description": "The Temporal-verified first inclusive local calendar date.",
                    "calendar_role": "occurrence_start_date",
                    "filterable": True,
                },
                {
                    "id": "end_date",
                    "value_type": "date",
                    "required": False,
                    "description": "Last inclusive date of a multi-day occurrence; must not precede start_date.",
                    "calendar_role": "occurrence_end_date",
                    "filterable": True,
                },
                {
                    "id": "recurrence_weekday",
                    "value_type": "integer",
                    "required": False,
                    "constraints": {"enum": list(range(7))},
                    "description": "Bounded weekly recurrence: Monday=0 to Sunday=6, only within explicit start_date/end_date.",
                    "filterable": False,
                },
                {
                    "id": "start_at",
                    "value_type": "string",
                    "required": False,
                    "constraints": {"format": "date-time"},
                    "description": "Optional Temporal-resolved instant with explicit UTC offset.",
                    "calendar_role": "occurrence_start_time",
                    "filterable": True,
                },
                {
                    "id": "end_at",
                    "value_type": "string",
                    "required": False,
                    "constraints": {"format": "date-time"},
                    "description": "Optional bounded end instant with explicit UTC offset.",
                    "calendar_role": "occurrence_end_time",
                    "filterable": True,
                },
            ],
        },
    ),
)
