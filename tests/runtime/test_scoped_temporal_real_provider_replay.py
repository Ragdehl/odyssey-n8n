"""Authentic post-split provider replies, replayed through a clean synthetic vault.

F06 is a COMPLETE fresh six-call route-local success with inherited Temporal
and two independently reviewed Core writings. F04 is a recorded PARTIAL
negative sentinel where Temporal included an unresolved order connector.
No provider access, personal vault, or changed expected reply is permitted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

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

FROZEN = ROOT / "benchmarks/application_router/scoped_routing_v2"


@pytest.mark.parametrize("capture_id", ["F06", "F04", "F04-earlier-partial"])
def test_frozen_fresh_scoped_model_replies_preserve_real_outcome(capture_id: str, tmp_path: Path):
    case_id = capture_id.split("-")[0]
    case = next(item for item in CASES if item["id"] == case_id)
    snap = json.loads((FROZEN / f"{capture_id}.json").read_text(encoding="utf-8"))
    assert (
        snap["original_source_sha256"] == hashlib.sha256(case["source"].encode("utf-8")).hexdigest()
    )
    assert snap["version"] == 2
    sdk = FrozenProvider(snap["responses"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)

    result = execute_candidate_routed_message(
        case["source"],
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
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
        actor="frozen-v2-provider-only-synthetic",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"frozen-v2-{case_id}",
    )
    assert result.status.value == snap["captured_application_status"]
    assert [r["status"] for r in result.execution_flow["routes"]] == [
        r["status"] for r in snap["route_summaries"]
    ]
    assert len(sdk.calls) == len(snap["responses"])
    assert sdk.calls[0]["input"][1]["content"] == case["source"]
    assert all(request["input"][1]["content"] != case["source"] for request in sdk.calls[1:])
    assert (
        sum(
            "odyssey:fact request=route-" in repo.read_text(path)
            for path in repo.list_markdown_paths()
        )
        == snap["written_notes"]
    )
    content = "\n".join(repo.read_text(path) for path in repo.list_markdown_paths())
    if case_id == "F06":
        assert result.status.value == "completed"
        assert len(sdk.calls) == 6
        assert "Vi a [[Ana|Ana]]." in content
        assert "Compré pan." in content
        assert (
            sum(
                "odyssey:fact request=route-" in repo.read_text(path)
                for path in repo.list_markdown_paths()
            )
            == 1
        )
        assert sdk.calls[2]["input"][1]["content"] == "Hoy vi a Ana"
        assert sdk.calls[4]["input"][1]["content"] == " y compré pan."
    elif capture_id == "F04":
        assert result.status.value == "completed"
        assert len(sdk.calls) == 7
        assert "parque" in content.lower()
        assert "cine" in content.lower()
        assert "12:00" in content
        assert "18:00" in content
    else:
        assert result.status.value == "partial"
        assert len(sdk.calls) == 5
        assert "parque" in content.lower()
        assert "cine" not in content.lower()
