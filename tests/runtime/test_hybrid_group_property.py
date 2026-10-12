"""One verified Core entity, two independently reviewed grouped properties."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus
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
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault

SOURCE = "El proyecto Odyssey tiene un fallo en Router y otro en Temporal."
FACTS = ("Tiene un fallo en Router.", "Tiene otro fallo en Temporal.")


def grouped_plan(
    *,
    owner: str = "Odyssey",
    owner_query: str = "El proyecto Odyssey",
    facts: tuple[str, ...] = FACTS,
):
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(owner, owner_query, "project", (), None),
                        "record",
                        (),
                        (),
                        facts,
                        (),
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
        (
            CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinal=0),
            CoreCandidateCoverageClaim("candidate-2", "planned_fact", fact_ordinal=1),
        ),
        canonical_binding=canonical_binding,
    )


def run(tmp_path, *, owner="Odyssey", owner_query="El proyecto Odyssey", facts=FACTS):
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    original = repo.read_text("Odyssey.md")

    def factory(hints, domain):
        assert len(hints.candidates) == 2
        assert hints.source == SOURCE
        assert domain is None
        return SimpleNamespace(
            plan=lambda source: grouped_plan(owner=owner, owner_query=owner_query, facts=facts)
        )

    result = execute_candidate_routed_message(
        SOURCE,
        router=RecordedRouter("F23"),
        temporal=None,
        core_planner_factory=factory,
        candidate_coverage_factory=coverage,
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="hybrid-group-property",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f23-grouped-proof",
        bundle_compiler=compile_hybrid_candidate_bundle,
    )
    return result, repo, original


def test_two_distinct_properties_physically_written_to_one_existing_note(tmp_path):
    result, repo, before = run(tmp_path)
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    text = repo.read_text("Odyssey.md")
    assert text.count(FACTS[0]) == 1 and text.count(FACTS[1]) == 1
    assert text != before
    assert not any(repo.read_text(f"{thing}.md").count("fallo") for thing in ("Ana", "Luis"))
    assert not any(path in {"Router.md", "Temporal.md"} for path in repo.list_markdown_paths())


@pytest.mark.parametrize(
    ("owner", "query", "facts"),
    [
        ("Ana", "El proyecto Odyssey", FACTS),
        ("Odyssey", "Otro proyecto", FACTS),
        (
            "Odyssey",
            "El proyecto Odyssey",
            ("Tiene un fallo en Router.", "Tiene otro fallo en Calendar."),
        ),
        (
            "Odyssey",
            "El proyecto Odyssey",
            ("Tiene un fallo en Temporal.", "Tiene otro fallo en Router."),
        ),
        (
            "Odyssey",
            "El proyecto Odyssey",
            ("Tiene un fallo en Router.", "Tiene otro fallo en Temporal y SQL."),
        ),
        (
            "Odyssey",
            "El proyecto Odyssey",
            ("Tiene un fallo en Router.", "No tiene otro fallo en Temporal."),
        ),
    ],
)
def test_wrong_target_swapped_location_extra_or_negative_fact_blocked(
    tmp_path, owner, query, facts
):
    result, repo, before = run(tmp_path, owner=owner, owner_query=query, facts=facts)
    assert result.status is not ApplicationStatus.COMPLETED
    assert repo.read_text("Odyssey.md") == before


def test_group_missing_second_fact_does_not_pass_coverage(tmp_path):
    result, repo, before = run(tmp_path, facts=(FACTS[0],))
    assert result.status is not ApplicationStatus.COMPLETED
    assert repo.read_text("Odyssey.md") == before


def test_wrong_inherited_subject_provenance_is_rejected_even_with_right_fact():
    from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
    from odyssey_core.candidate_grouped_property import validate_shared_subject_property
    from tests.benchmarks.test_recorded_real_models_source_replay import _saved_router_outputs

    context = (
        compile_hybrid_candidate_bundle(
            validate_fact_candidate_proposal(SOURCE, _saved_router_outputs()["F23"])
        )
        .units[0]
        .context
    )
    wrong_second = replace(context.candidates[1], inherits=())
    wrong_context = replace(context, candidates=(context.candidates[0], wrong_second))
    with pytest.raises(ValueError, match="dependence"):
        validate_shared_subject_property(
            SOURCE, wrong_context, 1, grouped_plan().actions[0].units[0], FACTS[1]
        )
