"""Historical Calendar routing descriptor retained only for consumed benchmark evidence."""

from odyssey_apps import ApplicationDescriptor

CALENDAR_DESCRIPTOR = ApplicationDescriptor(
    id="calendar",
    routing_description=(
        "temporal interpretation of date-qualified statements, day/date-owned occurrences, "
        "personal diary/journal capture, and Calendar navigation"
    ),
    dependencies=("temporal",),
)
