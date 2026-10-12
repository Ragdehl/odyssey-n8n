"""Immutable real-model three-attempt correction regression, no API calls."""

from __future__ import annotations

import hashlib
import json

import pytest

from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

SOURCE = next(c["source"] for c in CASES if c["id"] == "F19")
ARCHIVE = ROOT / "benchmarks/application_router/hybrid_correction_v1/F19.json"


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [
        ("first_original", "failed"),
        ("first_guided", "needs_attention"),
        ("final_reviewed", "completed"),
    ],
)
def test_genuine_correction_model_attempts_replay_without_guessing(attempt, expected, tmp_path):
    saved = json.loads(ARCHIVE.read_text())
    assert saved["source_sha256"] == hashlib.sha256(SOURCE.encode()).hexdigest()
    provider = FrozenProvider(saved["versions"][attempt]["provider_outputs"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    originals = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = execute_candidate_routed_message(
        SOURCE,
        router=RecordedRouter("F19"),
        temporal=OpenAITemporalInterpreter(
            provider, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda hints, domain: OpenAILunaExperimentalPlanner(
            provider, SCHEMA, CLOCK, candidate_context=hints, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(provider),
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="f19-frozen-genuine-correction",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f19-genuine-" + attempt,
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status.value == expected, result.execution_flow
    assert len(provider.calls) == len(saved["versions"][attempt]["provider_outputs"])
    if attempt == "final_reviewed":
        day = repo.read_text("calendar/days/2026-10-05.md")
        assert day.count("12:00 — Iremos al cine") == 1
        assert "parque" not in day
        assert "11:00" not in day
        assert "calendar/days/2026-10-05.md" not in originals
    else:
        assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == originals
