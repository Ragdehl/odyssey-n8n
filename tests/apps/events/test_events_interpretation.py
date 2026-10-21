"""E5 domain-only tests; no E4, Writer, vault, GPT or schema dependencies."""

from dataclasses import FrozenInstanceError

import pytest

from odyssey_apps.events import (
    EventInterpretation,
    EventInterpretationError,
    EventOperation,
    EventTemporalMention,
    EventTemporalRole,
)
from odyssey_core.domain_interpretation import DomainInterpretation


@pytest.mark.parametrize(
    ("text", "quotes_and_roles"),
    [
        (
            "La foto de clase es el 22 de septiembre.",
            (("22 de septiembre", EventTemporalRole.DATE),),
        ),
        (
            "Campamento del 4 al 8 de julio.",
            (("4", EventTemporalRole.START), ("8 de julio", EventTemporalRole.END)),
        ),
        (
            "Piscina los lunes hasta el 20 de junio.",
            (
                ("lunes", EventTemporalRole.RECURRING_WEEKDAY),
                ("20 de junio", EventTemporalRole.RECURRENCE_RANGE),
            ),
        ),
        ("Excursión por la mañana.", (("por la mañana", EventTemporalRole.START),)),
    ],
)
def test_event_occurrence_roles_preserve_exact_source_without_inventing_dates(
    text, quotes_and_roles
):
    mentions = tuple(EventTemporalMention(quote, role) for quote, role in quotes_and_roles)
    event = EventInterpretation(text, EventOperation.CREATE, mentions)
    common = event.as_domain_interpretation()
    assert isinstance(common, DomainInterpretation)
    assert (common.capability_id, common.source_text, common.intent) == ("events", text, "CREATE")
    assert [(item.source_text, item.value) for item in common.evidence] == [
        (quote, role.value) for quote, role in quotes_and_roles
    ]
    assert all("2026" not in item.value for item in common.evidence)
    assert not hasattr(event, "write") and not hasattr(event, "repository")


@pytest.mark.parametrize("operation", [EventOperation.UPDATE, EventOperation.CANCEL])
def test_lifecycle_uses_source_reference_but_never_a_canonical_note_id(operation):
    text = "Cancela la excursión del miércoles."
    event = EventInterpretation(text, operation, event_reference="la excursión")
    handoff = event.as_domain_interpretation()
    assert handoff.evidence[0].kind == "event.reference"
    assert handoff.evidence[0].value == "la excursión"
    with pytest.raises(FrozenInstanceError):
        event.event_reference = "other"


def test_event_query_without_mutation():
    event = EventInterpretation("¿Qué excursiones hay en noviembre?", EventOperation.QUERY)
    assert event.as_domain_interpretation().intent == "QUERY"
    assert event.as_domain_interpretation().evidence == ()


@pytest.mark.parametrize(
    "make",
    [
        lambda: EventInterpretation("", EventOperation.CREATE),
        lambda: EventInterpretation("Feria", "CREATE"),
        lambda: EventInterpretation("Feria", EventOperation.UPDATE),
        lambda: EventInterpretation("Feria", EventOperation.CANCEL),
        lambda: EventInterpretation("Feria", EventOperation.CREATE, event_reference="Feria"),
        lambda: EventInterpretation("Feria", EventOperation.UPDATE, event_reference="otra"),
        lambda: EventInterpretation(
            "El lunes y el lunes",
            EventOperation.CREATE,
            (EventTemporalMention("lunes", EventTemporalRole.DATE),),
        ),
        lambda: EventInterpretation(
            "El jueves",
            EventOperation.CREATE,
            (EventTemporalMention("viernes", EventTemporalRole.DATE),),
        ),
        lambda: EventInterpretation(
            "El martes",
            EventOperation.CREATE,
            [EventTemporalMention("martes", EventTemporalRole.DATE)],
        ),
        lambda: EventInterpretation(
            "El martes",
            EventOperation.CREATE,
            (EventTemporalMention("martes", EventTemporalRole.DATE),) * 2,
        ),
        lambda: EventTemporalMention("", EventTemporalRole.DATE),
        lambda: EventTemporalMention("martes", "DATE"),
    ],
)
def test_unsupported_or_ungrounded_interpretation_fails_closed(make):
    with pytest.raises(EventInterpretationError):
        make()


def test_event_domain_requires_no_schema_calendar_or_tasks_runtime_registration():
    event = EventInterpretation("Fiesta el sábado", EventOperation.CREATE)
    data = event.as_domain_interpretation()
    assert data.capability_id == "events"
    assert data.evidence == ()
    assert not hasattr(event, "task_target")
    assert not hasattr(event, "reminder_schedule")
