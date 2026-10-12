"""Shared negation/conditional interpretation as exactly one verbatim statement.

No link, no hypothetical-to-occurred mutation, no model output required.
The real Temporal provider reply is frozen from the earlier negative tests.
"""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, SelectionCriteria, WriteAction
from odyssey_core.temporal_interpretation import parse_temporal_interpretation
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault


def case_info(case_id):
    source = next(x["source"] for x in CASES if x["id"] == case_id)
    day = {"F17": "2026-10-03", "F20": "2026-10-10"}[case_id]
    item = json.loads(
        (ROOT / f"benchmarks/application_router/hybrid_sensitive_v1/{case_id}.json").read_text()
    )
    interpretation = parse_temporal_interpretation(
        json.loads(item["provider_outputs"][0]["output_text"]), source, timezone="Europe/Paris"
    )
    domain = interpretation.core_domain_interpretation()
    hint = compile_hybrid_candidate_bundle(RecordedRouter(case_id).propose(source)).units[0].context
    return source, day, interpretation, replace(hint, verified_sensitive_temporal=domain)


def full_literal_plan(source, day, **changes):
    target = SelectionCriteria(
        None, changes.get("target", day), changes.get("note_type", "calendar_day"), (), None
    )
    unit = KnowledgeUnit(
        target,
        "record",
        (),
        (),
        (changes.get("fact", source),),
        (),
    )
    return RequestPlan((WriteAction((unit,)),), ())


def claims():
    return tuple(
        CoreCandidateCoverageClaim(f"candidate-{i}", "planned_fact", fact_ordinals=(0,))
        for i in (1, 2)
    )


@pytest.mark.parametrize("case_id", ("F17", "F20"))
def test_n_to_one_sensitive_literal_has_independently_dated_source_scope(case_id):
    source, day, _interpret, context = case_info(case_id)
    manifest = build_candidate_coverage_manifest(
        source, context, full_literal_plan(source, day), claims()
    )
    assert len(manifest.claims) == 2
    assert all(x.fact_ordinals == (0,) for x in manifest.claims)


@pytest.mark.parametrize(
    "case_id,mutant",
    [
        ("F17", {"fact": "Ayer vi a Ana y a Luis."}),
        ("F17", {"fact": "Ayer no vi a Ana."}),
        ("F17", {"note_type": "person"}),
        ("F17", {"target": "2026-10-04"}),
        ("F20", {"fact": "El sábado iremos al cine y nos quedaremos en casa."}),
        ("F20", {"fact": "El sábado iremos al cine si llueve y nos quedaremos en casa."}),
        ("F20", {"target": "2026-10-11"}),
    ],
)
def test_unsafe_polarity_condition_or_target_cannot_write(case_id, mutant):
    source, day, _interpret, context = case_info(case_id)
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(
            source, context, full_literal_plan(source, day, **mutant), claims()
        )


@pytest.mark.parametrize("case_id", ("F17", "F20"))
def test_canonical_day_records_literal_statement_not_confirmed_events(case_id, tmp_path):
    source, day, interpretation, _context = case_info(case_id)
    repo, index, semantic, embedder = fresh_corpus_vault(tmp_path)
    prior = {p: repo.read_text(p) for p in repo.list_markdown_paths()}

    class Temporal:
        def interpret(self, fragment):
            assert fragment == source
            return interpretation

    def factory(hints, domain):
        assert hints.verified_sensitive_temporal is not None
        assert domain is not None
        return SimpleNamespace(plan=lambda _: full_literal_plan(source, day))

    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter(case_id),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=lambda src, ctx, plan: build_candidate_coverage_manifest(
            src, ctx, plan, claims()
        ),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="hybrid-sensitive-literal",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "sensitive-" + case_id,
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    text = repo.read_text("calendar/days/" + day + ".md")
    assert text.count(source) == 1
    assert "{{ref:" not in text
    added = set(repo.list_markdown_paths()) - prior.keys()
    assert added <= {"calendar/days/" + day + ".md", "calendar/days/2026-10-04.md"}
    assert "calendar/days/" + day + ".md" in added
