"""Only-review continuation proposals: no planner or writer owns mutation here."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core.candidate_continuation_context import (
    prepare_selected_candidate_continuation,
)
from odyssey_core.candidate_continuation_plan import (
    CandidateContinuationPlanError,
    inspect_selected_candidate_plan,
)
from odyssey_core.request_planning import (
    KnowledgeReference,
    RequestPlan,
    RetrieveAction,
    WriteAction,
)
from tests.runtime.test_candidate_pending_state import _ready, _reply
from tests.runtime.test_temporal_user_path_e2e import (
    SCHEMA,
    _day_plan,
    _linked_day_plan,
)


def _ready_inspector(tmp_path: Path):
    preview, repo, vault, _state = _ready(tmp_path)
    assert _reply(repo, vault, "Con Luis").outcome == "choice_recorded"
    evidence = prepare_selected_candidate_continuation(
        repo,
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
        target_name="Luis",
    )
    return evidence, plan, vault


def test_source_exact_read_only_proposal_lists_only_pending_new_facts(tmp_path: Path):
    evidence, plan, vault = _ready_inspector(tmp_path)
    before = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
    inspected = inspect_selected_candidate_plan(evidence, plan)
    assert not inspected.may_execute
    assert inspected.source_digest == evidence.source_digest
    assert inspected.pending_record_digest == evidence.pending_record_digest
    assert inspected.captured_at == evidence.captured_at
    assert inspected.plan_digest and len(inspected.plan_digest) == 64
    assert inspected.selected_identity_reference_ordinals == (0,)
    assert [fact.text for fact in inspected.proposed_facts] == ["Iré al cine con {{ref:0}}."]
    reviewer = inspected.review_payload(evidence)
    assert reviewer["pending_source"] == "Mañana iré al cine con él"
    assert reviewer["already_written_fact_ordinals"] == [0, 1]
    assert reviewer["proposed_facts"][0]["temporal_values"] == ["2026-10-05"]
    assert reviewer["selected_identity_name"] == "Luis"
    assert "selected_note_id" not in reviewer
    assert "selected_identity_guard" not in reviewer
    assert "pending_record_digest" not in reviewer
    assert {p: vault.read_text(p) for p in vault.list_markdown_paths()} == before


def test_one_pending_candidate_can_propose_multiple_facts_without_extra_write(tmp_path: Path):
    evidence, plan, _vault = _ready_inspector(tmp_path)
    action = plan.actions[0]
    writer = action.units[0]
    expanded = replace(
        writer,
        facts=(
            "Iré al cine con {{ref:0}}.",
            "Visitaremos la exposición con {{ref:0}}.",
        ),
        fact_temporal_anchors=writer.fact_temporal_anchors * 2,
    )
    result = inspect_selected_candidate_plan(
        evidence, RequestPlan((WriteAction((expanded, action.units[1])),), ())
    )
    assert tuple(f.ordinal for f in result.proposed_facts) == (0, 1)
    assert result.selected_identity_reference_ordinals == (0, 1)
    assert not result.may_execute  # Semantic extra facts are NOT thereby justified.


@pytest.mark.parametrize(
    "mutation",
    [
        "no_reference",
        "wrong_name",
        "fake_mention",
        "fake_reference_target",
        "unreferenced_helper",
        "missing_ref_token",
        "rewrite",
        "extra_read",
    ],
)
def test_unexpected_or_unbound_continuation_plan_rejected(tmp_path: Path, mutation: str):
    evidence, plan, _vault = _ready_inspector(tmp_path)
    action = plan.actions[0]
    writer, helper = action.units
    if mutation == "no_reference":
        plan = _day_plan("2026-10-05", "Iré al cine con Luis.", "2026-10-05")
    elif mutation == "wrong_name":
        helper = replace(helper, target=replace(helper.target, entity="Eric"))
    elif mutation == "fake_mention":
        writer = replace(writer, references=(KnowledgeReference(1, "person", "Luis"),))
    elif mutation == "fake_reference_target":
        writer = replace(writer, references=(KnowledgeReference(0, "person", "él"),))
    elif mutation == "unreferenced_helper":
        plan = RequestPlan((WriteAction((writer, helper, helper)),), ())
    elif mutation == "missing_ref_token":
        writer = replace(writer, facts=("Iré al cine solo.",))
    elif mutation == "rewrite":
        writer = replace(writer, intent="amend")
    elif mutation == "extra_read":
        plan = RequestPlan((*plan.actions, RetrieveAction(writer.target)), ())
    if mutation in {
        "wrong_name",
        "fake_mention",
        "fake_reference_target",
        "missing_ref_token",
        "rewrite",
    }:
        plan = RequestPlan((WriteAction((writer, helper)),), ())
    with pytest.raises(CandidateContinuationPlanError):
        inspect_selected_candidate_plan(evidence, plan)


def test_plan_digest_rejects_one_fact_changed_after_review(tmp_path: Path):
    evidence, plan, _vault = _ready_inspector(tmp_path)
    inspected = inspect_selected_candidate_plan(evidence, plan)
    changed_evidence = replace(evidence, pending_record_digest="0" * 64)
    with pytest.raises(CandidateContinuationPlanError):
        inspected.review_payload(changed_evidence)
    altered_writer = replace(plan.actions[0].units[0], facts=("Me encontré con {{ref:0}}.",))
    changed_plan = RequestPlan((WriteAction((altered_writer, plan.actions[0].units[1])),), ())
    other = inspect_selected_candidate_plan(evidence, changed_plan)
    assert inspected.plan_digest != other.plan_digest
    assert other.selected_identity_reference_ordinals == (0,)
    assert not other.may_execute  # Hash binding is not semantic approval.


def test_existing_other_original_facts_are_not_reproposed(tmp_path: Path):
    evidence, plan, _vault = _ready_inspector(tmp_path)
    assert len(evidence.completed_facts) == 2
    proposals = inspect_selected_candidate_plan(evidence, plan).proposed_facts
    assert len(proposals) == 1
    assert not any("Hablé con" in fact.text for fact in proposals)


def test_exact_previous_fact_cannot_be_reintroduced_alongside_pending_fact(tmp_path: Path):
    evidence, plan, _vault = _ready_inspector(tmp_path)
    writer, helper = plan.actions[0].units
    duplicate = replace(
        writer,
        facts=("Hablé con Eric.", "Iré al cine con {{ref:0}}."),
        fact_temporal_anchors=writer.fact_temporal_anchors * 2,
    )
    with pytest.raises(CandidateContinuationPlanError, match="repeats previously"):
        inspect_selected_candidate_plan(
            evidence, RequestPlan((WriteAction((duplicate, helper)),), ())
        )


def test_wrong_relative_date_stays_non_executable_pending_independent_semantics(tmp_path: Path):
    evidence, plan, _vault = _ready_inspector(tmp_path)
    writer, helper = plan.actions[0].units
    mismatched = replace(
        writer,
        target=replace(writer.target, query="2026-10-07"),
    )
    inspected = inspect_selected_candidate_plan(
        evidence, RequestPlan((WriteAction((mismatched, helper)),), ())
    )
    assert inspected.proposed_facts[0].destination_query == "2026-10-07"
    assert not inspected.may_execute
    # Source/plan digest plus exact quote can validate integrity; ONLY the
    # next independent semantic review can reject a false day interpretation.


def test_current_plan_guard_rejects_changed_proposal_and_stale_identity(tmp_path: Path):
    from odyssey_core.candidate_continuation_plan import (
        validate_inspected_candidate_plan_current,
    )

    preview, repo, vault, _state = _ready(tmp_path)
    _reply(repo, vault, "Con Luis")
    context = prepare_selected_candidate_continuation(
        repo,
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
        target_name="Luis",
    )
    inspected = inspect_selected_candidate_plan(context, plan)
    validate_inspected_candidate_plan_current(
        inspected, context, plan, repo, vault=vault, schema=SCHEMA
    )
    writer, helper = plan.actions[0].units
    changed = RequestPlan(
        (WriteAction((replace(writer, facts=("Iré a otro lugar con {{ref:0}}.",)), helper)),), ()
    )
    with pytest.raises(CandidateContinuationPlanError):
        validate_inspected_candidate_plan_current(
            inspected, context, changed, repo, vault=vault, schema=SCHEMA
        )
    note = vault.root / "Luis.md"
    note.write_text(note.read_text(encoding="utf-8") + chr(10), encoding="utf-8")
    with pytest.raises(CandidateContinuationPlanError):
        validate_inspected_candidate_plan_current(
            inspected, context, plan, repo, vault=vault, schema=SCHEMA
        )


def test_current_plan_guard_rejects_modified_pending_record(tmp_path: Path):
    from odyssey_core.candidate_continuation_plan import (
        validate_inspected_candidate_plan_current,
    )

    preview, repo, vault, state = _ready(tmp_path)
    _reply(repo, vault, "Con Luis")
    context = prepare_selected_candidate_continuation(
        repo,
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
        target_name="Luis",
    )
    inspected = inspect_selected_candidate_plan(context, plan)
    record_path = state / "candidates" / (preview.request_id + ".json")
    import json

    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["original_request"] = record["original_request"].replace("cine", "casa")
    record["pending"][0]["text"] = record["pending"][0]["text"].replace("cine", "casa")
    record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CandidateContinuationPlanError):
        validate_inspected_candidate_plan_current(
            inspected, context, plan, repo, vault=vault, schema=SCHEMA
        )
