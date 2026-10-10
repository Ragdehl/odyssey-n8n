"""Real Core semantic compilation with fake model outputs and pending Temporal.

Router and Luna providers are deterministic fakes; the Core compiler, coverage
preflight, Markdown writer, fact readback, and pending store are real on tmp_path.
This is NOT a paid live-model gate nor a model-generated semantic correctness proof.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_attribution import validate_candidate_attribution
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.clarification import ClarificationOption
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan, RequestPlanningError
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.apps.test_fact_candidates import CASES, _from_design
from tests.core.test_candidate_attribution import _f14_group
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_multi_participant_event import _vault_with_people
from tests.runtime.test_temporal_user_path_e2e import SCHEMA

CLOCK = {"date": "2026-10-04", "time": "17:35", "timezone": "Europe/Paris"}


def _raw_semantic_plan() -> dict:
    """Provider-shaped semantic WRITE, NOT a hand-authored Core RequestPlan."""

    def person(name: str) -> dict:
        return {
            "description": name,
            "binding": "described",
            "direct_name": name,
            "note_type": "person",
            "filters": [],
            "candidate_scope": None,
        }

    return {
        "result": {
            "outcome": "PLAN",
            "actions": [
                {
                    "kind": "write",
                    "operations": [
                        {
                            "target": {
                                "description": "2026-10-03",
                                "binding": "described",
                                "direct_name": None,
                                "note_type": "calendar_day",
                                "filters": [],
                                "candidate_scope": None,
                            },
                            "apply_to": "one",
                            "intent": "record",
                            "facts": [
                                {
                                    "parts": [
                                        {"kind": "literal", "text": "Hablé con "},
                                        {
                                            "kind": "identity",
                                            "text": "Eric",
                                            "identity": person("Eric"),
                                        },
                                        {"kind": "literal", "text": " y "},
                                        {
                                            "kind": "identity",
                                            "text": "Luis",
                                            "identity": person("Luis"),
                                        },
                                        {"kind": "literal", "text": "."},
                                    ]
                                }
                            ],
                            "properties": [],
                            "tag_changes": [],
                            "destination_type": None,
                        }
                    ],
                }
            ],
            "limitations": [],
            "clarification_code": None,
            "presentation_intent": "answer",
        }
    }


def _pipeline(model_result: dict | None = None):
    """Pass unchanged source through real Router/Temporal adapters and Luna compiler."""
    case = next(item for item in CASES if item["id"] == "F14")
    router_fake, router_calls = _sdk_fake(_from_design(case))
    router = OpenAIFactCandidateRouter(router_fake)
    proposed = router.propose(case["source"])
    temporal_fake, temporal_calls = _sdk_fake(
        {
            "mentions": [
                _exact_date("Ayer", "2026-10-03"),
                _exact_date("Mañana", "2026-10-05"),
            ]
        }
    )
    temporal = OpenAITemporalInterpreter(temporal_fake, CLOCK).interpret(case["source"])
    scope = bind_temporal_to_fact_candidates(proposed, temporal)
    context = to_core_candidate_context(proposed)
    plan_fake, plan_calls = _sdk_fake(model_result or _raw_semantic_plan())
    planner = OpenAILunaExperimentalPlanner(
        plan_fake,
        SCHEMA,
        CLOCK,
        domain_interpretation=temporal.core_domain_interpretation(),
        candidate_context=context,
    )
    return case, context, scope, planner, (router_calls, temporal_calls, plan_calls)


def test_actual_semantic_compiler_can_leave_pending_future_date_without_faking_plan() -> None:
    """Temporal's future mention belongs to unplanned pronoun, not missing saved fact."""
    case, context, scope, planner, calls = _pipeline()
    assert [(x.candidate_id, x.role, x.resolution.exact_date) for x in scope] == [
        ("candidate-1", "date", "2026-10-03"),
        ("candidate-2", "date", "2026-10-05"),
    ]
    plan = planner.plan(case["source"])
    assert isinstance(plan, RequestPlan)
    assert len(plan.actions) == 1
    assert len(plan.actions[0].units) == 3
    day, eric, luis = plan.actions[0].units
    assert day.target.query == "2026-10-03"
    assert day.facts == ("Hablé con {{ref:0}} y {{ref:1}}.",)
    assert [(r.mention, r.role) for r in day.references] == [
        ("Eric", "identity"),
        ("Luis", "identity"),
    ]
    assert eric.reference_lookup_only and luis.reference_lookup_only
    assert [x.value for x in day.fact_temporal_anchors[0]] == ["2026-10-03"]
    assert all(len(x) == 1 and x[0]["store"] is False for x in calls)
    assert calls[2][0]["model"] == "gpt-5.6-luna"


def test_same_model_plan_fails_closed_without_pending_candidate_source_proof() -> None:
    """The old full Temporal evidence validator remains strict by default."""
    case, context, _scope, _planner, _calls = _pipeline()
    data = _raw_semantic_plan()
    domain = DomainInterpretation(
        "temporal",
        case["source"],
        "TEMPORAL_RESOLUTION",
        (
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Ayer", "2026-10-03"),
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Mañana", "2026-10-05"),
        ),
    )
    fake, calls = _sdk_fake(data)
    with pytest.raises(RequestPlanningError, match="omitted required temporal"):
        OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=domain).plan(
            case["source"]
        )
    assert len(calls) == 1
    # A context marked nonambiguous cannot omit an independently needed date.
    altered = replace(
        context,
        candidates=(
            context.candidates[0],
            replace(context.candidates[1], state="candidate"),
        ),
    )
    fake2, calls2 = _sdk_fake(data)
    with pytest.raises(RequestPlanningError, match="omitted required temporal"):
        OpenAILunaExperimentalPlanner(
            fake2, SCHEMA, CLOCK, domain_interpretation=domain, candidate_context=altered
        ).plan(case["source"])
    assert len(calls2) == 1


def test_real_compiled_plan_crosses_core_pending_markdown_and_reference_guards(
    tmp_path: Path,
) -> None:
    """Provider-shaped Luna payload compiles, then Core writes exactly one linked fact."""
    case, context, _scope, planner, _calls = _pipeline()
    real_plan = planner.plan(case["source"])
    repo = _vault_with_people(tmp_path)
    manifest = build_candidate_coverage_manifest(
        case["source"],
        context,
        real_plan,
        (
            CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
            CoreCandidateCoverageClaim(
                "candidate-2", "pending", pending_reason="ambiguous_identity"
            ),
        ),
    )
    state = tmp_path / "state" / "pending"
    state.mkdir(parents=True)
    pending = CandidatePendingRepository(state)

    def record(preview):
        return pending.record(
            preview,
            conversation_id="chat-compiler",
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
        planner=SimpleNamespace(plan=lambda _: real_plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="experimental-compiler",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "semantic-compiled",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
        candidate_pending_recorder=record,
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.pending_work.persisted
    assert [(e.source_mention, e.stable_note_id) for e in result.canonical_reference_evidence] == [
        ("Eric", "eric-id"),
        ("Luis", "luis-id"),
    ]
    fact = repo.read_text("calendar/days/2026-10-03.md")
    assert "Hablé con [[Eric|Eric]] y [[Luis|Luis]]." in fact
    assert "Mañana" not in fact and "cine" not in fact
    receipts = readback_core_facts(case["source"], context, real_plan, result, repo, SCHEMA)
    assert [(r.status, r.note_id) for r in receipts.persisted_facts] == [
        ("verified_in_markdown", "date:2026-10-03"),
    ]
    assert pending.read(result.request_id)["pending"][0]["reference_text"] == "él"


def test_read_only_core_attribution_accepts_actual_semantic_compiler_shape() -> None:
    """One compiled Core fact with two identity roles can only be an untrusted claim."""
    case, context, _scope, planner, _calls = _pipeline()
    real_plan = planner.plan(case["source"])
    _source, _ctx, _manual_plan, reviewed = _f14_group()
    claim = validate_candidate_attribution(case["source"], context, real_plan, reviewed)
    assert claim.candidates[0].fact_ordinal == 0
    assert claim.candidates[1].pending_reason == "ambiguous_identity"
    assert not claim.may_authorize_writes and not claim.semantically_verified


def test_wrong_day_target_cannot_hide_required_safe_past_temporal_scope() -> None:
    """An ambiguous future day does not authorize moving the past fact to tomorrow."""
    case, context, _scope, _planner, _calls = _pipeline()
    model = _raw_semantic_plan()
    model["result"]["actions"][0]["operations"][0]["target"]["description"] = "2026-10-05"
    domain = DomainInterpretation(
        "temporal",
        case["source"],
        "TEMPORAL_RESOLUTION",
        (
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Ayer", "2026-10-03"),
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Mañana", "2026-10-05"),
        ),
    )
    fake, calls = _sdk_fake(model)
    with pytest.raises(RequestPlanningError, match="omitted required temporal"):
        OpenAILunaExperimentalPlanner(
            fake,
            SCHEMA,
            CLOCK,
            candidate_context=context,
            domain_interpretation=domain,
        ).plan(case["source"])
    assert len(calls) == 1


def test_repeated_temporal_literal_is_not_assigned_to_unproven_source_candidate() -> None:
    """Text-only Temporal mentions are ambiguous across duplicate occurrences."""
    case, context, _scope, _planner, _calls = _pipeline()
    amended_source = case["source"] + " Mañana también quizá vuelva."
    # The old span offsets remain honest for this exact prefix, but Temporal
    # returns only the shared literal: no occurrence can be distinguished.
    adjusted = replace(context, source=amended_source)
    domain = DomainInterpretation(
        "temporal",
        amended_source,
        "TEMPORAL_RESOLUTION",
        (
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Ayer", "2026-10-03"),
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Mañana", "2026-10-05"),
        ),
    )
    fake, calls = _sdk_fake(_raw_semantic_plan())
    with pytest.raises(RequestPlanningError, match="omitted required temporal"):
        OpenAILunaExperimentalPlanner(
            fake,
            SCHEMA,
            CLOCK,
            candidate_context=adjusted,
            domain_interpretation=domain,
        ).plan(amended_source)
    assert len(calls) == 1


def test_ambiguity_without_original_date_scope_cannot_bypass_temporal_guard() -> None:
    """A Router state flag alone is insufficient without the precise role span."""
    case, context, _scope, _planner, _calls = _pipeline()
    altered = replace(
        context,
        candidates=(
            context.candidates[0],
            replace(
                context.candidates[1],
                roles=tuple(r for r in context.candidates[1].roles if r.role != "date"),
            ),
        ),
    )
    domain = DomainInterpretation(
        "temporal",
        case["source"],
        "TEMPORAL_RESOLUTION",
        (
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Ayer", "2026-10-03"),
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Mañana", "2026-10-05"),
        ),
    )
    fake, calls = _sdk_fake(_raw_semantic_plan())
    with pytest.raises(RequestPlanningError, match="omitted required temporal"):
        OpenAILunaExperimentalPlanner(
            fake,
            SCHEMA,
            CLOCK,
            candidate_context=altered,
            domain_interpretation=domain,
        ).plan(case["source"])
    assert len(calls) == 1


def test_real_compiled_plan_does_not_write_without_independent_core_candidate_review(
    tmp_path: Path,
) -> None:
    """A model-valid PLAN is never itself permission to bypass source coverage."""
    case, context, _scope, planner, _calls = _pipeline()
    plan = planner.plan(case["source"])
    repo = _vault_with_people(tmp_path)
    before = tuple(repo.list_markdown_paths())
    with pytest.raises(ValueError, match="requires both Core context and review factory"):
        execute_request(
            case["source"],
            planner=SimpleNamespace(plan=lambda _: plan),
            repository=repo,
            schema=SCHEMA,
            context_index=object(),
            semantic_index=object(),
            embedder=object(),
            contextual_reasoner=object(),
            actor="unreviewed-candidate",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "model-unreviewed",
            candidate_context=context,
        )
    assert tuple(repo.list_markdown_paths()) == before


def test_real_compiled_plan_with_unreviewed_candidate_mapping_writes_nothing(
    tmp_path: Path,
) -> None:
    """Unsupported model mapping still returns attention before canonical mutation."""
    case, context, _scope, planner, _calls = _pipeline()
    plan = planner.plan(case["source"])
    repo = _vault_with_people(tmp_path)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    result = execute_request(
        case["source"],
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="unreviewed-coverage",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "model-missing-coverage",
        candidate_context=context,
        candidate_coverage_factory=lambda *_args: None,
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
