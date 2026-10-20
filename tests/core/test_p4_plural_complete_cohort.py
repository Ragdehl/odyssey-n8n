"""A plural never authorizes GPT to choose two arbitrary people from three."""

from types import SimpleNamespace

import pytest

from odyssey_core.application import ActionStatus
from odyssey_core.dependent_group_evidence import (
    CanonicalGroupEdge,
    CanonicalGroupEvidenceError,
    _require_complete_person_cohort,
)


def _proof(name):
    return SimpleNamespace(
        note_type="person",
        stable_note_id="id-" + name,
        source_mention=name,
        canonical_name=name,
    )


def _receipts(*people):
    return {
        0: SimpleNamespace(
            action_results=(
                SimpleNamespace(
                    status=ActionStatus.COMPLETED,
                    canonical_reference_evidence=tuple(_proof(n) for n in people),
                    canonical_direct_target_evidence=(),
                ),
            )
        )
    }


def _edges(mention="los dos", people=("Ana", "Luis")):
    return tuple(CanonicalGroupEdge(0, 1, person, mention, _proof(person)) for person in people)


@pytest.mark.parametrize("reference", ["los dos", "a los dos", "ambos", "a ambos"])
def test_exact_two_people_entire_core_cohort_is_allowed(reference):
    assert _require_complete_person_cohort(_edges(reference), _receipts("Ana", "Luis")) is None


@pytest.mark.parametrize("reference", ["los dos", "a los dos", "ambos", "a ambos"])
def test_partial_selection_out_of_three_materialized_people_is_never_allowed(reference):
    with pytest.raises(CanonicalGroupEvidenceError, match="omits a physical"):
        _require_complete_person_cohort(_edges(reference), _receipts("Ana", "Luis", "Marta"))


def test_even_correct_number_cannot_include_unmaterialized_identity():
    with pytest.raises(CanonicalGroupEvidenceError, match="omits a physical"):
        _require_complete_person_cohort(
            _edges(people=("Ana", "Desconocida")),
            _receipts("Ana", "Luis"),
        )


def test_non_person_edges_are_not_burdened_by_person_cohort_logic():
    items = _edges()
    task_edges = tuple(
        CanonicalGroupEdge(
            x.predecessor_index,
            x.consumer_index,
            x.antecedent_mention,
            x.dependent_mention,
            SimpleNamespace(note_type="task", stable_note_id="task-" + str(i)),
        )
        for i, x in enumerate(items)
    )
    assert _require_complete_person_cohort(task_edges, {}) is None
