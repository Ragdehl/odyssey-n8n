"""A reviewed continuation reaches actual Core/E3 only with synthetic verdicts.

Experimental isolated seam, NOT called by RuntimeComposition and NOT fresh GPT.
Tests preserve the already-written day, resolve the chosen canonical identity,
and reject altered proposals before Core makes any physical mutation.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_continuation_context import (
    prepare_selected_candidate_continuation,
)
from odyssey_core.candidate_continuation_guard import ReviewedCandidateContinuationWriteGuard
from odyssey_core.candidate_continuation_plan import inspect_selected_candidate_plan
from odyssey_core.candidate_continuation_semantic import (
    validate_independent_continuation_verdict,
)
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_candidate_pending_state import _ready, _reply
from tests.runtime.test_temporal_user_path_e2e import (
    SCHEMA,
    _linked_day_plan,
)


def _prepared(tmp_path: Path, *, chosen_name: str = "Luis"):
    preview, pending, vault, _state = _ready(tmp_path)
    assert _reply(pending, vault, f"Con {chosen_name}").outcome == "choice_recorded"
    context = prepare_selected_candidate_continuation(
        pending,
        conversation_id="chat-1",
        request_id=preview.request_id,
        vault=vault,
        schema=SCHEMA,
    )
    plan = _linked_day_plan(
        "2026-10-05",
        "Iré al cine con {{ref:0}}.",
        "él",
        "2026-10-05",
        target_name=chosen_name,
    )
    inspected = inspect_selected_candidate_plan(context, plan)
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "kind": "record",
                "reviewed_text": "Iré al cine con {{ref:0}}.",
                "date": "2026-10-05",
                "reference_names": [chosen_name],
                "supported": True,
            }
        ],
    }
    verdict = validate_independent_continuation_verdict(context, inspected, review)
    guard = ReviewedCandidateContinuationWriteGuard(
        pending,
        context,
        inspected,
        verdict,
        review,
        plan,
        vault,
        SCHEMA,
    )
    return preview, pending, vault, context, plan, guard


def _execute(vault, context, plan, guard, *, request_id="continuation-test"):
    return execute_request(
        context.pending_source,
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=vault,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-continuation-only",
        now=context.captured_at,
        context_limit=5,
        request_id_factory=lambda: request_id,
        write_preflight_guard=guard,
    )


def test_synthetic_reviewed_plan_reaches_real_e3_with_one_selected_canonical_link(
    tmp_path: Path,
):
    preview, pending, vault, context, plan, guard = _prepared(tmp_path)
    prior = vault.read_text("calendar/days/2026-10-03.md")
    result = _execute(vault, context, plan, guard)
    assert result.status is ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("date:2026-10-05",)
    assert vault.read_text("calendar/days/2026-10-03.md") == prior
    today = vault.read_text("calendar/days/2026-10-05.md")
    assert today.count("Iré al cine con [[Luis|Luis]]") == 1
    assert "Eric" not in today
    # No completion transition is claimed without a durable E3 receipt/readback.
    assert pending.read(preview.request_id)["status"] == "selected"


@pytest.mark.parametrize(
    "changed",
    [
        "plan_fact",
        "extra_action",
        "selection",
        "existing_fact",
        "review",
        "wrong_vault",
    ],
)
def test_reviewed_continuation_rejects_drift_before_any_e3_write(tmp_path: Path, changed: str):
    preview, pending, vault, context, plan, guard = _prepared(tmp_path)
    before = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
    if changed == "plan_fact":
        writer, helper = plan.actions[0].units
        altered = replace(writer, facts=("Iré al teatro con {{ref:0}}.",))
        plan = RequestPlan((WriteAction((altered, helper)),), ())
    elif changed == "extra_action":
        plan = replace(plan, actions=(plan.actions[0], plan.actions[0]))
    elif changed == "selection":
        (vault.root / "Luis.md").write_text(
            (vault.root / "Luis.md").read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
    elif changed == "existing_fact":
        (vault.root / "calendar/days/2026-10-03.md").write_text(
            vault.read_text("calendar/days/2026-10-03.md").replace(
                "Hablé con Eric.", "Canté con Eric."
            ),
            encoding="utf-8",
        )
    elif changed == "review":
        guard.review["facts"][0]["date"] = "2026-10-06"
    elif changed == "wrong_vault":
        guard = replace(guard, _bound_vault=object())
    result = _execute(vault, context, plan, guard)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.affected_stable_note_ids == ()
    assert not (vault.root / "calendar/days/2026-10-05.md").exists()
    assert pending.read(preview.request_id)["status"] == "selected"
    if changed in {"plan_fact", "extra_action", "review", "wrong_vault"}:
        assert {p: vault.read_text(p) for p in before} == before


def test_multiple_pending_facts_share_one_canonical_selected_identity(tmp_path: Path):
    preview, pending, vault, context, plan, _guard = _prepared(tmp_path)
    first, helper = plan.actions[0].units
    expanded = replace(
        first,
        facts=("Iré al cine con {{ref:0}}.", "Iré al museo con {{ref:0}}."),
        fact_temporal_anchors=first.fact_temporal_anchors * 2,
    )
    plan = RequestPlan((WriteAction((expanded, helper)),), ())
    inspection = inspect_selected_candidate_plan(context, plan)
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": i,
                "kind": "record",
                "reviewed_text": fact,
                "date": "2026-10-05",
                "reference_names": ["Luis"],
                "supported": True,
            }
            for i, fact in enumerate(expanded.facts)
        ],
    }
    guard = ReviewedCandidateContinuationWriteGuard(
        pending,
        context,
        inspection,
        validate_independent_continuation_verdict(context, inspection, review),
        review,
        plan,
        vault,
        SCHEMA,
    )
    result = _execute(vault, context, plan, guard)
    assert result.status is ApplicationStatus.COMPLETED
    day = vault.read_text("calendar/days/2026-10-05.md")
    assert day.count("Iré al cine con [[Luis|Luis]]") == 1
    assert day.count("Iré al museo con [[Luis|Luis]]") == 1
    assert pending.read(preview.request_id)["status"] == "selected"


def test_replayed_core_delivery_does_not_duplicate_synthetic_continuation(tmp_path: Path):
    _preview, _pending, vault, context, plan, guard = _prepared(tmp_path)
    first = _execute(vault, context, plan, guard, request_id="same-synthetic-delivery")
    assert first.status is ApplicationStatus.COMPLETED
    second = _execute(vault, context, plan, guard, request_id="same-synthetic-delivery")
    third = _execute(vault, context, plan, guard, request_id="another-synthetic-delivery")
    day = vault.read_text("calendar/days/2026-10-05.md")
    assert day.count("Iré al cine con [[Luis|Luis]]") == 1
    assert second.status in {ApplicationStatus.COMPLETED, ApplicationStatus.NEEDS_ATTENTION}
    assert third.status in {ApplicationStatus.COMPLETED, ApplicationStatus.NEEDS_ATTENTION}


def test_reviewed_guard_reuses_canonical_preflight_for_another_identity(tmp_path: Path):
    """Do not implement the same source-reference proof with name-based branches."""
    _preview, _pending, vault, context, plan, guard = _prepared(tmp_path, chosen_name="Eric")
    outcome = _execute(vault, context, plan, guard, request_id="selected-other-identity")
    assert outcome.status is ApplicationStatus.COMPLETED
    day = vault.read_text("calendar/days/2026-10-05.md")
    assert day.count("Iré al cine con [[Eric|Eric]]") == 1
    assert "[[Luis|Luis]]" not in day
