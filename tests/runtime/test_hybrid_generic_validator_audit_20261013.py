"""Protect generic source ownership against arbitrary 2-name/3-unit templates."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import TaskCorePlanner, TaskInterpretation, TaskOperation
from odyssey_core.candidate_context import (
    CoreCandidate,
    CoreCandidateContext,
    CoreCandidateRole,
    CoreSourceSpan,
)
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.canonical_source_context import CanonicalSourceNameHint
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    RequestPlanningError,
    SelectionCriteria,
    WriteAction,
)


def _many_people(count: int, *, wrong_name: bool = False):
    names = ("Ada", "Bea", "Cora", "Dora", "Ella", "Fran", "Gina", "Hugo", "Iris")[:count]
    source = "Met " + ", ".join(names[:-1]) + " and " + names[-1] + "."

    def span(text):
        return CoreSourceSpan(text, source.index(text), source.index(text) + len(text))

    candidate = CoreCandidate(
        "candidate-1",
        "occurrence",
        "candidate",
        (span("Met"),),
        (
            CoreCandidateRole("predicate", span("Met")),
            *(CoreCandidateRole("participants", span(person)) for person in names),
        ),
        (),
    )
    context = CoreCandidateContext(
        source, (candidate,), scoped_route_source=True, hybrid_interpretation_mode=True
    )
    ref_tokens = ", ".join(f"{{{{ref:{i}}}}}" for i in range(count))
    content = "Met " + ref_tokens + "."
    refs = tuple(
        KnowledgeReference(i + 1, "person", "Stranger" if wrong_name and i == count - 1 else name)
        for i, name in enumerate(names)
    )
    unit = KnowledgeUnit(
        SelectionCriteria(None, "2031-07-14", "calendar_day", (), None),
        "record",
        (),
        (),
        (content,),
        refs,
    )
    helpers = tuple(
        KnowledgeUnit(
            SelectionCriteria(person, person, "person", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        for person in names
    )
    plan = RequestPlan((WriteAction((unit, *helpers)),), ())
    claim = CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinal=0)
    return source, context, plan, (claim,)


@pytest.mark.parametrize("count", (1, 3, 5, 9))
def test_positive_source_proved_people_accept_any_bounded_number(count):
    source, context, plan, claims = _many_people(count)
    manifest = build_candidate_coverage_manifest(source, context, plan, claims)
    assert manifest.claims == claims


@pytest.mark.parametrize("count", (3, 5, 9))
def test_invented_last_person_never_passes_generic_validation(count):
    source, context, plan, claims = _many_people(count, wrong_name=True)
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(source, context, plan, claims)


def _tasks_plan(*, linked: bool):
    main = KnowledgeUnit(
        SelectionCriteria("Write to Ada", "Write to Ada", "task", (), None),
        "record",
        (PropertyChange("status", "set", "pending"),),
        (),
        ("Write to {{ref:0}}.",) if linked else (),
        (KnowledgeReference(1, "person", "Ada"),) if linked else (),
    )
    helpers = (
        (
            KnowledgeUnit(
                SelectionCriteria("Ada", "Ada", "person", (), None),
                "record",
                (),
                (),
                (),
                (),
                reference_lookup_only=True,
            ),
        )
        if linked
        else ()
    )
    return RequestPlan((WriteAction((main, *helpers)),), ())


def test_verified_existing_person_cannot_be_dropped_by_task_fallback():
    planner = TaskCorePlanner(
        SimpleNamespace(plan=lambda _source, _context=(): _tasks_plan(linked=False)),
        TaskInterpretation("Write to Ada", TaskOperation.CREATE),
    )
    planner.bind_verified_source_note_names((CanonicalSourceNameHint("Ada", "Ada", "person"),))
    with pytest.raises(RequestPlanningError, match="dropped"):
        planner.plan("Write to Ada")


def test_linked_task_remains_one_semantic_fact_without_plain_duplicate():
    planner = TaskCorePlanner(
        SimpleNamespace(plan=lambda _source, _context=(): _tasks_plan(linked=True)),
        TaskInterpretation("Write to Ada", TaskOperation.CREATE),
    )
    planner.bind_verified_source_note_names((CanonicalSourceNameHint("Ada", "Ada", "person"),))
    result = planner.plan("Write to Ada")
    unit = result.actions[0].units[0]
    assert unit.facts == ("Write to {{ref:0}}.",)
    assert len(unit.references) == 1
