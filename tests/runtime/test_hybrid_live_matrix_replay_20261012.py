"""Freeze the new genuine hybrid-model F11 success and 18-case corpus receipt.

No provider access: replay the authentic Router, Temporal, Core and reviewer
outputs on an isolated canonical vault and verify the resulting source fact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

EVIDENCE = ROOT / "benchmarks/application_router/hybrid_live_matrix_20261012"


def test_real_matrix_is_complete_and_each_provider_result_preserved() -> None:
    summary = json.loads((EVIDENCE / "SUMMARY.json").read_text())
    assert summary["finished_count"] == summary["requested_count"] == 18
    assert len(list(EVIDENCE.glob("F*.json"))) == 18
    for row in summary["results"]:
        case = next(c for c in CASES if c["id"] == row["case"])
        saved = json.loads((EVIDENCE / f"{row['case']}.json").read_text())
        assert saved["source_sha256"] == hashlib.sha256(case["source"].encode()).hexdigest()
        assert saved["status"] == "finished"
        assert saved["application_status"] == row["application_status"]
        assert saved["provider_calls"] == len(saved["real_model_outputs"])
        assert all(item["status"] == "completed" for item in saved["real_model_outputs"])
        assert saved["estimated_new_usd"] >= 0


def test_genuine_f11_models_write_exact_joint_purchase_to_canonical_day(tmp_path: Path) -> None:
    case = next(c for c in CASES if c["id"] == "F11")
    saved = json.loads((EVIDENCE / "F11.json").read_text())
    sdk = FrozenProvider(saved["real_model_outputs"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    before = set(repo.list_markdown_paths())
    result = execute_candidate_routed_message(
        case["source"],
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
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="f11-frozen-live-models-only",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f11-frozen-purchase",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert len(sdk.calls) == len(saved["real_model_outputs"]) == 4
    assert set(repo.list_markdown_paths()) - before == {"calendar/days/2026-10-04.md"}
    day = repo.read_text("calendar/days/2026-10-04.md")
    assert day.count("- Hoy compré pan y leche.") == 1
    assert "calendar/days/2026-10-05" not in day
    assert len(result.execution_flow["routes"]) == 1


def test_genuine_f07_grouped_named_events_keep_distinct_people_and_hours(tmp_path: Path) -> None:
    """Replay linked grouped events through ordinary canonical reference binding."""
    case = next(c for c in CASES if c["id"] == "F07")
    saved = json.loads((EVIDENCE / "F07.json").read_text())
    sdk = FrozenProvider(saved["real_model_outputs"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    result = execute_candidate_routed_message(
        case["source"],
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
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="f07-frozen-linked-events",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f07-frozen-linked-events",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    assert len(sdk.calls) == len(saved["real_model_outputs"]) == 4
    day = repo.read_text("calendar/days/2026-10-04.md")
    assert "15:00 — A las  veo a [[Bea|Bea]]." in day
    assert "17:00 — A las  veo a [[Luis|Luis]]." in day
    assert "15:00" not in day[day.index("[[Luis|Luis]]") - 30 : day.index("[[Luis|Luis]]")]
    assert "17:00" not in day[day.index("[[Bea|Bea]]") - 30 : day.index("[[Bea|Bea]]")]
