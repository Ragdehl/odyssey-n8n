"""E2 fact ordinal ownership is explicit; same-date matching never guesses by order."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.execution_context import ContextContractError, ExecutionContext, QualitativeTime
from odyssey_core.fact_temporal_ownership import CoreFactTemporalOwnership
from odyssey_core.qualitative_fact_preservation import preserve_qualitative_day_facts
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_temporal_user_path_e2e import _core_with_plan, _day_plan

SRC = "Hoy por la tarde llamé a Bea. Hoy por la noche vi a Marta."
DATE = "2026-10-15"
PHRASES = (("Hoy por la tarde", "por la tarde"), ("Hoy por la noche", "por la noche"))


def ctx():
    return ExecutionContext(
        "explicit-source-fact",
        SRC,
        "2026-10-15T09:00:00+02:00",
        "Europe/Paris",
        domains=(
            DomainInterpretation(
                "temporal",
                SRC,
                "TEMPORAL_RESOLUTION",
                tuple(DomainEvidence("temporal_reference", phrase, DATE) for phrase, _ in PHRASES),
            ),
        ),
        qualitative_times=tuple(
            QualitativeTime(phrase, DATE, part, "Europe/Paris") for phrase, part in PHRASES
        ),
    )


def plan():
    a = _day_plan(DATE, "Llamé a Bea.", DATE)
    base = a.actions[0].units[0]
    combined = replace(
        base,
        facts=("Llamé a Bea.", "Vi a Marta."),
        fact_temporal_anchors=(base.fact_temporal_anchors[0],) * 2,
    )
    return RequestPlan((WriteAction((combined,)),), ())


def explicitly_core_bound(original):
    # Stand-in for future Core reviewer output. No Router or App may construct
    # this proof as a semantic authorization; a plan-bound verifier is required.
    return tuple(
        CoreFactTemporalOwnership(
            i, i, sha256(SRC.encode()).hexdigest(), sha256(repr(original).encode()).hexdigest()
        )
        for i in (0, 1)
    )


def test_same_date_without_core_fact_proof_fails_closed():
    with pytest.raises(ContextContractError, match="Multiple qualitative dates"):
        preserve_qualitative_day_facts(plan(), context=ctx())


def test_same_date_with_plan_bound_core_fact_proof_modifies_correct_facts_only():
    original = plan()
    amended = preserve_qualitative_day_facts(
        original, context=ctx(), reviewed_ownership=explicitly_core_bound(original)
    )
    assert amended.actions[0].units[0].facts[0] == "Llamé a Bea (por la tarde)."
    assert amended.actions[0].units[0].facts[1] == "Vi a Marta (por la noche)."
    assert original.actions[0].units[0].facts == ("Llamé a Bea.", "Vi a Marta.")
    assert amended.actions[0].units[0].target == original.actions[0].units[0].target
    assert (
        amended.actions[0].units[0].fact_temporal_anchors
        == original.actions[0].units[0].fact_temporal_anchors
    )


def test_same_date_core_binding_stale_reversed_or_incomplete_is_rejected():
    original = plan()
    proofs = explicitly_core_bound(original)
    for bad in (
        (proofs[0],),
        (replace(proofs[0], plan_digest="0" * 64), proofs[1]),
        (proofs[0], replace(proofs[1], fact_ordinal=0)),
    ):
        with pytest.raises(ContextContractError):
            preserve_qualitative_day_facts(original, context=ctx(), reviewed_ownership=bad)


def test_same_date_core_verified_fact_projection_writes_two_facts_to_same_real_day(tmp_path):
    repo, *_ = fresh_corpus_vault(tmp_path)
    original = plan()
    bound = preserve_qualitative_day_facts(
        original, context=ctx(), reviewed_ownership=explicitly_core_bound(original)
    )
    result = _core_with_plan(repo, SRC, "same-day-bound", bound)
    assert result.status is ApplicationStatus.COMPLETED, result.planning_error
    markdown = repo.read_text("calendar/days/2026-10-15.md")
    assert "Llamé a Bea (por la tarde)." in markdown
    assert "Vi a Marta (por la noche)." in markdown


def test_core_reviewed_task_fact_reuses_same_qualifier_without_changing_schedule():
    from odyssey_core.request_planning import SelectionCriteria

    original = plan()
    unit = original.actions[0].units[0]
    task_unit = replace(
        unit, target=SelectionCriteria(None, "Trabajar en Odyssey", "task", (), None)
    )
    task_plan = RequestPlan((WriteAction((task_unit,)),), ())
    proof = tuple(
        CoreFactTemporalOwnership(
            index,
            index,
            sha256(SRC.encode()).hexdigest(),
            sha256(repr(task_plan).encode()).hexdigest(),
        )
        for index in (0, 1)
    )
    changed = preserve_qualitative_day_facts(task_plan, context=ctx(), reviewed_ownership=proof)
    assert changed.actions[0].units[0].target == task_unit.target
    assert changed.actions[0].units[0].facts == (
        "Llamé a Bea (por la tarde).",
        "Vi a Marta (por la noche).",
    )
    assert changed.actions[0].units[0].fact_temporal_anchors == task_unit.fact_temporal_anchors


def test_reviewed_core_coverage_generates_source_bound_fact_ownership_without_order_guess():
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
    from odyssey_core.fact_temporal_ownership import reviewed_fact_temporal_ownership

    source = SRC
    clauses = ("Hoy por la tarde llamé a Bea.", "Hoy por la noche vi a Marta.")
    candidates = []
    for index, clause in enumerate(clauses, 1):
        start = source.index(clause)
        qualifier = PHRASES[index - 1][1]
        qstart = source.index(qualifier, start)
        candidates.append(
            CoreCandidate(
                f"candidate-{index}",
                "occurrence",
                "candidate",
                (CoreSourceSpan(clause, start, start + len(clause)),),
                (
                    CoreCandidateRole(
                        "time_approx", CoreSourceSpan(qualifier, qstart, qstart + len(qualifier))
                    ),
                ),
                (),
            )
        )
    source_context = CoreCandidateContext(
        source,
        tuple(candidates),
        scoped_route_source=True,
        hybrid_interpretation_mode=True,
        verified_route_temporal=ctx().domains[0],
    )
    original = plan()
    unit = original.actions[0].units[0]
    reviewed = RequestPlan((WriteAction((replace(unit, facts=clauses),)),), ())
    manifest = build_candidate_coverage_manifest(
        source,
        source_context,
        reviewed,
        (
            CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
            CoreCandidateCoverageClaim("candidate-2", "planned_fact", 1),
        ),
    )
    bindings = reviewed_fact_temporal_ownership(
        replace(ctx(), candidates=source_context), source_context, reviewed, manifest
    )
    assert [item.fact_ordinal for item in bindings] == [0, 1]
    assert (
        preserve_qualitative_day_facts(
            reviewed,
            context=replace(ctx(), candidates=source_context),
            reviewed_ownership=bindings,
        )
        is reviewed
    )  # Core plan had already preserved both literals

    # Forging the swapped association cannot pass the same Core source review.
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(
            source,
            source_context,
            reviewed,
            (
                CoreCandidateCoverageClaim("candidate-1", "planned_fact", 1),
                CoreCandidateCoverageClaim("candidate-2", "planned_fact", 0),
            ),
        )
