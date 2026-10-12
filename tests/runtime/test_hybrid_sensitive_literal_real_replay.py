"""Re-run genuine GPT-6/5.6 sensitive literal plans on disposable Markdown.

Neither this test nor its fixtures contact a model provider.
"""

from __future__ import annotations

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


@pytest.mark.parametrize(("case_id", "day"), (("F17", "2026-10-03"), ("F20", "2026-10-10")))
def test_real_models_store_sensitive_statements_without_inventing_events(case_id, day, tmp_path):
    source = next(c["source"] for c in CASES if c["id"] == case_id)
    stored = json.loads(
        (
            ROOT / f"benchmarks/application_router/hybrid_sensitive_literal_v1/{case_id}.json"
        ).read_text()
    )
    assert stored["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert stored["physical_markdown_readback"] == ["verified_in_markdown"]
    client = FrozenProvider(stored["provider_outputs"])
    repo, index, semantic, embedder = fresh_corpus_vault(tmp_path)
    original_paths = set(repo.list_markdown_paths())
    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter(case_id),
        temporal=OpenAITemporalInterpreter(
            client, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda context, domain: OpenAILunaExperimentalPlanner(
            client, SCHEMA, CLOCK, candidate_context=context, domain_interpretation=domain
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(client),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="sensitive-real-replay",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "sensitive-real-" + case_id,
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    assert len(client.calls) == len(stored["provider_outputs"])
    assert repo.read_text("calendar/days/" + day + ".md").count(source) == 1
    assert set(repo.list_markdown_paths()) - original_paths <= {
        "calendar/days/" + day + ".md",
        "calendar/days/2026-10-04.md",
    }
