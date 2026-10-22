"""E5 untrusted GPT provider → Temporal → Core/E3 → Markdown → Calendar.

All actors and target notes are synthetic. A real-model provider test and
browser-on-n8n proof must still independently pass before adopting E5 in DEV.
"""

from __future__ import annotations

import pytest

from odyssey_apps.events.execution import execute_event_candidate
from odyssey_apps.events.mutations import EventMutationService
from odyssey_apps.events.provider import validate_event_candidate
from odyssey_core.notes import parse_note
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from tests.apps.events.test_event_calendar_vertical import CLOCK, calendar, setup


def proposal(op, *, title=None, reference=None, mentions=None):
    return {
        "operation": op,
        "event_reference": reference,
        "title_quote": title,
        "temporal_mentions": mentions if mentions is not None else [],
    }


def temporal(source, quote, *, date_value="2026-11-22"):
    return TemporalInterpretation(
        source,
        (
            TemporalMention(
                quote, TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date=date_value)
            ),
        ),
    )


def apply(
    tmp_path, source, candidate_payload, temporal_result, *, authed=True, ref=None, op_id="event-r1"
):
    schema, repo = setup(tmp_path)
    service = EventMutationService(repo, schema)
    candidate = validate_event_candidate(source, candidate_payload)
    result = execute_event_candidate(
        candidate=candidate,
        temporal=temporal_result,
        repository=repo,
        schema=schema,
        mutations=service,
        request_id=op_id,
        actor="fixture",
        now=CLOCK,
        authenticated=authed,
    )
    return result, repo, schema, service


def test_provider_bound_create_real_core_readback_calendar(tmp_path):
    source = "Foto del colegio el 22 de noviembre de 2026."
    result, repo, schema, _ = apply(
        tmp_path,
        source,
        proposal(
            "CREATE",
            title="Foto del colegio",
            mentions=[{"quote": "22 de noviembre de 2026", "role": "DATE"}],
        ),
        temporal(source, "22 de noviembre de 2026"),
    )
    assert result.status.value == "completed"
    assert len(result.affected_stable_note_ids) == 1
    assert result.action_results[0].unit_results[0].operation == "created"
    day = calendar(tmp_path, repo, schema).day("2026-11-22")
    assert len(day.events) == 1 and day.tasks == ()
    assert day.events[0].source.name == "Foto del colegio"


def test_provider_bound_create_reschedule_cancel_cas_and_markdown(tmp_path):
    source = "Foto del colegio el 22 de noviembre de 2026."
    schema, repo = setup(tmp_path)
    srv = EventMutationService(repo, schema)
    create = execute_event_candidate(
        candidate=validate_event_candidate(
            source,
            proposal(
                "CREATE",
                title="Foto del colegio",
                mentions=[{"quote": "22 de noviembre de 2026", "role": "DATE"}],
            ),
        ),
        temporal=temporal(source, "22 de noviembre de 2026"),
        repository=repo,
        schema=schema,
        mutations=srv,
        actor="fixture",
        authenticated=True,
        now=CLOCK,
        request_id="e5-1",
    )
    assert create.status.value == "completed"
    edit = "Cambia Foto del colegio al 24 de noviembre de 2026."
    updated = execute_event_candidate(
        candidate=validate_event_candidate(
            edit,
            proposal(
                "UPDATE",
                reference="Foto del colegio",
                mentions=[{"quote": "24 de noviembre de 2026", "role": "DATE"}],
            ),
        ),
        temporal=temporal(edit, "24 de noviembre de 2026", date_value="2026-11-24"),
        repository=repo,
        schema=schema,
        mutations=srv,
        actor="fixture",
        authenticated=True,
        now=CLOCK,
        request_id="e5-2",
    )
    assert updated.status.value == "completed"
    assert calendar(tmp_path, repo, schema).day("2026-11-22").events == ()
    assert len(calendar(tmp_path, repo, schema).day("2026-11-24").events) == 1
    cancel = "Cancela Foto del colegio."
    cancelled = execute_event_candidate(
        candidate=validate_event_candidate(
            cancel, proposal("CANCEL", reference="Foto del colegio")
        ),
        temporal=None,
        repository=repo,
        schema=schema,
        mutations=srv,
        actor="fixture",
        authenticated=True,
        now=CLOCK,
        request_id="e5-3",
    )
    assert cancelled.status.value == "completed"
    assert calendar(tmp_path, repo, schema).day("2026-11-24").events == ()
    assert (
        sum(repo.read_text(path).count("event_status:") == 1 for path in repo.list_markdown_paths())
        == 1
    )


@pytest.mark.parametrize(
    "candidate",
    [
        proposal(
            "CREATE",
            title="inventado",
            mentions=[{"quote": "22 de noviembre de 2026", "role": "DATE"}],
        ),
        proposal(
            "CREATE",
            title="Foto del colegio",
            mentions=[{"quote": "24 de noviembre de 2026", "role": "DATE"}],
        ),
        proposal("CREATE", title="Foto del colegio", mentions=[], reference="Foto del colegio"),
        proposal("CANCEL", reference="Foto del colegio", title="Foto del colegio"),
        proposal("UPDATE", reference=None, mentions=[{"quote": "22", "role": "DATE"}]),
    ],
)
def test_adversarial_provider_cannot_invent_event_title_identity_or_date(candidate):
    from odyssey_apps.events.interpretation import EventInterpretationError

    with pytest.raises(EventInterpretationError):
        validate_event_candidate("Foto del colegio el 22 de noviembre de 2026.", candidate)


def test_temporal_source_collision_and_disallowed_recurrence_fail_closed(tmp_path):
    source = "Foto del colegio el 22 de noviembre de 2026."
    schema, repo = setup(tmp_path)
    srv = EventMutationService(repo, schema)
    candidate = validate_event_candidate(
        source,
        proposal(
            "CREATE",
            title="Foto del colegio",
            mentions=[{"quote": "22 de noviembre de 2026", "role": "DATE"}],
        ),
    )
    mismatched = temporal(source, "Foto del colegio")
    result = execute_event_candidate(
        candidate=candidate,
        temporal=mismatched,
        repository=repo,
        schema=schema,
        mutations=srv,
        request_id="e5-invalid",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "needs_attention"
    assert not any("event_status:" in repo.read_text(path) for path in repo.list_markdown_paths())


def test_unauthenticated_event_never_mutates(tmp_path):
    source = "Foto del colegio el 22 de noviembre de 2026."
    result, repo, _, _ = apply(
        tmp_path,
        source,
        proposal(
            "CREATE",
            title="Foto del colegio",
            mentions=[{"quote": "22 de noviembre de 2026", "role": "DATE"}],
        ),
        temporal(source, "22 de noviembre de 2026"),
        authed=False,
    )
    assert result.status.value == "needs_attention"
    assert result.affected_stable_note_ids == ()
    assert tuple(repo.list_markdown_paths()) == ()


def test_exact_target_reference_requires_unique_event_not_guess(tmp_path):
    schema, repo = setup(tmp_path)
    for path, uid, title in [
        ("photo-a.md", "a", "Foto del colegio"),
        ("photo-b.md", "b", "Foto del colegio (otro grupo)"),
    ]:
        from odyssey_core import create_entity

        create_entity(
            repo,
            schema,
            path=path,
            entity_id=uid,
            metadata={
                "name": title,
                "type": "event",
                "event_status": "scheduled",
                "start_date": "2026-11-22",
            },
            content="",
            actor="fixture",
            now=CLOCK,
        )
    source = "Cancela Foto del colegio."
    result = execute_event_candidate(
        candidate=validate_event_candidate(
            source, proposal("CANCEL", reference="Foto del colegio")
        ),
        temporal=None,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-ambiguous",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "needs_attention"
    assert all(
        parse_note(repo.read_text(path)).metadata["event_status"] == "scheduled"
        for path in repo.list_markdown_paths()
    )


def test_postwrite_failure_preserves_partial_e3_receipt_not_false_no_write(tmp_path):
    from odyssey_apps.events.mutations import EventMutationError

    source = "Foto del colegio el 22 de noviembre de 2026."
    candidate = validate_event_candidate(
        source,
        proposal(
            "CREATE",
            title="Foto del colegio",
            mentions=[
                {"quote": "22 de noviembre de 2026", "role": "DATE"},
            ],
        ),
    )
    schema, repo = setup(tmp_path)

    class PartialMutation:
        def create(self, **_kwargs):
            raise EventMutationError(
                "POSTWRITE_UNVERIFIED", physical_write=True, target_id="event-physical"
            )

    result = execute_event_candidate(
        candidate=candidate,
        temporal=temporal(source, "22 de noviembre de 2026"),
        repository=repo,
        schema=schema,
        mutations=PartialMutation(),
        request_id="e5-partial",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "partial"
    assert result.affected_stable_note_ids == ("event-physical",)
    assert result.planning_error == "EVENT_POSTWRITE_UNVERIFIED"


def test_query_is_not_claimed_complete_without_bound_read_service(tmp_path):
    schema, repo = setup(tmp_path)
    source = "¿Qué eventos hay en noviembre?"
    result = execute_event_candidate(
        candidate=validate_event_candidate(source, proposal("QUERY")),
        temporal=None,
        repository=repo,
        schema=schema,
        mutations=EventMutationService(repo, schema),
        request_id="e5-query",
        actor="fixture",
        now=CLOCK,
        authenticated=True,
    )
    assert result.status.value == "needs_attention"
    assert result.planning_error == "EVENT_QUERY_NOT_CONNECTED"
