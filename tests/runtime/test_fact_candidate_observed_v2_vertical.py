"""Replay actual GPT-6 Router v2 proposals through isolated Core writes.

The provider outputs are frozen synthetic evidence. Core plans come from the
existing provider-shaped fake semantic compiler; no live call or personal vault.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_continuation_guard import build_selected_candidate_guard
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.clarification import ClarificationOption
from tests.apps.test_fact_candidates import CASES
from tests.benchmarks.test_fact_candidate_prompt_v2_observed import _context
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import _pipeline as f14_pipeline
from tests.runtime.test_fact_candidate_sequential_vertical import (
    _claims as f27_claims,
)
from tests.runtime.test_fact_candidate_sequential_vertical import (
    _pipeline as f27_pipeline,
)
from tests.runtime.test_fact_multi_participant_event import _vault_with_people
from tests.runtime.test_temporal_user_path_e2e import SCHEMA, _linked_day_plan


def _reviewed(case_id: str, *, prompt_revision: str = "v2"):
    if prompt_revision == "v2":
        source, context = _context(case_id)
    elif prompt_revision == "v3":
        saved = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "benchmarks/fact_candidate_v2_live/results/20261010T193754Z.json"
            ).read_text(encoding="utf-8")
        )
        assert saved["prompt_revision"] == "v3"
        case = next(c for c in CASES if c["id"] == case_id)
        source = case["source"]
        context = to_core_candidate_context(
            validate_fact_candidate_proposal(source, saved["raw_router_json"][case_id])
        )
    else:
        raise ValueError("Unknown frozen live evidence revision")
    if case_id == "F14":
        _case, _old_context, _scope, planner, _calls = f14_pipeline()
        plan = planner.plan(source)
        claims = (
            CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
            CoreCandidateCoverageClaim(
                "candidate-2", "pending", pending_reason="ambiguous_identity"
            ),
        )
    else:
        _case, _old_context, plan = f27_pipeline()
        claims = f27_claims()
    return source, context, plan, claims


@pytest.mark.parametrize("prompt_revision", ["v2", "v3"])
@pytest.mark.parametrize("case_id,expected_count", [("F14", 1), ("F27", 2)])
def test_real_gpt6_router_evidence_crosses_core_and_verifies_only_safe_facts(
    tmp_path: Path, case_id: str, expected_count: int, prompt_revision: str
) -> None:
    """Actual model source evidence survives Core's canonical/write/readback guards."""
    source, context, plan, claims = _reviewed(case_id, prompt_revision=prompt_revision)
    manifest = build_candidate_coverage_manifest(source, context, plan, claims)
    repo = _vault_with_people(tmp_path)
    (tmp_path / "pending").mkdir()
    pending = CandidatePendingRepository(tmp_path / "pending")

    def record(preview):
        return pending.record(
            preview,
            conversation_id=f"observed-{case_id}",
            created_at=NOW,
            options=(
                ClarificationOption("eric-id", "Eric"),
                ClarificationOption("luis-id", "Luis"),
            ),
            vault=repo,
            schema=SCHEMA,
        )

    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="observed-router-v2-isolated",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"observed-{case_id}-source",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
        candidate_pending_recorder=record,
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.pending_work.persisted
    assert len(result.canonical_reference_evidence) == 2
    assert [
        (ref.source_mention, ref.stable_note_id) for ref in result.canonical_reference_evidence
    ] == [
        ("Eric", "eric-id"),
        ("Luis", "luis-id"),
    ]
    text = repo.read_text("calendar/days/2026-10-03.md")
    assert text.count("<!-- odyssey:fact request=observed-") == expected_count
    assert "cine" not in text
    assert "[[Eric|Eric]]" in text and "[[Luis|Luis]]" in text
    receipts = readback_core_facts(source, context, plan, result, repo, SCHEMA)
    assert len(receipts.persisted_facts) == expected_count
    assert all(receipt.status == "verified_in_markdown" for receipt in receipts.persisted_facts)
    pending_item = pending.read(result.request_id)["pending"][0]
    assert pending_item["reference_text"] == "él"
    assert pending_item["text"] == "Mañana iré al cine con él"
    answer = pending.reply(
        conversation_id=f"observed-{case_id}",
        reply="Con Luis",
        answer_id=f"observed-{case_id}-reply",
        vault=repo,
        schema=SCHEMA,
        immediate_followup=True,
    )
    assert answer.outcome == "choice_recorded"
    assert answer.selected_note_id == "luis-id"
    guard = build_selected_candidate_guard(
        pending,
        conversation_id=f"observed-{case_id}",
        request_id=result.request_id,
        vault=repo,
        schema=SCHEMA,
    )
    assert guard is not None
    follow_plan = _linked_day_plan(
        "2026-10-05",
        "Iré al cine con {{ref:0}}.",
        "él",
        "2026-10-05",
        target_name="Luis",
    )
    follow = execute_request(
        "Mañana iré al cine con él.",
        planner=SimpleNamespace(plan=lambda _: follow_plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="observed-router-v2-isolated",
        now=guard.original_captured_at,
        context_limit=5,
        request_id_factory=lambda: f"observed-{case_id}-reply",
        write_preflight_guard=guard,
    )
    assert follow.status is ApplicationStatus.COMPLETED
    assert repo.read_text("calendar/days/2026-10-03.md") == text
    future = repo.read_text("calendar/days/2026-10-05.md")
    assert "Iré al cine con [[Luis|Luis]]." in future
    assert "Eric" not in future
    assert pending.read(result.request_id)["status"] == "selected"


@pytest.mark.parametrize("prompt_revision", ["v2", "v3"])
@pytest.mark.parametrize(
    "case_id,change",
    [
        ("F14", "drop_luis"),
        ("F14", "double_luis"),
        ("F14", "separate_statement"),
        ("F27", "drop_date"),
        ("F27", "drop_reference"),
        ("F27", "wrong_contact"),
        ("F27", "drop_inheritance"),
    ],
)
def test_tampered_actual_router_source_evidence_is_rejected_without_mutation(
    tmp_path: Path, case_id: str, change: str, prompt_revision: str
) -> None:
    """A fake/source-spliced role cannot make Core accept unverified links."""
    source, context, plan, claims = _reviewed(case_id, prompt_revision=prompt_revision)
    repo = _vault_with_people(tmp_path)
    before = tuple(repo.list_markdown_paths())
    first = context.candidates[0]
    if change == "drop_luis":
        first = replace(
            first,
            roles=tuple(
                r for r in first.roles if not (r.role == "participants" and r.span.text == "Luis")
            ),
        )
    elif change == "double_luis":
        participants = [r for r in first.roles if r.role == "participants"]
        first = replace(
            first,
            roles=tuple(
                replace(r, span=participants[1].span) if r == participants[0] else r
                for r in first.roles
            ),
        )
    elif change == "separate_statement":
        first = replace(first, roles=tuple(r for r in first.roles if r.role != "predicate"))
    elif change == "drop_date":
        first = replace(first, roles=tuple(r for r in first.roles if r.role != "date"))
    elif change == "drop_inheritance":
        second = context.candidates[1]
        context = replace(
            context,
            candidates=(first, replace(second, inherits=()), context.candidates[2]),
        )
    elif change == "wrong_contact":
        second = context.candidates[1]
        context = replace(
            context,
            candidates=(
                first,
                replace(second, roles=tuple(r for r in second.roles if r.role != "order")),
                context.candidates[2],
            ),
        )
    else:
        future = context.candidates[2]
        context = replace(
            context,
            candidates=(
                first,
                context.candidates[1],
                replace(future, roles=tuple(r for r in future.roles if r.role != "reference")),
            ),
        )
    if change not in {"drop_inheritance", "wrong_contact", "drop_reference"}:
        context = replace(context, candidates=(first, *context.candidates[1:]))
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(source, context, plan, claims)
    assert tuple(repo.list_markdown_paths()) == before
