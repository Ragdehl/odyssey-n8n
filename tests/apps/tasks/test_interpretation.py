"""Provider-free Tasks lifecycle and Temporal composition tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import (
    OpenAITaskInterpreter,
    TaskInterpretation,
    TaskInterpretationError,
    TaskOperation,
    TaskQueryScope,
    TaskTemporalMention,
    TaskTemporalRole,
    compose_task_domain_interpretation,
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
                        "clear_fields": [],
                        "query_scope": None,
                    }
                ),
                usage=None,
                id="task-test",
            )

    responses = Responses()
    interpreter = OpenAITaskInterpreter(SimpleNamespace(responses=responses))
    result = interpreter.interpret(source)
    assert result.operation is TaskOperation.CREATE
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
