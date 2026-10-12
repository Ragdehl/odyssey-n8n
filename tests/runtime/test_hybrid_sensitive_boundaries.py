"""Hybrid grouped sensitive-scope and independent-task safety sentinels.

These tests intentionally do not try to turn negations, rejected proposals,
or conditional branches into confirmed occurrences. They preserve the first
authentic model attempts and demonstrate the existing fail-closed Writer
boundary without an API call.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, SelectionCriteria, WriteAction
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider


def _case(case_id: str):
    source = next(row["source"] for row in CASES if row["id"] == case_id)
    group = compile_hybrid_candidate_bundle(RecordedRouter(case_id).propose(source))
    return source, group


@pytest.mark.parametrize(
    ("case_id", "historic_status", "responses"),
    [
        ("F17", "needs_attention", 3),
        ("F19", "failed", 2),
        ("F20", "needs_attention", 3),
    ],
)
def test_three_real_sensitive_group_model_outputs_cannot_write_as_occurrences(
    case_id,
    historic_status,
    responses,
    tmp_path,
):
    source, group = _case(case_id)
    assert len(group.units) == 1
    archive = json.loads(
        (ROOT / f"benchmarks/application_router/hybrid_sensitive_v1/{case_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert archive["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert archive["real_model_captured_status"] == historic_status
    assert archive["real_model_written_notes"] == []
    sdk = FrozenProvider(archive["provider_outputs"])
    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    initial = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter(case_id),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda hints, domain: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=hints, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="sensitive-hybrid-no-write",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"sensitive-replay-{case_id}",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status.value == historic_status, result.execution_flow
    assert len(sdk.calls) == responses
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == initial


@pytest.mark.parametrize(
    ("case_id", "facts"),
    [
        ("F17", ("Ayer no vi a Ana.", "Ayer no vi a Luis.")),
        ("F19", ("Iremos al parque a las 11.", "Iremos al cine a las 12.")),
        ("F20", ("Iremos al cine.", "Nos quedaremos en casa.")),
    ],
)
def test_reviewed_fact_ordinal_cannot_silently_authorize_sensitive_source(
    case_id,
    facts,
):
    source, bundle = _case(case_id)
    context = bundle.units[0].context
    assert len(context.candidates) == 2
    day = "2026-10-05"
    plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(None, day, "calendar_day", (), None),
                        "record",
                        (),
                        (),
                        facts,
                        (),
                    ),
                )
            ),
        ),
        (),
    )
    claims = tuple(
        CoreCandidateCoverageClaim(f"candidate-{i + 1}", "planned_fact", fact_ordinal=i)
        for i in range(2)
    )
    with pytest.raises(ValueError, match="Sensitive scoped"):
        build_candidate_coverage_manifest(source, context, plan, claims)


def test_cancelled_first_candidate_cannot_make_replacement_a_confirmed_event():
    source, bundle = _case("F19")
    plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(None, "2026-10-05", "calendar_day", (), None),
                        "record",
                        (),
                        (),
                        ("Iremos al cine a las 12.",),
                        (),
                    ),
                )
            ),
        ),
        (),
    )
    with pytest.raises(ValueError, match="Sensitive scoped"):
        build_candidate_coverage_manifest(
            source,
            bundle.units[0].context,
            plan,
            (
                CoreCandidateCoverageClaim(
                    "candidate-1", "pending", pending_reason="unsupported_scope"
                ),
                CoreCandidateCoverageClaim("candidate-2", "planned_fact", fact_ordinal=0),
            ),
        )


def test_three_independent_tasks_do_not_inherit_modality_or_targets_without_proof():
    source, bundle = _case("F22")
    assert len(bundle.units) == 3
    assert [x.context.source for x in bundle.units] == [
        "Hoy tengo que llamar a Ana",
        " y escribir a Luis",
        "; mañana preparar la factura.",
    ]
    assert [x.context.candidates[0].kind for x in bundle.units] == ["task"] * 3
    assert "tengo que" not in bundle.units[1].context.source
    assert all(x.route.depends_on is None for x in bundle.units)
    assert [x.route.capability_id for x in bundle.units] == ["temporal", "core", "temporal"]
    assert all(len(item.context.candidates) == 1 for item in bundle.units)


def test_ambiguous_antecedent_stays_separate_and_never_verifies_a_canonical_actor():
    source, bundle = _case("F14")
    assert len(bundle.units) == 2
    assert bundle.units[1].context.candidates[0].state == "ambiguous_identity"
    plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(None, "2026-10-05", "calendar_day", (), None),
                        "record",
                        (),
                        (),
                        ("Iré al cine con Eric.",),
                        (),
                    ),
                )
            ),
        ),
        (),
    )
    with pytest.raises(ValueError, match="Ambiguous identity"):
        build_candidate_coverage_manifest(
            bundle.units[1].context.source,
            bundle.units[1].context,
            plan,
            (CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinal=0),),
        )


def test_unprovable_f27_source_dependency_stays_rejected():
    from odyssey_core.candidate_dependencies import CandidateDependencyError

    source = next(row["source"] for row in CASES if row["id"] == "F27")
    with pytest.raises(CandidateDependencyError, match="no evidence"):
        compile_hybrid_candidate_bundle(RecordedRouter("F27").propose(source))
