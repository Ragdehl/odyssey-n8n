"""Task CREATE uses existing Core plan enrichment for E2-proven plural references."""

from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import TaskCorePlanner, TaskInterpretation, TaskOperation
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    RequestPlanningError,
    SelectionCriteria,
    WriteAction,
)

PROOFS = (("ambos", "Ana Prototipo"), ("ambos", "Luis Prototipo"))


def original_plan(*, extra_name=None):
    references = ()
    helpers = ()
    if extra_name is not None:
        references = (KnowledgeReference(1, "person", "ambos"),)
        helpers = (
            KnowledgeUnit(
                SelectionCriteria(extra_name, extra_name, "person", (), None),
                "record",
                (),
                (),
                (),
                (),
                reference_lookup_only=True,
            ),
        )
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria("Llamar a ambos", "Llamar a ambos", "task", (), None),
                        "record",
                        (PropertyChange("status", "set", "pending"),),
                        (),
                        ("Llamar a ambos.",),
                        references,
                    ),
                    *helpers,
                )
            ),
        ),
        (),
    )


def plan(*, extra_name=None):
    fixed = original_plan(extra_name=extra_name)
    wrapper = TaskCorePlanner(
        SimpleNamespace(plan=lambda *_args: fixed),
        TaskInterpretation("Tengo que llamar a ambos", TaskOperation.CREATE),
        verified_person_set=PROOFS,
    )
    return wrapper.plan("Tengo que llamar a ambos")


def test_missing_two_links_are_added_by_generic_core_enrichment():
    result = plan()
    assert isinstance(result, RequestPlan)
    units = result.actions[0].units
    assert len(units) == 3
    assert [ref.mention for ref in units[0].references] == ["ambos", "ambos"]
    assert [ref.role for ref in units[0].references] == ["person", "person"]
    assert [units[ref.target_index].target.entity for ref in units[0].references] == [
        "Ana Prototipo",
        "Luis Prototipo",
    ]
    assert sum("{{ref:" in fact for fact in units[0].facts) == 2


def test_existing_proven_link_is_not_duplicated():
    result = plan(extra_name="Ana Prototipo")
    units = result.actions[0].units
    assert len(units) == 3
    assert len(units[0].references) == 2
    assert {units[ref.target_index].target.entity for ref in units[0].references} == {
        "Ana Prototipo",
        "Luis Prototipo",
    }


@pytest.mark.parametrize("name", ["Marta Prototipo", "ambos"])
def test_wrong_or_ambiguous_planner_link_is_never_masked(name):
    with pytest.raises(RequestPlanningError, match="not one proven identity"):
        plan(extra_name=name)


def test_single_target_task_uses_original_core_planner_unchanged():
    fixed = original_plan()
    wrapper = TaskCorePlanner(
        SimpleNamespace(plan=lambda *_args: fixed),
        TaskInterpretation("Tengo que llamar a alguien", TaskOperation.CREATE),
    )
    result = wrapper.plan("Tengo que llamar a alguien")
    assert not result.actions[0].units[0].references


@pytest.mark.parametrize("role", ["assignee", "parent_task"])
def test_core_cannot_invent_unrequested_task_relationship_during_plural_enrichment(role):
    existing = original_plan()
    primary = existing.actions[0].units[0]
    from dataclasses import replace

    person_name = "Ana Prototipo" if role == "assignee" else "Reunir documentos"
    helper_type = "person" if role == "assignee" else "task"
    forged = replace(
        existing,
        actions=(
            WriteAction(
                (
                    replace(primary, references=(KnowledgeReference(1, role, person_name),)),
                    KnowledgeUnit(
                        SelectionCriteria(person_name, person_name, helper_type, (), None),
                        "record",
                        (),
                        (),
                        (),
                        (),
                        reference_lookup_only=True,
                    ),
                )
            ),
        ),
    )
    wrapper = TaskCorePlanner(
        SimpleNamespace(plan=lambda *_args: forged),
        TaskInterpretation("Tengo que llamar a ambos", TaskOperation.CREATE),
        verified_person_set=PROOFS,
    )
    with pytest.raises(
        RequestPlanningError, match="unrequested Task relationship|unapproved member"
    ):
        wrapper.plan("Tengo que llamar a ambos")


def test_closed_verified_person_set_rejects_unapproved_foreign_mention():
    primary = original_plan().actions[0].units[0]
    from dataclasses import replace

    foreign = replace(
        primary,
        references=(KnowledgeReference(1, "person", "Marta"),),
    )
    helper = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "record",
        (),
        (),
        (),
        (),
        reference_lookup_only=True,
    )
    unsafe = RequestPlan((WriteAction((foreign, helper)),), ())
    wrapper = TaskCorePlanner(
        SimpleNamespace(plan=lambda *_: unsafe),
        TaskInterpretation("Tengo que llamar a ambos", TaskOperation.CREATE),
        verified_person_set=PROOFS,
    )
    with pytest.raises(RequestPlanningError, match="unapproved member"):
        wrapper.plan("Tengo que llamar a ambos")
