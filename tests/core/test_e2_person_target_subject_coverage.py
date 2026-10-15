"""E2 Core source participants: a directly targeted Person carries only their own subject."""

from __future__ import annotations

import pytest

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
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.temporal import TemporalAnchor

SOURCE = "Mañana por la tarde Bea hablará con Marta."


def _span(word):
    start = SOURCE.index(word)
    return CoreSourceSpan(word, start, start + len(word))


def _context(*, subject=True):
    roles = [
        CoreCandidateRole(role, _span(text))
        for role, text in (
            ("predicate", "hablará"),
            ("date", "Mañana"),
            ("time", "por la tarde"),
            ("participants", "Bea"),
            ("participants", "Marta"),
        )
    ]
    if subject:
        roles.append(CoreCandidateRole("subject", _span("Bea")))
    return CoreCandidateContext(
        SOURCE,
        (
            CoreCandidate(
                "candidate-1",
                "occurrence",
                "candidate",
                (_span("hablará"),),
                tuple(roles),
                (),
            ),
        ),
        scoped_route_source=True,
        hybrid_interpretation_mode=True,
    )


def _plan(*, target="Bea", kind="person", fact="Hablará con {{ref:0}} por la tarde."):
    unit = KnowledgeUnit(
        SelectionCriteria(target, target, kind, (), None),
        "record",
        (),
        (),
        (fact,),
        (KnowledgeReference(1, "identity", "Marta"),),
        fact_temporal_anchors=((TemporalAnchor("2026-10-16"),),),
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
    return RequestPlan((WriteAction((unit, helper)),), ())


def _review(context, plan):
    return build_candidate_coverage_manifest(
        SOURCE,
        context,
        plan,
        (CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),),
    )


def test_exact_source_subject_can_be_represented_by_its_own_person_note_target():
    manifest = _review(_context(), _plan())
    assert manifest.claims[0].fact_ordinal == 0


@pytest.mark.parametrize(
    "context,plan",
    [
        (_context(), _plan(target="Ana")),
        (_context(), _plan(kind="project")),
        (_context(subject=False), _plan()),
        (_context(), _plan(fact="Hablará por la tarde.")),
    ],
)
def test_wrong_target_missing_subject_or_missing_other_participant_is_rejected(context, plan):
    with pytest.raises(ValueError):
        _review(context, plan)


def test_calendar_day_fact_accepts_physical_subject_reference_as_well_as_object():
    from dataclasses import replace

    ctx = _context()
    candidate = ctx.candidates[0]
    object_only = replace(
        candidate,
        roles=tuple(
            role
            for role in candidate.roles
            if role.role != "participants" or role.span.text != "Bea"
        ),
    )
    ctx = replace(ctx, candidates=(object_only,))
    plan = _plan()
    write = plan.actions[0]
    day_unit = replace(
        write.units[0],
        target=SelectionCriteria("2026-10-16", "2026-10-16", "calendar_day", (), None),
        facts=("{{ref:0}} hablará con {{ref:1}} por la tarde.",),
        references=(
            KnowledgeReference(1, "identity", "Bea"),
            KnowledgeReference(2, "identity", "Marta"),
        ),
    )
    helper_bea = replace(write.units[1], target=SelectionCriteria("Bea", "Bea", "person", (), None))
    day_plan = replace(plan, actions=(WriteAction((day_unit, helper_bea, write.units[1])),))
    assert _review(ctx, day_plan).claims[0].fact_ordinal == 0
    altered = replace(
        day_unit,
        references=(
            KnowledgeReference(1, "identity", "Ana"),
            KnowledgeReference(2, "identity", "Marta"),
        ),
    )
    wrong_plan = replace(plan, actions=(WriteAction((altered, helper_bea, write.units[1])),))
    with pytest.raises(ValueError):
        _review(ctx, wrong_plan)
