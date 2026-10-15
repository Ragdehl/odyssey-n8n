"""Preserve a verified natural daypart through ordinary Core Writer plans."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.execution_context import ContextContractError, ExecutionContext, QualitativeTime
from odyssey_core.qualitative_fact_preservation import preserve_qualitative_day_facts
from odyssey_core.request_planning import RequestPlan, WriteAction
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
    with pytest.raises(ContextContractError, match="no unique fact owner"):
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
    # Two conflicting dates for the same quoted original phrase are not proof.
    second = DomainEvidence("temporal_reference", PHRASE, "2026-10-06")
    domain = context().domains[0]
    two_dates = replace(context(), domains=(replace(domain, evidence=(*domain.evidence, second)),))
    with pytest.raises(ContextContractError, match="one matching exact"):
        preserve_qualitative_day_facts(plan(), context=two_dates)


def test_no_writes_never_fabricates_a_fact():
    empty = RequestPlan((), ())
    assert preserve_qualitative_day_facts(empty, context=context()) is empty


MULTI_SOURCE = (
    "Mañana por la tarde hablaré con Bea. Pasado mañana por la noche revisaré el Proyecto Atlas."
)
MULTI_PHRASES = (
    ("Mañana por la tarde", "por la tarde", "2026-10-05"),
    ("Pasado mañana por la noche", "por la noche", "2026-10-06"),
)


def multiple_context():
    return ExecutionContext(
        "multiple-dayparts",
        MULTI_SOURCE,
        "2026-10-04T10:00:00+02:00",
        "Europe/Paris",
        domains=(
            DomainInterpretation(
                "temporal",
                MULTI_SOURCE,
                "TEMPORAL_RESOLUTION",
                tuple(
                    DomainEvidence("temporal_reference", text, day)
                    for text, _, day in MULTI_PHRASES
                ),
            ),
        ),
        qualitative_times=tuple(
            QualitativeTime(text, day, qualifier, "Europe/Paris")
            for text, qualifier, day in MULTI_PHRASES
        ),
    )


def multiple_plan(*, second_day="2026-10-06", second_text="Revisaré {{ref:0}}."):
    first = _linked_day_plan("2026-10-05", "Hablaré con {{ref:0}}.", "Bea", "2026-10-05")
    second = _linked_day_plan(second_day, second_text, "Proyecto Atlas", second_day)
    return RequestPlan((first.actions[0], second.actions[0]), ())


def test_two_distinct_dates_preserve_both_qualifiers_in_the_correct_day_facts():
    original = multiple_plan()
    modified = preserve_qualitative_day_facts(original, context=multiple_context())
    assert modified.actions[0].units[0].facts == ("Hablaré con {{ref:0}} (por la tarde).",)
    assert modified.actions[1].units[0].facts == ("Revisaré {{ref:0}} (por la noche).",)
    for i in (0, 1):
        assert original.actions[i].units[0].references == modified.actions[i].units[0].references
        assert original.actions[i].units[0].target == modified.actions[i].units[0].target
        assert original.actions[i].units[1] is modified.actions[i].units[1]
    assert preserve_qualitative_day_facts(modified, context=multiple_context()) is modified


def test_one_existing_daypart_is_not_repeated_and_other_is_preserved():
    original = multiple_plan(second_text="Revisaré {{ref:0}} por la noche.")
    modified = preserve_qualitative_day_facts(original, context=multiple_context())
    assert modified.actions[1] is original.actions[1]
    assert modified.actions[0].units[0].facts == ("Hablaré con {{ref:0}} (por la tarde).",)
    assert modified.actions[1].units[0].facts[0].count("por la noche") == 1


def test_multi_day_missing_one_owner_fails_without_changing_original_plan():
    original = multiple_plan(second_day="2026-10-07")
    before = original.actions[0].units[0].facts
    with pytest.raises(ContextContractError, match="no unique fact owner"):
        preserve_qualitative_day_facts(original, context=multiple_context())
    assert original.actions[0].units[0].facts == before


def test_same_day_two_qualifiers_are_not_guessed_into_two_facts():
    source = "Hoy por la tarde llamé a Bea y hoy por la noche vi a Marta."
    phrases = (("Hoy por la tarde", "por la tarde"), ("hoy por la noche", "por la noche"))
    ctx = ExecutionContext(
        "same-day-twice",
        source,
        "2026-10-04T10:00:00+02:00",
        "Europe/Paris",
        domains=(
            DomainInterpretation(
                "temporal",
                source,
                "TEMPORAL_RESOLUTION",
                tuple(
                    DomainEvidence("temporal_reference", text, "2026-10-04") for text, _ in phrases
                ),
            ),
        ),
        qualitative_times=tuple(
            QualitativeTime(text, "2026-10-04", qual, "Europe/Paris") for text, qual in phrases
        ),
    )
    a = _linked_day_plan("2026-10-04", "Llamé a {{ref:0}}.", "Bea", "2026-10-04")
    b = _linked_day_plan("2026-10-04", "Vi a {{ref:0}}.", "Marta", "2026-10-04")
    original = RequestPlan((WriteAction(a.actions[0].units), WriteAction(b.actions[0].units)), ())
    with pytest.raises(ContextContractError, match="Multiple qualitative dates"):
        preserve_qualitative_day_facts(original, context=ctx)


def test_multiple_different_dates_cannot_silently_duplicate_one_temporal_quote():
    context_base = multiple_context()
    domain = context_base.domains[0]
    bad = replace(
        context_base,
        domains=(
            replace(
                domain,
                evidence=(
                    *domain.evidence,
                    DomainEvidence("temporal_reference", "Mañana por la tarde", "2026-10-07"),
                ),
            ),
        ),
    )
    with pytest.raises(ContextContractError, match="matching exact"):
        preserve_qualitative_day_facts(multiple_plan(), context=bad)


def test_two_qualified_day_facts_reach_existing_core_writer_and_real_markdown(tmp_path):
    from odyssey_core.application import ApplicationStatus
    from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
    from tests.runtime.test_temporal_user_path_e2e import _core_with_plan

    repo, *_ = fresh_corpus_vault(tmp_path)
    source = "Mañana por la tarde hablaré con Bea. Pasado mañana por la noche veré a Marta."
    base = multiple_context()
    scoped = replace(base, source=source, domains=(replace(base.domains[0], source_text=source),))
    first = _linked_day_plan("2026-10-05", "Hablaré con {{ref:0}}.", "Bea", "2026-10-05")
    second = _linked_day_plan("2026-10-06", "Veré a {{ref:0}}.", "Marta", "2026-10-06")
    original = RequestPlan((first.actions[0], second.actions[0]), ())
    before_bea = repo.read_text("Bea.md")
    before_marta = repo.read_text("Marta.md")
    enriched = preserve_qualitative_day_facts(original, context=scoped)
    result = _core_with_plan(repo, source, "e2-multi-qualifier", enriched)
    assert result.status is ApplicationStatus.COMPLETED, result.planning_error
    assert "Hablaré con [[Bea|Bea]] (por la tarde)." in repo.read_text(
        "calendar/days/2026-10-05.md"
    )
    assert "Veré a [[Marta|Marta]] (por la noche)." in repo.read_text("calendar/days/2026-10-06.md")
    assert repo.read_text("Bea.md") == before_bea
    assert repo.read_text("Marta.md") == before_marta


def test_prewrite_daypart_does_not_seize_a_core_chosen_person_target():
    """A real GPT-5.6 Luna result can directly own a Person fact rather than a Day."""
    from odyssey_core.request_planning import SelectionCriteria

    original = plan()
    day_unit = original.actions[0].units[0]
    person_unit = replace(
        day_unit,
        target=SelectionCriteria(None, "Bea", "person", (), None),
        facts=("2026-10-05 por la tarde hablará con {{ref:0}}.",),
    )
    person_plan = RequestPlan((WriteAction((person_unit,)),), ())
    assert preserve_qualitative_day_facts(person_plan, context=context()) is person_plan
    omitted = RequestPlan(
        (WriteAction((replace(person_unit, facts=("Hablará con {{ref:0}}.",)),)),), ()
    )
    with pytest.raises(ContextContractError, match="missing from non-Day fact"):
        preserve_qualitative_day_facts(omitted, context=context())
