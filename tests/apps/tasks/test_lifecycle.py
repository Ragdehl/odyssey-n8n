"""Tasks shared-planner narrowing and post-resolution lifecycle guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskCorePlanner,
    TaskInterpretation,
    TaskLifecycleGuard,
    TaskOperation,
    TaskRelationshipMention,
    TaskRelationshipRole,
)
from odyssey_core import create_entity
from odyssey_core.application import WritePreflightGuardError
from odyssey_core.reference_preflight import UnitTargetPreflight
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    RequestPlanningError,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.storage import VaultRepository
from odyssey_core.write_target import WriteTargetOutcome

ROOT = Path(__file__).resolve().parents[3]


def schema():  # type: ignore[no-untyped-def]
    base = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    return compose_application_schema(base, (TASK_SCHEMA_EXTENSION,))


def plan(intent: str = "amend", *, cardinality: str = "one") -> RequestPlan:
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria("llamar al banco", "llamar al banco", "task", (), None),
                        intent,
                        (PropertyChange("status", "set", "completed"),),
                        (),
                        (),
                        (),
                        cardinality,
                    ),
                )
            ),
        ),
        (),
    )


class FixedPlanner:
    def __init__(self, value):  # type: ignore[no-untyped-def]
        self.value = value

    def plan(self, request, conversation_context=()):  # type: ignore[no-untyped-def]
        del request, conversation_context
        return self.value


def test_task_core_planner_accepts_only_one_task_lifecycle_write() -> None:
    wrapper = TaskCorePlanner(
        FixedPlanner(plan()),
        TaskInterpretation("Marca llamar al banco como hecho", TaskOperation.COMPLETE),
    )
    assert isinstance(wrapper.plan("x"), RequestPlan)

    bulk = TaskCorePlanner(
        FixedPlanner(plan(cardinality="all_matching")),
        TaskInterpretation("Marca llamar al banco como hecho", TaskOperation.COMPLETE),
    )
    with pytest.raises(RequestPlanningError, match="one task"):
        bulk.plan("x")

    wrong_intent = TaskCorePlanner(
        FixedPlanner(plan(intent="remove")),
        TaskInterpretation("Marca llamar al banco como hecho", TaskOperation.COMPLETE),
    )
    with pytest.raises(RequestPlanningError, match="lifecycle operation"):
        wrong_intent.plan("x")


def task_repo(tmp_path: Path, status: str):  # type: ignore[no-untyped-def]
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    current_schema = schema()
    create_entity(
        repository,
        current_schema,
        path="call-bank.md",
        entity_id="task-bank",
        metadata={"name": "Call the bank", "type": "task", "status": status},
        content="- Call the bank.\n",
        actor="fixture",
        now="2026-10-04T21:00:00+02:00",
    )
    return repository, current_schema


def preflight(outcome=WriteTargetOutcome.UPDATE):  # type: ignore[no-untyped-def]
    return (UnitTargetPreflight(0, outcome, "task-bank", "Call the bank", "call-bank.md"),)


def test_lifecycle_guard_accepts_and_rejects_current_state_without_mutating(tmp_path: Path) -> None:
    repository, current_schema = task_repo(tmp_path, "pending")
    complete = TaskLifecycleGuard(TaskOperation.COMPLETE)
    complete(plan().actions[0], preflight(), repository, current_schema)

    reopen = TaskLifecycleGuard(TaskOperation.REOPEN)
    with pytest.raises(WritePreflightGuardError, match="TASK_INVALID_TRANSITION"):
        reopen(plan().actions[0], preflight(), repository, current_schema)

    create = TaskLifecycleGuard(TaskOperation.CREATE)
    create(
        plan(intent="record").actions[0],
        preflight(WriteTargetOutcome.CREATE),
        repository,
        current_schema,
    )
    with pytest.raises(WritePreflightGuardError, match="TASK_ALREADY_EXISTS"):
        create(plan(intent="record").actions[0], preflight(), repository, current_schema)


@pytest.mark.parametrize(
    ("operation", "status", "allowed"),
    [
        (TaskOperation.START, "pending", True),
        (TaskOperation.START, "in_progress", False),
        (TaskOperation.COMPLETE, "pending", True),
        (TaskOperation.COMPLETE, "in_progress", True),
        (TaskOperation.COMPLETE, "completed", False),
        (TaskOperation.REOPEN, "completed", True),
        (TaskOperation.REOPEN, "pending", False),
        (TaskOperation.CANCEL, "pending", True),
        (TaskOperation.CANCEL, "in_progress", True),
        (TaskOperation.CANCEL, "completed", False),
        (TaskOperation.UPDATE, "pending", True),
        (TaskOperation.UPDATE, "in_progress", True),
        (TaskOperation.UPDATE, "completed", False),
    ],
)
def test_lifecycle_guard_transition_matrix(
    tmp_path: Path, operation: TaskOperation, status: str, allowed: bool
) -> None:
    repository, current_schema = task_repo(tmp_path, status)
    guard = TaskLifecycleGuard(operation)
    if allowed:
        guard(plan().actions[0], preflight(), repository, current_schema)
    else:
        with pytest.raises(WritePreflightGuardError, match="TASK_INVALID_TRANSITION"):
            guard(plan().actions[0], preflight(), repository, current_schema)


def test_task_create_adds_visible_action_when_shared_plan_is_property_only() -> None:
    create_plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria("Llamar al banco", "llamar al banco", "task", (), None),
                        "record",
                        (PropertyChange("status", "set", "pending"),),
                        (),
                        (),
                        (),
                        "one",
                    ),
                )
            ),
        ),
        (),
    )
    wrapper = TaskCorePlanner(
        FixedPlanner(create_plan),
        TaskInterpretation("Tengo que llamar al banco", TaskOperation.CREATE),
    )
    result = wrapper.plan("Tengo que llamar al banco")
    assert isinstance(result, RequestPlan)
    unit = result.actions[0].units[0]  # type: ignore[union-attr]
    assert unit.facts == ("[ ] Llamar al banco.",)
    assert unit.fact_temporal_anchors == ((),)


def test_task_core_planner_lowers_assignee_and_parent_to_core_references() -> None:
    create_plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(
                            "Reunir documentos", "reunir documentos", "task", (), None
                        ),
                        "record",
                        (PropertyChange("status", "set", "pending"),),
                        (),
                        ("Reunir documentos.",),
                        (),
                        "one",
                        fact_temporal_anchors=((),),
                    ),
                )
            ),
        ),
        (),
    )
    interpretation = TaskInterpretation(
        "Beatriz tiene que reunir documentos para preparar dossier",
        TaskOperation.CREATE,
        relationship_mentions=(
            TaskRelationshipMention("Beatriz", TaskRelationshipRole.ASSIGNEE),
            TaskRelationshipMention("preparar dossier", TaskRelationshipRole.PARENT_TASK),
        ),
    )
    result = TaskCorePlanner(FixedPlanner(create_plan), interpretation).plan("x")
    unit = result.actions[0].units[0]  # type: ignore[union-attr]
    assert unit.facts == (
        "[ ] Reunir documentos.",
        "Responsable: {{ref:0}}.",
        "Tarea superior: {{ref:1}}.",
    )
    assert [(ref.role, ref.mention, ref.target_index) for ref in unit.references] == [
        ("assignee", "Beatriz", 1),
        ("parent_task", "preparar dossier", 2),
    ]
    lookup_units = result.actions[0].units[1:]  # type: ignore[union-attr]
    assert [
        (item.target.query, item.target.type, item.reference_lookup_only) for item in lookup_units
    ] == [
        ("Beatriz", "person", True),
        ("preparar dossier", "task", True),
    ]


def test_parent_task_guard_rejects_cycle_from_current_canonical_graph(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    current_schema = schema()
    create_entity(
        repository,
        current_schema,
        path="a.md",
        entity_id="task-a",
        metadata={"name": "A", "type": "task", "status": "pending"},
        content="- A.\n",
        actor="fixture",
        now="2026-10-05T07:00:00+02:00",
    )
    create_entity(
        repository,
        current_schema,
        path="b.md",
        entity_id="task-b",
        metadata={"name": "B", "type": "task", "status": "pending"},
        content="- B.\n- Tarea superior: [[a|A]].\n",
        actor="fixture",
        now="2026-10-05T07:00:00+02:00",
    )
    action = WriteAction(
        (
            KnowledgeUnit(
                SelectionCriteria("A", "A", "task", (), None),
                "amend",
                (),
                (),
                ("Tarea superior: {{ref:0}}.",),
                (KnowledgeReference(1, "parent_task", "B"),),
                fact_temporal_anchors=((),),
            ),
            KnowledgeUnit(
                SelectionCriteria("B", "B", "task", (), None),
                "record",
                (),
                (),
                (),
                (),
                reference_lookup_only=True,
            ),
        )
    )
    preflight = (
        UnitTargetPreflight(0, WriteTargetOutcome.UPDATE, stable_id="task-a"),
        UnitTargetPreflight(1, WriteTargetOutcome.UPDATE, stable_id="task-b", reference_only=True),
    )
    with pytest.raises(WritePreflightGuardError, match="TASK_PARENT_CYCLE"):
        TaskLifecycleGuard(TaskOperation.UPDATE)(action, preflight, repository, current_schema)
