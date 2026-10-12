"""Opt-in correction: discard old plan and only persist final future intention."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, SelectionCriteria, WriteAction
from odyssey_core.temporal import TemporalAnchor
from odyssey_core.temporal_interpretation import parse_temporal_interpretation
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault

SOURCE = next(c["source"] for c in CASES if c["id"] == "F19")
RECEIPT = ROOT / "benchmarks/application_router/hybrid_sensitive_v1/F19.json"
DAY = "2026-10-05"
TIME = "2026-10-05T12:00:00+02:00"
GOOD = "Iremos al cine a las 12:00."


def domain():
    saved = json.loads(RECEIPT.read_text())
    reply = json.loads(saved["provider_outputs"][0]["output_text"])
    return parse_temporal_interpretation(
        reply, SOURCE, timezone="Europe/Paris"
    ).core_domain_interpretation()


def _context():
    context = (
        compile_hybrid_candidate_bundle(RecordedRouter("F19").propose(SOURCE)).units[0].context
    )
    return replace(context, verified_correction_temporal=domain())


def plan(fact=GOOD, *, day=DAY, clock=TIME):
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(None, day, "calendar_day", (), None),
                        "record",
                        (),
                        (),
                        (fact,),
                        (),
                        fact_temporal_anchors=((TemporalAnchor.from_value(clock),),),
                    ),
                )
            ),
        ),
        (),
    )


def review(source, context, plan, *, canonical_binding=None):
    return build_candidate_coverage_manifest(
        source,
        context,
        plan,
        (
            CoreCandidateCoverageClaim(
                "candidate-1", "pending", pending_reason="superseded_by_correction"
            ),
            CoreCandidateCoverageClaim("candidate-2", "planned_fact", fact_ordinal=0),
        ),
        canonical_binding=canonical_binding,
    )


def test_corrected_plan_coverage_can_prove_final_future_intention():
    context = _context()
    manifest = review(SOURCE, context, plan())
    assert [c.disposition for c in manifest.claims] == ["pending", "planned_fact"]


@pytest.mark.parametrize(
    "fact,day,clock",
    [
        ("Iremos al parque a las 11:00.", DAY, TIME),
        ("Iremos al cine a las 11:00.", DAY, TIME),
        ("No iremos al cine a las 12:00.", DAY, TIME),
        ("Iremos a un concierto a las 12:00.", DAY, TIME),
        (GOOD, "2026-10-06", TIME),
        (GOOD, DAY, "2026-10-05T11:00:00+02:00"),
    ],
)
def test_cancelled_wrong_date_or_invented_final_facts_are_rejected(fact, day, clock):
    with pytest.raises(ValueError):
        review(SOURCE, _context(), plan(fact, day=day, clock=clock))


def test_correction_isolated_writer_cannot_save_discarded_plan(tmp_path):
    repo, index, semantic, embedder = fresh_corpus_vault(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    temporal = domain()

    class Temporal:
        def interpret(self, fragment):
            assert fragment == SOURCE
            from odyssey_core.temporal_interpretation import parse_temporal_interpretation

            saved = json.loads(RECEIPT.read_text())
            return parse_temporal_interpretation(
                json.loads(saved["provider_outputs"][0]["output_text"]),
                SOURCE,
                timezone="Europe/Paris",
            )

    def factory(context, interpreted):
        assert context.verified_correction_temporal == temporal
        assert interpreted == temporal
        return SimpleNamespace(plan=lambda text: plan())

    result = execute_candidate_routed_message(
        SOURCE,
        router=RecordedRouter("F19"),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=review,
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="hybrid-corrected-intention",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "hybrid-f19-correction",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is not ApplicationStatus.FAILED, result.execution_flow
    daytext = repo.read_text("calendar/days/2026-10-05.md")
    assert "Iremos al cine" in daytext
    assert "parque" not in daytext
    assert "11:00" not in daytext
    assert "calendar/days/2026-10-05.md" not in before
    assert "calendar/days/2026-10-05.md" in repo.list_markdown_paths()


def test_abandoned_plan_cannot_be_marked_complete_without_verified_final_fact():
    context = _context()
    no_write = RequestPlan((), ())
    with pytest.raises(ValueError, match="compatible unresolved reason"):
        build_candidate_coverage_manifest(
            SOURCE,
            context,
            no_write,
            (
                CoreCandidateCoverageClaim(
                    "candidate-1", "pending", pending_reason="superseded_by_correction"
                ),
                CoreCandidateCoverageClaim(
                    "candidate-2", "pending", pending_reason="needs_capability"
                ),
            ),
        )
