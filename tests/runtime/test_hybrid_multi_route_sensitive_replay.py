"""F18/F22 fresh real Core outputs: preserve independent routes and task semantics.

F18: mixed negative/positive may not guess previous day or canonical identity.
F22: an independent task may not masquerade as an ordinary Calendar fact.
The source recordings remain immutable even when a new guard improves safety.
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
from odyssey_runtime.source_scope_compiler import compile_candidate_route_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider


def test_tasks_must_not_be_reported_done_as_plain_calendar_day_facts():
    source = next(c["source"] for c in CASES if c["id"] == "F22")
    router = RecordedRouter("F22").propose(source)
    hybrid = compile_hybrid_candidate_bundle(router)
    strict = compile_candidate_route_bundle(router)
    assert len(hybrid.units) == 3 and len(strict.units) == 3
    assert all(u.context.hybrid_interpretation_mode for u in hybrid.units)
    assert all(not u.context.hybrid_interpretation_mode for u in strict.units)
    assert hybrid.units[2].context.source == "; mañana preparar la factura."
    plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(None, "2026-10-05", "calendar_day", (), None),
                        "record",
                        (),
                        (),
                        ("mañana preparar la factura.",),
                        (),
                    ),
                )
            ),
        ),
        (),
    )
    with pytest.raises(ValueError, match="specialized Tasks"):
        build_candidate_coverage_manifest(
            hybrid.units[2].context.source,
            hybrid.units[2].context,
            plan,
            (CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinal=0),),
        )


@pytest.mark.parametrize(
    ("case_id", "old_status", "expected_routes"),
    [
        ("F18", "needs_attention", 2),
        ("F22", "partial", 3),
    ],
)
def test_frozen_real_multiroute_models_never_invent_identities_or_complete_tasks(
    case_id, old_status, expected_routes, tmp_path
):
    source = next(c["source"] for c in CASES if c["id"] == case_id)
    saved = json.loads(
        (ROOT / f"benchmarks/application_router/hybrid_sensitive_v1/{case_id}.json").read_text()
    )
    assert saved["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert saved["real_model_captured_status"] == old_status
    sdk = FrozenProvider(saved["provider_outputs"])
    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
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
        actor="hybrid-sensitive-real-model-replay",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"hybrid-guarded-{case_id}",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert len(sdk.calls) == len(saved["provider_outputs"])
    assert len(result.execution_flow["routes"]) == expected_routes
    assert result.status.value != "completed"
    assert all(repo.read_text(p) == v for p, v in before.items())
    assert set(repo.list_markdown_paths()) == set(before)


def test_repairs_needed_are_not_automatically_created_as_tasks():
    source = next(c["source"] for c in CASES if c["id"] == "F25")
    group = compile_hybrid_candidate_bundle(RecordedRouter("F25").propose(source))
    assert len(group.units) == 1
    assert {c.kind for c in group.units[0].context.candidates} == {"property", "task"}
    plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(
                            "Casa de Toulouse", "La casa de Toulouse", "property", (), None
                        ),
                        "record",
                        (),
                        (),
                        ("Tiene humedad en el sótano.", "Necesita reparar el tejado."),
                        (),
                    ),
                )
            ),
        ),
        (),
    )
    with pytest.raises(ValueError, match="specialized Tasks"):
        build_candidate_coverage_manifest(
            source,
            group.units[0].context,
            plan,
            (
                CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinal=0),
                CoreCandidateCoverageClaim("candidate-2", "planned_fact", fact_ordinal=1),
            ),
        )
