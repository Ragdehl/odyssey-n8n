"""Provider-free Tasks lifecycle and Temporal composition tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import (
    OpenAITaskInterpreter,
    TaskActivityTarget,
    TaskInterpretation,
    TaskInterpretationError,
    TaskOperation,
    TaskQueryScope,
    TaskRelationshipMention,
    TaskRelationshipRole,
    TaskTemporalMention,
    TaskTemporalRole,
    compose_task_domain_interpretation,
    compose_work_session_activity_date,
    compose_work_session_times,
)
from odyssey_core.temporal_interpretation import parse_temporal_interpretation


def temporal(source: str, text: str, kind: str, *, date=None, dt=None):  # type: ignore[no-untyped-def]
    return parse_temporal_interpretation(
        {
            "mentions": [
                {
                    "temporal_text": text,
                    "temporal": {
                        "kind": kind,
                        "exact_date": date,
                        "exact_datetime": dt,
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                }
            ]
        },
        source,
        timezone="Europe/Paris",
    )


def evidence_map(domain):  # type: ignore[no-untyped-def]
    return {item.kind: item.value for item in domain.evidence}


def test_create_composes_status_and_target_date_without_temporal_fact_authority() -> None:
    source = "Tengo que llamar al banco el viernes"
    task = TaskInterpretation(
        source,
        TaskOperation.CREATE,
        (TaskTemporalMention("el viernes", TaskTemporalRole.TARGET_DATE),),
    )
    resolved = temporal(source, "el viernes", "EXACT_DATE", date="2026-10-09")
    domain = compose_task_domain_interpretation(task, resolved, now="2026-10-04T21:40:00+02:00")
    assert domain.capability_id == "tasks"
    assert domain.intent == "CREATE"
    assert evidence_map(domain) == {
        "property.status": "pending",
        "property.target_date": "2026-10-09",
    }
    assert not domain.temporal_references()


def test_deadline_preserves_date_only_and_exact_datetime_without_inventing_clock() -> None:
    date_source = "Tengo que enviar la solicitud antes del viernes"
    date_task = TaskInterpretation(
        date_source,
        TaskOperation.CREATE,
        (TaskTemporalMention("viernes", TaskTemporalRole.DEADLINE_AT),),
    )
    date_domain = compose_task_domain_interpretation(
        date_task,
        temporal(date_source, "viernes", "EXACT_DATE", date="2026-10-09"),
        now="2026-10-04T21:40:00+02:00",
    )
    assert evidence_map(date_domain)["property.deadline_at"] == "2026-10-09"

    time_source = "Tengo que enviarla el viernes antes de las 17:30"
    time_task = TaskInterpretation(
        time_source,
        TaskOperation.CREATE,
        (TaskTemporalMention("el viernes antes de las 17:30", TaskTemporalRole.DEADLINE_AT),),
    )
    time_domain = compose_task_domain_interpretation(
        time_task,
        temporal(
            time_source,
            "el viernes antes de las 17:30",
            "EXACT_DATETIME",
            dt="2026-10-09T17:30:00+02:00",
        ),
        now="2026-10-04T21:40:00+02:00",
    )
    assert evidence_map(time_domain)["property.deadline_at"] == "2026-10-09T17:30:00+02:00"


def test_complete_sets_status_and_exact_completion_capture_time() -> None:
    source = "Marca llamar al banco como hecho"
    domain = compose_task_domain_interpretation(
        TaskInterpretation(source, TaskOperation.COMPLETE),
        None,
        now="2026-10-04T21:42:03+02:00",
    )
    assert evidence_map(domain) == {
        "property.status": "completed",
        "property.completed_at": "2026-10-04T21:42:03+02:00",
    }


def test_planned_start_requires_exact_datetime_and_mixed_set_remove_fails_closed() -> None:
    source = "El martes empiezo a las 14:00"
    task = TaskInterpretation(
        source,
        TaskOperation.UPDATE,
        (TaskTemporalMention("El martes empiezo a las 14:00", TaskTemporalRole.PLANNED_START_AT),),
    )
    with pytest.raises(TaskInterpretationError, match="exact date-time"):
        compose_task_domain_interpretation(
            task,
            temporal(source, "El martes empiezo a las 14:00", "EXACT_DATE", date="2026-10-06"),
            now="2026-10-04T21:42:03+02:00",
        )

    with pytest.raises(TaskInterpretationError, match="Mixed"):
        TaskInterpretation(
            source,
            TaskOperation.UPDATE,
            (
                TaskTemporalMention(
                    "El martes empiezo a las 14:00", TaskTemporalRole.PLANNED_START_AT
                ),
            ),
            ("deadline_at",),
        )


def test_query_is_domain_semantics_without_core_target_or_property_mutation() -> None:
    source = "¿Qué tareas tengo vencidas?"
    domain = compose_task_domain_interpretation(
        TaskInterpretation(source, TaskOperation.QUERY, query_scope=TaskQueryScope.OVERDUE),
        None,
        now="2026-10-04T21:42:03+02:00",
    )
    assert evidence_map(domain) == {"task.query_scope": "OVERDUE"}


def test_relationship_mentions_preserve_roles_without_resolving_identity() -> None:
    source = "Beatriz tiene que reunir documentos para preparar dossier"
    task = TaskInterpretation(
        source,
        TaskOperation.CREATE,
        relationship_mentions=(
            TaskRelationshipMention("Beatriz", TaskRelationshipRole.ASSIGNEE),
            TaskRelationshipMention("preparar dossier", TaskRelationshipRole.PARENT_TASK),
        ),
    )
    assert [(item.text, item.role.value) for item in task.relationship_mentions] == [
        ("Beatriz", "ASSIGNEE"),
        ("preparar dossier", "PARENT_TASK"),
    ]


def test_relationship_mentions_are_for_create_or_update_only() -> None:
    source = "Beatriz ha terminado llamar al banco"
    with pytest.raises(TaskInterpretationError, match="relationship"):
        TaskInterpretation(
            source,
            TaskOperation.COMPLETE,
            relationship_mentions=(
                TaskRelationshipMention("Beatriz", TaskRelationshipRole.ASSIGNEE),
            ),
        )


def test_work_session_start_uses_current_instant_without_inventing_temporal_text() -> None:
    source = "Empiezo una work session para Trabajar en Odyssey"
    task = TaskInterpretation(
        source,
        TaskOperation.START_WORK_SESSION,
        task_reference="Trabajar en Odyssey",
    )
    assert compose_work_session_times(task, None, now="2026-10-05T18:30:00+02:00") == (
        "2026-10-05T18:30:00+02:00",
        None,
    )
    with pytest.raises(TaskInterpretationError, match="do not mutate Task state"):
        compose_task_domain_interpretation(task, None, now="2026-10-05T18:30:00+02:00")


def test_work_session_edit_maps_exact_actual_work_time_without_task_schedule_authority() -> None:
    source = "La work session de Odyssey empezó hoy a las 17:30"
    phrase = "hoy a las 17:30"
    task = TaskInterpretation(
        source,
        TaskOperation.EDIT_WORK_SESSION,
        (TaskTemporalMention(phrase, TaskTemporalRole.WORK_SESSION_START_AT),),
        task_reference="Odyssey",
    )
    resolved = temporal(
        source,
        phrase,
        "EXACT_DATETIME",
        dt="2026-10-05T17:30:00+02:00",
    )
    assert compose_work_session_times(task, resolved, now="2026-10-05T18:30:00+02:00") == (
        "2026-10-05T17:30:00+02:00",
        None,
    )


def test_work_session_merges_split_date_and_clock_for_one_actual_work_instant() -> None:
    source = "Corrige la sesión de Odyssey de hoy: terminé a las 18:15."
    task = TaskInterpretation(
        source,
        TaskOperation.EDIT_WORK_SESSION,
        (
            TaskTemporalMention("hoy", TaskTemporalRole.WORK_SESSION_END_AT),
            TaskTemporalMention("a las 18:15", TaskTemporalRole.WORK_SESSION_END_AT),
        ),
        task_reference="Odyssey",
    )
    resolved = parse_temporal_interpretation(
        {
            "mentions": [
                {
                    "temporal_text": "hoy",
                    "temporal": {
                        "kind": "EXACT_DATE",
                        "exact_date": "2026-10-05",
                        "exact_datetime": None,
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                },
                {
                    "temporal_text": "18:15",
                    "temporal": {
                        "kind": "EXACT_DATETIME",
                        "exact_date": None,
                        "exact_datetime": "2026-10-05T18:15:00+02:00",
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                },
            ]
        },
        source,
        timezone="Europe/Paris",
    )
    assert compose_work_session_times(task, resolved, now="2026-10-05T19:00:00+02:00") == (
        None,
        "2026-10-05T18:15:00+02:00",
    )


def test_work_session_split_date_and_clock_fail_closed_when_they_conflict() -> None:
    source = "Corrige la sesión de Odyssey de hoy: terminé a las 18:15."
    task = TaskInterpretation(
        source,
        TaskOperation.EDIT_WORK_SESSION,
        (
            TaskTemporalMention("hoy", TaskTemporalRole.WORK_SESSION_END_AT),
            TaskTemporalMention("a las 18:15", TaskTemporalRole.WORK_SESSION_END_AT),
        ),
        task_reference="Odyssey",
    )
    resolved = parse_temporal_interpretation(
        {
            "mentions": [
                {
                    "temporal_text": "hoy",
                    "temporal": {
                        "kind": "EXACT_DATE",
                        "exact_date": "2026-10-04",
                        "exact_datetime": None,
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                },
                {
                    "temporal_text": "18:15",
                    "temporal": {
                        "kind": "EXACT_DATETIME",
                        "exact_date": None,
                        "exact_datetime": "2026-10-05T18:15:00+02:00",
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                },
            ]
        },
        source,
        timezone="Europe/Paris",
    )
    with pytest.raises(TaskInterpretationError, match="conflict"):
        compose_work_session_times(task, resolved, now="2026-10-05T19:00:00+02:00")


def test_work_session_shared_date_can_ground_both_corrected_instants() -> None:
    source = (
        "Corrige la work session de Trabajar en Odyssey de hoy: "
        "empezó a las 18:00 y terminó a las 18:30."
    )
    task = TaskInterpretation(
        source,
        TaskOperation.EDIT_WORK_SESSION,
        (
            TaskTemporalMention("de hoy", TaskTemporalRole.WORK_SESSION_START_AT),
            TaskTemporalMention("a las 18:00", TaskTemporalRole.WORK_SESSION_START_AT),
            TaskTemporalMention("de hoy", TaskTemporalRole.WORK_SESSION_END_AT),
            TaskTemporalMention("a las 18:30", TaskTemporalRole.WORK_SESSION_END_AT),
        ),
        task_reference="Trabajar en Odyssey",
    )
    resolved = parse_temporal_interpretation(
        {
            "mentions": [
                {
                    "temporal_text": "de hoy",
                    "temporal": {
                        "kind": "EXACT_DATE",
                        "exact_date": "2026-10-05",
                        "exact_datetime": None,
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                },
                {
                    "temporal_text": "a las 18:00",
                    "temporal": {
                        "kind": "EXACT_DATETIME",
                        "exact_date": None,
                        "exact_datetime": "2026-10-05T18:00:00+02:00",
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                },
                {
                    "temporal_text": "a las 18:30",
                    "temporal": {
                        "kind": "EXACT_DATETIME",
                        "exact_date": None,
                        "exact_datetime": "2026-10-05T18:30:00+02:00",
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                },
            ]
        },
        source,
        timezone="Europe/Paris",
    )
    assert compose_work_session_times(task, resolved, now="2026-10-05T19:00:00+02:00") == (
        "2026-10-05T18:00:00+02:00",
        "2026-10-05T18:30:00+02:00",
    )


def test_work_session_requires_grounded_task_reference_and_rejects_schedule_roles() -> None:
    source = "Empiezo una work session para Odyssey"
    with pytest.raises(TaskInterpretationError, match="Task reference"):
        TaskInterpretation(source, TaskOperation.START_WORK_SESSION)
    with pytest.raises(TaskInterpretationError, match="Task reference"):
        TaskInterpretation(
            source, TaskOperation.START_WORK_SESSION, task_reference="Una tarea inventada"
        )
    with pytest.raises(TaskInterpretationError, match="scheduling temporal roles"):
        TaskInterpretation(
            source,
            TaskOperation.START_WORK_SESSION,
            (TaskTemporalMention("Odyssey", TaskTemporalRole.TARGET_DATE),),
            task_reference="Odyssey",
        )
    with pytest.raises(TaskInterpretationError, match="Only Work Session"):
        TaskInterpretation(source, TaskOperation.START, task_reference="Odyssey")


def test_work_session_activity_supports_current_session_and_exact_date_selection() -> None:
    current_source = "Apunta en la work session actual que he terminado los tests"
    current = TaskInterpretation(
        current_source,
        TaskOperation.ADD_WORK_SESSION_ACTIVITY,
        activity_text="he terminado los tests",
        activity_target=TaskActivityTarget.ACTIVE,
    )
    assert compose_work_session_activity_date(current, None) is None
    assert current.task_reference is None

    dated_source = "En la work session de Odyssey de hoy apunta que corregí el calendario"
    dated = TaskInterpretation(
        dated_source,
        TaskOperation.ADD_WORK_SESSION_ACTIVITY,
        (TaskTemporalMention("hoy", TaskTemporalRole.WORK_SESSION_AT),),
        task_reference="Odyssey",
        activity_text="corregí el calendario",
        activity_target=TaskActivityTarget.TASK,
    )
    resolved = temporal(dated_source, "hoy", "EXACT_DATE", date="2026-10-05")
    assert compose_work_session_activity_date(dated, resolved) == "2026-10-05"


def test_work_session_activity_fails_closed_for_ungrounded_or_wrong_domain_fields() -> None:
    source = "Apunta en la work session de Odyssey que terminé los tests"
    with pytest.raises(TaskInterpretationError, match="activity span"):
        TaskInterpretation(
            source,
            TaskOperation.ADD_WORK_SESSION_ACTIVITY,
            task_reference="Odyssey",
            activity_text="texto inventado",
            activity_target=TaskActivityTarget.TASK,
        )
    with pytest.raises(TaskInterpretationError, match="session-selection time"):
        TaskInterpretation(
            source,
            TaskOperation.ADD_WORK_SESSION_ACTIVITY,
            (TaskTemporalMention("Odyssey", TaskTemporalRole.WORK_SESSION_START_AT),),
            task_reference="Odyssey",
            activity_text="terminé los tests",
            activity_target=TaskActivityTarget.TASK,
        )
    with pytest.raises(TaskInterpretationError, match="Only Work Session activity"):
        TaskInterpretation(source, TaskOperation.CREATE, activity_text="terminé los tests")


def test_task_interpreter_call_is_bounded_and_returns_only_domain_semantics() -> None:
    source = "Tengo que llamar al banco el viernes"

    class Responses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):  # type: ignore[no-untyped-def]
            self.kwargs = kwargs
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps(
                    {
                        "operation": "CREATE",
                        "temporal_mentions": [{"text": "el viernes", "role": "TARGET_DATE"}],
                        "relationship_mentions": [],
                        "clear_fields": [],
                        "query_scope": None,
                        "task_reference": "",
                        "activity_text": "",
                        "activity_target": "NONE",
                    }
                ),
                usage=None,
                id="task-test",
            )

    responses = Responses()
    interpreter = OpenAITaskInterpreter(SimpleNamespace(responses=responses))
    result = interpreter.interpret(source)
    assert result.operation is TaskOperation.CREATE
    assert result.task_reference is None
    task_reference_schema = responses.kwargs["text"]["format"]["schema"]["properties"][
        "task_reference"
    ]
    assert task_reference_schema["type"] == "string"
    assert "without deciding whether they resolve" in task_reference_schema["description"]
    assert responses.kwargs["model"] == "gpt-6-luna"
    assert responses.kwargs["reasoning"] == {"effort": "low"}
    assert responses.kwargs["store"] is False


def test_core_domain_validation_requires_exact_task_property_evidence() -> None:
    from odyssey_core.domain_interpretation import DomainInterpretation
    from odyssey_core.request_planning import (
        KnowledgeUnit,
        PropertyChange,
        RequestPlan,
        RequestPlanningError,
        SelectionCriteria,
        WriteAction,
        validate_plan_against_domain_interpretation,
    )

    source = "Marca llamar al banco como hecho"
    domain = compose_task_domain_interpretation(
        TaskInterpretation(source, TaskOperation.COMPLETE),
        None,
        now="2026-10-04T21:42:03+02:00",
    )
    target = SelectionCriteria("llamar al banco", "llamar al banco", "task", (), None)
    good = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        target,
                        "amend",
                        (
                            PropertyChange("status", "set", "completed"),
                            PropertyChange("completed_at", "set", "2026-10-04T21:42:03+02:00"),
                        ),
                        (),
                        (),
                        (),
                    ),
                )
            ),
        ),
        (),
    )
    validate_plan_against_domain_interpretation(good, domain)

    invented = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        target,
                        "amend",
                        (
                            PropertyChange("status", "set", "completed"),
                            PropertyChange("completed_at", "set", "2026-10-04T21:42:03+02:00"),
                            PropertyChange("deadline_at", "set", "2026-10-10"),
                        ),
                        (),
                        (),
                        (),
                    ),
                )
            ),
        ),
        (),
    )
    with pytest.raises(RequestPlanningError, match="exactly match"):
        validate_plan_against_domain_interpretation(invented, domain)

    missing = DomainInterpretation(
        "tasks",
        source,
        "COMPLETE",
        tuple(item for item in domain.evidence if item.kind != "property.completed_at"),
    )
    with pytest.raises(RequestPlanningError, match="exactly match"):
        validate_plan_against_domain_interpretation(good, missing)
