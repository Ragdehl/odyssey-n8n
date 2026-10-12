"""Post-fix replay of genuine independent Router/Core/reviewer outputs for F16.

The original real test remained PARTIAL because the positive additive marker
'también' was legitimately sourced as predicate_relation rather than leaving
the role unspecified. This test keeps the original status unchanged in the
receipt and demonstrates the corrected source-role verifier/writer on the same
unchanged real-model outputs. No provider calls; synthetic Markdown only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_event_handoff import SOURCE
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider


@pytest.mark.parametrize(
    ("capture", "old_statuses", "old_note_count"),
    [
        ("F16-v8", ["completed", "needs_attention"], 1),
        ("F16-v9", ["completed", "completed"], 2),
    ],
)
def test_f16_saved_real_five_model_replies_write_two_independent_notes(
    tmp_path: Path, capture: str, old_statuses: list[str], old_note_count: int
):
    fixture = json.loads(
        (ROOT / f"benchmarks/application_router/scoped_routing_v2/{capture}.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture["captured_application_status"] == (
        "completed" if old_note_count == 2 else "partial"
    )
    assert fixture["captured_route_statuses"] == old_statuses
    assert fixture["captured_written_notes"] == old_note_count
    assert fixture["original_source_sha256"] == hashlib.sha256(SOURCE.encode()).hexdigest()
    provider = FrozenProvider(fixture["responses"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    result = execute_candidate_routed_message(
        SOURCE,
        router=OpenAIFactCandidateRouter(provider, prompt_revision="v4"),
        temporal=None,
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
        actor="f16-genuine-models-new-writer",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"{capture}-frozen-provider",
    )
    assert result.status.value == "completed", result.execution_flow
    assert [r["status"] for r in result.execution_flow["routes"]] == ["completed", "completed"]
    assert len(provider.calls) == len(fixture["responses"]) == 5
    assert [
        call["input"][1]["content"]
        for call in provider.calls
        if call["model"] == "gpt-5.6-luna"
        and "odyssey_luna_first_planner_result" in str(call.get("text", {}))
    ] == [
        "Ana compró entradas para el concierto",
        " y Luis también.",
    ]
    ana = repo.read_text("Ana.md")
    luis = repo.read_text("Luis.md")
    assert "Ana compró entradas para el concierto." in ana
    assert "compró entradas para el concierto." in luis.casefold()
    assert "ana compró entradas para el concierto." not in luis.casefold()
    assert "odyssey:fact request=route-" in ana
    assert "odyssey:fact request=route-" in luis


def test_bad_real_router_role_mapping_is_rejected_without_core_calls():

    import pytest

    from odyssey_apps.fact_candidates import (
        OpenAIFactCandidateRouter,
        RouterError,
    )

    data = json.loads(
        (
            ROOT
            / "benchmarks/application_router/scoped_routing_v2/F16-v7-router-contradiction.json"
        ).read_text(encoding="utf-8")
    )
    sdk = FrozenProvider([data["router_response"]])
    with pytest.raises(RouterError, match="grounded source evidence"):
        OpenAIFactCandidateRouter(sdk, prompt_revision="v4").propose(SOURCE)
    assert len(sdk.calls) == 1


def test_router_v4_is_an_opt_in_suffix_that_preserves_v3_prompt_bytes():
    from odyssey_apps.fact_candidates import (
        FACT_CANDIDATE_PROMPT_V4_EXTENSION,
        OpenAIFactCandidateRouter,
    )

    saved = json.loads(
        (ROOT / "benchmarks/application_router/scoped_routing_v2/F16-v9.json").read_text(
            encoding="utf-8"
        )
    )
    prompts = []
    for revision in ("v3", "v4"):
        sdk = FrozenProvider([saved["responses"][0]])
        result = OpenAIFactCandidateRouter(sdk, prompt_revision=revision).propose(SOURCE)
        assert len(result.candidates) == 2
        prompts.append(sdk.calls[0]["input"][0]["content"])
    assert prompts[1] == prompts[0] + FACT_CANDIDATE_PROMPT_V4_EXTENSION
    assert "Predicate/verb source text" not in prompts[0]
