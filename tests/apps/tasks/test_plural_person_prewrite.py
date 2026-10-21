"""A plural Person-linked Task must be independently reviewed before Core writes."""

from copy import deepcopy

import pytest

from odyssey_apps.tasks.dependent_target import (
    TaskDependentTargetError,
    verify_plural_person_task_semantics,
)
from odyssey_apps.tasks.interpretation import TaskInterpretation, TaskOperation

BEFORE = "Hoy he conocido a Ana y a Luis."
AFTER = " Mañana debo llamar a los dos."
MENTIONS = ("Ana", "Luis")
REVIEW = {
    "full_source_quote": BEFORE + AFTER,
    "antecedent_quote": BEFORE,
    "dependent_quote": AFTER,
    "dependent_mention": "los dos",
    "antecedent_mentions": ["Ana", "Luis"],
    "all_referents": True,
    "single_personal_task": True,
    "operation_supported": True,
}


def verify(review_a=None, review_b=None, *, names=MENTIONS):
    return verify_plural_person_task_semantics(
        full_source=BEFORE + AFTER,
        antecedent_source=BEFORE,
        dependent_source=AFTER,
        dependent_mention="los dos",
        antecedent_mentions=names,
        interpretation=TaskInterpretation(AFTER.strip(), TaskOperation.CREATE),
        reviews=(
            deepcopy(REVIEW) if review_a is None else review_a,
            deepcopy(REVIEW) if review_b is None else review_b,
        ),
    )


def test_two_independent_complete_plural_reviews_are_required():
    assert verify() is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("all_referents", False),
        ("single_personal_task", False),
        ("operation_supported", False),
        ("antecedent_mentions", ["Ana"]),
        ("antecedent_mentions", ["Ana", "Marta"]),
        ("dependent_mention", "ella"),
        ("dependent_quote", " Mueve una tarea."),
        ("full_source_quote", "texto recortado"),
    ],
)
def test_semantic_model_review_cannot_drop_person_or_rewrite_source(field, value):
    altered = deepcopy(REVIEW)
    altered[field] = value
    with pytest.raises(TaskDependentTargetError):
        verify(review_b=altered)


@pytest.mark.parametrize("names", [(), ("Ana",), ("Ana", "Ana"), ("Ana", "Marta"), ("Luis", "Ana")])
def test_unbacked_or_reordered_referent_set_cannot_be_approved(names):
    with pytest.raises(TaskDependentTargetError):
        verify(names=names)


@pytest.mark.parametrize("ambiguous", ["ellos", "Ana y Luis", "esas personas"])
def test_unbounded_plural_wording_cannot_claim_finite_semantic_proof(ambiguous):
    dependent = f" Mañana debo llamar a {ambiguous}."
    review = {
        **REVIEW,
        "full_source_quote": BEFORE + dependent,
        "dependent_quote": dependent,
        "dependent_mention": ambiguous,
    }
    with pytest.raises(TaskDependentTargetError, match="not uniquely grounded"):
        verify_plural_person_task_semantics(
            full_source=BEFORE + dependent,
            antecedent_source=BEFORE,
            dependent_source=dependent,
            dependent_mention=ambiguous,
            antecedent_mentions=MENTIONS,
            interpretation=TaskInterpretation(dependent.strip(), TaskOperation.CREATE),
            reviews=(deepcopy(review), deepcopy(review)),
        )


def test_plural_carrier_requires_exact_finite_cardinal_even_if_targets_are_distinct():
    from types import SimpleNamespace

    from odyssey_apps.tasks.dependent_target import TaskPersonReferenceSet
    from odyssey_core.source_bound_dependency import SourceBoundDependency

    def dependencies(mention):
        return tuple(
            SourceBoundDependency(
                BEFORE,
                AFTER,
                mention,
                SimpleNamespace(stable_note_id=name, note_type="person"),
            )
            for name in MENTIONS
        )

    assert len(TaskPersonReferenceSet(dependencies("los dos"), "actor").dependencies) == 2
    for mention in ("ellos", "Ana y Luis", "esas personas"):
        with pytest.raises(TaskDependentTargetError, match="complete proof"):
            TaskPersonReferenceSet(dependencies(mention), "actor")
