"""Disposable Markdown proof and cautious receipt tracking for Router v1 candidates.

The Core plans are synthetic and deliberately injected after independent source
validation. This is NOT proof that the provider can produce them or that a live
candidate->write mapping exists; canonical mutation uses only existing Core.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_write_observation import observe_candidate_write_outcomes
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.storage import VaultRepository
from tests.apps.test_fact_candidates import CASES, _from_design
from tests.runtime.test_temporal_user_path_e2e import (
    _calendar,
    _core_with_plan,
    _day_plan,
    _visible_day,
)


def _case(case_id: str):
    """Return original design case and independently validated Core source context."""
    case = next(value for value in CASES if value["id"] == case_id)
    proposal = validate_fact_candidate_proposal(case["source"], _from_design(case))
    return case, to_core_candidate_context(proposal)


def _new_repo(tmp_path: Path) -> VaultRepository:
    """Create an empty disposable Markdown vault with no production paths."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return VaultRepository(vault)


def test_f01_three_activity_facts_write_to_only_two_real_disposable_day_notes(
    tmp_path: Path,
) -> None:
    """One park+cinema day and a different concert day, preserving context by Core."""
    case, context = _case("F01")
    repository = _new_repo(tmp_path)
    day1 = _day_plan(
        "2026-10-03",
        "Fuimos con mi mujer y mis hijos al parque a las tres por la tarde.",
        "2026-10-03",
    )
    day2 = _day_plan(
        "2026-10-04", "Hoy vamos a ir a un concierto con mi mujer y mis hijos.", "2026-10-04"
    )
    first = day1.actions[0].units[0]
    # The second fact has the same inherited date, but NO inherited 15:00 hour.
    first = replace(
        first,
        facts=(*first.facts, "Después fuimos al cine con mi mujer y mis hijos."),
        fact_temporal_anchors=(
            (first.fact_temporal_anchors[0][0],),
            (first.fact_temporal_anchors[0][0],),
        ),
    )
    plan = RequestPlan((WriteAction((first, day2.actions[0].units[0])),), ())
    result = _core_with_plan(repository, case["source"], "test-f01", plan)
    receipt = observe_candidate_write_outcomes(case["source"], context, plan, result)

    assert result.status is ApplicationStatus.COMPLETED
    assert set(result.affected_stable_note_ids) == {"date:2026-10-03", "date:2026-10-04"}
    assert receipt.core_request_status == "completed"
    assert receipt.candidate_ids == ("candidate-1", "candidate-2", "candidate-3")
    assert receipt.attribution_status == "unattributed"  # not 1:1 with Core write units
    assert [(w.status, w.fact_ordinals) for w in receipt.observed_core_write_units] == [
        ("succeeded", (0, 1)),
        ("succeeded", (2,)),
    ]
    assert len(repository.list_markdown_paths()) == 2
    calendar = _calendar(repository, tmp_path)
    yesterday = _visible_day(calendar, "2026-10-03")
    today = _visible_day(calendar, "2026-10-04")
    assert any("Fuimos con mi mujer y mis hijos al parque" in item for item in yesterday)
    assert any("Después fuimos al cine" in item for item in yesterday)
    assert not any("tres por la tarde" in item for item in today)
    assert any("Hoy vamos a ir a un concierto" in item for item in today)


def test_f11_two_purchase_items_reuse_one_disposable_day_note_and_replay_deduplicates(
    tmp_path: Path,
) -> None:
    """Two item-level facts are NOT two canonical purchases or duplicate notes."""
    case, context = _case("F11")
    repository = _new_repo(tmp_path)
    one_day = _day_plan("2026-10-04", "Compré pan.", "2026-10-04")
    unit = one_day.actions[0].units[0]
    unit = replace(
        unit,
        facts=("Compré pan.", "Compré leche."),
        fact_temporal_anchors=(
            (unit.fact_temporal_anchors[0][0],),
            (unit.fact_temporal_anchors[0][0],),
        ),
    )
    plan = RequestPlan((WriteAction((unit,)),), ())
    first = _core_with_plan(repository, case["source"], "f11-same-logical-request", plan)
    second = _core_with_plan(repository, case["source"], "f11-same-logical-request", plan)
    receipts = [
        observe_candidate_write_outcomes(case["source"], context, plan, r) for r in (first, second)
    ]
    assert first.status is ApplicationStatus.COMPLETED
    assert second.status is ApplicationStatus.COMPLETED
    assert len(repository.list_markdown_paths()) == 1
    assert receipts[0].observed_core_write_units[0].fact_ordinals == (0, 1)
    assert receipts[1].attribution_status == "unattributed"
    calendar = _calendar(repository, tmp_path)
    facts = _visible_day(calendar, "2026-10-04")
    assert sum("Compré pan." in fact for fact in facts) == 1
    assert sum("Compré leche." in fact for fact in facts) == 1


def test_f27_separate_conversations_independent_writes_do_not_falsely_verify_ambiguous_third_candidate(
    tmp_path: Path,
) -> None:
    """Core results cannot claim a pronoun was saved just because other units succeeded."""
    case, context = _case("F27")
    repository = _new_repo(tmp_path)
    day = _day_plan("2026-10-03", "Hablé con Eric.", "2026-10-03")
    unit = day.actions[0].units[0]
    unit = replace(
        unit,
        facts=("Hablé con Eric.", "Hablé con Luis."),
        fact_temporal_anchors=(
            (unit.fact_temporal_anchors[0][0],),
            (unit.fact_temporal_anchors[0][0],),
        ),
    )
    plan = RequestPlan((WriteAction((unit,)),), ())
    result = _core_with_plan(repository, case["source"], "test-f27-safe-only", plan)
    observation = observe_candidate_write_outcomes(case["source"], context, plan, result)
    assert result.status is ApplicationStatus.COMPLETED
    assert observation.ambiguous_candidate_ids == ("candidate-3",)
    assert observation.attribution_status == "unattributed"
    assert observation.observed_core_write_units[0].status == "succeeded"
    notes = _visible_day(_calendar(repository, tmp_path), "2026-10-03")
    assert any("Hablé con Eric." in fact for fact in notes)
    assert any("Hablé con Luis." in fact for fact in notes)
    assert not any("cine" in fact or "él" in fact for fact in notes)
    # Still NOT an accepted product partial-success flow: the current Core
    # request result says 'completed', so explicit per-candidate pending-work
    # reconciliation remains mandatory before enabling Router v1.


def test_write_observation_fails_closed_on_unmatched_action_or_duplicate_unit_receipts(
    tmp_path: Path,
) -> None:
    """Never assign one Core receipt twice or misrepresent an unrelated plan result."""
    case, context = _case("F11")
    repository = _new_repo(tmp_path)
    plan = _day_plan("2026-10-04", "Compré pan.", "2026-10-04")
    result = _core_with_plan(repository, case["source"], "test-write-audit", plan)
    wrong_result = replace(result, action_results=())
    with pytest.raises(ValueError, match="actions differ"):
        observe_candidate_write_outcomes(case["source"], context, plan, wrong_result)
    action = result.action_results[0]
    if action.unit_results:
        duplicate = replace(action, unit_results=(*action.unit_results, action.unit_results[0]))
        with pytest.raises(ValueError, match="uniquely correlated"):
            observe_candidate_write_outcomes(
                case["source"],
                context,
                plan,
                replace(result, action_results=(duplicate,)),
            )
    with pytest.raises(ValueError, match="full current source"):
        observe_candidate_write_outcomes("A different request", context, plan, result)


def test_missing_core_unit_receipt_is_not_reported_as_a_success(tmp_path: Path) -> None:
    """No result entry cannot be converted into a completed candidate or unit."""
    case, context = _case("F11")
    repo = _new_repo(tmp_path)
    plan = _day_plan("2026-10-04", "Compré pan.", "2026-10-04")
    confirmed = _core_with_plan(repo, case["source"], "test-missing-result", plan)
    missing_units = replace(
        confirmed,
        action_results=(replace(confirmed.action_results[0], unit_results=()),),
    )
    observation = observe_candidate_write_outcomes(case["source"], context, plan, missing_units)
    assert observation.observed_core_write_units[0].status == "not_observed"
    assert observation.attribution_status == "unattributed"
    mismatched = replace(
        confirmed,
        action_results=(replace(confirmed.action_results[0], kind="retrieve"),),
    )
    with pytest.raises(ValueError, match="does not correspond"):
        observe_candidate_write_outcomes(case["source"], context, plan, mismatched)


def test_conditional_or_correction_candidate_is_never_an_executable_route_on_its_own(
    tmp_path: Path,
) -> None:
    """Parsing F19/F20 must not quietly materialize their alternative intentions."""
    repository = _new_repo(tmp_path)
    for case_id in ("F19", "F20"):
        case, context = _case(case_id)
        assert len(context.candidates) == len(case["expected_units"])
        assert all(
            candidate.kind in {"plan", "conditional", "occurrence"}
            for candidate in context.candidates
        )
        assert not hasattr(context, "execute")
    assert repository.list_markdown_paths() == []
