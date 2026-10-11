"""Full Router -> independent Temporal -> real GPT-5.6 parser -> normal Core Writer.

All SDK responses are provider-shaped deterministic test fixtures; the
original production-capable model adapters, Core application, candidate
prewrite review, Markdown Writer, and physical fact readback really execute.
The vault is a temporary isolated fixture, not DEV/PROD or personal notes.
No linguistic case-ID switches or fixed fact counts occur in implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.complete_source_handoff import (
    collect_complete_source_evidence,
    execute_complete_source_with_core,
)
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA


def _scenario(count: int):
    """N independent pieces of user knowledge, one shared source date."""
    objects = [f"item{chr(ord('a') + index)}" for index in range(count)]
    source = "Hoy " + "; ".join(f"compré {word}" for word in objects) + "."
    router_payload = {
        "version": 1,
        "units": [
            {
                "kind": "purchase_item",
                "anchors": [{"text": word, "occurrence": 0}],
                "scoped_source": [
                    {"role": "object", "anchor": {"text": word, "occurrence": 0}},
                    *(
                        [{"role": "date", "anchor": {"text": "Hoy", "occurrence": 0}}]
                        if index == 0
                        else []
                    ),
                ],
                "inheritance": [{"role": "date", "from_unit": 1}] if index else [],
                "state": "candidate",
            }
            for index, word in enumerate(objects)
        ],
    }
    # Genuine Core semantic PLAN parser/validator uses this unmodified
    # provider shape, not an independently written RequestPlan.
    core_payload = {
        "result": {
            "outcome": "PLAN",
            "actions": [
                {
                    "kind": "write",
                    "operations": [
                        {
                            "target": {
                                "description": "2026-10-04",
                                "binding": "described",
                                "direct_name": None,
                                "note_type": "calendar_day",
                                "filters": [],
                                "candidate_scope": None,
                            },
                            "apply_to": "one",
                            "intent": "record",
                            "facts": [
                                {"parts": [{"kind": "literal", "text": f"Compré {word}."}]}
                                for word in objects
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
    return source, objects, router_payload, core_payload


def _providers(source: str, router_payload: dict, core_payload: dict):
    router_fake, router_calls = _sdk_fake(router_payload)
    temporal_fake, temporal_calls = _sdk_fake({"mentions": [_exact_date("Hoy", "2026-10-04")]})
    core_fake, core_calls = _sdk_fake(core_payload)
    evidence = collect_complete_source_evidence(
        source,
        router=OpenAIFactCandidateRouter(router_fake, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(temporal_fake, CLOCK),
    )

    def factory(context, domain):
        return OpenAILunaExperimentalPlanner(
            core_fake,
            SCHEMA,
            CLOCK,
            candidate_context=context,
            domain_interpretation=domain,
        )

    return evidence, factory, (router_calls, temporal_calls, core_calls)


def _execute(evidence, planner_factory, reviewer, repo: VaultRepository, rid: str):
    return execute_complete_source_with_core(
        evidence,
        core_planner_factory=planner_factory,
        candidate_coverage_factory=reviewer,
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="isolated-multi-fact-core",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: rid,
    )


@pytest.mark.parametrize("count", [1, 2, 3, 5, 8, 13])
def test_actual_sdk_router_temporal_core_planner_writer_and_readback_end_to_end(
    count: int, tmp_path: Path
):
    source, objects, router_raw, core_raw = _scenario(count)
    evidence, factory, calls = _providers(source, router_raw, core_raw)
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")

    # In these deterministic fixtures an independently reviewed one-to-one
    # correspondence *happens* to be correct. This is external Core-reviewed
    # evidence, never a mapping inferred by the handoff or real Router.
    audited_plans = []

    def reviewed(original, context, plan):
        audited_plans.append(plan)
        claims = tuple(
            CoreCandidateCoverageClaim(f"candidate-{index + 1}", "planned_fact", index)
            for index in range(count)
        )
        return build_candidate_coverage_manifest(original, context, plan, claims)

    result = _execute(evidence, factory, reviewed, repo, f"complete-{count}")
    assert result.status is ApplicationStatus.COMPLETED
    assert len(result.action_results) == 1
    assert len(repo.list_markdown_paths()) == 1
    markdown = repo.read_text("calendar/days/2026-10-04.md")
    for index, word in enumerate(objects):
        assert markdown.count(f"Compré {word}.") == 1
        assert markdown.count(f"request=complete-{count} ordinal={index} recorded_at=") == 1

    # Original N candidates, ONE Core provider call and ONE Core WriteAction;
    # no hidden second planner, writer or per-candidate provider invocation.
    assert [len(call_list) for call_list in calls] == [1, 1, 1]
    assert calls[0][0]["input"][1]["content"] == source
    assert calls[1][0]["input"][1]["content"] == source
    assert calls[2][0]["input"][1]["content"] == source
    assert calls[2][0]["model"] == "gpt-5.6-luna"

    # Read authoritative physically persisted Core atomic markers, not
    # a claimed "done" from the Router, Core model or the fake SDK.
    assert len(audited_plans) == 1
    readback = readback_core_facts(source, evidence.context, audited_plans[0], result, repo, SCHEMA)
    assert len(readback.persisted_facts) == count
    assert all(fact.status == "verified_in_markdown" for fact in readback.persisted_facts)
    assert not readback.safe_to_report_all_candidates_complete
    assert len(calls[2]) == 1  # no second Core model call even for auditing


@pytest.mark.parametrize("count", [1, 3, 5])
def test_missing_core_coverage_review_refuses_every_write_before_materialization(
    count: int, tmp_path: Path
):
    source, _, router_raw, core_raw = _scenario(count)
    evidence, planner, calls = _providers(source, router_raw, core_raw)
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")
    with pytest.raises(ValueError, match="coverage review required"):
        _execute(evidence, planner, None, repo, f"no-coverage-{count}")
    assert len(calls[2]) == 0
    assert repo.list_markdown_paths() == []


@pytest.mark.parametrize("count", [3, 5])
def test_incomplete_or_forged_coverage_refuses_all_notes(count: int, tmp_path: Path):
    source, _, router_raw, core_raw = _scenario(count)
    evidence, planner, calls = _providers(source, router_raw, core_raw)
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")

    def incomplete(original, context, plan):
        claims = tuple(
            CoreCandidateCoverageClaim(f"candidate-{index + 1}", "planned_fact", index)
            for index in range(count - 1)
        )
        return build_candidate_coverage_manifest(original, context, plan, claims)

    result = _execute(evidence, planner, incomplete, repo, f"incomplete-{count}")
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
    assert result.action_results == ()
    assert repo.list_markdown_paths() == []
    assert [len(call_list) for call_list in calls] == [1, 1, 1]


def test_one_candidate_cannot_claim_three_facts_without_a_general_review(tmp_path):
    source, _, router_raw, core_raw = _scenario(3)
    # This tests many-facts-per-candidate *as a safe refusal*, not a
    # fictitious 'general coverage already solved' statement.
    router_raw["units"] = [router_raw["units"][0]]
    evidence, planner, _calls = _providers(source, router_raw, core_raw)
    (tmp_path / "vault").mkdir()
    repo = VaultRepository(tmp_path / "vault")

    def unsafe_claim(original, context, plan):
        return build_candidate_coverage_manifest(
            original,
            context,
            plan,
            (CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),),
        )

    result = _execute(evidence, planner, unsafe_claim, repo, "n-to-one-not-proven")
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert repo.list_markdown_paths() == []


def test_full_route_preserves_canonical_people_links_and_unresolved_reference(tmp_path):
    """One event with two distinct people, pending later pronoun, no false link.

    Uses unchanged Router, Temporal, semantic Core planner SDK decoders and
    ordinary Core Writer; this is a regression SENTINEL, not special routing.
    """
    from odyssey_core.candidate_coverage import CoreCandidateCoverageClaim
    from tests.apps.test_fact_candidates import CASES, _from_design
    from tests.runtime.test_fact_candidate_semantic_luna_vertical import (
        _raw_semantic_plan,
        _vault_with_people,
    )

    case = next(item for item in CASES if item["id"] == "F14")
    source = case["source"]
    router_fake, router_calls = _sdk_fake(_from_design(case))
    temporal_fake, temporal_calls = _sdk_fake(
        {
            "mentions": [
                _exact_date("Ayer", "2026-10-03"),
                _exact_date("Mañana", "2026-10-05"),
            ],
        }
    )
    core_fake, core_calls = _sdk_fake(_raw_semantic_plan())
    evidence = collect_complete_source_evidence(
        source,
        router=OpenAIFactCandidateRouter(router_fake, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(temporal_fake, CLOCK),
    )

    def planner_factory(context, domain):
        return OpenAILunaExperimentalPlanner(
            core_fake,
            SCHEMA,
            CLOCK,
            candidate_context=context,
            domain_interpretation=domain,
        )

    def reviewed(original, context, plan):
        return build_candidate_coverage_manifest(
            original,
            context,
            plan,
            (
                CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
                CoreCandidateCoverageClaim(
                    "candidate-2", "pending", pending_reason="ambiguous_identity"
                ),
            ),
        )

    repo = _vault_with_people(tmp_path)
    result = _execute(evidence, planner_factory, reviewed, repo, "linked-original")
    assert result.status is ApplicationStatus.PARTIAL
    assert {link.stable_note_id for link in result.canonical_reference_evidence} == {
        "eric-id",
        "luis-id",
    }
    written = repo.read_text("calendar/days/2026-10-03.md")
    assert "Hablé con [[Eric|Eric]] y [[Luis|Luis]]." in written
    assert "request=linked-original ordinal=0 recorded_at=" in written
    assert "Mañana" not in written and "cine" not in written
    assert [len(calls) for calls in (router_calls, temporal_calls, core_calls)] == [1, 1, 1]
