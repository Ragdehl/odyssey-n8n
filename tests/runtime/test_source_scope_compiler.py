"""New (nonhistorical) per-unit Router dispatch contract and provenance safety."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.request_planning import PlannerClarification
from odyssey_runtime.candidate_route_dispatch import (
    compile_candidate_route_bundle,
    execute_candidate_routed_message,
)
from odyssey_runtime.source_scope_compiler import validate_bundle_original_provenance
from tests.apps.test_fact_candidates import CASES
from tests.benchmarks.test_recorded_real_models_source_replay import _saved_router_outputs
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import _source_temporal
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault

SAVED = _saved_router_outputs()
CASE = {row["id"]: row["source"] for row in CASES}


def bundle(case_id):
    source = CASE[case_id]
    return compile_candidate_route_bundle(validate_fact_candidate_proposal(source, SAVED[case_id]))


@pytest.mark.parametrize("case_id", [f"F{i:02}" for i in range(1, 28) if i != 27])
def test_every_grounded_real_router_output_has_original_exact_partition_and_evidence(
    case_id,
):
    compiled = bundle(case_id)
    validate_bundle_original_provenance(compiled)
    assert "".join(route.source_text for route in compiled.plan.routes) == CASE[case_id]
    assert len(compiled.units) == len(compiled.plan.routes)
    for item in compiled.units:
        assert item.context.source == item.route.source_text
        assert item.route.source_text == CASE[case_id][item.original_start : item.original_end]
        assert not any(
            candidate.candidate_id != f"candidate-{i}"
            for i, candidate in enumerate(item.context.candidates, start=1)
        )
        for proof in item.context.source_provenance:
            assert proof.text == CASE[case_id][proof.original_start : proof.original_end]
            assert (
                proof.text not in item.context.source
                or proof.original_start < item.original_start
                or proof.original_end > item.original_end
            )


@pytest.mark.parametrize(
    ("case_id", "expected"),
    [
        ("F02", 3),
        ("F03", 2),
        ("F04", 2),
        ("F06", 2),
        ("F07", 2),
        ("F08", 2),
        ("F12", 2),
        ("F15", 3),
        ("F16", 2),
        ("F17", 2),
        ("F18", 2),
        ("F20", 2),
        ("F21", 2),
        ("F22", 3),
        ("F23", 2),
        ("F24", 2),
        ("F25", 2),
        ("F26", 2),
        ("F13", 3),
    ],
)
def test_separable_sources_are_not_silently_remerged(case_id, expected):
    assert len(bundle(case_id).units) == expected


@pytest.mark.parametrize("case_id", ["F09", "F10", "F11", "F19"])
def test_joint_original_events_and_corrections_are_not_miswritten_as_early_facts(case_id):
    compiled = bundle(case_id)
    assert len(compiled.units) == 1


def test_shared_date_is_provenance_not_repeated_literal_or_authorized_date():
    compiled = bundle("F06")
    first, second = compiled.units
    assert first.route.source_text == "Hoy vi a Ana"
    assert second.route.source_text == " y compré pan."
    assert second.route.capability_id == "core"
    assert len(second.context.candidates) == 1
    assert not any(r.role == "date" for r in second.context.candidates[0].roles)
    assert [(r.role, r.text) for r in second.context.source_provenance] == [("date", "Hoy")]
    assert "Hoy" not in second.context.source
    suffix = second.context.prompt_suffix()
    assert "shared_source_provenance" in suffix
    assert "NOT extra request text" in suffix
    assert "NOT extra request text" not in first.context.prompt_suffix()


def test_shared_subject_and_predicate_are_only_read_only_provenance():
    compiled = bundle("F23")
    assert len(compiled.units) == 2
    second = compiled.units[1]
    assert second.context.source == " y otro en Temporal."
    assert {(r.role, r.text) for r in second.context.source_provenance} == {
        ("subject", "El proyecto Odyssey"),
        ("predicate", "tiene"),
    }


def test_tampered_shared_source_provenance_is_rejected_before_any_write():
    original = bundle("F06")
    second = original.units[1]
    witness = second.context.source_provenance[0]
    tampered_context = replace(
        second.context, source_provenance=(replace(witness, original_sha256="0" * 64),)
    )
    altered = replace(
        original, units=(original.units[0], replace(second, context=tampered_context))
    )
    with pytest.raises(ValueError, match="Shared context does not match"):
        validate_bundle_original_provenance(altered)


def test_router_invalid_cross_unit_dependency_still_fails_closed():
    from odyssey_core.candidate_dependencies import CandidateDependencyError

    with pytest.raises(CandidateDependencyError):
        bundle("F27")


def test_core_and_temporal_receive_only_their_original_scoped_texts(tmp_path):
    source = CASE["F06"]
    repository, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    planner_inputs = []
    temporal_inputs = []

    class Router:
        def propose(self, message):
            assert message == source
            return validate_fact_candidate_proposal(message, SAVED["F06"])

    class Temporal:
        def interpret(self, message):
            temporal_inputs.append(message)
            return _source_temporal(message)

    def factory(context, _domain):
        def plan(message):
            assert message == context.source
            assert message != source
            planner_inputs.append((message, context.source_provenance))
            return PlannerClarification("UNREPRESENTABLE_REQUEST")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        source,
        router=Router(),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=lambda *_: (_ for _ in ()).throw(
            AssertionError("No write must be attempted")
        ),
        repository=repository,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="scope-only-synthetic-test",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "test-f06-scoped-guards",
    )
    assert result.status.value in ("needs_attention", "failed")
    assert temporal_inputs == ["Hoy vi a Ana"]
    assert [row[0] for row in planner_inputs] == ["Hoy vi a Ana", " y compré pan."]
    assert [(e.role, e.text) for e in planner_inputs[1][1]] == [("date", "Hoy")]
    assert not any(
        "odyssey:fact request=" in repository.read_text(path)
        for path in repository.list_markdown_paths()
    )
