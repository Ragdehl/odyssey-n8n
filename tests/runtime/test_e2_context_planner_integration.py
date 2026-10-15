"""E2 real Router→Temporal→Core Planner→Writer with source role Note lookup.

The new ContextAwareCorePlannerFactory is a *structural* port, not an alternate
planner/Writer. Old two-argument factories must remain fully compatible.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidates import validate_semantic_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus
from odyssey_core.execution_context import ContextPort, ExecutionContext, StageSpec, stage_input
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.composition import _persistence_actor
from odyssey_runtime.context_planner_ports import ContextAwareCorePlannerFactory
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import (
    _review_one_real_core_fact,
    _source_temporal,
)
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_generic_candidate_source_relations import proposal, quote, unit
from tests.runtime.test_hybrid_v6_prewrite_writer_vertical import Reviewer
from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan

SOURCE = "Hoy hablé con Bea."
UNIT = unit(SOURCE, "Hoy hablé con Bea", predicate="hablé", date="Hoy")
UNIT["scoped_source"].append({"role": "participants", "anchor": quote("Bea")})
PROPOSAL = proposal(SOURCE, [UNIT], [("independent_assertion", 0)])


class Router:
    def propose(self, original):
        assert original == SOURCE
        return validate_semantic_fact_candidate_proposal(original, PROPOSAL)


class Temporal:
    def interpret(self, original):
        assert original == SOURCE
        return _source_temporal(original)


class ContextFactory:
    """No inheritance from ContextAwareCorePlannerFactory is required."""

    def __init__(self):
        self.seen: list[ExecutionContext] = []

    def create_for_context(self, context: ExecutionContext):
        assert context.source == SOURCE
        assert context.candidates is not None
        assert len(context.domains) == 1
        assert context.qualitative_times == ()
        assert len(context.note_mentions) == 1
        mention = context.note_mentions[0]
        assert mention.source_text == "Bea"
        assert SOURCE[mention.start : mention.end] == "Bea"
        assert len(mention.candidates) == 1
        assert mention.candidates[0].note_type == "person"
        assert mention.candidates[0].canonical_name == "Bea"
        assert context.authenticated_actor is None
        assert (
            stage_input(
                context,
                StageSpec(
                    "core.notes",
                    frozenset({ContextPort.NOTE_MENTIONS}),
                    frozenset({ContextPort.PENDING}),
                ),
            ).actor
            is None
        )
        self.seen.append(context)
        return SimpleNamespace(
            plan=lambda text, prior=(): _linked_day_plan(
                "2026-10-04", "Hablé con {{ref:0}}.", "Bea", "2026-10-04"
            )
        )


def _execute(
    tmp_path,
    factory,
    *,
    temporal_override=None,
    repository_hook=None,
    progress_callback=None,
    conversation_context=(),
):
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    original_bea = repo.read_text("Bea.md")
    if repository_hook is not None:
        repository_hook(repo)
    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=temporal_override or Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor=_persistence_actor("e2-context-port", None),
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "e2-context-port",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=Reviewer(),
        progress_callback=progress_callback,
        conversation_context=conversation_context,
    )
    assert result.status is ApplicationStatus.COMPLETED, (
        result.planning_error,
        result.clarification_code,
        [(item.status.value, item.reason) for item in result.action_results],
    )
    assert "Hablé con [[Bea|Bea]]." in repo.read_text("calendar/days/2026-10-04.md")
    assert repo.read_text("Bea.md") == original_bea
    return result


def test_context_aware_factory_receives_real_bound_candidates_and_writer_is_unchanged(tmp_path):
    factory = ContextFactory()
    assert isinstance(factory, ContextAwareCorePlannerFactory)
    assert ContextAwareCorePlannerFactory not in ContextFactory.__bases__
    result = _execute(tmp_path, factory)
    assert len(factory.seen) == 1
    assert result.affected_stable_note_ids


def test_legacy_factory_still_uses_two_arguments_and_writes_same_fact(tmp_path):
    called = []

    def legacy(context, domain):
        called.append((context, domain))
        return SimpleNamespace(
            plan=lambda text: _linked_day_plan(
                "2026-10-04", "Hablé con {{ref:0}}.", "Bea", "2026-10-04"
            )
        )

    assert not isinstance(legacy, ContextAwareCorePlannerFactory)
    _execute(tmp_path, legacy)
    assert len(called) == 1
    assert called[0][0].source == SOURCE


def test_missing_factory_callable_or_port_is_rejected_before_source_execution(tmp_path):
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)

    class WrongFactory:
        def create(self, context):
            raise AssertionError("must never be called")

    with pytest.raises(ValueError, match="planner and coverage callbacks"):
        execute_candidate_routed_message(
            SOURCE,
            router=Router(),
            temporal=Temporal(),
            core_planner_factory=WrongFactory(),
            candidate_coverage_factory=_review_one_real_core_fact,
            repository=repo,
            schema=SCHEMA,
            context_index=context_index,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=object(),
            actor=_persistence_actor("e2-invalid-port", None),
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "e2-invalid-port",
            bundle_compiler=compile_hybrid_candidate_bundle,
        )


def test_e2_hybrid_with_real_prior_turns_survives_core_adapter(tmp_path):
    """Previous turns must reach Core before a canonical, source-verified write."""
    prior = (
        {"role": "user", "content": "Una pregunta anterior"},
        {"role": "assistant", "content": "Respuesta anterior"},
    )
    result = _execute(tmp_path, ContextFactory(), conversation_context=prior)
    assert result.status is ApplicationStatus.COMPLETED
    assert result.execution_flow["routes"][0]["status"] == "completed"
