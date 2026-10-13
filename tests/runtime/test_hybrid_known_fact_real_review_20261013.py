"""F09: actual double reviewer agrees known-vs-new; canonical no-op is read back.

This replays only genuine GPT-6 / GPT-5.6 provider outputs from the
experiment. No new model call and no personal/production Note writes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.known_fact_equivalence import (
    KnownFactReviewError,
    OpenAIKnownFactVerifier,
    validate_current_known_fact,
)
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider


def _complete(tmp_path: Path):
    source = next(row["source"] for row in CASES if row["id"] == "F09")
    receipt = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_known_fact_v1/F09.json").read_text()
    )
    assert len(receipt["real_new_model_outputs"]) == 2
    sdk = FrozenProvider(receipt["model_provenance"])
    reviewer_provider = FrozenProvider(receipt["real_new_model_outputs"])
    reviewer = OpenAIKnownFactVerifier(reviewer_provider)
    vault, ctx, semantic, emb = fresh_corpus_vault(tmp_path)
    before = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    result = execute_candidate_routed_message(
        source,
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v5"),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda c, domain: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=c, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        known_fact_verifier=reviewer,
        repository=vault,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=emb,
        contextual_reasoner=object(),
        actor="source-verified-existing-facts-replay",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f09-real-two-reviewers",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert len(reviewer_provider.calls) == 2
    assert len(sdk.calls) == len(receipt["model_provenance"])
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    return vault, before, result


def test_real_f09_existing_fact_is_verified_noop_while_new_person_is_written(
    tmp_path: Path,
):
    vault, before, result = _complete(tmp_path)
    assert vault.read_text("Marta.md") == before["Marta.md"]
    assert "Vive en Lyon." in vault.read_text("Luis.md")
    assert "Vive en Lyon." not in before["Luis.md"]
    assert vault.read_text("Luis.md").count("Vive en Lyon.") == 1
    proof_actions = [action for action in result.action_results if action.known_fact_evidence]
    assert len(proof_actions) == 1
    assert len(proof_actions[0].known_fact_evidence) == 1
    proof = proof_actions[0].known_fact_evidence[0]
    assert proof.path == "Marta.md"
    assert any(unit.operation == "ALREADY_KNOWN" for unit in proof_actions[0].unit_results)
    validate_current_known_fact(proof, "Vive en Lyon.", vault, SCHEMA)


def test_known_fact_noop_rejects_stale_canonical_note_even_after_valid_reviews(
    tmp_path: Path,
):
    vault, before, result = _complete(tmp_path)
    proof = next(proof for action in result.action_results for proof in action.known_fact_evidence)
    path = vault.root / proof.path
    path.write_text(before[proof.path] + "\n", encoding="utf-8")
    with pytest.raises(KnownFactReviewError, match="stale"):
        validate_current_known_fact(proof, "Vive en Lyon.", vault, SCHEMA)
