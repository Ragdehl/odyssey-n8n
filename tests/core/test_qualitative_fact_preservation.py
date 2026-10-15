"""Preserve a verified natural daypart through ordinary Core Writer plans."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.execution_context import ContextContractError, ExecutionContext, QualitativeTime
from odyssey_core.qualitative_fact_preservation import preserve_qualitative_day_facts
from odyssey_core.request_planning import RequestPlan
from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan

SRC = "Mañana por la tarde hablaré con Bea."
PHRASE = "Mañana por la tarde"
DAY = "2026-10-05"


def context(qualifier="por la tarde", date=DAY):
    return ExecutionContext(
        "req-daypart",
        SRC,
        "2026-10-04T10:00:00+02:00",
        "Europe/Paris",
        domains=(
            DomainInterpretation(
                "temporal",
                SRC,
                "TEMPORAL_RESOLUTION",
                (DomainEvidence("temporal_reference", PHRASE, DAY),),
            ),
        ),
        qualitative_times=(QualitativeTime(PHRASE, date, qualifier, "Europe/Paris"),),
    )


def plan(text="Hablaré con {{ref:0}}."):
    return _linked_day_plan(DAY, text, "Bea", DAY)


def test_daypart_is_preserved_once_without_changing_owner_references_or_date():
    original = plan()
    modified = preserve_qualitative_day_facts(original, context=context())
    assert modified is not original
    before = original.actions[0].units[0]
    after = modified.actions[0].units[0]
    assert before.facts == ("Hablaré con {{ref:0}}.",)
    assert after.facts == ("Hablaré con {{ref:0}} (por la tarde).",)
    assert after.target == before.target
    assert after.references == before.references
    assert after.fact_temporal_anchors == before.fact_temporal_anchors
    assert modified.actions[0].units[1] is original.actions[0].units[1]
    assert preserve_qualitative_day_facts(modified, context=context()) == modified


def test_daypart_already_present_is_not_duplicated():
    existing = plan("Hablaré con {{ref:0}} por la tarde.")
    assert preserve_qualitative_day_facts(existing, context=context()) is existing


def test_day_only_context_keeps_existing_plan():
    base = replace(context(), qualitative_times=())
    original = plan()
    assert preserve_qualitative_day_facts(original, context=base) is original


def test_bad_date_or_target_or_complex_plan_never_gets_guess():
    original = plan()
    with pytest.raises(ContextContractError, match="verified temporal date anchor"):
        preserve_qualitative_day_facts(original, context=context(date="2026-10-06"))
    other_day = replace(
        original.actions[0].units[0],
        target=replace(original.actions[0].units[0].target, query="2026-10-06"),
    )
    wrong_plan = replace(
        original,
        actions=(replace(original.actions[0], units=(other_day, original.actions[0].units[1])),),
    )
    with pytest.raises(ContextContractError, match="cannot be safely attached"):
        preserve_qualitative_day_facts(wrong_plan, context=context())
    multiple_facts = replace(original.actions[0].units[0], facts=("Fui al parque.", "Vi a Bea."))
    complex_plan = replace(
        original,
        actions=(
            replace(original.actions[0], units=(multiple_facts, original.actions[0].units[1])),
        ),
    )
    with pytest.raises(ContextContractError, match="cannot be safely attached"):
        preserve_qualitative_day_facts(complex_plan, context=context())


def test_two_dayparts_and_two_date_anchors_fail_closed():
    two_times = replace(context(), qualitative_times=context().qualitative_times * 2)
    with pytest.raises(ContextContractError, match="Multiple qualitative"):
        preserve_qualitative_day_facts(plan(), context=two_times)
    second = DomainEvidence("temporal_reference", "hablaré", "2026-10-06")
    domain = context().domains[0]
    two_dates = replace(context(), domains=(replace(domain, evidence=(*domain.evidence, second)),))
    with pytest.raises(ContextContractError, match="one matching exact"):
        preserve_qualitative_day_facts(plan(), context=two_dates)


def test_no_writes_never_fabricates_a_fact():
    empty = RequestPlan((), ())
    assert preserve_qualitative_day_facts(empty, context=context()) is empty
