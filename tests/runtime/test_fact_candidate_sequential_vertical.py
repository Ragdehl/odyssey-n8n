"""F27: explicitly sequential contacts stay separate with canonical backlinks.

Uses frozen provider-shaped fakes and actual Core semantic compiler, canonical
Markdown writer/readback, durable candidate pending and guarded continuation.
This is NOT a real provider-model acceptance test or production deployment.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_attribution import (
    CandidateAttributionError,
    validate_candidate_attribution,
)
from odyssey_core.candidate_continuation_guard import build_selected_candidate_guard
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.clarification import ClarificationOption
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.apps.test_fact_candidates import CASES, _from_design
from tests.core.test_candidate_attribution import _match, _pending
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, _raw_semantic_plan
from tests.runtime.test_fact_multi_participant_event import _notes, _vault_with_people
from tests.runtime.test_temporal_user_path_e2e import SCHEMA, _linked_day_plan


def _model_payload() -> dict:
    """One provider-shaped Core semantic write, with two independently linked facts."""
    raw = _raw_semantic_plan()
    parts = raw["result"]["actions"][0]["operations"][0]["facts"][0]["parts"]
    raw["result"]["actions"][0]["operations"][0]["facts"] = [
        {"parts": [parts[0], parts[1], parts[4]]},
        {"parts": [{"kind": "literal", "text": "Después hablé con "}, parts[3], parts[4]]},
    ]
    return raw


def _pipeline():
    """Compile the exact F27 source through existing adapters without networking."""
    case = next(c for c in CASES if c["id"] == "F27")
    fake_router, calls_router = _sdk_fake(_from_design(case))
    candidate = OpenAIFactCandidateRouter(fake_router).propose(case["source"])
    context = to_core_candidate_context(candidate)
    fake_temporal, calls_temporal = _sdk_fake(
        {"mentions": [_exact_date("Ayer", "2026-10-03"), _exact_date("Mañana", "2026-10-05")]}
    )
    temporal = OpenAITemporalInterpreter(fake_temporal, CLOCK).interpret(case["source"])
    fake_planner, calls_planner = _sdk_fake(_model_payload())
    plan = OpenAILunaExperimentalPlanner(
        fake_planner,
        SCHEMA,
        CLOCK,
        domain_interpretation=temporal.core_domain_interpretation(),
        candidate_context=context,
    ).plan(case["source"])
    assert isinstance(plan, RequestPlan)
    assert [x[0]["store"] for x in (calls_router, calls_temporal, calls_planner)] == [
        False,
        False,
        False,
    ]
    return case, context, plan


def _claims():
    return (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
        CoreCandidateCoverageClaim("candidate-2", "planned_fact", 1),
        CoreCandidateCoverageClaim("candidate-3", "pending", pending_reason="ambiguous_identity"),
    )


def _attribution():
    return {
        "candidates": [
            _match(1, "Eric", 0, "Hablé con {{ref:0}}."),
            _match(2, "Luis", 1, "Después hablé con {{ref:1}}."),
            _pending(3, "Mañana iré al cine con él", "ambiguous_identity"),
        ]
    }


def test_f27_compiler_yields_two_distinct_atomic_facts_and_ambiguity() -> None:
    """A source-explicit 'después' never collapses into one conversation fact."""
    case, context, plan = _pipeline()
    assert len(context.candidates) == 3
    assert len(plan.actions) == 1
    day, eric, luis = plan.actions[0].units
    assert day.facts == ("Hablé con {{ref:0}}.", "Después hablé con {{ref:1}}.")
    assert day.target.query == "2026-10-03"
    assert [tuple(x.value for x in anchors) for anchors in day.fact_temporal_anchors] == [
        ("2026-10-03",),
        ("2026-10-03",),
    ]
    assert [r.mention for r in day.references] == ["Eric", "Luis"]
    assert eric.reference_lookup_only and luis.reference_lookup_only
    assert build_candidate_coverage_manifest(case["source"], context, plan, _claims())
    proposed = validate_candidate_attribution(case["source"], context, plan, _attribution())
    assert len(proposed.candidates) == 3
    assert not proposed.semantically_verified and not proposed.may_authorize_writes


def test_f27_real_core_writes_two_linked_facts_with_one_pending_ambiguous_future(
    tmp_path: Path,
) -> None:
    """Both facts physically exist and both canonical people get backlinks."""
    case, context, plan = _pipeline()
    repo = _vault_with_people(tmp_path)
    manifest = build_candidate_coverage_manifest(case["source"], context, plan, _claims())
    state = tmp_path / "state" / "pending"
    state.mkdir(parents=True)
    pending = CandidatePendingRepository(state)

    def record(preview):
        return pending.record(
            preview,
            conversation_id="f27-sequence",
            created_at=NOW,
            options=(
                ClarificationOption("eric-id", "Eric"),
                ClarificationOption("luis-id", "Luis"),
            ),
            vault=repo,
            schema=SCHEMA,
        )

    result = execute_request(
        case["source"],
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-f27",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f27-source",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
        candidate_pending_recorder=record,
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.pending_work.persisted
    assert [(x.source_mention, x.stable_note_id) for x in result.canonical_reference_evidence] == [
        ("Eric", "eric-id"),
        ("Luis", "luis-id"),
    ]
    text = repo.read_text("calendar/days/2026-10-03.md")
    assert "Hablé con [[Eric|Eric]]." in text
    assert "Después hablé con [[Luis|Luis]]." in text
    assert "cine" not in text
    assert text.count("<!-- odyssey:fact request=f27-source ordinal=") == 2
    evidence = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    assert [(x.ordinal, x.status) for x in evidence.persisted_facts] == [
        (0, "verified_in_markdown"),
        (1, "verified_in_markdown"),
    ]
    assert pending.read("f27-source")["physically_verified_fact_count"] == 2
    notes = _notes(repo, tmp_path)
    for name in ("eric-id", "luis-id"):
        assert any(item.source.id == "date:2026-10-03" for item in notes.backlinks(name).items)
    answer = pending.reply(
        conversation_id="f27-sequence",
        reply="Con Luis",
        answer_id="f27-answer",
        vault=repo,
        schema=SCHEMA,
        immediate_followup=True,
    )
    assert answer.outcome == "choice_recorded" and answer.selected_note_id == "luis-id"
    guard = build_selected_candidate_guard(
        pending,
        conversation_id="f27-sequence",
        request_id=result.request_id,
        vault=repo,
        schema=SCHEMA,
    )
    assert guard is not None
    original = text
    follow = _linked_day_plan(
        "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Luis"
    )
    second = execute_request(
        "Mañana iré al cine con él.",
        planner=SimpleNamespace(plan=lambda _: follow),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-f27",
        now=guard.original_captured_at,
        context_limit=5,
        request_id_factory=lambda: "f27-answer",
        write_preflight_guard=guard,
    )
    assert second.status is ApplicationStatus.COMPLETED
    assert repo.read_text("calendar/days/2026-10-03.md") == original
    assert "Iré al cine con [[Luis|Luis]]." in repo.read_text("calendar/days/2026-10-05.md")
    assert pending.read("f27-source")["status"] == "selected"


@pytest.mark.parametrize(
    "mutation",
    (
        "swap_refs",
        "swap_facts",
        "drop_ref",
        "duplicate_helper",
        "change_date",
        "nonsequential_source",
    ),
)
def test_f27_fails_before_writes_on_wrong_identity_or_source_mapping(
    tmp_path: Path, mutation: str
) -> None:
    """Source order, independent event facts and exact references are required."""
    case, context, plan = _pipeline()
    action = plan.actions[0]
    day, eric, luis = action.units
    helpers = (eric, luis)
    if mutation == "swap_refs":
        day = replace(day, references=tuple(reversed(day.references)))
    elif mutation == "swap_facts":
        day = replace(day, facts=tuple(reversed(day.facts)))
    elif mutation == "drop_ref":
        day = replace(day, references=day.references[:1])
    elif mutation == "duplicate_helper":
        helpers = (*helpers, luis)
    elif mutation == "change_date":
        day = replace(day, fact_temporal_anchors=(day.fact_temporal_anchors[0], ()))
    else:
        revised = case["source"].replace(" y después con ", " y con ")
        context = replace(context, source=revised)
        case = {**case, "source": revised}
    altered = RequestPlan((WriteAction((day, *helpers)),), ())
    repo = _vault_with_people(tmp_path)
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(case["source"], context, altered, _claims())
    assert not (repo.root / "calendar/days/2026-10-03.md").exists()


def test_f27_wrong_model_attribution_order_is_not_write_authority() -> None:
    """A model cannot reassign Eric's fact to Luis even if text is exact."""
    case, context, plan = _pipeline()
    corrupted = json.loads(json.dumps(_attribution()))
    corrupted["candidates"][0]["fact_ordinal"] = 1
    corrupted["candidates"][0]["planned_fact_text"] = "Después hablé con {{ref:1}}."
    with pytest.raises(CandidateAttributionError):
        validate_candidate_attribution(case["source"], context, plan, corrupted)


def test_f27_rejects_a_pending_pronoun_without_exact_reference_role() -> None:
    """The source-only ambiguity flag cannot cover a missing unanchored 'él'."""
    case, context, plan = _pipeline()
    future = context.candidates[2]
    changed = replace(
        context,
        candidates=(
            *context.candidates[:2],
            replace(future, roles=tuple(r for r in future.roles if r.role != "reference")),
        ),
    )
    with pytest.raises(ValueError, match="Future reference ambiguity"):
        build_candidate_coverage_manifest(case["source"], changed, plan, _claims())


def test_f27_tampering_any_link_invalidates_both_shared_day_guards(tmp_path: Path) -> None:
    """A modified Day invalidates both source-note content guards (fail closed)."""
    case, context, plan = _pipeline()
    repo = _vault_with_people(tmp_path)
    manifest = build_candidate_coverage_manifest(case["source"], context, plan, _claims())
    result = execute_request(
        case["source"],
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="f27-guard-test",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f27-tamper",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
    )
    assert result.status is ApplicationStatus.PARTIAL
    path = repo.root / "calendar/days/2026-10-03.md"
    original = path.read_text()
    assert "Después hablé con [[Luis|Luis]]." in original
    path.write_text(original.replace("[[Luis|Luis]]", "[[Eric|Luis]]"), encoding="utf-8")
    receipts = readback_core_facts(case["source"], context, plan, result, repo, SCHEMA)
    assert [(item.ordinal, item.status) for item in receipts.persisted_facts] == [
        (0, "not_verified"),
        (1, "not_verified"),
    ]
