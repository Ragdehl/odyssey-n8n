"""Tasks-owned prewrite compatibility check for multiple domain operations.

Checks deterministic impossibilities in a pending ordered request. It is NOT
an alternative to the time-of-use WorkSessionService state/CAS checks.
"""

from __future__ import annotations

from collections.abc import Sequence

from .interpretation import TaskInterpretation, TaskOperation


class TaskBatchPreflightError(ValueError):
    """This sequence violates a Tasks-owned lifecycle invariant."""


def validate_task_batch_prewrite(operations: Sequence[TaskInterpretation]) -> None:
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
    new_session_active = False
    for operation in operations:
        if operation.operation is TaskOperation.START_WORK_SESSION:
            if new_session_active:
                raise TaskBatchPreflightError(
                    "Two starts conflict with the one-active-session invariant"
                )
            new_session_active = True
        elif operation.operation is TaskOperation.STOP_WORK_SESSION:
            if new_session_active:
                # This STOP depends on the new session created by an earlier
                # operation in this delivery. The current DAG only carries
                # Core->Task Note links, not an E2/E3 session-instance proof.
                # Never pretend an active-session lookup is a proven edge.
                raise TaskBatchPreflightError(
                    "Stop after same-message start requires a typed session dependency"
                )
            new_session_active = False
