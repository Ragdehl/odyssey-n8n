"""Independent facts can persist while unplanned pronoun work stays visible."""

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
from odyssey_core.candidate_pending_projection import (
    CandidatePendingProjectionError,
    project_unresolved_candidate_preview,
)
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_fact_candidate_writes_e2e import _case, _new_repo
from tests.runtime.test_temporal_user_path_e2e import SCHEMA, _day_plan


def _case_with_pending(tmp_path: Path):
    case, context = _case("F14")
    original = _day_plan("2026-10-03", "Hablé con Eric.", "2026-10-03")
    unit = original.actions[0].units[0]
    plan = RequestPlan(
        (
            WriteAction(
                (
                    replace(
                        unit,
                        facts=("Hablé con Eric.", "Hablé con Luis."),
                        fact_temporal_anchors=(unit.fact_temporal_anchors[0],) * 2,
                    ),
                )
            ),
        ),
        (),
    )
    claims = (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
        CoreCandidateCoverageClaim("candidate-2", "planned_fact", 1),
        CoreCandidateCoverageClaim("candidate-3", "pending", pending_reason="ambiguous_identity"),
    )
    manifest = build_candidate_coverage_manifest(case["source"], context, plan, claims)
    repo = _new_repo(tmp_path)
    result = execute_request(
        case["source"],
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-pending",
        now="2026-10-04T17:35:00+02:00",
        context_limit=5,
        request_id_factory=lambda: "candidate-pending-test",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
    )
    readback = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    return case, context, plan, manifest, result, readback, repo


def test_two_saved_facts_and_one_ambiguous_pronoun_are_shown_without_replay_claim(
    tmp_path: Path,
) -> None:
    case, context, plan, manifest, result, readback, repo = _case_with_pending(tmp_path)
    assert result.status is ApplicationStatus.PARTIAL
    projected = project_unresolved_candidate_preview(
        case["source"], context, plan, manifest, result, readback
    )
    assert projected.request_id == "candidate-pending-test"
    assert projected.request_status == "partial"
    assert projected.physically_verified_fact_count == 2
    assert len(projected.pending) == 1
    pending = projected.pending[0]
    assert pending.candidate_id == "candidate-3"
    assert pending.source_text == "Mañana iré al cine con él"
    assert pending.reason == "ambiguous_identity"
    assert case["source"][pending.source_start : pending.source_end] == pending.source_text
    assert not projected.persisted and not projected.resumable
    assert not projected.candidate_semantics_verified
    assert not pending.resumable
    assert "calendar/days/2026-10-03.md" in repo.list_markdown_paths()
    assert projected.physically_verified_fact_count == 2


def test_unmatched_current_request_or_result_id_has_no_pretendable_pending_record(
    tmp_path: Path,
) -> None:
    case, context, plan, manifest, result, readback, _repo = _case_with_pending(tmp_path)
    with pytest.raises(CandidatePendingProjectionError):
        project_unresolved_candidate_preview(
            "different source", context, plan, manifest, result, readback
        )
    with pytest.raises(CandidatePendingProjectionError):
        project_unresolved_candidate_preview(
            case["source"],
            context,
            plan,
            manifest,
            replace(result, request_id="different-id"),
            readback,
        )


def test_no_pending_candidate_cannot_be_presented_as_a_clarification(
    tmp_path: Path,
) -> None:
    case, context, plan, manifest, result, readback, _repo = _case_with_pending(tmp_path)
    all_done = replace(
        manifest,
        claims=(
            CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
            CoreCandidateCoverageClaim("candidate-2", "planned_fact", 1),
            CoreCandidateCoverageClaim("candidate-3", "planned_fact", 2),
        ),
    )
    with pytest.raises(CandidatePendingProjectionError):
        project_unresolved_candidate_preview(
            case["source"], context, plan, all_done, result, readback
        )


def test_preview_is_not_a_durable_phase17b_record(tmp_path: Path) -> None:
    case, context, plan, manifest, result, readback, repo = _case_with_pending(tmp_path)
    projected = project_unresolved_candidate_preview(
        case["source"], context, plan, manifest, result, readback
    )
    assert not hasattr(projected, "record")
    assert not hasattr(projected, "resume")
    assert not any(path.name.startswith("candidate-") for path in repo.root.iterdir())
    assert projected.original_request == case["source"]
