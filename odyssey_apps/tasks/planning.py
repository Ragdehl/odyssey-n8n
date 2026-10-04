"""Tasks-owned validation around the shared Core semantic planner."""

from __future__ import annotations

from typing import Any

from odyssey_core.request_planning import (
    PlannerClarification,
    RequestPlan,
    RequestPlanningError,
    WriteAction,
)

from .interpretation import TaskInterpretation, TaskOperation
from .schema import TASK_TYPE


class TaskCorePlanner:
    """Reuse the shared planner while narrowing execution to Tasks v0 lifecycle shapes."""

    def __init__(self, planner: Any, interpretation: TaskInterpretation) -> None:
        self._planner = planner
        self._interpretation = interpretation

    def __getattr__(self, name: str) -> Any:
        return getattr(self._planner, name)

    def plan(self, request: str, conversation_context=()):  # type: ignore[no-untyped-def]
        result = self._planner.plan(request, conversation_context)
        if isinstance(result, PlannerClarification):
            return result
        if not isinstance(result, RequestPlan):
            raise RequestPlanningError("Tasks shared planner returned unsupported result")
        self._validate(result)
        return result

    def _validate(self, plan: RequestPlan) -> None:
        if self._interpretation.operation is TaskOperation.QUERY:
            raise RequestPlanningError("Task queries do not use Core mutation planning")
        if len(plan.actions) != 1 or not isinstance(plan.actions[0], WriteAction):
            raise RequestPlanningError("Tasks v0 requires exactly one write action")
        action = plan.actions[0]
        primary = [unit for unit in action.units if not unit.reference_lookup_only]
        if len(primary) != 1:
            raise RequestPlanningError("Tasks v0 requires exactly one primary task target")
        unit = primary[0]
        if unit.target.type != TASK_TYPE or unit.cardinality != "one":
            raise RequestPlanningError("Tasks v0 target must be one task")
        if unit.destination_type is not None:
            raise RequestPlanningError("Tasks v0 cannot reclassify task notes")
        expected_intents = {
            TaskOperation.CREATE: {"record"},
            TaskOperation.START: {"amend"},
            TaskOperation.COMPLETE: {"amend"},
            TaskOperation.REOPEN: {"amend"},
            TaskOperation.CANCEL: {"amend"},
            TaskOperation.UPDATE: {"amend", "remove"},
        }
        allowed = expected_intents.get(self._interpretation.operation)
        if allowed is None or unit.intent not in allowed:
            raise RequestPlanningError(
                "Tasks v0 Core write intent does not match lifecycle operation"
            )
