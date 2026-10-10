"""Vertical opt-in Core preflight: reject lost source candidates BEFORE vault writes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
    review_candidate_coverage,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_fact_candidate_provenance_readback import _two_items
from tests.runtime.test_fact_candidate_writes_e2e import _case, _new_repo
from tests.runtime.test_temporal_user_path_e2e import SCHEMA, _day_plan


def _run(tmp_path: Path, source: str, context, plan: RequestPlan, factory, *, use_gate=True):
    repo = _new_repo(tmp_path)
    kwargs = (
        {
            "candidate_context": context,
            "candidate_coverage_factory": factory,
        }
        if use_gate
        else {}
    )
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda request: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-fact-coverage",
        now="2026-10-04T17:35:00+02:00",
        context_limit=5,
        request_id_factory=lambda: "isolated-coverage-test",
        **kwargs,
    )
    return result, repo


def _claims(*mapping: tuple[int, int]):
    return tuple(
        CoreCandidateCoverageClaim(f"candidate-{index}", "planned_fact", ordinal)
        for index, ordinal in mapping
    )


def test_explicit_exhaustive_claims_allow_only_normal_core_persistence(tmp_path: Path) -> None:
    """Preflight does not replace write code; valid two-item Core write still works."""
    case, context = _case("F11")
    plan = _two_items()
    captured = []

    def reviewed(source, packet, exact_plan):
        captured.append((source, packet, exact_plan))
        return build_candidate_coverage_manifest(
            source, packet, exact_plan, _claims((1, 0), (2, 1))
        )

    result, repo = _run(tmp_path, case["source"], context, plan, reviewed)
    assert result.status is ApplicationStatus.COMPLETED
    assert len(captured) == 1 and captured[0][0] == case["source"]
    assert len(repo.list_markdown_paths()) == 1
    assert any(stage.name == "candidate_coverage" for stage in result.operational.stages)
    readback = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    reviewed_again = reviewed(case["source"], context, plan)
    summary = review_candidate_coverage(case["source"], context, plan, reviewed_again, readback)
    assert [item.status for item in summary.items] == ["physically_written_claim"] * 2
    assert not summary.candidate_semantics_verified


@pytest.mark.parametrize(
    "bad_claims",
    [
        _claims((1, 0)),
        _claims((1, 0), (2, 0)),
        _claims((1, 0), (2, 77)),
    ],
)
def test_uncovered_or_duplicated_fact_prevents_all_core_writes(tmp_path: Path, bad_claims) -> None:
    """No action result, Markdown file or misleading completed status on failed review."""
    case, context = _case("F11")
    plan = _two_items()

    def invalid(source, packet, exact_plan):
        return build_candidate_coverage_manifest(source, packet, exact_plan, bad_claims)

    result, repo = _run(tmp_path, case["source"], context, plan, invalid)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
    assert result.action_results == ()
    assert repo.list_markdown_paths() == []


def test_absent_coverage_review_fails_closed_without_writing(tmp_path: Path) -> None:
    case, context = _case("F11")
    plan = _two_items()
    result, repo = _run(tmp_path, case["source"], context, plan, lambda *_: None)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert repo.list_markdown_paths() == []


def test_opt_in_requires_both_context_and_factory(tmp_path: Path) -> None:
    """An accidentally partial activation is rejected instead of silently bypassing gate."""
    case, context = _case("F11")
    plan = _two_items()
    with pytest.raises(ValueError, match="requires both"):
        _run(tmp_path, case["source"], context, plan, None)


def test_normal_core_is_bitwise_opt_in_and_can_run_without_candidates(tmp_path: Path) -> None:
    """Existing route users are not forced into Router v1 coverage or its prompts."""
    case, context = _case("F11")
    result, repo = _run(tmp_path, case["source"], context, _two_items(), None, use_gate=False)
    assert result.status is ApplicationStatus.COMPLETED
    assert not any(stage.name == "candidate_coverage" for stage in result.operational.stages)
    assert len(repo.list_markdown_paths()) == 1


def test_ambiguous_candidate_is_explicitly_held_without_blocking_independent_core_plan(
    tmp_path: Path,
) -> None:
    """Core can write two separate facts but cannot silently drop the pending pronoun."""
    case, context = _case("F14")
    original = _day_plan("2026-10-03", "Hablé con Eric.", "2026-10-03")
    unit = original.actions[0].units[0]
    unit = replace(
        unit,
        facts=("Hablé con Eric.", "Hablé con Luis."),
        fact_temporal_anchors=(unit.fact_temporal_anchors[0],) * 2,
    )
    plan = RequestPlan((WriteAction((unit,)),), ())

    def reviewed(source, packet, exact_plan):
        return build_candidate_coverage_manifest(
            source,
            packet,
            exact_plan,
            (
                *_claims((1, 0), (2, 1)),
                CoreCandidateCoverageClaim(
                    "candidate-3", "pending", pending_reason="ambiguous_identity"
                ),
            ),
        )

    result, repo = _run(tmp_path, case["source"], context, plan, reviewed)
    assert result.status is ApplicationStatus.PARTIAL  # only experimental opt-in route
    assert result.clarification_code == "CANDIDATE_COVERAGE_PENDING"
    assert result.pending_work.required and not result.pending_work.persisted
    assert "not yet implemented" in result.pending_work.error
    evidence = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    summary = review_candidate_coverage(
        case["source"], context, plan, reviewed(case["source"], context, plan), evidence
    )
    assert summary.pending_candidate_ids == ("candidate-3",)
    assert [item.status for item in summary.items] == [
        "physically_written_claim",
        "physically_written_claim",
        "pending",
    ]
    assert not summary.safe_to_report_all_candidates_complete


def test_provider_plan_cannot_smuggle_a_dangerous_unsupported_core_write(tmp_path: Path) -> None:
    """The opt-in barrier does not silently apply mappings to destructive operations."""
    case, context = _case("F11")
    plan = _two_items()
    unit = replace(plan.actions[0].units[0], intent="delete")
    destructive = RequestPlan((WriteAction((unit,)),), ())
    result, repo = _run(
        tmp_path,
        case["source"],
        context,
        destructive,
        lambda source, packet, exact_plan: build_candidate_coverage_manifest(
            source, packet, exact_plan, _claims((1, 0), (2, 1))
        ),
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert repo.list_markdown_paths() == []


def test_review_exception_is_closed_and_does_not_create_pending_or_markdown(tmp_path: Path) -> None:
    """A crashing evidence adapter cannot bypass the pre-mutation Core gate."""
    case, context = _case("F11")

    def broken_review(*_args):
        raise RuntimeError("synthetic adapter exception with untrusted details")

    result, repo = _run(tmp_path, case["source"], context, _two_items(), broken_review)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.action_results == ()
    assert repo.list_markdown_paths() == []
    assert not result.pending_work.persisted
    assert "untrusted details" not in str(result)


def test_complex_relational_core_write_stays_out_of_initial_pilot(tmp_path: Path) -> None:
    """A reference-bearing, identity-sensitive fact needs a stronger verified contract."""
    from odyssey_core.request_planning import KnowledgeReference

    case, context = _case("F11")
    unit = _two_items().actions[0].units[0]
    complex_unit = replace(unit, references=(KnowledgeReference(1, "person", "Eric"),))
    plan = RequestPlan((WriteAction((complex_unit,)),), ())
    result, repo = _run(
        tmp_path,
        case["source"],
        context,
        plan,
        lambda source, packet, exact_plan: build_candidate_coverage_manifest(
            source, packet, exact_plan, _claims((1, 0), (2, 1))
        ),
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert repo.list_markdown_paths() == []
