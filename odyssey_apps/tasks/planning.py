"""Tasks-owned validation around the shared Core semantic planner."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from odyssey_core.request_planning import (
    PlannerClarification,
    RequestPlan,
    RequestPlanningError,
    WriteAction,
)
from odyssey_core.write_plan_enrichment import (
    CoreLinkFactSpec,
    add_core_reference_facts,
    ensure_complete_core_reference_set,
    ensure_visible_core_action_fact,
)

from .interpretation import TaskInterpretation, TaskOperation, TaskRelationshipRole
from .schema import TASK_TYPE


class TaskCorePlanner:
    """Reuse the shared planner while narrowing execution to Tasks v0 lifecycle shapes."""

    # Core provides bounded, read-only exact Note-name hints before calling
    # this specialized decorator. No Task code scans the vault or selects IDs.
    wants_verified_source_names = True

    def __init__(
        self,
        planner: Any,
        interpretation: TaskInterpretation,
        *,
        verified_person_set: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._planner = planner
        if verified_person_set and (
            not 2 <= len(verified_person_set) <= 8
            or any(
                not isinstance(p, tuple)
                or len(p) != 2
                or any(not isinstance(v, str) or not v.strip() for v in p)
                for p in verified_person_set
            )
            or len({canonical for _, canonical in verified_person_set}) != len(verified_person_set)
            or len({mention for mention, _ in verified_person_set}) != 1
        ):
            raise RequestPlanningError("Unproven plural canonical Person set")
        self._verified_person_set = verified_person_set
        self._interpretation = interpretation
        self._verified_source_names: tuple[object, ...] = ()

    def bind_verified_source_note_names(self, names: Sequence[object]) -> None:
        from odyssey_core.canonical_source_context import CanonicalSourceNameHint

        if self._verified_source_names or any(
            not isinstance(hint, CanonicalSourceNameHint) for hint in names
        ):
            raise RequestPlanningError("Task canonical source hint binding is invalid")
        if len(names) > 16 or any(
            hint.mention.casefold() not in self._interpretation.source_text.casefold()
            for hint in names
        ):
            raise RequestPlanningError("Task canonical source hint not grounded in request")
        self._verified_source_names = tuple(names)
        binder = getattr(self._planner, "bind_verified_source_note_names", None)
        if callable(binder) and names:
            binder(names)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._planner, name)

    def plan(self, request: str, conversation_context=()):  # type: ignore[no-untyped-def]
        result = self._planner.plan(request, conversation_context)
        if isinstance(result, PlannerClarification):
            return result
        if not isinstance(result, RequestPlan):
            raise RequestPlanningError("Tasks shared planner returned unsupported result")
        self._validate(result)
        result = self._ensure_visible_action(result)
        result = self._ensure_relationship_facts(result)
        result = self._ensure_verified_person_set(result)
        self._require_source_identity_links(result)
        return result

    def _ensure_verified_person_set(self, plan: RequestPlan) -> RequestPlan:
        """Supply receipts to Core; never inspect Core units in Tasks."""
        if not self._verified_person_set:
            return plan
        if self._interpretation.operation is not TaskOperation.CREATE:
            raise RequestPlanningError("Plural person links require one Task CREATE")
        return ensure_complete_core_reference_set(
            plan,
            tuple(
                CoreLinkFactSpec(
                    "Persona relacionada",
                    mention,
                    "person",
                    "person",
                    canonical_target_name=name,
                )
                for mention, name in self._verified_person_set
            ),
            compatible_roles=("identity",),
        )

    def _require_source_identity_links(self, plan: RequestPlan) -> None:
        """Prevent a generic Task label from disguising a dropped known person.

        Source-name hints are read-only. Actual helper IDs are still selected
        independently by Core/Writer. An uncertain name interpretation
        must be revisited, not converted into a source-blind Task completion.
        """
        if self._interpretation.operation is not TaskOperation.CREATE:
            return
        people = [
            h for h in self._verified_source_names if getattr(h, "note_type", None) == "person"
        ]
        if not people:
            return
        action = plan.actions[0]
        assert isinstance(action, WriteAction)
        primary = next(unit for unit in action.units if not unit.reference_lookup_only)
        for person in people:
            if not any(
                reference.mention.casefold() == person.mention.casefold()
                and reference.role in {"person", "identity", "assignee"}
                and 0 <= reference.target_index < len(action.units)
                and action.units[reference.target_index].reference_lookup_only
                and action.units[reference.target_index].target.type == "person"
                for reference in primary.references
            ):
                raise RequestPlanningError(
                    "Task CREATE dropped a Core-verified named source person identity"
                )

    def _ensure_visible_action(self, plan: RequestPlan) -> RequestPlan:
        """Delegate shared plan mechanics to Core, preserve Tasks CREATE policy."""
        if self._interpretation.operation is not TaskOperation.CREATE:
            return plan
        return ensure_visible_core_action_fact(plan)

    def _ensure_relationship_facts(self, plan: RequestPlan) -> RequestPlan:
        """Tasks owns roles; Core owns references, helpers and fact construction."""
        specs = []
        for mention in self._interpretation.relationship_mentions:
            if mention.role is TaskRelationshipRole.ASSIGNEE:
                specs.append(CoreLinkFactSpec("Responsable", mention.text, "person", "assignee"))
            elif mention.role is TaskRelationshipRole.PARENT_TASK:
                specs.append(
                    CoreLinkFactSpec("Tarea superior", mention.text, TASK_TYPE, "parent_task")
                )
            else:
                raise RequestPlanningError("Unsupported Tasks relationship role")
        return add_core_reference_facts(plan, tuple(specs))

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
