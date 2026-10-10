"""Human-reviewed continuation plan -> existing Core linked writer, with v2 state.

All model/semantic plans are frozen fixtures. This is NOT proof that Luna can
produce the resumed plan, and no runtime path is activated by these tests.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_continuation_guard import build_selected_candidate_guard
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.temporal import TemporalAnchor
from tests.runtime.test_candidate_pending_state import NOW, _ready, _reply
from tests.runtime.test_temporal_user_path_e2e import (
    SCHEMA,
    _calendar,
    _linked_day_plan,
    _visible_day,
)


def _attempt(repo, vault, guard, plan, *, request_id="reply-1"):
    return execute_request(
        "Mañana iré al cine con él.",
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=vault,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="selected-pending-synthetic",
        now=guard.original_captured_at,
        context_limit=5,
        request_id_factory=lambda: request_id,
        write_preflight_guard=guard,
    )


def test_direct_reply_only_writes_pending_cinema_link_to_luis_in_disposable_vault(
    tmp_path: Path,
) -> None:
    preview, repo, vault, _state = _ready(tmp_path)
    initial = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    assert _reply(repo, vault, "Con Luis").outcome == "choice_recorded"
    guard = build_selected_candidate_guard(
        repo,
        conversation_id="chat-1",
        request_id=preview.request_id,
        vault=vault,
        schema=SCHEMA,
    )
    assert guard is not None and guard.selected_note_id == "luis-id"
    assert guard.original_captured_at == NOW
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Luis"
    )
    result = _attempt(repo, vault, guard, plan)
    assert result.status is ApplicationStatus.COMPLETED
    assert "date:2026-10-05" in result.affected_stable_note_ids
    # The ordinary write guard proves the selected canonical target at the
    # last moment; this source-ambiguous pronoun does not generate a separate
    # Core canonical-reference *handoff* proof (which needs a literal name).
    assert not result.canonical_reference_evidence
    assert all(vault.read_text(path) == content for path, content in initial.items())
    lines = _visible_day(_calendar(vault, tmp_path), "2026-10-05")
    assert any("Iré al cine con " in fact and "Luis" in fact for fact in lines)
    assert not any("Eric" in fact for fact in lines)
    # Core did write cinema, but the source candidate's semantic truth still
    # needs a model gate; the v2 pending record is not silently marked resolved.
    assert repo.read(preview.request_id)["status"] == "selected"


def test_wrong_selected_canonical_note_is_deferred_without_new_markdown(tmp_path: Path) -> None:
    preview, repo, vault, _ = _ready(tmp_path)
    assert _reply(repo, vault, "Con Luis").outcome == "choice_recorded"
    guard = build_selected_candidate_guard(
        repo, conversation_id="chat-1", request_id=preview.request_id, vault=vault, schema=SCHEMA
    )
    assert guard is not None
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Eric"
    )
    before = tuple(vault.list_markdown_paths())
    result = _attempt(repo, vault, guard, plan)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert not result.affected_stable_note_ids
    assert tuple(vault.list_markdown_paths()) == before


def test_changed_choice_guard_defers_after_staging_but_before_actual_write(tmp_path: Path) -> None:
    preview, repo, vault, _ = _ready(tmp_path)
    assert _reply(repo, vault, "Con Luis").outcome == "choice_recorded"
    guard = build_selected_candidate_guard(
        repo, conversation_id="chat-1", request_id=preview.request_id, vault=vault, schema=SCHEMA
    )
    assert guard is not None
    (vault.root / "Luis.md").write_text((vault.root / "Luis.md").read_text() + "\n")
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Luis"
    )
    result = _attempt(repo, vault, guard, plan)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert not (vault.root / "calendar" / "days" / "2026-10-05.md").exists()


def test_unverified_reference_word_is_not_accepted_even_if_selected_note_matches(
    tmp_path: Path,
) -> None:
    preview, repo, vault, _ = _ready(tmp_path)
    assert _reply(repo, vault, "Con Luis").outcome == "choice_recorded"
    guard = build_selected_candidate_guard(
        repo, conversation_id="chat-1", request_id=preview.request_id, vault=vault, schema=SCHEMA
    )
    assert guard is not None
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "Luis", "2026-10-05", target_name="Luis"
    )
    result = _attempt(repo, vault, guard, plan)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert not (vault.root / "calendar" / "days" / "2026-10-05.md").exists()


def test_cancellation_has_no_later_guard_or_continuation_write_authority(tmp_path: Path) -> None:
    preview, repo, vault, _ = _ready(tmp_path)
    assert _reply(repo, vault, "cancelar").outcome == "cancelled"
    assert (
        build_selected_candidate_guard(
            repo,
            conversation_id="chat-1",
            request_id=preview.request_id,
            vault=vault,
            schema=SCHEMA,
        )
        is None
    )


def test_unexpected_extra_write_unit_is_rejected_by_core_guard(tmp_path: Path) -> None:
    preview, repo, vault, _ = _ready(tmp_path)
    assert _reply(repo, vault, "Con Luis").outcome == "choice_recorded"
    guard = build_selected_candidate_guard(
        repo, conversation_id="chat-1", request_id=preview.request_id, vault=vault, schema=SCHEMA
    )
    assert guard is not None
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Luis"
    )
    action = plan.actions[0]
    excessive = RequestPlan(
        (WriteAction((*action.units, replace(action.units[1], target=action.units[1].target))),), ()
    )
    result = _attempt(repo, vault, guard, excessive)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert not (vault.root / "calendar" / "days" / "2026-10-05.md").exists()


@pytest.mark.parametrize(
    "unsafe",
    (
        "extra_second_write_action",
        "extra_second_retrieve_action",
        "wrong_day",
        "wrong_fact_date",
        "wrong_activity",
        "extra_fact",
        "extra_limitation",
        "invented_day_filter",
        "malformed_selected_source",
        "wrong_capture_time",
    ),
)
def test_selected_continuation_plan_is_rejected_before_any_write(
    tmp_path: Path, unsafe: str
) -> None:
    """One answer cannot grant authority to an extra action or wrong future fact."""
    preview, repo, vault, _ = _ready(tmp_path)
    assert _reply(repo, vault, "Con Luis").outcome == "choice_recorded"
    guard = build_selected_candidate_guard(
        repo,
        conversation_id="chat-1",
        request_id=preview.request_id,
        vault=vault,
        schema=SCHEMA,
    )
    assert guard is not None
    plan = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Luis"
    )
    action = plan.actions[0]
    day, helper = action.units
    if unsafe == "extra_second_write_action":
        plan = replace(plan, actions=(action, action))
    elif unsafe == "extra_second_retrieve_action":
        # A later unrelated action must not bypass the first safe write.
        from odyssey_core.request_planning import RetrieveAction

        plan = replace(plan, actions=(action, RetrieveAction(day.target)))
    elif unsafe == "wrong_day":
        day = replace(day, target=replace(day.target, query="2026-10-06"))
    elif unsafe == "wrong_fact_date":
        day = replace(day, fact_temporal_anchors=((TemporalAnchor("2026-10-06"),),))
    elif unsafe == "wrong_activity":
        day = replace(day, facts=("Iré al teatro con {{ref:0}}.",))
    elif unsafe == "extra_fact":
        day = replace(day, facts=(*day.facts, "Además compraré pan."))
    elif unsafe == "extra_limitation":
        plan = replace(plan, limitations=("some semantic uncertainty",))
    elif unsafe == "invented_day_filter":
        day = replace(day, target=replace(day.target, entity="Luis"))
    elif unsafe == "malformed_selected_source":
        guard = replace(guard, pending_source_text="Mañana iré al teatro con él")
    elif unsafe == "wrong_capture_time":
        guard = replace(guard, original_captured_at="2026-10-06T17:35:00+02:00")
    if unsafe in {
        "wrong_day",
        "wrong_fact_date",
        "wrong_activity",
        "extra_fact",
        "invented_day_filter",
    }:
        plan = replace(plan, actions=(WriteAction((day, helper)),))
    before = {str(path): vault.read_text(path) for path in vault.list_markdown_paths()}
    result = _attempt(repo, vault, guard, plan)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CANDIDATE_CONTINUATION_UNSAFE_PLAN"
    assert result.action_results == ()
    assert result.affected_stable_note_ids == ()
    assert not (vault.root / "calendar" / "days" / "2026-10-05.md").exists()
    assert {str(path): vault.read_text(path) for path in vault.list_markdown_paths()} == before
    assert repo.read(preview.request_id)["status"] == "selected"


def test_late_reply_still_uses_original_capture_date_not_late_clock(tmp_path: Path) -> None:
    """The original 'mañana' date stays pinned even when answered much later."""
    preview, repo, vault, _ = _ready(tmp_path)
    assert _reply(repo, vault, "Con Luis").outcome == "choice_recorded"
    guard = build_selected_candidate_guard(
        repo,
        conversation_id="chat-1",
        request_id=preview.request_id,
        vault=vault,
        schema=SCHEMA,
    )
    assert guard is not None
    original = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Luis"
    )
    completed = _attempt(repo, vault, guard, original, request_id="late-reply")
    assert completed.status is ApplicationStatus.COMPLETED
    assert "date:2026-10-05" in completed.affected_stable_note_ids
    assert "date:2026-10-11" not in completed.affected_stable_note_ids
