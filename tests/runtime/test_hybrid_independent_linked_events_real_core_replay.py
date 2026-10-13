"""True frozen Router/Temporal/Planner with separately synthetic reviewer claims.

The independent reviewer acceptance in these tests is SYNTHETIC, not a new
real-model success. The Core parser, provenance, canonical writes and physical
Markdown readback are genuine and use only a disposable fixture vault.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import plan_fact_ordinals
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

SOURCE = next(row["source"] for row in CASES if row["id"] == "F08")
RECEIPT = json.loads(
    (ROOT / "benchmarks/application_router/hybrid_semantic_live_v6/F08.json").read_text()
)


def _sdk_with_source_proven_claims(*, swapped=False, bad_clock=False):
    outputs = [dict(item) for item in RECEIPT["real_model_outputs"]]
    context = (
        compile_hybrid_candidate_bundle(
            OpenAIFactCandidateRouter(FrozenProvider(outputs[:1]), prompt_revision="v4").propose(
                SOURCE
            )
        )
        .units[0]
        .context
    )
    domain = (
        OpenAITemporalInterpreter(
            FrozenProvider(outputs[1:2]),
            CLOCK,
            max_output_tokens=1536,
            scoped_date_time_context=True,
        )
        .interpret(SOURCE)
        .core_domain_interpretation()
    )
    plan = OpenAILunaExperimentalPlanner(
        FrozenProvider(outputs[2:3]),
        SCHEMA,
        CLOCK,
        candidate_context=context,
        domain_interpretation=domain,
    ).plan(SOURCE)
    words: dict[int, str] = {}
    indices = iter(plan_fact_ordinals(plan))
    for action in plan.actions:
        if hasattr(action, "units"):
            for unit in action.units:
                words.update(zip(next(indices), unit.facts, strict=True))
    order = (1, 0) if swapped else (0, 1)
    output = {
        "candidates": [
            {
                "candidate_id": f"candidate-{n + 1}",
                "source_quote": name,
                "fact_ordinals": [order[n]],
                "planned_fact_texts": [words[order[n]]],
                "pending_reason": None,
            }
            for n, name in enumerate(("Marta", "Luis"))
        ],
    }
    outputs[3]["output_text"] = json.dumps(output, ensure_ascii=False)
    if bad_clock:
        response = json.loads(outputs[2]["output_text"])
        operations = response["result"]["actions"][0]["operations"]
        second = operations[0]["facts"][1]["parts"]
        clock = next(part for part in second if part["kind"] == "temporal_reference")
        clock["value"] = "2026-10-05T11:00:00+02:00"
        outputs[2]["output_text"] = json.dumps(response, ensure_ascii=False)
    return FrozenProvider(outputs)


def _execute(tmp_path: Path, sdk):
    repo, ctx, sem, emb = fresh_corpus_vault(tmp_path)
    unchanged = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = execute_candidate_routed_message(
        SOURCE,
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v4"),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda c, d: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=c, domain_interpretation=d
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=sem,
        embedder=emb,
        contextual_reasoner=object(),
        actor="disposable-synthetic-reviewer-proof",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "independent-links-literal-test",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    return result, repo, unchanged


def test_two_named_events_verify_independent_clock_and_real_canonical_markdown(tmp_path: Path):
    sdk = _sdk_with_source_proven_claims()
    result, repo, _before = _execute(tmp_path, sdk)
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    day = repo.read_text("calendar/days/2026-10-05.md")
    assert "- 10:00 — [[Marta|Marta]] irá al médico." in day
    assert "- 10:00 — [[Luis|Luis]] irá al dentista." in day
    assert day.count("odyssey:fact request=") == 2
    assert len(sdk.calls) == 4
    prompt = json.loads(sdk.calls[3]["input"][1]["content"])
    assert prompt["core_verified_temporal_read_only"]["capability_id"] == "temporal"
    assert len(prompt["core_verified_temporal_read_only"]["evidence"]) == 3
    assert "a la misma hora" in str(prompt["core_verified_temporal_read_only"])


@pytest.mark.parametrize("attack", ["swapped", "bad_clock"])
def test_wrong_participant_or_clock_cannot_write_even_with_reviewer_claim(
    attack: str, tmp_path: Path
):
    sdk = _sdk_with_source_proven_claims(
        swapped=attack == "swapped", bad_clock=attack == "bad_clock"
    )
    result, repo, before = _execute(tmp_path, sdk)
    assert result.status is not ApplicationStatus.COMPLETED
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_authentic_mixed_car_property_and_future_event_write_same_note(tmp_path: Path):
    source = next(row["source"] for row in CASES if row["id"] == "F24")
    record = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_semantic_live_v6/F24.json").read_text()
    )
    sdk = FrozenProvider(record["real_model_outputs"])
    repo, ctx, sem, emb = fresh_corpus_vault(tmp_path)
    result = execute_candidate_routed_message(
        source,
        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v4"),
        temporal=OpenAITemporalInterpreter(
            sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
        ),
        core_planner_factory=lambda c, d: OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=c, domain_interpretation=d
        ),
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=sem,
        embedder=emb,
        contextual_reasoner=object(),
        actor="disposable-authentic-corpus",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "actual-car-source-review",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    car = repo.read_text("El coche.md")
    assert "- Está en el taller." in car
    assert "- Pasará la revisión [[calendar/days/2026-10-05|05-10-2026]]." in car
    assert car.count("odyssey:fact request=") == 2
    assert len(sdk.calls) == 4
