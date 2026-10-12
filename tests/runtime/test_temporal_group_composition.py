"""Temporal shared-clock gate: two dates verified, one clock used twice."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_core.request_planning import PlannerClarification
from odyssey_core.temporal_group_composition import compose_shared_clock_group
from odyssey_core.temporal_interpretation import (
    TemporalInterpreterError,
    parse_temporal_interpretation,
)
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault

SOURCE = next(case["source"] for case in CASES if case["id"] == "F21")
ARCHIVE = ROOT / "benchmarks/application_router/hybrid_grouped_v1/F21.json"


def original_payload():
    return json.loads(
        json.loads(ARCHIVE.read_text())["saved_genuine_provider_outputs"][0]["output_text"]
    )


def make_context():
    return compile_hybrid_candidate_bundle(RecordedRouter("F21").propose(SOURCE)).units[0].context


def interpret(payload=None, source=SOURCE):
    return parse_temporal_interpretation(
        original_payload() if payload is None else payload, source, timezone="Europe/Paris"
    )


def test_real_temporal_reply_gives_two_distinct_evening_instants():
    domain = compose_shared_clock_group(interpret(), make_context(), timezone="Europe/Paris")
    assert [(e.source_text, e.value) for e in domain.evidence] == [
        ("el lunes", "2026-10-05"),
        ("a las 18h", "2026-10-05T18:00:00+02:00"),
        ("el miércoles", "2026-10-07"),
        ("a las 18h", "2026-10-07T18:00:00+02:00"),
    ]


@pytest.mark.parametrize(
    "corrupt",
    [
        "wrong_weekday",
        "wrong_range",
        "duplicate_day",
        "time_not_exact_clock",
        "extra_unknown",
    ],
)
def test_temporal_shared_clock_rejects_ambiguous_or_conflicting_dates(corrupt):
    data = original_payload()
    if corrupt == "wrong_weekday":
        data["mentions"][1]["temporal"]["exact_date"] = "2026-10-06"
    elif corrupt == "wrong_range":
        data["mentions"][0]["temporal"]["range_end_exclusive"] = "2026-10-07"
    elif corrupt == "duplicate_day":
        data["mentions"][2]["temporal"]["exact_date"] = "2026-10-05"
    elif corrupt == "time_not_exact_clock":
        data["mentions"][3]["temporal_text"] = "18h"
    elif corrupt == "extra_unknown":
        data["mentions"].append(deepcopy(data["mentions"][-1]))
    with pytest.raises((TemporalInterpreterError, ValueError)):
        compose_shared_clock_group(interpret(data), make_context(), timezone="Europe/Paris")


def test_group_rejects_reassigned_clock_role():
    context = make_context()
    from odyssey_core.candidate_context import CoreCandidateRole, CoreSourceSpan

    wrong = tuple(
        CoreCandidateRole(
            role.role,
            CoreSourceSpan(
                "el miércoles",
                SOURCE.index("el miércoles"),
                SOURCE.index("el miércoles") + len("el miércoles"),
            )
            if role.role == "time"
            else role.span,
        )
        for role in context.candidates[1].roles
    )
    tampered = replace(
        context, candidates=(context.candidates[0], replace(context.candidates[1], roles=wrong))
    )
    with pytest.raises(TemporalInterpreterError):
        compose_shared_clock_group(interpret(), tampered, timezone="Europe/Paris")


def test_executor_reaches_core_after_real_model_temporal_reply(tmp_path):
    frozen = json.loads(ARCHIVE.read_text())
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    seen = []

    class Temporal:
        timezone = "Europe/Paris"

        def interpret(self, source):
            assert source == SOURCE
            return interpret(json.loads(frozen["saved_genuine_provider_outputs"][0]["output_text"]))

    def factory(hints, domain):
        assert domain is not None
        seen.append([(e.source_text, e.value) for e in domain.evidence])
        return SimpleNamespace(plan=lambda source: PlannerClarification("UNREPRESENTABLE_REQUEST"))

    result = execute_candidate_routed_message(
        SOURCE,
        router=RecordedRouter("F21"),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=lambda *_args: None,
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="F21-verified-shared-clock",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f21-clock-check",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert len(seen) == 1 and len(seen[0]) == 4, result.execution_flow
    assert result.status.value != "completed"
    assert all(repo.read_text(p) == content for p, content in before.items())
