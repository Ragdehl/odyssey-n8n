"""Tasks-owned validation around the shared Core semantic planner."""

from __future__ import annotations

from collections.abc import Sequence
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

    # Core provides bounded, read-only exact Note-name hints before calling
    # this specialized decorator. No Task code scans the vault or selects IDs.
    wants_verified_source_names = True

    def __init__(self, planner: Any, interpretation: TaskInterpretation) -> None:
        self._planner = planner
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
        self._require_source_identity_links(result)
        return result

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
        """Guarantee a newly created Task has one human-readable action fact in its body."""
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
        facts = list(unit.facts)
        anchors = list(unit.fact_temporal_anchors)
        if not anchors and facts:
            anchors = [() for _ in facts]
        elif len(anchors) != len(facts):
            raise RequestPlanningError("Task facts and temporal anchors are misaligned")
        normalized_label = label.rstrip(".!?").strip().casefold()

        # A linked fact is already visible after Core substitutes its
        # canonical helpers. Do not add a competing plain-text duplicate.
        def visible_source_fact(fact: str) -> str:
            rendered = fact
            for index, reference in enumerate(unit.references):
                rendered = rendered.replace(f"{{{{ref:{index}}}}}", reference.mention)
            return rendered.strip().rstrip(".!?").strip().casefold()

        has_visible_action = any(visible_source_fact(fact) == normalized_label for fact in facts)
        if not has_visible_action:
            facts.insert(0, label)
            anchors.insert(0, ())
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
