"""Signed clauses retain separate polarity and require independently proven time."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from odyssey_runtime.scoped_temporal_handoff import ScopedTemporalHandoff
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter, _source_temporal
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_hybrid_sensitive_literal_storage import full_literal_plan
from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan

SOURCE = next(item["source"] for item in CASES if item["id"] == "F18")
DAY = "2026-10-03"


def _router_without_date_evidence():
    """Adversarial proposal that drops the positive candidate's exact date role."""
    original = RecordedRouter("F18").propose(SOURCE)
    positive = original.candidates[1]
    return replace(
        original,
        candidates=(
            original.candidates[0],
            replace(
                positive,
                scopes=tuple(role for role in positive.scopes if role.role != "date"),
            ),
        ),
    )


def test_mixed_polarity_date_is_only_shared_when_explicitly_proven():
    verified = compile_hybrid_candidate_bundle(RecordedRouter("F18").propose(SOURCE))
    missing = compile_hybrid_candidate_bundle(_router_without_date_evidence())
    assert len(verified.units) == len(missing.units) == 2
    assert [item.context.candidates[0].kind for item in verified.units] == [
        "negative",
        "occurrence",
    ]
    assert not missing.units[1].context.source_provenance
    assert [(role.role, role.text) for role in verified.units[1].context.source_provenance] == [
        ("date", "Ayer")
    ]
    assert all(role.role != "polarity" for role in verified.units[1].context.source_provenance)

    first, second = verified.units
    handoff = ScopedTemporalHandoff(SOURCE)
    assert not handoff.inherited(
        second.context,
        current_route_index=1,
        start=second.original_start,
        end=second.original_end,
    )
    handoff.remember(
        _source_temporal(first.context.source),
        route_index=0,
        start=first.original_start,
        end=first.original_end,
    )
    inherited = handoff.inherited(
        second.context,
        current_route_index=1,
        start=second.original_start,
        end=second.original_end,
    )
    assert [(item.source_text, item.value) for item in inherited] == [("Ayer", DAY)]


def test_negative_literal_and_positive_link_write_independently_with_verified_date(tmp_path):
    proposal = RecordedRouter("F18").propose(SOURCE)
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    planner_calls = []

    class Router:
        def propose(self, source):
            assert source == SOURCE
            return proposal

    class Temporal:
        def interpret(self, source):
            assert source == "Ayer no vi a Ana"
            return _source_temporal(source)

    def factory(context, domain):
        planner_calls.append((context, domain))
        if context.candidates[0].kind == "negative":
            assert context.verified_sensitive_temporal is not None
            assert domain is not None
            return SimpleNamespace(plan=lambda source: full_literal_plan(source, DAY))
        assert context.candidates[0].kind == "occurrence"
        assert not any(role.role == "polarity" for role in context.candidates[0].roles)
        assert domain is not None and len(domain.inherited_temporal) == 1
        assert domain.inherited_temporal[0].source_text == "Ayer"
        return SimpleNamespace(
            plan=lambda _source: _linked_day_plan(DAY, "Hablé con {{ref:0}}.", "Luis", DAY)
        )

    def review(source, context, plan, *, canonical_binding=None):
        claim = (
            CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinals=(0,))
            if context.candidates[0].kind == "negative"
            else CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinal=0)
        )
        return build_candidate_coverage_manifest(
            source, context, plan, (claim,), canonical_binding=canonical_binding
        )

    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=review,
        repository=repo,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="verified-signed-date-handoff",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "verified-signed-date-handoff",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )

    assert [route["status"] for route in result.execution_flow["routes"]] == [
        "completed",
        "completed",
    ], result.execution_flow
    assert result.status is ApplicationStatus.COMPLETED
    assert len(planner_calls) == 2
    day = repo.read_text(f"calendar/days/{DAY}.md")
    assert day.count("Ayer no vi a Ana") == 1
    assert day.count("Hablé con [[Luis|Luis]].") == 1
    assert "No hablé con" not in day
    assert "Vi a [[Ana" not in day
    assert repo.read_text("Ana.md").count("Ayer no vi a Ana") == 0
