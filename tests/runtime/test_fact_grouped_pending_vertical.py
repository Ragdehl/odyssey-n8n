"""One group fact with two canonical links, plus one durable pending pronoun.

Runs existing Core/Markdown writer and pending state in an empty disposable
vault. All plans/clarification choices are reviewed fixtures, NOT live models.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_continuation_guard import build_selected_candidate_guard
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.clarification import ClarificationOption
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_multi_participant_event import (
    _core_linked_event,
    _f14_proposal,
    _vault_with_people,
)
from tests.runtime.test_temporal_user_path_e2e import SCHEMA, _linked_day_plan


def _fixture(tmp_path: Path):
    case, _proposal, context = _f14_proposal()
    repo = _vault_with_people(tmp_path)
    state = tmp_path / "state" / "pending"
    state.mkdir(parents=True)
    pending = CandidatePendingRepository(state)
    plan = _core_linked_event()
    claims = (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
        CoreCandidateCoverageClaim("candidate-2", "pending", pending_reason="ambiguous_identity"),
    )
    manifest = build_candidate_coverage_manifest(case["source"], context, plan, claims)

    def persist(preview):
        return pending.record(
            preview,
            conversation_id="chat-group",
            created_at=NOW,
            options=(
                ClarificationOption("eric-id", "Eric"),
                ClarificationOption("luis-id", "Luis"),
            ),
            vault=repo,
            schema=SCHEMA,
        )

    return case, context, repo, pending, plan, manifest, persist


def _core(tmp_path: Path):
    case, context, repo, pending, plan, manifest, persist = _fixture(tmp_path)
    result = execute_request(
        case["source"],
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-approved-group",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "group-source-request",
        candidate_context=context,
        candidate_coverage_factory=lambda *_args: manifest,
        candidate_pending_recorder=persist,
    )
    return case, context, repo, pending, plan, result


def test_grouped_f14_core_writes_one_verified_fact_and_durable_ambiguous_second(
    tmp_path: Path,
) -> None:
    """Prove physical linked fact from 2 Core identities, not 2 conversations."""
    case, context, repo, pending, plan, result = _core(tmp_path)
    assert result.status is ApplicationStatus.PARTIAL
    assert result.pending_work.persisted and result.pending_work.record_id == "group-source-request"
    assert [p.state for p in context.candidates] == ["candidate", "ambiguous_identity"]
    assert [(x.source_mention, x.stable_note_id) for x in result.canonical_reference_evidence] == [
        ("Eric", "eric-id"),
        ("Luis", "luis-id"),
    ]
    receipts = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    assert [(x.ordinal, x.status, x.note_id) for x in receipts.persisted_facts] == [
        (0, "verified_in_markdown", "date:2026-10-03"),
    ]
    assert receipts.unresolved_candidate_ids == ("candidate-2",)
    saved = pending.read("group-source-request")
    assert saved["physically_verified_fact_count"] == 1
    assert len(saved["completed_fact_markers"]) == 1
    assert saved["pending"][0]["text"] == "Mañana iré al cine con él"
    assert saved["pending"][0]["reference_text"] == "él"
    day = repo.read_text("calendar/days/2026-10-03.md")
    assert day.count("<!-- odyssey:fact request=group-source-request ordinal=0") == 1
    assert "Hablé con [[Eric|Eric]] y [[Luis|Luis]]." in day
    assert "cine" not in day


def test_answer_then_core_guard_writes_only_the_dependent_fact_not_the_group_again(
    tmp_path: Path,
) -> None:
    """Approved shape end-to-end: grouped linked fact + pending + choice + guarded cinema."""
    _case, _context, repo, pending, _plan, first = _core(tmp_path)
    original = repo.read_text("calendar/days/2026-10-03.md")
    choice = pending.reply(
        conversation_id="chat-group",
        reply="Con Luis",
        answer_id="group-answer-1",
        vault=repo,
        schema=SCHEMA,
        immediate_followup=True,
    )
    assert choice.outcome == "choice_recorded" and choice.selected_note_id == "luis-id"
    guard = build_selected_candidate_guard(
        pending,
        conversation_id="chat-group",
        request_id=first.request_id,
        vault=repo,
        schema=SCHEMA,
    )
    assert guard is not None and guard.original_captured_at == NOW
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Luis"
    )
    second = execute_request(
        "Mañana iré al cine con él.",
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-approved-group",
        now=guard.original_captured_at,
        context_limit=5,
        request_id_factory=lambda: "group-answer-1",
        write_preflight_guard=guard,
    )
    assert second.status is ApplicationStatus.COMPLETED
    assert repo.read_text("calendar/days/2026-10-03.md") == original
    assert "Iré al cine con [[Luis|Luis]]." in repo.read_text("calendar/days/2026-10-05.md")
    assert not any(
        "Eric" in line for line in repo.read_text("calendar/days/2026-10-05.md").splitlines()
    )
    assert pending.read(first.request_id)["status"] == "selected"  # no false automatic closure


@pytest.mark.parametrize(
    "problem", ["missing_luis", "swapped_names", "extra_helper", "mutating_helper"]
)
def test_grouped_source_preflight_rejects_unproven_reference_coverage_before_writes(
    tmp_path: Path,
    problem: str,
) -> None:
    case, context, repo, _pending, plan, _manifest, _persist = _fixture(tmp_path)
    action = plan.actions[0]
    day = action.units[0]
    helpers = action.units[1:]
    if problem == "missing_luis":
        day = replace(day, facts=("Hablé con {{ref:0}}.",), references=(day.references[0],))
    elif problem == "swapped_names":
        day = replace(day, references=tuple(reversed(day.references)))
    elif problem == "extra_helper":
        helper = replace(helpers[1], reference_lookup_only=True)
        helpers = (*helpers, helper)
    else:
        helpers = (helpers[0], replace(helpers[1], reference_lookup_only=False, facts=("Extra.",)))
    altered = RequestPlan((WriteAction((day, *helpers)),), ())
    claims = (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
        CoreCandidateCoverageClaim("candidate-2", "pending", pending_reason="ambiguous_identity"),
    )
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(case["source"], context, altered, claims)
    assert not (repo.root / "calendar" / "days" / "2026-10-03.md").exists()


def test_modified_linked_markdown_or_person_note_invalidates_physical_fact_proof(
    tmp_path: Path,
) -> None:
    case, context, repo, _pending, plan, result = _core(tmp_path)
    day = repo.root / "calendar" / "days" / "2026-10-03.md"
    original = day.read_text()
    day.write_text(original.replace("[[Luis|Luis]]", "[[Eric|Luis]]"), encoding="utf-8")
    receipts = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    assert receipts.persisted_facts[0].status == "not_verified"
    day.write_text(original, encoding="utf-8")
    luis = repo.root / "Luis.md"
    luis.write_text(luis.read_text() + "\n", encoding="utf-8")
    receipts = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    assert receipts.persisted_facts[0].status == "not_verified"


def test_injected_luna_group_attribution_cannot_skip_independent_core_coverage_review(
    tmp_path: Path,
) -> None:
    """Router source -> read-only fake Luna proposal -> independent Core -> real linked Markdown."""
    import json

    from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
    from tests.core.test_candidate_attribution import _f14_group

    case, context, repo, pending, plan, manifest, persist = _fixture(tmp_path)
    source, model_context, model_plan, expected = _f14_group()
    assert source == case["source"] and model_context == context and model_plan == plan
    calls = []
    fake_reply = SimpleNamespace(status="completed", output_text=json.dumps(expected), usage=None)
    fake = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kw: calls.append(kw) or fake_reply)
    )
    proposal = OpenAICoreCandidateAttributor(fake).propose(source, context, plan)
    assert len(calls) == 1
    assert proposal.candidates[0].fact_ordinal == 0
    assert proposal.candidates[1].pending_reason == "ambiguous_identity"
    assert not proposal.may_authorize_writes and not proposal.semantically_verified
    assert not (repo.root / "calendar/days/2026-10-03.md").exists()

    # This separately human-reviewed manifest is NEVER inferred from the model
    # proposal. Only ordinary Core's existing writer can persist the two links.
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-model-attribution-group",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "injected-group-attribution",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
        candidate_pending_recorder=persist,
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.pending_work.persisted
    readback = readback_core_facts(source, context, plan, result, repo, SCHEMA)
    assert readback.persisted_facts[0].status == "verified_in_markdown"
    assert readback.unresolved_candidate_ids == ("candidate-2",)
    assert pending.read(result.request_id)["physically_verified_fact_count"] == 1
    assert "Hablé con [[Eric|Eric]] y [[Luis|Luis]]." in repo.read_text(
        "calendar/days/2026-10-03.md"
    )
