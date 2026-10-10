"""Generic source/plan dependency proofs on REAL model outputs and mutations.

This intentionally does not grant write authority or bypass old coverage.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.candidate_dependency_attestation import (
    DependentFactAttestationError,
    attest_two_dependent_core_plans,
)
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_fact_candidate_dependent_actual_core_vertical import _plans


@pytest.mark.parametrize(
    "case_id,relation", [("F23", "shared_subject"), ("F26", "source_anaphora")]
)
def test_real_model_dependency_relations_are_source_proven_but_not_write_authorized(
    case_id, relation
):
    source, context, entries = _plans(case_id)
    proof = attest_two_dependent_core_plans(source, context, tuple(p for _request, p in entries))
    assert proof.candidate_ids == ("candidate-1", "candidate-2")
    assert proof.relation == relation
    assert not proof.may_write_notes
    assert not proof.canonical_reuse_verified
    assert proof.plan_digests[0] != proof.plan_digests[1]
    assert proof.source_antecedent.casefold() == proof.plan_referent.casefold()


def _mutate(unit_plan, *, fact=None, target=None, refs=None, helpers=None):
    action = unit_plan.actions[0]
    first, *rest = action.units
    modified = replace(
        first,
        facts=(fact,) if fact is not None else first.facts,
        target=target if target is not None else first.target,
        references=refs if refs is not None else first.references,
    )
    return RequestPlan((WriteAction((modified, *(rest if helpers is None else helpers))),), ())


@pytest.mark.parametrize(
    "mutation",
    [
        "different_project",
        "wrong_component",
        "swapped_component",
        "missing_noun",
        "new_subject",
        "unregistered_helper",
        "extra_fact",
    ],
)
def test_project_dependency_does_not_launder_wrong_target_or_content(mutation):
    source, context, entries = _plans("F23")
    a, b = (item[1] for item in entries)
    if mutation == "different_project":
        unit = b.actions[0].units[0]
        b = _mutate(b, target=replace(unit.target, query="el proyecto Atlas"))
    elif mutation == "wrong_component":
        b = _mutate(b, fact="Tiene otro fallo en Lisboa.")
    elif mutation == "swapped_component":
        b = _mutate(b, fact="Tiene otro fallo en Router.")
    elif mutation == "missing_noun":
        b = _mutate(b, fact="Tiene otro problema en Temporal.")
    elif mutation == "new_subject":
        b = _mutate(b, fact="El proyecto Atlas tiene otro fallo en Temporal.")
        # It contains both the correct location and noun, but inserts
        # a fabricated subject, which the attestation must reject.
    elif mutation == "unregistered_helper":
        a = _mutate(a, helpers=())
    else:
        unit = b.actions[0].units[0]
        b = _mutate(b, fact="Tiene otro fallo en Temporal.")
        broken = replace(b.actions[0].units[0], facts=(unit.facts[0], unit.facts[0]))
        b = RequestPlan((WriteAction((broken,)),), ())
    with pytest.raises(DependentFactAttestationError):
        attest_two_dependent_core_plans(source, context, (a, b))


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_document",
        "wrong_person",
        "wrong_document_type",
        "wrong_day",
        "no_reference",
        "extra_reference",
        "wrong_action_target",
    ],
)
def test_document_anaphora_rejects_mismatched_core_identity_or_date(mutation):
    source, context, entries = _plans("F26")
    a, b = (item[1] for item in entries)
    action = b.actions[0]
    main, doc_helper, person_helper = action.units
    if mutation == "wrong_document":
        doc_helper = replace(doc_helper, target=replace(doc_helper.target, query="el contrato"))
    elif mutation == "wrong_person":
        person_helper = replace(person_helper, target=replace(person_helper.target, query="Luis"))
    elif mutation == "wrong_document_type":
        doc_helper = replace(doc_helper, target=replace(doc_helper.target, type="project"))
    elif mutation == "wrong_day":
        earlier = a.actions[0].units[0]
        main = replace(main, fact_temporal_anchors=earlier.fact_temporal_anchors)
    elif mutation == "no_reference":
        main = replace(main, references=main.references[:1])
    elif mutation == "extra_reference":
        main = replace(main, references=(*main.references, main.references[0]))
    else:
        main = replace(main, target=replace(main.target, type="project"))
    b = RequestPlan((WriteAction((main, doc_helper, person_helper)),), ())
    with pytest.raises(DependentFactAttestationError):
        attest_two_dependent_core_plans(source, context, (a, b))


def test_reverse_source_order_fails_closed():
    source, context, entries = _plans("F26")
    plans = tuple(p for _, p in entries)
    with pytest.raises(DependentFactAttestationError):
        attest_two_dependent_core_plans(source, context, tuple(reversed(plans)))


def test_other_source_role_or_deleted_antecedent_cannot_reuse_prior_model_plans():
    source, context, entries = _plans("F26")
    plans = tuple(p for _, p in entries)
    with pytest.raises((DependentFactAttestationError, ValueError)):
        attest_two_dependent_core_plans(source.replace("El informe", "El contrato"), context, plans)


def test_shared_project_requires_exact_antecedent_not_just_a_common_word():
    source, context, entries = _plans("F23")
    a, b = (item[1] for item in entries)
    unit = b.actions[0].units[0]
    b = _mutate(b, target=replace(unit.target, query="el proyecto Odyssey y Atlántida"))
    with pytest.raises(DependentFactAttestationError):
        attest_two_dependent_core_plans(source, context, (a, b))


def test_new_entities_project_ellipsis_uses_same_source_plan_attestation():
    from tests.core.test_candidate_dependent_scope import _synthetic_role_source

    source = "El sistema Nébula presenta un problema en API y otro en interfaz."
    context = _synthetic_role_source(
        source,
        (
            ("subject", "El sistema Nébula"),
            ("predicate", "presenta"),
            ("object", "un problema"),
            ("location", "API"),
        ),
        (("object", "otro"), ("location", "interfaz")),
        inherit=("subject", "predicate"),
    )
    _old_source, _old_context, entries = _plans("F23")
    first, second = (plan for _r, plan in entries)
    first_unit, first_helper = first.actions[0].units
    second_unit = second.actions[0].units[0]
    new_subject = replace(first_unit.target, entity="Nébula", query="El sistema Nébula")
    first_unit = replace(
        first_unit,
        target=new_subject,
        facts=("Presenta un problema en {{ref:0}}.",),
        references=(replace(first_unit.references[0], mention="API"),),
    )
    first_helper = replace(
        first_helper, target=replace(first_helper.target, entity="API", query="API")
    )
    second_unit = replace(
        second_unit,
        target=new_subject,
        facts=("Presenta otro problema en interfaz.",),
    )
    first = RequestPlan((WriteAction((first_unit, first_helper)),), ())
    second = RequestPlan((WriteAction((second_unit,)),), ())
    proof = attest_two_dependent_core_plans(source, context, (first, second))
    assert proof.relation == "shared_subject"
    assert proof.source_antecedent == "El sistema Nébula"
    assert proof.plan_referent == "El sistema Nébula"
    assert not proof.may_write_notes


def test_new_document_and_person_anaphora_without_new_rules():
    from tests.core.test_candidate_dependent_scope import _synthetic_role_source

    source = "El contrato llegó ayer y hoy lo envié a Marta."
    context = _synthetic_role_source(
        source,
        (("subject", "El contrato"), ("predicate", "llegó"), ("date", "ayer")),
        (("date", "hoy"), ("reference", "lo"), ("predicate", "envié"), ("participants", "Marta")),
    )
    _old_source, _old_context, entries = _plans("F26")
    first, second = (plan for _r, plan in entries)
    first_unit = first.actions[0].units[0]
    first_unit = replace(first_unit, target=replace(first_unit.target, query="El contrato"))
    first = RequestPlan((WriteAction((first_unit,)),), ())
    second_unit, doc_helper, person_helper = second.actions[0].units
    second_unit = replace(
        second_unit,
        facts=("Envié {{ref:0}} a {{ref:1}}.",),
        references=(
            replace(second_unit.references[0], mention="el contrato"),
            replace(second_unit.references[1], mention="Marta"),
        ),
    )
    doc_helper = replace(doc_helper, target=replace(doc_helper.target, query="el contrato"))
    person_helper = replace(
        person_helper,
        target=replace(person_helper.target, entity="Marta", query="Marta"),
    )
    second = RequestPlan((WriteAction((second_unit, doc_helper, person_helper)),), ())
    proof = attest_two_dependent_core_plans(source, context, (first, second))
    assert proof.relation == "source_anaphora"
    assert proof.source_antecedent == "El contrato"
    assert proof.plan_referent == "el contrato"
    assert not proof.canonical_reuse_verified
