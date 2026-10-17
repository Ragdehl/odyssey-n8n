"""Global Work Session consistency belongs to the Tasks domain, not Router."""

import pytest

from odyssey_apps.tasks import (
    TaskBatchPreflightError,
    TaskInterpretation,
    TaskOperation,
    validate_task_batch_prewrite,
)


def _operation(action):
    if action in {TaskOperation.START_WORK_SESSION, TaskOperation.STOP_WORK_SESSION}:
        return TaskInterpretation(
            f"synthetic target {action.value}", action, task_reference="target"
        )
    return TaskInterpretation(f"synthetic {action.value}", action)


@pytest.mark.parametrize(
    "ops",
    [
        (TaskOperation.START_WORK_SESSION, TaskOperation.START_WORK_SESSION),
        (TaskOperation.START_WORK_SESSION, TaskOperation.STOP_WORK_SESSION),
        (
            TaskOperation.START_WORK_SESSION,
            TaskOperation.CREATE,
            TaskOperation.START_WORK_SESSION,
        ),
        (
            TaskOperation.START_WORK_SESSION,
            TaskOperation.COMPLETE,
            TaskOperation.START_WORK_SESSION,
        ),
    ],
)
def test_two_overlapping_new_sessions_are_rejected_before_earlier_writes(ops):
    with pytest.raises(TaskBatchPreflightError):
        validate_task_batch_prewrite(tuple(_operation(action) for action in ops))


@pytest.mark.parametrize(
    "ops",
    [
        (TaskOperation.START_WORK_SESSION,),
        (TaskOperation.STOP_WORK_SESSION, TaskOperation.START_WORK_SESSION),
        (TaskOperation.CREATE, TaskOperation.COMPLETE),
    ],
)
def test_batch_validator_does_not_invent_global_session_state(ops):
    validate_task_batch_prewrite(tuple(_operation(action) for action in ops))


def test_batch_validator_rejects_malformed_inputs():
    with pytest.raises(TaskBatchPreflightError):
        validate_task_batch_prewrite(("start",))


def test_prevalidated_session_dependency_allows_one_start_then_its_reviewed_stop():
    sequence = (
        _operation(TaskOperation.START_WORK_SESSION),
        _operation(TaskOperation.STOP_WORK_SESSION),
        _operation(TaskOperation.START_WORK_SESSION),
    )
    validate_task_batch_prewrite(sequence, session_linked_stops=frozenset({1}))
    with pytest.raises(TaskBatchPreflightError):
        validate_task_batch_prewrite(sequence)
    for link in (frozenset({0}), frozenset({2}), frozenset({3}), frozenset({True})):
        with pytest.raises(TaskBatchPreflightError):
            validate_task_batch_prewrite(sequence, session_linked_stops=link)
