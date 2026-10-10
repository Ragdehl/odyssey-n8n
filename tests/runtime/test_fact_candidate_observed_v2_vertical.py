"""Replay actual GPT-6 Router v2 proposals through isolated Core writes.

The provider outputs are frozen synthetic evidence. Core plans come from the
existing provider-shaped fake semantic compiler; no live call or personal vault.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.clarification import ClarificationOption
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
from tests.runtime.test_temporal_user_path_e2e import SCHEMA


def _reviewed(case_id: str):
    source, context = _context(case_id)
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


@pytest.mark.parametrize("case_id,expected_count", [("F14", 1), ("F27", 2)])
def test_real_gpt6_router_evidence_crosses_core_and_verifies_only_safe_facts(
    tmp_path: Path, case_id: str, expected_count: int
) -> None:
    """Actual model source evidence survives Core's canonical/write/readback guards."""
    source, context, plan, claims = _reviewed(case_id)
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
    assert len(pending.read(result.request_id)["pending"]) == 1


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
    tmp_path: Path, case_id: str, change: str
) -> None:
    """A fake/source-spliced role cannot make Core accept unverified links."""
    source, context, plan, claims = _reviewed(case_id)
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
