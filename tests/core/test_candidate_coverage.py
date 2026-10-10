"""Core candidate coverage is explicit, exhaustive, plan-bound and not semantic proof."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
    review_candidate_coverage,
    validate_candidate_coverage_manifest,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_fact_candidate_provenance_readback import _two_items
from tests.runtime.test_fact_candidate_writes_e2e import _case, _new_repo
from tests.runtime.test_temporal_user_path_e2e import SCHEMA, _core_with_plan, _day_plan


def _claim(candidate: int, fact: int) -> CoreCandidateCoverageClaim:
    return CoreCandidateCoverageClaim(f"candidate-{candidate}", "planned_fact", fact)


def _pending(candidate: int, reason: str) -> CoreCandidateCoverageClaim:
    return CoreCandidateCoverageClaim(f"candidate-{candidate}", "pending", pending_reason=reason)


def _three_day_plan() -> RequestPlan:
    day1 = _day_plan("2026-10-03", "Fuimos al parque.", "2026-10-03")
    day2 = _day_plan("2026-10-04", "Iremos a un concierto.", "2026-10-04")
    unit = day1.actions[0].units[0]
    first = replace(
        unit,
        facts=("Fuimos al parque.", "Después fuimos al cine."),
        fact_temporal_anchors=(unit.fact_temporal_anchors[0],) * 2,
    )
    return RequestPlan((WriteAction((first, day2.actions[0].units[0])),), ())


def test_three_fact_context_can_be_explicitly_accounted_without_inferring_by_order(
    tmp_path: Path,
) -> None:
    """A reviewed mapping and real Markdown confirm physical writes, not meaning."""
    case, context = _case("F01")
    repo = _new_repo(tmp_path)
    plan = _three_day_plan()
    manifest = build_candidate_coverage_manifest(
        case["source"], context, plan, (_claim(1, 0), _claim(2, 1), _claim(3, 2))
    )
    result = _core_with_plan(repo, case["source"], "f01-manifest", plan)
    physical = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    review = review_candidate_coverage(case["source"], context, plan, manifest, physical)
    assert len(review.items) == 3
    assert [x.status for x in review.items] == ["physically_written_claim"] * 3
    assert [x.fact_ordinal for x in review.items] == [0, 1, 2]
    assert review.pending_candidate_ids == ()
    assert review.fully_accounted_for_structurally
    assert not review.candidate_semantics_verified
    assert not review.safe_to_report_all_candidates_complete


def test_shared_purchase_maps_two_items_to_one_core_write_unit(tmp_path: Path) -> None:
    """Candidate count and Core write-unit count differ without losing source coverage."""
    case, context = _case("F11")
    repo = _new_repo(tmp_path)
    plan = _two_items()
    manifest = build_candidate_coverage_manifest(
        case["source"], context, plan, (_claim(1, 0), _claim(2, 1))
    )
    result = _core_with_plan(repo, case["source"], "f11-manifest", plan)
    readback = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    review = review_candidate_coverage(case["source"], context, plan, manifest, readback)
    assert len(result.action_results[0].unit_results) == 1
    assert [item.status for item in review.items] == ["physically_written_claim"] * 2
    assert len(repo.list_markdown_paths()) == 1


def test_ambiguous_pronoun_must_have_separate_pending_claim_even_if_core_completed(
    tmp_path: Path,
) -> None:
    """The two written Eric/Luis facts do not claim the independent 'él' proposal."""
    case, context = _case("F27")
    repo = _new_repo(tmp_path)
    original = _day_plan("2026-10-03", "Hablé con Eric.", "2026-10-03")
    unit = original.actions[0].units[0]
    safe = replace(
        unit,
        facts=("Hablé con Eric.", "Hablé con Luis."),
        fact_temporal_anchors=(unit.fact_temporal_anchors[0],) * 2,
    )
    plan = RequestPlan((WriteAction((safe,)),), ())
    manifest = build_candidate_coverage_manifest(
        case["source"],
        context,
        plan,
        (_claim(1, 0), _claim(2, 1), _pending(3, "ambiguous_identity")),
    )
    result = _core_with_plan(repo, case["source"], "f27-manifest", plan)
    readback = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    review = review_candidate_coverage(case["source"], context, plan, manifest, readback)
    assert readback.core_request_status == "completed"
    assert [item.status for item in review.items] == [
        "physically_written_claim",
        "physically_written_claim",
        "pending",
    ]
    assert review.pending_candidate_ids == ("candidate-3",)
    assert not review.safe_to_report_all_candidates_complete


@pytest.mark.parametrize(
    "bad",
    [
        (_claim(1, 0),),  # candidate missing
        (_claim(1, 0), _claim(1, 1)),  # duplicate candidate / missing candidate
        (_claim(1, 0), _claim(2, 0)),  # same fact credited to two source candidates
        (_claim(1, 0), _claim(2, 5)),  # fabricated fact ordinal
        (_claim(1, 0), _pending(2, "needs_clarification")),  # orphaned planned fact
        (_claim(1, 0), CoreCandidateCoverageClaim("candidate-2", "planned_fact", True)),
    ],
)
def test_invalid_coverage_fails_closed_before_any_markdown_write(
    tmp_path: Path, bad: tuple[CoreCandidateCoverageClaim, ...]
) -> None:
    """No omitted source candidate or unclaimed fact is allowed to write via the pilot."""
    case, context = _case("F11")
    repo = _new_repo(tmp_path)
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(case["source"], context, _two_items(), bad)
    assert repo.list_markdown_paths() == []


def test_stale_or_modified_core_plan_invalidates_previous_candidate_manifest() -> None:
    """A changed fact text, target or original request needs an entirely new review."""
    case, context = _case("F11")
    plan = _two_items()
    approved = build_candidate_coverage_manifest(
        case["source"], context, plan, (_claim(1, 0), _claim(2, 1))
    )
    units = plan.actions[0].units
    revised = replace(units[0], facts=("Compré pan.", "Regalé leche."))
    mutated = RequestPlan((WriteAction((revised,)),), ())
    with pytest.raises(ValueError, match="stale or mismatched"):
        validate_candidate_coverage_manifest(case["source"], context, mutated, approved)
    with pytest.raises(ValueError, match="full current source"):
        validate_candidate_coverage_manifest("An unrelated request", context, plan, approved)
    fake = replace(approved, source_digest="0" * 64)
    with pytest.raises(ValueError, match="stale or mismatched"):
        validate_candidate_coverage_manifest(case["source"], context, plan, fake)


def test_ambiguous_identity_may_not_be_declared_saved() -> None:
    case, context = _case("F27")
    plan = _three_day_plan()
    with pytest.raises(ValueError, match="Ambiguous identity"):
        build_candidate_coverage_manifest(
            case["source"], context, plan, (_claim(1, 0), _claim(2, 1), _claim(3, 2))
        )


def test_conditional_and_negative_claims_require_extra_semantic_proof() -> None:
    """Do not turn two hypothetical branches into completed events by count matching."""
    for case_id in ("F17", "F20"):
        case, context = _case(case_id)
        with pytest.raises(ValueError, match="Sensitive scoped"):
            build_candidate_coverage_manifest(
                case["source"], context, _two_items(), (_claim(1, 0), _claim(2, 1))
            )


def test_structural_coverage_may_not_be_promoted_on_missing_markdown_marker(tmp_path: Path) -> None:
    """Dedup by an earlier request is not physical persistence for the current one."""
    case, context = _case("F11")
    repo = _new_repo(tmp_path)
    plan = _two_items()
    manifest = build_candidate_coverage_manifest(
        case["source"], context, plan, (_claim(1, 0), _claim(2, 1))
    )
    _core_with_plan(repo, case["source"], "f11-original-claim", plan)
    second = _core_with_plan(repo, case["source"], "f11-new-claim", plan)
    readback = readback_core_facts(case["source"], context, plan, second, repo, SCHEMA)
    review = review_candidate_coverage(case["source"], context, plan, manifest, readback)
    assert [item.status for item in review.items] == ["planned_unverified"] * 2
    assert review.pending_candidate_ids == ("candidate-1", "candidate-2")
    assert not review.safe_to_report_all_candidates_complete


def test_pending_ambiguity_reason_cannot_be_applied_to_nonambiguous_candidate() -> None:
    """Only genuinely ambiguous source candidates may claim that pending reason."""
    case, context = _case("F27")
    with pytest.raises(ValueError, match="compatible unresolved reason"):
        build_candidate_coverage_manifest(
            case["source"],
            context,
            _two_items(),
            (_pending(1, "ambiguous_identity"), _claim(2, 0), _pending(3, "ambiguous_identity")),
        )


def test_ambiguous_candidate_cannot_hide_behind_generic_pending_reason() -> None:
    case, context = _case("F27")
    with pytest.raises(ValueError, match="compatible unresolved reason"):
        build_candidate_coverage_manifest(
            case["source"],
            context,
            _two_items(),
            (_claim(1, 0), _claim(2, 1), _pending(3, "needs_capability")),
        )


def test_untyped_mapping_shape_is_not_accepted_as_core_evidence() -> None:
    case, context = _case("F11")
    with pytest.raises(ValueError, match="typed Core"):
        build_candidate_coverage_manifest(
            case["source"],
            context,
            _two_items(),
            (
                {"candidate_id": "candidate-1", "disposition": "planned_fact", "fact_ordinal": 0},
                _claim(2, 1),
            ),
        )


def test_swapped_claim_is_blocked_before_any_write(tmp_path: Path) -> None:
    """Even a manually reviewed pan→leche mapping lacks source evidence."""
    case, context = _case("F11")
    repo = _new_repo(tmp_path)
    with pytest.raises(ValueError, match="distinctive original source evidence"):
        build_candidate_coverage_manifest(
            case["source"], context, _two_items(), (_claim(1, 1), _claim(2, 0))
        )
    assert repo.list_markdown_paths() == []


def test_sensitive_source_can_only_be_marked_pending_in_this_pilot() -> None:
    """Negated alternatives require a later model-backed semantic coverage gate."""
    case, context = _case("F20")
    from odyssey_core.request_planning import RequestPlan

    empty = RequestPlan((), ())
    manifest = build_candidate_coverage_manifest(
        case["source"],
        context,
        empty,
        (_pending(1, "unsupported_scope"), _pending(2, "unsupported_scope")),
    )
    assert len(manifest.claims) == 2
    with pytest.raises(ValueError, match="Sensitive scoped"):
        build_candidate_coverage_manifest(
            case["source"], context, _two_items(), (_claim(1, 0), _claim(2, 1))
        )
