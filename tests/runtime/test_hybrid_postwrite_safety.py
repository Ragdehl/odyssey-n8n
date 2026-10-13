"""Regression: physical writes survive failed routed verification and ambiguous carriers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter, validate_fact_candidate_proposal
from odyssey_core.application import (
    ApplicationResult,
    ApplicationStatus,
    CanonicalReferenceEvidence,
)
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import (
    _suppress_ambiguous_single_handoff,
    execute_candidate_routed_message,
)
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider


def _case(case_id: str) -> str:
    return next(row["source"] for row in CASES if row["id"] == case_id)


def test_single_proven_alias_carrier_never_resolves_two_participants() -> None:
    """Core's one non-alias carrier cannot choose between two original people."""
    receipt = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_remaining_diag_20261013/F14.json").read_text()
    )
    proposal = validate_fact_candidate_proposal(
        _case("F14"), json.loads(receipt["real_model_outputs"][0]["output_text"])
    )
    bundle = compile_hybrid_candidate_bundle(proposal)
    assert len(bundle.units) == 2
    proof = CanonicalReferenceEvidence(
        0, 0, 0, "Luis", "person:Luis", "person", "Luis", "day:one", "guard", "guard"
    )
    result = ApplicationResult(
        "source",
        ApplicationStatus.COMPLETED,
        (),
        (),
        canonical_reference_evidence=(proof,),
    )

    blocked = _suppress_ambiguous_single_handoff(
        bundle.units[0].context, bundle.units[1].route, 0, result
    )
    assert blocked.canonical_reference_evidence == ()
    assert blocked.status is ApplicationStatus.COMPLETED
    assert blocked.action_results == result.action_results


def test_postwrite_readback_exception_keeps_core_receipt_and_blocks_dependent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure AFTER Core wrote must never look like 'no Core write occurred'."""
    source = _case("F14")
    receipt = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_remaining_diag_20261013/F14.json").read_text()
    )
    sdk = FrozenProvider(receipt["real_model_outputs"])
    vault, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path / "vault")

    def broken_readback(*_args: object, **_kwargs: object):
        raise RuntimeError("injected after physical Markdown mutation")

    monkeypatch.setattr("odyssey_core.candidate_fact_readback.readback_core_facts", broken_readback)
    result = execute_candidate_routed_message(
        source,
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v5"),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda ctx, domain: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=ctx, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=vault,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="synthetic-postwrite",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "synthetic-postwrite",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert "date:2026-10-03" in result.affected_stable_note_ids
    assert result.execution_flow is not None
    routes = result.execution_flow["routes"]
    assert routes[0]["status"] == "partial"
    assert routes[1]["status"] == "needs_attention"
    assert routes[1]["reason"] == "ROUTE_DEPENDENCY_PREDECESSOR_NOT_COMPLETED"
    assert any(
        s.name == "candidate.postwrite_verification" and s.error_category == "RuntimeError"
        for s in result.operational.stages
    )
    day = vault.read_text("calendar/days/2026-10-03.md")
    assert "Ayer hablé con [[Eric|Eric]] y [[Luis|Luis]]." in day
    assert day.count("<!-- odyssey:fact request=") == 1
    assert "cine" not in day
