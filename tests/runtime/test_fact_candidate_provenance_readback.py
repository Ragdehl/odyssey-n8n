"""Proof from persisted Core Markdown markers, not inferred candidate write order."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_fact_candidate_writes_e2e import _case, _new_repo
from tests.runtime.test_temporal_user_path_e2e import (
    SCHEMA,
    _core_with_plan,
    _day_plan,
)


def _two_items():
    """Represent the existing Core plan grouping two items into one purchase day."""
    original = _day_plan("2026-10-04", "Compré pan.", "2026-10-04")
    unit = original.actions[0].units[0]
    return RequestPlan(
        (
            WriteAction(
                (
                    replace(
                        unit,
                        facts=("Compré pan.", "Compré leche."),
                        fact_temporal_anchors=(unit.fact_temporal_anchors[0],) * 2,
                    ),
                )
            ),
        ),
        (),
    )


def test_two_persisted_items_are_proven_by_real_request_and_ordinal_markers(tmp_path: Path) -> None:
    """Exact persisted evidence for both facts is distinct from unproven source coverage."""
    case, context = _case("F11")
    repo = _new_repo(tmp_path)
    plan = _two_items()
    first = _core_with_plan(repo, case["source"], "f11-readback-1", plan)
    evidence = readback_core_facts(case["source"], context, plan, first, repo, SCHEMA)
    assert [f.status for f in evidence.persisted_facts] == ["verified_in_markdown"] * 2
    assert [f.ordinal for f in evidence.persisted_facts] == [0, 1]
    assert [f.note_id for f in evidence.persisted_facts] == ["date:2026-10-04"] * 2
    assert evidence.candidate_ids == ("candidate-1", "candidate-2")
    assert evidence.candidate_coverage == "unverified"
    assert evidence.safe_to_report_all_candidates_complete is False
    assert evidence.unresolved_candidate_ids == ()
    assert [(c.candidate_id, c.status) for c in evidence.candidate_progress] == [
        ("candidate-1", "unproven"),
        ("candidate-2", "unproven"),
    ]

    # Replaying identical request ID/ordinals should not create a second fact.
    replay = _core_with_plan(repo, case["source"], "f11-readback-1", plan)
    again = readback_core_facts(case["source"], context, plan, replay, repo, SCHEMA)
    assert [f.status for f in again.persisted_facts] == ["verified_in_markdown"] * 2
    assert len(repo.list_markdown_paths()) == 1


def test_deduplicated_text_from_earlier_request_is_not_falsely_attributed_to_new_one(
    tmp_path: Path,
) -> None:
    """A note existing with equal text cannot prove different request's materialization."""
    case, context = _case("F11")
    repo = _new_repo(tmp_path)
    plan = _two_items()
    first = _core_with_plan(repo, case["source"], "f11-original", plan)
    assert first.affected_stable_note_ids
    second = _core_with_plan(repo, case["source"], "f11-other-request", plan)
    readback = readback_core_facts(case["source"], context, plan, second, repo, SCHEMA)
    assert all(f.status == "not_verified" for f in readback.persisted_facts)
    assert readback.safe_to_report_all_candidates_complete is False


def test_marker_corruption_or_duplicate_note_id_blocks_false_physical_proof(
    tmp_path: Path,
) -> None:
    """Modified fact marker and ambiguous stable identities must never confirm completion."""
    case, context = _case("F11")
    repo = _new_repo(tmp_path)
    plan = _two_items()
    result = _core_with_plan(repo, case["source"], "f11-corruption", plan)
    [path] = repo.list_markdown_paths()
    absolute = repo.root / path
    original = absolute.read_text(encoding="utf-8")
    duplicate = repo.root / "alternate.md"
    duplicate.write_text(original, encoding="utf-8")
    ambiguous = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    assert all(f.status == "not_verified" for f in ambiguous.persisted_facts)
    duplicate.unlink()

    # The second ordinal has the wrong request ID even though its text is intact.
    absolute.write_text(
        original.replace("request=f11-corruption ordinal=1", "request=forged-other ordinal=1"),
        encoding="utf-8",
    )
    changed = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    assert [f.status for f in changed.persisted_facts] == ["verified_in_markdown", "not_verified"]
    assert changed.safe_to_report_all_candidates_complete is False


def test_two_safe_facts_do_not_resolve_an_ambiguous_third_candidate(tmp_path: Path) -> None:
    """Markdown proves Eric/Luis facts, but 'él' remains unresolved and unattributed."""
    case, context = _case("F27")
    repo = _new_repo(tmp_path)
    one = _day_plan("2026-10-03", "Hablé con Eric.", "2026-10-03")
    unit = one.actions[0].units[0]
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
    result = _core_with_plan(repo, case["source"], "f27-partial-readback", plan)
    physical = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    assert [fact.status for fact in physical.persisted_facts] == ["verified_in_markdown"] * 2
    assert physical.unresolved_candidate_ids == ("candidate-3",)
    assert [(c.candidate_id, c.status) for c in physical.candidate_progress] == [
        ("candidate-1", "unproven"),
        ("candidate-2", "unproven"),
        ("candidate-3", "ambiguous_identity"),
    ]
    assert physical.candidate_ids == ("candidate-1", "candidate-2", "candidate-3")
    assert physical.core_request_status == "completed"
    assert physical.safe_to_report_all_candidates_complete is False


def test_corrupt_core_action_receipts_fail_before_reading_vault(tmp_path: Path) -> None:
    """Forged action indices cannot be used to obtain physical write provenance."""
    case, context = _case("F11")
    repo = _new_repo(tmp_path)
    plan = _two_items()
    result = _core_with_plan(repo, case["source"], "f11-readback-bad", plan)
    fake_action = replace(result.action_results[0], action_index=42)
    with pytest.raises(ValueError, match="does not correspond"):
        readback_core_facts(
            case["source"],
            context,
            plan,
            replace(result, action_results=(fake_action,)),
            repo,
            SCHEMA,
        )


def test_three_facts_across_two_days_have_distinct_verified_core_ordinals(
    tmp_path: Path,
) -> None:
    """Shared date/participants do not merge different physical fact locators."""
    case, context = _case("F01")
    repo = _new_repo(tmp_path)
    day = _day_plan("2026-10-03", "Fuimos al parque con los niños.", "2026-10-03")
    first = day.actions[0].units[0]
    first = replace(
        first,
        facts=("Fuimos al parque con los niños.", "Después fuimos al cine."),
        fact_temporal_anchors=(first.fact_temporal_anchors[0],) * 2,
    )
    other = _day_plan("2026-10-04", "Hoy iremos a un concierto.", "2026-10-04")
    plan = RequestPlan((WriteAction((first, other.actions[0].units[0])),), ())
    result = _core_with_plan(repo, case["source"], "f01-readback", plan)
    receipts = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    assert [(fact.ordinal, fact.status, fact.note_id) for fact in receipts.persisted_facts] == [
        (0, "verified_in_markdown", "date:2026-10-03"),
        (1, "verified_in_markdown", "date:2026-10-03"),
        (2, "verified_in_markdown", "date:2026-10-04"),
    ]
    assert receipts.candidate_coverage == "unverified"
    assert not receipts.safe_to_report_all_candidates_complete
