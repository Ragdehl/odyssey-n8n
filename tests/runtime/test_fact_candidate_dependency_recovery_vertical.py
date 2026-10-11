"""Dependence-aware replay safety on actual model plans and canonical Markdown.

A synthetic second-action failure must not silently cause the first
already-persisted fact to be appended twice on the same logical request ID.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import odyssey_core.application as core_application
from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationStatus,
    execute_request,
)
from odyssey_core.candidate_dependency_recovery import (
    DependentRequestRecoveryError,
    inspect_dependent_request_recovery,
)
from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_dependency_global_coverage_vertical import _setup
from tests.runtime.test_fact_candidate_dependent_actual_core_vertical import _vault
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder


def _execute(case, repo, index, joined, context, manifest, request_id):
    return execute_request(
        context.source,
        planner=SimpleNamespace(plan=lambda _: joined),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=EmptyIndex(),
        embedder=ConstantEmbedder(),
        contextual_reasoner=UnresolvedReasoner(),
        actor="synthetic-dependent-replay",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: request_id,
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
    )


@pytest.mark.parametrize("case", ("F23", "F26"))
def test_second_action_failure_persists_one_fact_and_blocks_same_id_replay(
    case, tmp_path: Path, monkeypatch
):
    _source, context, _plans, _claims, joined, manifest = _setup(case)
    repo, index = _vault(tmp_path, existing_report=True)
    original = core_application._execute_write

    def interrupted(action_index, *args, **kwargs):
        if action_index == 1:
            return ActionResult(
                action_index, "write", ActionStatus.FAILED, reason="simulated_second_action_failure"
            )
        return original(action_index, *args, **kwargs)

    monkeypatch.setattr(core_application, "_execute_write", interrupted)
    rid = "interrupted-" + case
    first = _execute(case, repo, index, joined, context, manifest, rid)
    assert first.status is ApplicationStatus.PARTIAL
    assert len(first.action_results) == 2
    state = inspect_dependent_request_recovery(repo, SCHEMA, rid)
    assert state.state == "partial"
    assert state.fact_ordinals == (0,)
    assert not state.safe_to_retry_automatically
    saved = {p: repo.read_text(p) for p in repo.list_markdown_paths()}

    monkeypatch.setattr(core_application, "_execute_write", original)
    replay = _execute(case, repo, index, joined, context, manifest, rid)
    assert replay.status is ApplicationStatus.NEEDS_ATTENTION
    assert replay.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
    assert replay.action_results == ()
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == saved
    with pytest.raises(DependentRequestRecoveryError, match="partial"):
        from odyssey_core.candidate_dependency_recovery import require_new_dependent_request

        require_new_dependent_request(repo, SCHEMA, rid)


@pytest.mark.parametrize("case", ("F23", "F26"))
def test_completed_request_replay_is_blocked_without_duplicate_facts(case, tmp_path):
    _source, context, _plans, _claims, joined, manifest = _setup(case)
    repo, index = _vault(tmp_path, existing_report=True)
    rid = "completed-" + case
    first = _execute(case, repo, index, joined, context, manifest, rid)
    assert first.status is ApplicationStatus.COMPLETED
    status = inspect_dependent_request_recovery(repo, SCHEMA, rid)
    assert status.state == "complete"
    assert set(status.fact_ordinals) == {0, 1}
    saved = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    replay = _execute(case, repo, index, joined, context, manifest, rid)
    assert replay.status is ApplicationStatus.NEEDS_ATTENTION
    assert replay.action_results == ()
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == saved


def test_an_orphan_second_fact_is_a_conflict_not_a_resume_candidate(tmp_path):
    source, context, _plans, _claims, joined, manifest = _setup("F23")
    repo, index = _vault(tmp_path, existing_report=True)
    rid = "orphan-f23"
    result = _execute("F23", repo, index, joined, context, manifest, rid)
    assert result.status is ApplicationStatus.COMPLETED
    path = tmp_path / "vault" / "Odyssey.md"
    before = path.read_text(encoding="utf-8")
    lines = before.splitlines(keepends=True)
    removed = []
    skip = False
    for line in lines:
        if line.startswith("- Tiene un fallo"):
            skip = True
        if not skip:
            removed.append(line)
        if skip and "ordinal=0" in line:
            skip = False
    path.write_text("".join(removed), encoding="utf-8")
    inspection = inspect_dependent_request_recovery(repo, SCHEMA, rid)
    assert inspection.state == "conflict"
    assert inspection.fact_ordinals == (1,)
    assert inspection.may_start_new_request is False


@pytest.mark.parametrize("case", ("F23", "F26"))
def test_one_canonical_delivery_review_reports_both_verified_source_facts(case, tmp_path):
    from odyssey_core.candidate_coverage import review_dependent_candidate_coverage

    _source, context, _plans, _claims, combined, manifest = _setup(case)
    repo, index = _vault(tmp_path, existing_report=True)
    result = _execute(case, repo, index, combined, context, manifest, "unified-" + case)
    assert result.status is ApplicationStatus.COMPLETED
    review = review_dependent_candidate_coverage(
        context.source, context, combined, manifest, result, repo, SCHEMA
    )
    assert review.candidate_semantics_verified
    assert review.safe_to_report_all_candidates_complete
    assert review.fully_accounted_for_structurally
    assert review.pending_candidate_ids == ()
    assert review.observed_original_fact_ordinals == (0, 1)
    assert review.recovery_state == "complete"
    assert [item.status for item in review.items] == [
        "physically_written_claim",
        "physically_written_claim",
    ]


@pytest.mark.parametrize("case", ("F23", "F26"))
def test_interrupted_request_reports_one_physically_present_without_false_completion(
    case, tmp_path, monkeypatch
):
    from odyssey_core.candidate_coverage import review_dependent_candidate_coverage

    _source, context, _plans, _claims, combined, manifest = _setup(case)
    repo, index = _vault(tmp_path, existing_report=True)
    original = core_application._execute_write

    def fail_second(action_index, *args, **kwargs):
        if action_index == 1:
            return ActionResult(action_index, "write", ActionStatus.FAILED, reason="interrupted")
        return original(action_index, *args, **kwargs)

    monkeypatch.setattr(core_application, "_execute_write", fail_second)
    result = _execute(case, repo, index, combined, context, manifest, "partial-review-" + case)
    assert result.status is ApplicationStatus.PARTIAL
    review = review_dependent_candidate_coverage(
        context.source, context, combined, manifest, result, repo, SCHEMA
    )
    assert review.recovery_state == "partial"
    assert review.observed_original_fact_ordinals == (0,)
    assert not review.candidate_semantics_verified
    assert not review.safe_to_report_all_candidates_complete
    assert review.pending_candidate_ids == ("candidate-1", "candidate-2")
    assert all(item.status == "planned_unverified" for item in review.items)


def test_tampered_link_downgrades_completed_candidate_report(tmp_path):
    from odyssey_core.candidate_coverage import review_dependent_candidate_coverage

    _source, context, _plans, _claims, combined, manifest = _setup("F26")
    repo, index = _vault(tmp_path, existing_report=True)
    result = _execute("F26", repo, index, combined, context, manifest, "tampered-report")
    assert result.status is ApplicationStatus.COMPLETED
    path = tmp_path / "vault" / "calendar/days/2026-10-04.md"
    original = path.read_text(encoding="utf-8")
    assert "[[El informe|El informe]]" in original
    path.write_text(
        original.replace("[[El informe|El informe]]", "[[Ana|El informe]]"),
        encoding="utf-8",
    )
    review = review_dependent_candidate_coverage(
        context.source, context, combined, manifest, result, repo, SCHEMA
    )
    assert review.recovery_state == "complete"
    assert review.observed_original_fact_ordinals == (0, 1)
    assert not review.safe_to_report_all_candidates_complete
    assert review.pending_candidate_ids == ("candidate-1", "candidate-2")
