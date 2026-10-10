"""Actual GPT-6 Router -> Temporal -> separately called GPT-5.6 Core replay.

All provider responses are saved *real* model JSON. The only model calls
here are deterministic fake SDK replays through the existing Core compiler.
Only disposable tmp-path vaults are ever written. The full original source
candidate coverage and ambiguous durable pending remain mandatory.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_core_live import run_scoped_live
from benchmarks.fact_candidate_core_live.run_temporal_live import temporal_evidence
from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_continuation_guard import build_selected_candidate_guard
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.candidate_scoped_planning import (
    merge_scoped_core_plans_for_review,
    plan_independent_core_units,
)
from odyssey_core.clarification import ClarificationOption
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from tests.benchmarks.test_fact_candidate_prompt_v3_observed import _case
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_fact_multi_participant_event import _vault_with_people
from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan


def _actual_core_plan(case_id: str):
    context = to_core_candidate_context(_case(case_id))
    temporal = temporal_evidence(context.source).core_domain_interpretation()
    provider_inputs: list[tuple[str, str]] = []

    def factory(unit, domain):
        paths = list(run_scoped_live.RESULTS.glob(f"*--{case_id}--{unit.candidate_id}.json"))
        assert len(paths) == 1
        receipt = json.loads(paths[0].read_text(encoding="utf-8"))
        assert receipt["mode"] == "LIVE_SCOPED_CORE_PLAN_ONLY"
        assert receipt["provider_status"] == "completed"
        assert receipt["outcome"] == "PLAN"
        assert receipt["validation"] == "locally_valid"
        assert receipt["may_authorize_writes"] is False
        payload = json.loads(receipt["raw_model_response"])
        fake, calls = _sdk_fake(payload)
        planner = OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=domain)

        class CheckedPlanner:
            def plan(self, request):
                result = planner.plan(request)
                assert len(calls) == 1
                assert calls[0]["model"] == "gpt-5.6-luna"
                assert calls[0]["input"][1]["content"] == unit.scoped_request()
                provider_inputs.append((unit.candidate_id, request))
                return result

        return CheckedPlanner()

    scoped = plan_independent_core_units(context.source, context, temporal, factory)
    assert not scoped.fully_reviewed_for_write
    plan = merge_scoped_core_plans_for_review(context.source, context, scoped)
    claims = tuple(
        CoreCandidateCoverageClaim(f"candidate-{i + 1}", "planned_fact", i)
        for i in range(len(scoped.planned))
    ) + (
        CoreCandidateCoverageClaim(
            f"candidate-{len(scoped.planned) + 1}",
            "pending",
            pending_reason="ambiguous_identity",
        ),
    )
    manifest = build_candidate_coverage_manifest(context.source, context, plan, claims)
    assert len(provider_inputs) == len(scoped.planned)
    return context, plan, manifest


@pytest.mark.parametrize("case_id,count", [("F14", 1), ("F27", 2)])
def test_real_scoped_core_plans_write_verified_past_and_durable_future_pending(
    tmp_path: Path, case_id: str, count: int
) -> None:
    """The previously blocked true model answers now physically cross Core."""
    context, plan, manifest = _actual_core_plan(case_id)
    repo = _vault_with_people(tmp_path)
    state = tmp_path / "candidate_pending"
    state.mkdir()
    pending = CandidatePendingRepository(state)

    def record(preview):
        return pending.record(
            preview,
            conversation_id=f"scoped-live-{case_id}",
            created_at=NOW,
            options=(
                ClarificationOption("eric-id", "Eric"),
                ClarificationOption("luis-id", "Luis"),
            ),
            vault=repo,
            schema=SCHEMA,
        )

    result = execute_request(
        context.source,
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="real-scoped-core-test-only",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"source-{case_id}",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
        candidate_pending_recorder=record,
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.pending_work.persisted
    assert [
        (ref.source_mention, ref.stable_note_id) for ref in result.canonical_reference_evidence
    ] == [("Eric", "eric-id"), ("Luis", "luis-id")]
    day = repo.read_text("calendar/days/2026-10-03.md")
    assert day.count("<!-- odyssey:fact request=source-") == count
    assert "Hablé con [[Eric|Eric]]" in day
    assert "Luis" in day
    assert ("Hablé después con [[Luis|Luis]]" in day) == (case_id == "F27")
    assert "cine" not in day
    assert (
        len(
            readback_core_facts(context.source, context, plan, result, repo, SCHEMA).persisted_facts
        )
        == count
    )
    state_record = pending.read(result.request_id)
    assert state_record["pending"][0]["reference_text"] == "él"
    assert state_record["pending"][0]["text"] == "Mañana iré al cine con él"
    follow = pending.reply(
        conversation_id=f"scoped-live-{case_id}",
        reply="Con Luis",
        answer_id=f"answer-{case_id}",
        vault=repo,
        schema=SCHEMA,
        immediate_followup=True,
    )
    assert follow.outcome == "choice_recorded"
    assert follow.selected_note_id == "luis-id"
    guard = build_selected_candidate_guard(
        pending,
        conversation_id=f"scoped-live-{case_id}",
        request_id=result.request_id,
        vault=repo,
        schema=SCHEMA,
    )
    assert guard is not None
    verified_before = repo.read_text("calendar/days/2026-10-03.md")
    follow_plan = _linked_day_plan(
        "2026-10-05",
        "Iré al cine con {{ref:0}}.",
        "él",
        "2026-10-05",
        target_name="Luis",
    )
    continuation = execute_request(
        "Mañana iré al cine con él.",
        planner=SimpleNamespace(plan=lambda _: follow_plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="scoped-guarded-continuation-test",
        now=guard.original_captured_at,
        context_limit=5,
        request_id_factory=lambda: f"reply-{case_id}",
        write_preflight_guard=guard,
    )
    assert continuation.status is ApplicationStatus.COMPLETED
    assert repo.read_text("calendar/days/2026-10-03.md") == verified_before
    future = repo.read_text("calendar/days/2026-10-05.md")
    assert "Iré al cine con [[Luis|Luis]]." in future
    assert "Eric" not in future


def test_original_provider_receipts_are_unique_and_under_approved_ceiling():
    """Frozen real models are replayed, never billed again in these tests."""
    rates = json.loads((run_scoped_live.ROOT / "config/runtime-pricing-snapshot.json").read_text())[
        "models"
    ]["gpt-5.6-luna"]
    names = [
        *run_scoped_live.HISTORIC,
        *[
            next(run_scoped_live.RESULTS.glob(f"*--{case}--{unit}.json")).name
            for case, unit in run_scoped_live.STAGES
        ],
    ]
    full_total = run_scoped_live.BASELINE_ESTIMATE_USD + sum(
        run_scoped_live._receipt_cost(
            json.loads((run_scoped_live.RESULTS / name).read_text()), rates
        )
        for name in names
    )
    assert round(full_total, 7) == 0.0259652
    assert full_total < run_scoped_live.AUTHORIZED_CUMULATIVE_CAP_USD
