"""Generic v6 fail-closed source dependency: never a bare HTTP 500 or a write."""

from __future__ import annotations

import pytest

from odyssey_apps.fact_candidates import validate_semantic_fact_candidate_proposal
from odyssey_apps.router import RouterError
from odyssey_core.application import ApplicationStatus
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_generic_candidate_source_relations import proposal, unit

SOURCE = "I repaired a blue cabinet and cleaned the workshop."
ROWS = [
    unit(SOURCE, "I repaired a blue cabinet", predicate="repaired"),
    unit(SOURCE, "cleaned the workshop", predicate="cleaned"),
]
# Unsupported inherited CLOCK role. Router may cite this, but it has no proof
# from any preceding source candidate. Neither Core nor Temporal may guess it.
ROWS[1]["inheritance"] = [{"role": "date", "from_unit": 1}]
DATA = proposal(SOURCE, ROWS, [("independent_assertion", 0), ("independent_assertion", 0)])


@pytest.mark.parametrize("error_at", ["compiler", "router"])
def test_unproven_v6_source_never_invokes_writer_or_loses_error_category(tmp_path, error_at):
    repository, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    prior = {path: repository.read_text(path) for path in repository.list_markdown_paths()}
    prior_paths = repository.list_markdown_paths()
    progress: list[str] = []

    class Router:
        def propose(self, source):
            assert source == SOURCE
            if error_at == "router":
                raise RouterError("synthetic invalid source quote from model")
            return validate_semantic_fact_candidate_proposal(source, DATA)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Planner or Writer must not execute after failed source proof")

    result = execute_candidate_routed_message(
        SOURCE,
        router=Router(),
        temporal=None,
        core_planner_factory=forbidden,
        candidate_coverage_factory=forbidden,
        repository=repository,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="synthetic-candidate-dependency-failure",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "v6-source-rejection",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=object(),
        progress_callback=lambda name, _payload: progress.append(name),
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CANDIDATE_SOURCE_COMPILATION_UNREPRESENTABLE"
    assert result.affected_stable_note_ids == ()
    assert result.planning_error == (
        "SOURCE_DEPENDENCY_UNVERIFIED"
        if error_at == "compiler"
        else "SOURCE_PROVENANCE_UNREPRESENTABLE"
    )
    assert [stage.name for stage in result.operational.stages] == [
        "candidate.source_compilation" if error_at == "compiler" else "application.router"
    ]
    assert result.operational.stages[0].error_category == (
        "CandidateDependencyError" if error_at == "compiler" else "RouterError"
    )
    assert "routing.boundary_review_required" in progress
    assert repository.list_markdown_paths() == prior_paths
    assert {path: repository.read_text(path) for path in prior_paths} == prior
