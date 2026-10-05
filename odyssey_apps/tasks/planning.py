"""Tasks-owned validation around the shared Core semantic planner."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PlannerClarification,
    RequestPlan,
    RequestPlanningError,
    SelectionCriteria,
    WriteAction,
)

from .interpretation import TaskInterpretation, TaskOperation, TaskRelationshipRole
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
        result = self._ensure_visible_action(result)
        return self._ensure_relationship_facts(result)

    def _ensure_visible_action(self, plan: RequestPlan) -> RequestPlan:
        """Guarantee a newly created Task has exactly one human-readable Markdown checkbox."""
        if self._interpretation.operation is not TaskOperation.CREATE:
            return plan
        action = plan.actions[0]
        assert isinstance(action, WriteAction)
        units = list(action.units)
        primary_index = next(
            index for index, unit in enumerate(units) if not unit.reference_lookup_only
        )
        unit = replace(units[primary_index], force_create=True)
        label = (unit.target.entity or unit.target.query).strip()
        if not label:
            raise RequestPlanningError("Task create target has no visible action wording")
        if label[-1] not in ".!?":
            label += "."
        checkbox = f"[ ] {label}"
        facts = list(unit.facts)
        anchors = list(unit.fact_temporal_anchors)
        normalized_label = label.rstrip(".!?").strip().casefold()
        replaced = False
        for index, fact in enumerate(facts):
            if "{{ref:" in fact:
                continue
            normalized_fact = fact.strip().rstrip(".!?").strip().casefold()
            if normalized_fact == normalized_label:
                facts[index] = checkbox
                replaced = True
                break
        if not replaced:
            facts.insert(0, checkbox)
            anchors.insert(0, ())
        elif len(anchors) < len(facts):
            anchors = [*anchors, *(((),) * (len(facts) - len(anchors)))]
        units[primary_index] = replace(
            unit,
            facts=tuple(facts),
            fact_temporal_anchors=tuple(anchors),
        )
        return replace(plan, actions=(replace(action, units=tuple(units)),))

    def _ensure_relationship_facts(self, plan: RequestPlan) -> RequestPlan:
        """Lower Tasks role wording to ordinary Core-resolved canonical references."""
        if not self._interpretation.relationship_mentions:
            return plan
        action = plan.actions[0]
        assert isinstance(action, WriteAction)
        units = list(action.units)
        primary_index = next(
            index for index, unit in enumerate(units) if not unit.reference_lookup_only
        )
        unit = units[primary_index]
        facts = list(unit.facts)
        anchors = list(unit.fact_temporal_anchors)
        references = list(unit.references)
        synthetic: list[KnowledgeUnit] = []
        for mention in self._interpretation.relationship_mentions:
            if mention.role is TaskRelationshipRole.ASSIGNEE:
                label, target_type, role = "Responsable", "person", "assignee"
            else:
                label, target_type, role = "Tarea superior", TASK_TYPE, "parent_task"
            selection = SelectionCriteria(None, mention.text, target_type, (), None)
            target_index = len(units) + len(synthetic)
            synthetic.append(
                KnowledgeUnit(
                    target=selection,
                    intent="record",
                    properties=(),
                    tag_changes=(),
                    facts=(),
                    references=(),
                    cardinality="one",
                    destination_type=None,
                    reference_lookup_only=True,
                )
            )
            reference_index = len(references)
            references.append(KnowledgeReference(target_index, role, mention.text))
            facts.append(f"{label}: {{{{ref:{reference_index}}}}}.")
            anchors.append(())
        units[primary_index] = replace(
            unit,
            facts=tuple(facts),
            references=tuple(references),
            fact_temporal_anchors=tuple(anchors),
        )
        return replace(plan, actions=(replace(action, units=tuple((*units, *synthetic))),))

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
