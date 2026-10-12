"""F03: one exact grouped source, two events, no invented person membership."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_context import (
    CoreCandidate,
    CoreCandidateContext,
    CoreCandidateInheritance,
    CoreCandidateRole,
    CoreSourceSpan,
)
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.request_planning import (
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.temporal import TemporalAnchor
from odyssey_core.temporal_interpretation import parse_temporal_interpretation
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault

SOURCE = next(row["source"] for row in CASES if row["id"] == "F03")
CAPTURE = ROOT / "benchmarks/application_router/hybrid_grouped_v1/F03.json"
DAY = "2026-10-05"
VALID = ("Vamos con mis hijos de paseo al parque.", "Luego iremos al cine con mis hijos.")


def make_plan(facts=VALID):
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(None, DAY, "calendar_day", (), None),
                        "record",
                        (),
                        (),
                        facts,
                        (),
                        fact_temporal_anchors=tuple((TemporalAnchor(DAY),) for _ in facts),
                    ),
                )
            ),
        ),
        (),
    )


def coverage(source, context, plan, *, canonical_binding=None):
    return build_candidate_coverage_manifest(
        source,
        context,
        plan,
        tuple(
            CoreCandidateCoverageClaim(f"candidate-{i + 1}", "planned_fact", fact_ordinal=i)
            for i in range(2)
        ),
        canonical_binding=canonical_binding,
    )


def run(tmp_path, *, facts=VALID):
    source_response = json.loads(CAPTURE.read_text())["saved_genuine_provider_outputs"][0]
    resolved = parse_temporal_interpretation(
        json.loads(source_response["output_text"]), SOURCE, timezone="Europe/Paris"
    )

    class Temporal:
        def interpret(self, text):
            assert text == SOURCE
            return resolved

    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}

    def factory(hints, domain):
        assert len(hints.candidates) == 2
        assert domain.evidence[0].value == DAY
        return SimpleNamespace(plan=lambda source: make_plan(facts))

    result = execute_candidate_routed_message(
        SOURCE,
        router=RecordedRouter("F03"),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=coverage,
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="f03-hybrid-literal-group",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f03-hybrid-safe",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    return result, repo, before


def test_group_events_with_unresolved_children_can_be_written_literally(tmp_path):
    result, repo, _before = run(tmp_path)
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    day = repo.read_text(f"calendar/days/{DAY}.md")
    assert all(day.count(item) == 1 for item in VALID)
    assert "{{ref:" not in day
    assert "mis hijos" in day


@pytest.mark.parametrize("count", (1, 3, 5, 9))
def test_participant_literal_accepts_any_bounded_number_of_source_proven_events(count):
    """The ordinary candidate context budget, not an event count, bounds this gate."""
    participant = "the cohort"
    activities = (
        "orchid",
        "harbor",
        "quartz",
        "willow",
        "meadow",
        "summit",
        "cobalt",
        "fernery",
        "lantern",
    )[:count]
    source = participant + " completed " + "; ".join(activities) + "."

    def span(text):
        start = source.index(text)
        return CoreSourceSpan(text, start, start + len(text))

    candidates = tuple(
        CoreCandidate(
            f"candidate-{index}",
            "occurrence",
            "candidate",
            (span(activity),),
            (
                *((CoreCandidateRole("participants", span(participant)),) if index == 1 else ()),
                CoreCandidateRole("object", span(activity)),
            ),
            () if index == 1 else (CoreCandidateInheritance("participants", 1),),
        )
        for index, activity in enumerate(activities, 1)
    )
    context = CoreCandidateContext(source, candidates, scoped_route_source=True)
    facts = tuple(f"{participant} completed {activity}." for activity in activities)
    unit = KnowledgeUnit(
        SelectionCriteria(None, "2031-07-14", "calendar_day", (), None),
        "record",
        (),
        (),
        facts,
        (),
    )
    plan = RequestPlan((WriteAction((unit,)),), ())
    manifest = build_candidate_coverage_manifest(
        source,
        context,
        plan,
        tuple(
            CoreCandidateCoverageClaim(candidate.candidate_id, "planned_fact", fact_ordinal=index)
            for index, candidate in enumerate(candidates)
        ),
    )
    assert len(manifest.claims) == count


@pytest.mark.parametrize(
    "changed",
    [
        ("Vamos de paseo al parque.", "Luego iremos al cine con mis hijos."),
        ("Vamos con mis hijos de paseo al parque.", "Luego iremos al cine."),
        ("Vamos con mis hijos de paseo al cine.", "Luego iremos al parque con mis hijos."),
        ("Vamos con mis primos de paseo al parque.", "Luego iremos al cine con mis hijos."),
    ],
)
def test_lost_actor_wrong_participant_or_swapped_event_stays_unwritten(tmp_path, changed):
    result, repo, before = run(tmp_path, facts=changed)
    assert result.status is not ApplicationStatus.COMPLETED
    assert all(repo.read_text(path) == data for path, data in before.items())
