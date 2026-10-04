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
)
from odyssey_core import create_entity
from odyssey_core.application import WritePreflightGuardError
from odyssey_core.reference_preflight import UnitTargetPreflight
from odyssey_core.request_planning import (
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
