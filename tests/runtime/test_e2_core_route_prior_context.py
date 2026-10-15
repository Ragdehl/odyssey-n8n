"""Regression for DEV hybrid Core-only routes with nonempty conversation history."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidates import validate_semantic_fact_candidate_proposal
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, SelectionCriteria, WriteAction
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import _review_one_real_core_fact
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_generic_candidate_source_relations import proposal, unit
from tests.runtime.test_hybrid_v6_prewrite_writer_vertical import Reviewer

SOURCE = "Bea terminó la reunión."
PRIOR = ({"role": "assistant", "text": "Una respuesta previa verificada."},)


def _run_core_route(tmp_path, prior):
    """Dateless Core path must pass authentic recent turns to the ordinary planner."""
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    raw = proposal(
        SOURCE,
        [unit(SOURCE, "Bea terminó la reunión", predicate="terminó")],
        [("independent_assertion", 0)],
    )

    class Router:
        def propose(self, source):
            assert source == SOURCE
            return validate_semantic_fact_candidate_proposal(source, raw)

    # The real Core Writer must be reached; the existing person target is
    # source-named and lives ONLY in an isolated disposable test vault.
    raw["units"][0]["scoped_source"].append(
        {"role": "subject", "anchor": {"text": "Bea", "occurrence": 0}}
    )
    seen = []

    def factory(ctx, domain):
        def plan(source, prior=()):
            seen.append((source, tuple(prior)))
            fact = KnowledgeUnit(
                SelectionCriteria("Bea", "Bea", "person", (), None),
                "record",
                (),
                (),
                ("Bea terminó la reunión.",),
                (),
            )
            return RequestPlan((WriteAction((fact,)),), ())

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=None,
        core_planner_factory=factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="e2-prior-regression",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "e2-core-with-history",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=Reviewer(),
        conversation_context=prior,
    )
    return result, repo, seen


@pytest.mark.parametrize(
    "prior",
    [
        (),
        PRIOR,
        (
            {"role": "user", "text": "Ayer hubo una reunión."},
            {"role": "assistant", "text": "Entendido."},
            {"role": "user", "text": "Gracias."},
        ),
    ],
    ids=["first_turn", "previous_assistant", "multiple_prior_turns"],
)
def test_existing_conversation_core_only_route_reaches_planner(tmp_path, prior):
    result, repo, seen = _run_core_route(tmp_path, prior)
    assert seen == [(SOURCE, prior)], [
        (stage.name, stage.error_category) for stage in result.operational.stages
    ]
    assert result.execution_flow["routes"][0]["status"] == "completed", (
        result.planning_error,
        [(stage.name, stage.error_category) for stage in result.operational.stages],
    )
    assert "Bea terminó la reunión." in repo.read_text("Bea.md")


def test_forged_prior_turns_cannot_enter_core_or_write(tmp_path, monkeypatch):
    """The named v0 adapter cannot substitute untrusted conversation history."""
    from odyssey_runtime import routing

    original = routing._invoke_core

    def inject_foreign_history(core_execute, source, locator, actor, prior, handoff=None):
        assert tuple(prior) == PRIOR
        return original(
            core_execute,
            source,
            locator,
            actor,
            ({"role": "assistant", "text": "FORGED EXTERNAL CONTEXT"},),
            handoff,
        )

    monkeypatch.setattr(routing, "_invoke_core", inject_foreign_history)
    result, repo, seen = _run_core_route(tmp_path, PRIOR)
    assert seen == []
    assert result.execution_flow["routes"][0]["status"] == "failed"
    assert any(
        stage.name == "application.execution" and stage.error_category == "ValueError"
        for stage in result.operational.stages
    )
    assert "Bea terminó la reunión." not in repo.read_text("Bea.md")
