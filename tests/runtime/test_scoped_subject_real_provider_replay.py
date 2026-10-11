"""Recorded F23 provider calls replayed after conservative general Core property fix.

The paid attempt had no writes because the old validator required a single
subject anchor, and the second planner escalated. Reusing exactly the same
provider outputs proves the first legitimate assertion now writes, while the
second remains pending until fresh models see the verified predecessor.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

SOURCE = next(c["source"] for c in CASES if c["id"] == "F23")
RECORD = ROOT / "benchmarks/application_router/scoped_routing_v2/F23.json"


def test_f23_real_model_first_property_now_writes_but_unproven_second_stays_pending(
    tmp_path: Path,
) -> None:
    data = json.loads(RECORD.read_text(encoding="utf-8"))
    assert data["captured_application_status"] == "needs_attention"
    assert data["written_notes"] == 0
    assert data["original_source_sha256"] == hashlib.sha256(SOURCE.encode()).hexdigest()
    sdk = FrozenProvider(data["responses"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    result = execute_candidate_routed_message(
        SOURCE,
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(sdk, CLOCK),
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
        actor="recorded-core-subject-safe",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "real-recorded-F23",
    )
    assert len(sdk.calls) == 4, result.execution_flow
    assert [row["status"] for row in result.execution_flow["routes"]] == [
        "completed",
        "needs_attention",
    ], result.execution_flow
    assert result.status.value == "partial"
    text = repo.read_text("Odyssey.md")
    assert "Tiene un fallo en Router." in text
    assert "Tiene otro fallo en Temporal." not in text
    assert sdk.calls[1]["input"][1]["content"] == "El proyecto Odyssey tiene un fallo en Router"
    assert sdk.calls[3]["input"][1]["content"] == " y otro en Temporal."


def test_later_real_f23_attempt_stopped_before_second_model_response():
    """Do not present the API budget refusal as an actual Core model decision."""
    attempted = json.loads(
        (ROOT / "benchmarks/application_router/scoped_routing_v2/F23-latest.json").read_text(
            encoding="utf-8"
        )
    )
    assert attempted["case_id"] == "F23"
    assert attempted["recorded_receipt_id"] == "F23-v3"
    assert attempted["captured_application_status"] == "partial"
    assert attempted["written_notes"] == 1
    assert len(attempted["responses"]) == 3
    assert [response["model"] for response in attempted["responses"]] == [
        "gpt-6-luna",
        "gpt-5.6-luna",
        "gpt-5.6-luna",
    ]
    # There is no second Core Planner response in the frozen evidence.
    assert [item["status"] for item in attempted["route_summaries"]] == ["completed", "failed"]
