"""E2 complete source→Router→Temporal→one Core reviewer→Writer same-day path.

Simulates a safely grouped unknown relationship with two separate facts. Only
original source spans and exact dates are evidence; no model or PROD access.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from odyssey_apps.fact_candidates import validate_semantic_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.composition import _persistence_actor
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_generic_candidate_source_relations import proposal, quote, unit
from tests.runtime.test_temporal_user_path_e2e import _day_plan

SOURCE = "Hoy por la tarde llamé a Bea y hoy por la noche vi a Marta."
DAY = "2026-10-15"
TIMES = ("Hoy por la tarde", "hoy por la noche")
FACTS = ("Llamé a Bea.", "Vi a Marta.")


class Router:
    def propose(self, message):
        assert message == SOURCE
        first = unit(SOURCE, "Hoy por la tarde llamé a Bea", predicate="llamé", date=TIMES[0])
        second = unit(SOURCE, "hoy por la noche vi a Marta", predicate="vi", date=TIMES[1])
        for row, _temporal, daypart, person in (
            (first, TIMES[0], "por la tarde", "Bea"),
            (second, TIMES[1], "por la noche", "Marta"),
        ):
            row["scoped_source"].extend(
                [
                    {"role": "time_approx", "anchor": quote(daypart)},
                    {"role": "participants", "anchor": quote(person)},
                ]
            )
        return validate_semantic_fact_candidate_proposal(
            SOURCE,
            proposal(
                SOURCE,
                [first, second],
                [
                    ("independent_assertion", 0),
                    ("unresolved", 1),
                ],
            ),
        )


class Temporal:
    timezone = "Europe/Paris"

    def interpret(self, message):
        assert message == SOURCE
        return TemporalInterpretation(
            message,
            tuple(
                TemporalMention(
                    text, TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date=DAY)
                )
                for text in TIMES
            ),
        )


class PlannerFactory:
    def __init__(self):
        self.contexts = []

    def create_for_context(self, context):
        self.contexts.append(context)
        assert [q.qualifier for q in context.qualitative_times] == ["por la tarde", "por la noche"]
        first = _day_plan(DAY, FACTS[0], DAY)
        unit = first.actions[0].units[0]
        planned = replace(
            first,
            actions=(
                replace(
                    first.actions[0],
                    units=(
                        replace(
                            unit, facts=FACTS, fact_temporal_anchors=unit.fact_temporal_anchors * 2
                        ),
                    ),
                ),
            ),
        )
        return SimpleNamespace(plan=lambda text: planned)


def _execute(tmp_path, swapped=False):
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    router = Router()
    bundle = compile_hybrid_candidate_bundle(router.propose(SOURCE))
    assert len(bundle.units) == 1
    assert len(bundle.units[0].context.candidates) == 2
    quote_parts = [item.anchors[0].text for item in bundle.units[0].context.candidates]
    order = [1, 0] if swapped else [0, 1]
    payload = {
        "candidates": [
            {
                "candidate_id": f"candidate-{i + 1}",
                "source_quote": quote_parts[i],
                "fact_ordinals": [order[i]],
                "planned_fact_texts": [FACTS[order[i]]],
                "pending_reason": None,
            }
            for i in (0, 1)
        ]
    }
    sdk, calls = _sdk_fake(payload)
    factory = PlannerFactory()
    result = execute_candidate_routed_message(
        SOURCE,
        router=router,
        temporal=Temporal(),
        core_planner_factory=factory,
        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor=_persistence_actor("same-day-hybrid", None),
        now="2026-10-15T09:00:00+02:00",
        context_limit=5,
        request_id_factory=lambda: "same-day-hybrid",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    return result, repo, calls, factory


def test_whole_same_day_hybrid_uses_existing_review_once_and_physical_writer(tmp_path):
    result, repo, calls, factory = _execute(tmp_path)
    assert result.status is ApplicationStatus.COMPLETED, (
        result.planning_error,
        result.clarification_code,
    )
    assert len(calls) == 1
    assert len(factory.contexts) == 1
    markdown = repo.read_text(f"calendar/days/{DAY}.md")
    assert "Llamé a Bea (por la tarde)." in markdown
    assert "Vi a Marta (por la noche)." in markdown
    assert "15:00" not in markdown and "21:00" not in markdown
    assert result.execution_flow["routes"][0]["status"] == "completed"


def test_full_hybrid_wrong_fact_owner_fails_before_any_day_write(tmp_path):
    result, repo, calls, _factory = _execute(tmp_path, swapped=True)
    assert len(calls) == 1
    assert result.status in {ApplicationStatus.NEEDS_ATTENTION, ApplicationStatus.FAILED}
    assert f"calendar/days/{DAY}.md" not in repo.list_markdown_paths()
