"""Untrusted model-reply → E5 domain handoff, including adversarial messages.

Tests are provider-free by design: they do NOT claim a live chat/Writer E2E.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from odyssey_apps.events import EventInterpretationError, validate_event_proposal
from odyssey_core.domain_interpretation import DomainInterpretation


def reply(operation="CREATE", mentions=(), reference=None):
    return {
        "operation": operation,
        "temporal_mentions": [{"quote": quote, "role": role} for quote, role in mentions],
        "event_reference": reference,
    }


@pytest.mark.parametrize(
    ("source", "candidate", "intent", "quotes"),
    [
        (
            "Foto de clase el 22 de noviembre de 2026.",
            reply(mentions=(("22 de noviembre de 2026", "DATE"),)),
            "CREATE",
            ("22 de noviembre de 2026",),
        ),
        (
            "Campamento del 4 al 8 de julio.",
            reply(mentions=(("4", "START"), ("8 de julio", "END"))),
            "CREATE",
            ("4", "8 de julio"),
        ),
        (
            "Piscina todos los lunes hasta el 20 de junio.",
            reply(mentions=(("lunes", "RECURRING_WEEKDAY"), ("20 de junio", "RECURRENCE_RANGE"))),
            "CREATE",
            ("lunes", "20 de junio"),
        ),
        (
            "¿Qué hay la semana del 12 de octubre?",
            reply("QUERY", (("12 de octubre", "DATE"),)),
            "QUERY",
            ("12 de octubre",),
        ),
        (
            "Cancela la excursión del miércoles.",
            reply("CANCEL", (("miércoles", "DATE"),), "la excursión"),
            "CANCEL",
            ("miércoles",),
        ),
        (
            "Mueve la función de teatro del martes al jueves.",
            reply("UPDATE", (("martes", "START"), ("jueves", "END")), "la función de teatro"),
            "UPDATE",
            ("martes", "jueves"),
        ),
        (
            "Jornada escolar a las 08:30.",
            reply(mentions=(("08:30", "START"),)),
            "CREATE",
            ("08:30",),
        ),
        ("Mañana hay feria.", reply(mentions=(("Mañana", "DATE"),)), "CREATE", ("Mañana",)),
        ("El colegio tiene una fiesta de disfraces.", reply(), "CREATE", ()),
    ],
)
def test_recorded_proposal_validates_and_hands_off_source_verbatim(
    source, candidate, intent, quotes
):
    model_output = deepcopy(candidate)
    typed = validate_event_proposal(source, model_output)
    handoff = typed.as_domain_interpretation()
    assert type(handoff) is DomainInterpretation
    assert handoff.capability_id == "events"
    assert handoff.intent == intent
    assert handoff.source_text == source
    assert [e.source_text for e in handoff.evidence if e.kind == "event.temporal_role"] == list(
        quotes
    )
    assert all(e.kind in {"event.temporal_role", "event.reference"} for e in handoff.evidence)
    assert not hasattr(typed, "writer") and not hasattr(handoff, "write")
    assert candidate == model_output, "Untrusted reply must remain immutable to the validator"
    with pytest.raises(FrozenInstanceError):
        typed.operation = "QUERY"


@pytest.mark.parametrize(
    "key",
    [
        "note_id",
        "target_id",
        "resolved_datetime",
        "normalized_date",
        "year",
        "timezone",
        "author",
        "assignee",
        "task_to_create",
        "reminder_to_send",
        "source_text",
        "markdown",
        "writer_action",
        "source_note_id",
        "calendar_event_id",
    ],
)
def test_provider_can_never_gain_core_or_temporal_authority(key):
    data = reply(mentions=(("mañana", "DATE"),))
    data[key] = "invented"
    with pytest.raises(EventInterpretationError, match="unknown or missing fields"):
        validate_event_proposal("Mañana hay feria.", data)


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        (),
        [],
        {"operation": "CREATE", "temporal_mentions": []},
        {"operation": "CREATE", "temporal_mentions": [], "event_reference": None, "write": True},
        reply(operation="START_WORK_SESSION"),
        reply(operation="REMIND"),
        reply(operation=0),
        reply(mentions=(("mañana", "DATETIME"),)),
        reply(mentions=(("2026-10-21", "DATE"),)),
        reply(mentions=(("mañana", "DATE"), ("mañana", "DATE"))),
        reply(mentions=(("mañana", "DATE"),), reference="Feria inexistente"),
        reply(operation="CANCEL"),
        reply(operation="CREATE", reference="la feria"),
    ],
)
def test_forged_or_ungrounded_model_proposals_fail_closed(candidate):
    with pytest.raises(EventInterpretationError):
        validate_event_proposal("La feria será mañana.", candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        {
            "operation": "CREATE",
            "temporal_mentions": [{"quote": "mañana", "role": "DATE", "target": "self"}],
            "event_reference": None,
        },
        {"operation": "CREATE", "temporal_mentions": "mañana", "event_reference": None},
        {"operation": "CREATE", "temporal_mentions": [None], "event_reference": None},
        {
            "operation": "CREATE",
            "temporal_mentions": [{"quote": None, "role": "DATE"}],
            "event_reference": None,
        },
        {
            "operation": "CREATE",
            "temporal_mentions": [{"quote": "mañana", "role": None}],
            "event_reference": None,
        },
        {"operation": "CREATE", "temporal_mentions": [], "event_reference": 31},
        {"operation": "CREATE", "temporal_mentions": [], "event_reference": ["fiesta"]},
        reply(mentions=(("mañana", "DATE"),) * 17),
    ],
)
def test_malformed_provider_types_never_coerce(candidate):
    with pytest.raises(EventInterpretationError):
        validate_event_proposal("La feria será mañana.", candidate)


def test_date_fragment_must_not_match_inside_other_number():
    with pytest.raises(EventInterpretationError, match="source-bound"):
        validate_event_proposal("Fiesta el 14 de noviembre.", reply(mentions=(("4", "DATE"),)))


def test_two_overlapping_temporal_claims_cannot_both_inherit_one_span():
    source = "Fiesta el 14 de noviembre."
    with pytest.raises(EventInterpretationError, match="source-bound"):
        validate_event_proposal(
            source, reply(mentions=(("14", "START"), ("14 de noviembre", "END")))
        )


def test_repeat_occurrence_requires_explicit_scoping_and_cannot_choose_last():
    source = "Hay feria el lunes y otra feria el lunes."
    with pytest.raises(EventInterpretationError, match="source-bound"):
        validate_event_proposal(source, reply(mentions=(("lunes", "RECURRING_WEEKDAY"),)))


def test_distinct_source_scopes_preserve_two_events_without_fake_global_identity():
    pieces = ["Foto el 22 de noviembre.", "Cena el 23 de noviembre."]
    outputs = [
        reply(mentions=(("22 de noviembre", "DATE"),)),
        reply(mentions=(("23 de noviembre", "DATE"),)),
    ]
    result = [
        validate_event_proposal(source, payload).as_domain_interpretation()
        for source, payload in zip(pieces, outputs, strict=True)
    ]
    assert len(result) == 2
    assert [x.source_text for x in result] == pieces
    assert not any(hasattr(x, "note_id") for x in result)
    assert not any(hasattr(x, "write") for x in result)


def test_non_event_proposal_abstains_without_any_write_authority():
    source = "Mañana tengo que llamar a Ana y preparar la mochila."
    result = validate_event_proposal(source, reply(operation="ABSTAIN"))
    assert result.as_domain_interpretation().intent == "ABSTAIN"
    assert not result.as_domain_interpretation().evidence
    with pytest.raises(EventInterpretationError):
        validate_event_proposal(source, reply(operation="ABSTAIN", mentions=(("Mañana", "DATE"),)))
