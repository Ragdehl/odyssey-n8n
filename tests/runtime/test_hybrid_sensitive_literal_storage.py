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
from odyssey_core.candidate_attribution import CandidateFactLinks, inspect_candidate_fact_graph
from odyssey_core.candidate_context import (
    CoreCandidate,
    CoreCandidateContext,
    CoreCandidateRole,
    CoreSourceSpan,
)
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


def _span(source, text, start=0):
    position = source.index(text, start)
    return CoreSourceSpan(text, position, position + len(text))


def _synthetic_sensitive_context(count, *, conditional=False):
    """Create source-provenanced N:1 literal evidence without Router semantics."""
    date_text = "2031-07-14"
    objects = tuple(f"item-{index}" for index in range(1, count + 1))
    if conditional:
        clauses = tuple(
            f"condition-{index} action-{index} {item}" for index, item in enumerate(objects, 1)
        )
        source = date_text + ": " + "; ".join(clauses) + "."
        candidates = tuple(
            CoreCandidate(
                f"candidate-{index}",
                "occurrence",
                "candidate",
                (_span(source, clause),),
                (
                    CoreCandidateRole("condition", _span(source, f"condition-{index}")),
                    CoreCandidateRole("predicate", _span(source, f"action-{index}")),
                    CoreCandidateRole("object", _span(source, item)),
                    CoreCandidateRole("date", _span(source, date_text)),
                ),
                (),
            )
            for index, (clause, item) in enumerate(zip(clauses, objects, strict=True), 1)
        )
    else:
        source = date_text + ": not observed " + ", ".join(objects) + "."
        candidates = tuple(
            CoreCandidate(
                f"candidate-{index}",
                "negative",
                "candidate",
                (_span(source, item),),
                (
                    CoreCandidateRole("polarity", _span(source, "not")),
                    CoreCandidateRole("predicate", _span(source, "observed")),
                    CoreCandidateRole("object", _span(source, item)),
                    CoreCandidateRole("date", _span(source, date_text)),
                ),
                (),
            )
            for index, item in enumerate(objects, 1)
        )
    domain = parse_temporal_interpretation(
        {
            "mentions": [
                {
                    "temporal_text": date_text,
                    "temporal": {
                        "kind": "EXACT_DATE",
                        "exact_date": date_text,
                        "exact_datetime": None,
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                }
            ]
        },
        source,
        timezone="Europe/Paris",
    ).core_domain_interpretation()
    return (
        source,
        date_text,
        CoreCandidateContext(
            source,
            candidates,
            scoped_route_source=True,
            hybrid_interpretation_mode=True,
            verified_sensitive_temporal=domain,
        ),
    )


@pytest.mark.parametrize("count", (1, 3, 5, 9))
@pytest.mark.parametrize("conditional", (False, True))
def test_sensitive_literal_n_to_one_accepts_variable_verified_candidate_counts(count, conditional):
    source, day, context = _synthetic_sensitive_context(count, conditional=conditional)
    plan = full_literal_plan(source, day)
    graph = inspect_candidate_fact_graph(
        source,
        context,
        plan,
        tuple(
            CandidateFactLinks(candidate.candidate_id, candidate.anchors[0].text, (0,))
            for candidate in context.candidates
        ),
    )
    manifest = build_candidate_coverage_manifest(
        source,
        context,
        plan,
        tuple(
            CoreCandidateCoverageClaim(candidate.candidate_id, "planned_fact", fact_ordinals=(0,))
            for candidate in context.candidates
        ),
    )
    assert graph.fact_count == 1
    assert len(manifest.claims) == count


@pytest.mark.parametrize(
    "mutation",
    ("wrong_type", "wrong_target", "partial_coverage", "mixed_polarity", "wrong_date"),
)
def test_sensitive_literal_n_to_one_rejects_adversarial_mutations(mutation):
    source, day, context = _synthetic_sensitive_context(3)
    plan = full_literal_plan(
        source,
        "2031-07-15" if mutation in {"wrong_target", "wrong_date"} else day,
        note_type="person" if mutation == "wrong_type" else "calendar_day",
    )
    if mutation == "mixed_polarity":
        context = replace(
            context,
            candidates=(replace(context.candidates[0], kind="occurrence"), *context.candidates[1:]),
        )
    claims = tuple(
        CoreCandidateCoverageClaim(candidate.candidate_id, "planned_fact", fact_ordinals=(0,))
        for candidate in context.candidates
    )
    if mutation == "partial_coverage":
        claims = claims[:-1]
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(source, context, plan, claims)


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
