"""R0 structural regression: only Core planning has a bounded 16-link budget.

An externally provided verified Person set is test data, NOT a model attestation.
The old finite-source grammar and exact Core/E3 guards are independently tested.
"""

from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import TaskCorePlanner, TaskInterpretation, TaskOperation
from odyssey_apps.tasks.dependent_target import TaskDependentTargetError, TaskPersonReferenceSet
from odyssey_core.request_planning import RequestPlanningError
from odyssey_core.source_bound_dependency import SourceBoundDependency
from tests.apps.tasks.test_verified_plural_person_planning import original_plan


@pytest.mark.parametrize("count", [2, 5, 8, 9, 12, 16])
@pytest.mark.parametrize("reverse", [False, True])
def test_core_plan_structurally_carries_all_already_verified_references(count, reverse):
    names = tuple(f"Entidad{i:02d}" for i in range(count))
    if reverse:
        names = tuple(reversed(names))
    # The authoritative source proof is supplied by the real E2 Core handoff,
    # NOT created or inferred by the TaskCorePlanner decorator.
    wrapper = TaskCorePlanner(
        SimpleNamespace(plan=lambda *_: original_plan()),
        TaskInterpretation("Tengo que revisar el conjunto", TaskOperation.CREATE),
        verified_person_set=tuple(("grupo", name) for name in names),
    )
    plan = wrapper.plan("Tengo que revisar el conjunto")
    action = plan.actions[0]
    assert len(action.units) == count + 1
    refs = action.units[0].references
    assert len(refs) == count
    assert [action.units[ref.target_index].target.entity for ref in refs] == list(names)
    assert all(f"{{{{ref:{i}}}}}" in action.units[0].facts[i + 1] for i in range(count))


def test_core_plan_refuses_over_budget_and_duplicate_canonical_targets():
    for names in (
        tuple(f"Entidad{i:02d}" for i in range(17)),
        ("Entidad00", "Entidad00"),
    ):
        with pytest.raises(RequestPlanningError):
            TaskCorePlanner(
                SimpleNamespace(plan=lambda *_: original_plan()),
                TaskInterpretation("Tengo que revisar el conjunto", TaskOperation.CREATE),
                verified_person_set=tuple(("grupo", name) for name in names),
            )


def test_bigger_unattested_set_is_not_accepted_as_task_membership_proof():
    """Core plan structure is NOT a bypass for Task semantic/source authority."""
    dependencies = tuple(
        SourceBoundDependency(
            "He conocido a varias personas.",
            " Tengo que escribirles.",
            "los ocho",
            SimpleNamespace(stable_note_id=f"id{i}", note_type="person"),
        )
        for i in range(9)
    )
    with pytest.raises(TaskDependentTargetError, match="complete proof"):
        TaskPersonReferenceSet(dependencies, "actor")
