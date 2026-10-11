"""A second authentic F16 Router shape can enter independent Core planning."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.request_planning import PlannerClarification
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_scoped_event_handoff import SOURCE, review


def test_current_real_router_output_reaches_only_the_first_core_planner(tmp_path):
    root = Path(__file__).resolve().parents[2]
    receipt = json.loads(
        (root / "benchmarks/application_router/scoped_routing_v2/F16-router-only.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["case_id"] == "F16" and len(receipt["provider_outputs"]) == 1
    payload = json.loads(receipt["provider_outputs"][0]["output_text"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    observed = []

    class Router:
        def propose(self, source):
            return validate_fact_candidate_proposal(source, payload)

    def factory(ctx, domain):
        observed.append(("factory", ctx.source))

        def plan(source):
            observed.append(("plan", source))
            return PlannerClarification("UNREPRESENTABLE_REQUEST")

        return SimpleNamespace(plan=plan)

    execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=None,
        core_planner_factory=factory,
        candidate_coverage_factory=review,
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="source-variant-offline",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f16-live-router-scope",
    )
    assert ("plan", "Ana compró entradas para el concierto") in observed
