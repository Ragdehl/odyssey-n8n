"""Frozen real GPT-6/5.6 replies after safe grouped fixes; synthetic Notes."""

import hashlib
import json

import pytest

from odyssey_core.application import ApplicationStatus
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


@pytest.mark.parametrize("case_id", ("F03", "F21", "F23"))
def test_three_real_hybrid_groups_are_written_independently(case_id, tmp_path):
    source = next(x["source"] for x in CASES if x["id"] == case_id)
    saved = json.loads(
        (ROOT / f"benchmarks/application_router/hybrid_grouped_v2/{case_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert saved["fresh_provider_capture_status"] == "completed"
    assert saved["verified_markdown_facts"] == 2
    sdk = FrozenProvider(saved["provider_outputs"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    original_paths = set(repo.list_markdown_paths())
    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter(case_id),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        )
        if case_id != "F23"
        else None,
        core_planner_factory=lambda hints, domain: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=hints, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="replay-of-verified-hybrid-group",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"grouped-current-{case_id}",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    assert [x["status"] for x in result.execution_flow["routes"]] == ["completed"]
    assert len(sdk.calls) == len(saved["provider_outputs"])
    added = set(repo.list_markdown_paths()) - original_paths
    assert "Router.md" not in added and "Temporal.md" not in added
    if case_id == "F23":
        contents = repo.read_text("Odyssey.md")
        assert "Tiene un fallo en Router." in contents
        assert "Tiene otro fallo en Temporal." in contents
    elif case_id == "F03":
        contents = repo.read_text("calendar/days/2026-10-05.md")
        assert "Mañana vamos con mis hijos de paseo al parque." in contents
        assert "Luego iremos con mis hijos al cine." in contents
        assert "{{ref:" not in contents
    else:
        monday = repo.read_text("calendar/days/2026-10-05.md")
        wednesday = repo.read_text("calendar/days/2026-10-07.md")
        assert monday.count("18:00 — Tengo clase") == 1
        assert wednesday.count("18:00 — Tengo clase") == 1
