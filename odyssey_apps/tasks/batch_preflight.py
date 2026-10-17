"""Tasks-owned prewrite compatibility check for multiple domain operations.

Checks deterministic impossibilities in a pending ordered request. It is NOT
an alternative to the time-of-use WorkSessionService state/CAS checks.
"""

from __future__ import annotations

from collections.abc import Sequence

from .interpretation import TaskInterpretation, TaskOperation


class TaskBatchPreflightError(ValueError):
    """This sequence violates a Tasks-owned lifecycle invariant."""


def validate_task_batch_prewrite(
    operations: Sequence[TaskInterpretation],
    *,
    session_linked_stops: frozenset[int] = frozenset(),
) -> None:
    """At most one globally active new session until an intervening STOP.

    The domain allows only one active Work Session globally. Starting two
    sessions is impossible. A STOP after an in-message START requires a
    separate typed session-instance handoff, not just the earlier Task link,
    so it remains blocked until that carrier exists. A STOP may refer to an
    already active session, so the first STOP is not rejected here.
    """
    if not isinstance(operations, (tuple, list)) or any(
        not isinstance(item, TaskInterpretation) for item in operations
    ):
        raise TaskBatchPreflightError("Task batch interpretation is malformed")
    if not isinstance(session_linked_stops, frozenset) or any(
        not isinstance(index, int)
        or isinstance(index, bool)
        or index < 0
        or index >= len(operations)
        for index in session_linked_stops
    ):
        raise TaskBatchPreflightError("Session dependency indices malformed")
    new_session_active = False
    for ordinal, operation in enumerate(operations):
        if ordinal in session_linked_stops and (
            operation.operation is not TaskOperation.STOP_WORK_SESSION or not new_session_active
        ):
            raise TaskBatchPreflightError("Claimed session link does not consume new START")
        if operation.operation is TaskOperation.START_WORK_SESSION:
            if new_session_active:
                raise TaskBatchPreflightError(
                    "Two starts conflict with the one-active-session invariant"
                )
            new_session_active = True
        elif operation.operation is TaskOperation.STOP_WORK_SESSION:
            if new_session_active and ordinal not in session_linked_stops:
                raise TaskBatchPreflightError(
                    "Stop after same-message start requires a typed session dependency"
                )
            new_session_active = False
