"""Genuine F14/F27 model replay: safe completed facts plus durable ambiguous source.

No fabricated provider replies; still no invented Eric/Luis antecedent.
A deterministic v2 pending record asks for a later user choice and captures
the original time for correct temporal resolution on continuation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.candidate_continuation_guard import build_selected_candidate_guard
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider
from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan


@pytest.mark.parametrize(
    ("case", "count", "first_facts"),
    (
        ("F14", 1, ("Ayer hablé con [[Eric|Eric]] y [[Luis|Luis]].",)),
        (
            "F27",
            2,
            ("Ayer hablé con [[Eric|Eric]].", "Después hablé con [[Luis|Luis]]."),
        ),
    ),
)
def test_actual_models_complete_safe_events_and_record_ambiguous_cinema(
    case: str, count: int, first_facts: tuple[str, ...], tmp_path: Path
) -> None:
    source = next(row["source"] for row in CASES if row["id"] == case)
    receipt = json.loads(
        (
            ROOT / f"benchmarks/application_router/hybrid_remaining_diag_20261013/{case}.json"
        ).read_text()
    )
    assert receipt["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    sdk = FrozenProvider(receipt["real_model_outputs"])
    vault, ctx, semantic, emb = fresh_corpus_vault(tmp_path / "vault")
    state = tmp_path / "state" / "pending"
    state.mkdir(parents=True)
    pending = CandidatePendingRepository(state)
    prior_day = (
        vault.read_text("calendar/days/2026-10-04.md")
        if "calendar/days/2026-10-04.md" in vault.list_markdown_paths()
        else None
    )
    conversation = "real-model-" + case.casefold()

    def save(preview, choices):
        assert preview.original_request == source
        assert preview.pending[0].reason == "ambiguous_identity"
        assert preview.pending[0].source_text == "Mañana iré al cine con él"
        assert preview.pending[0].reference_text == "él"
        assert source[preview.pending[0].source_start : preview.pending[0].source_end] == (
            "Mañana iré al cine con él"
        )
        assert {item.label for item in choices} == {"Eric", "Luis"}
        assert all(item.note_type == "person" for item in choices)
        return pending.record(
            preview,
            conversation_id=conversation,
            created_at=NOW,
            options=choices,
            vault=vault,
            schema=SCHEMA,
        )

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
        repository=vault,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=emb,
        contextual_reasoner=object(),
        actor="synthetic-safe-ambiguity",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "safe-" + case.casefold(),
        bundle_compiler=compile_hybrid_candidate_bundle,
        route_ambiguity_recorder=save,
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.pending_work.required and result.pending_work.persisted
    assert len(sdk.calls) == len(receipt["real_model_outputs"])
    trace = result.execution_flow
    assert trace is not None
    assert len(trace["routes"]) == 2
    assert trace["routes"][0]["status"] == "completed"
    assert trace["routes"][1]["status"] == "needs_attention"
    assert trace["routes"][1]["steps"][-1]["name"] == "candidate.pending_identity"
    assert "Eric" in trace["routes"][1]["steps"][-1]["output"]
    assert "Luis" in trace["routes"][1]["steps"][-1]["output"]
    day = vault.read_text("calendar/days/2026-10-03.md")
    for fact in first_facts:
        assert fact in day
    assert day.count("<!-- odyssey:fact request=") == count
    if prior_day is None:
        if "calendar/days/2026-10-04.md" in vault.list_markdown_paths():
            # Date navigation may provision a Day scaffold, never a fact
            # asserting a guessed canonical participant.
            day_after = vault.read_text("calendar/days/2026-10-04.md")
            assert not any(line.startswith("- ") for line in day_after.splitlines())
    else:
        assert vault.read_text("calendar/days/2026-10-04.md") == prior_day
    assert "cine" not in "\n".join(
        vault.read_text(p) for p in vault.list_markdown_paths() if p.startswith("calendar/days")
    )
    persisted = pending.read(result.pending_work.record_id)
    assert persisted["status"] == "open"
    assert persisted["created_at"] == NOW
    assert len(persisted["pending"]) == 1
    assert persisted["pending"][0]["text"] == "Mañana iré al cine con él"
    assert persisted["pending"][0]["reference_text"] == "él"
    assert {option["label"] for option in persisted["options"]} == {"Eric", "Luis"}
    assert pending.open_requests(conversation) == (result.pending_work.record_id,)

    # A user response is a different, explicit authorization; it does not
    # retroactively rewrite or rerun either completed conversation.
    before = vault.read_text("calendar/days/2026-10-03.md")
    answer = pending.reply(
        conversation_id=conversation,
        reply="Con Luis",
        answer_id="answer-" + case.casefold(),
        vault=vault,
        schema=SCHEMA,
        immediate_followup=True,
    )
    assert answer.outcome == "choice_recorded"
    selected_guard = build_selected_candidate_guard(
        pending,
        conversation_id=conversation,
        request_id=result.pending_work.record_id,
        vault=vault,
        schema=SCHEMA,
    )
    assert selected_guard is not None
    assert selected_guard.original_captured_at == NOW
    assert vault.read_text("calendar/days/2026-10-03.md") == before
    # A separate user-authorized continuation exercises the existing Core
    # write guard; this reviewed deterministic plan is not a new LLM reply.
    resumed = execute_request(
        "Mañana iré al cine con él.",
        planner=type(
            "ReviewedContinuation",
            (),
            {
                "plan": lambda self, _src: _linked_day_plan(
                    "2026-10-05",
                    "Iré al cine con {{ref:0}}.",
                    "él",
                    "2026-10-05",
                    target_name="Luis",
                )
            },
        )(),
        repository=vault,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=emb,
        contextual_reasoner=object(),
        actor="synthetic-reviewed-followup",
        now=selected_guard.original_captured_at,
        context_limit=5,
        request_id_factory=lambda: "answer-" + case.casefold(),
        write_preflight_guard=selected_guard,
    )
    assert resumed.status is ApplicationStatus.COMPLETED
    continued_day = vault.read_text("calendar/days/2026-10-05.md")
    assert "Iré al cine con [[Luis|Luis]]." in continued_day
    assert "Eric" not in continued_day
    assert vault.read_text("calendar/days/2026-10-03.md") == before
    if prior_day is None:
        if "calendar/days/2026-10-04.md" in vault.list_markdown_paths():
            # Date navigation may provision a Day scaffold, never a fact
            # asserting a guessed canonical participant.
            day_after = vault.read_text("calendar/days/2026-10-04.md")
            assert not any(line.startswith("- ") for line in day_after.splitlines())
    else:
        assert vault.read_text("calendar/days/2026-10-04.md") == prior_day


@pytest.mark.parametrize("case", ("F14", "F27"))
def test_without_opt_in_recorder_stays_blocked_and_never_guesses(case: str, tmp_path: Path):
    source = next(row["source"] for row in CASES if row["id"] == case)
    receipt = json.loads(
        (
            ROOT / f"benchmarks/application_router/hybrid_remaining_diag_20261013/{case}.json"
        ).read_text()
    )
    sdk = FrozenProvider(receipt["real_model_outputs"])
    vault, ctx, semantic, emb = fresh_corpus_vault(tmp_path)
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
        repository=vault,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=emb,
        contextual_reasoner=object(),
        actor="synthetic-old-fail-closed",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "old-" + case.casefold(),
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.execution_flow["routes"][1]["reason"] == (
        "ROUTE_DEPENDENCY_CANONICAL_EVIDENCE_UNAVAILABLE"
    )
    assert not result.pending_work.persisted
