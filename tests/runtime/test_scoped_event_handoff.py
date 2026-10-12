"""Scoped Core event handoff: two independent buyers, one verified purchase.

Every test uses a disposable canonical Markdown vault; no API, DEV or user Notes.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus, WritePreflightGuardError
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
from odyssey_core.scoped_event_evidence import (
    CoreInheritedEventWriteGuard,
    validate_event_target_fact,
)
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault

SOURCE = "Ana compró entradas para el concierto y Luis también."
FACT = "Compró entradas para el concierto."


def plan(name: str, fact: str = FACT, note_type: str = "person"):
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(name, name, note_type, (), None),
                        "record",
                        (),
                        (),
                        (fact,),
                        (),
                    ),
                )
            ),
        ),
        (),
    )


def review(source, context, proposed, *, canonical_binding=None):
    assert len(context.candidates) == 1
    return build_candidate_coverage_manifest(
        source,
        context,
        proposed,
        (CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinal=0),),
        canonical_binding=canonical_binding,
    )


def dispatch(
    tmp_path,
    *,
    first_fact=FACT,
    second_fact=FACT,
    second_target="Luis",
    first_ok=True,
    latest_router=False,
):
    from odyssey_core.request_planning import PlannerClarification

    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    requests = []
    router = RecordedRouter("F16")
    if latest_router:
        import json
        from pathlib import Path

        from odyssey_apps.fact_candidates import validate_fact_candidate_proposal

        archive = (
            Path(__file__).resolve().parents[2]
            / "benchmarks/application_router/scoped_routing_v2/F16-router-only.json"
        )
        reply = json.loads(json.loads(archive.read_text())["provider_outputs"][0]["output_text"])
        router = SimpleNamespace(propose=lambda msg: validate_fact_candidate_proposal(msg, reply))

    def factory(hints, _domain):
        def run(source):
            assert hints.source == source
            assert source != SOURCE
            requests.append((source, hints.verified_inherited_event))
            if "Ana compró" in source:
                return (
                    plan("Ana", first_fact)
                    if first_ok
                    else PlannerClarification("UNREPRESENTABLE_REQUEST")
                )
            assert source == " y Luis también."
            proof = hints.verified_inherited_event
            assert proof is not None
            assert proof.predecessor_name == "Ana"
            assert proof.predecessor_type == "person"
            assert proof.predecessor_note_id == "fixture-person-ana"
            from odyssey_core.scoped_event_evidence import _tokens

            assert _tokens(proof.verified_fact) == _tokens(FACT)
            assert {role.role: role.text for role in proof.roles} == {
                "predicate": "compró",
                "object": "entradas",
                "transaction": "para el concierto",
            }
            assert "Ana compró" not in source
            return plan(second_target, second_fact)

        return SimpleNamespace(plan=run)

    result = execute_candidate_routed_message(
        SOURCE,
        router=router,
        temporal=None,
        core_planner_factory=factory,
        candidate_coverage_factory=review,
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="scoped-event-verified",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f16-event-e2e",
    )
    return result, repo, requests


@pytest.mark.parametrize("latest_router", [False, True])
@pytest.mark.parametrize("first_fact", [FACT, "Ana compró entradas para el concierto."])
def test_two_buyers_get_separate_notes_only_after_real_core_readback(
    tmp_path, latest_router, first_fact
):
    result, repo, requests = dispatch(tmp_path, latest_router=latest_router, first_fact=first_fact)
    assert result.status is ApplicationStatus.COMPLETED
    assert [r["status"] for r in result.execution_flow["routes"]] == ["completed", "completed"]
    assert len(requests) == 2
    assert requests[0][1] is None
    assert requests[1][1] is not None
    assert first_fact in repo.read_text("Ana.md")
    assert FACT in repo.read_text("Luis.md")


def test_missing_prior_write_cannot_authorize_luis(tmp_path):
    result, repo, requests = dispatch(tmp_path, first_ok=False)
    assert len(requests) == 1
    assert requests[0][1] is None
    assert result.status is not ApplicationStatus.COMPLETED
    assert FACT not in repo.read_text("Luis.md")


@pytest.mark.parametrize(
    "corruption",
    [
        "Compró entradas para el concierto y un hotel.",
        "Compró entradas entradas para el concierto.",
        "Entradas compró para el concierto.",
        "No compró entradas para el concierto.",
        "Reservó entradas para el concierto.",
    ],
)
def test_unsupported_second_fact_is_never_written(tmp_path, corruption):
    result, repo, requests = dispatch(tmp_path, second_fact=corruption)
    assert len(requests) == 2
    assert result.status is not ApplicationStatus.COMPLETED
    assert corruption not in repo.read_text("Luis.md")
    assert FACT in repo.read_text("Ana.md")


def test_previous_buyer_cannot_be_reused_as_second_buyer(tmp_path):
    result, repo, requests = dispatch(tmp_path, second_target="Ana")
    assert len(requests) == 2
    assert result.status is not ApplicationStatus.COMPLETED
    assert repo.read_text("Ana.md").count(FACT) == 1
    assert FACT not in repo.read_text("Luis.md")


def test_tampered_event_role_provenance_fails_before_coverage(tmp_path):
    result, repo, requests = dispatch(tmp_path)
    proof = requests[1][1]
    assert proof is not None
    altered = replace(proof, roles=(replace(proof.roles[0], text="vendió"), *proof.roles[1:]))
    with pytest.raises(ValueError):
        altered.validate()


def test_event_guard_rechecks_predecessor_content_digest(tmp_path):
    from odyssey_core.application import _current_canonical_reference
    from odyssey_core.reference_preflight import UnitTargetPreflight
    from odyssey_core.write_target import WriteTargetOutcome

    result, repo, requests = dispatch(tmp_path)
    proof = requests[1][1]
    assert proof is not None
    assert _current_canonical_reference(repo, SCHEMA, proof.predecessor_note_id) is not None
    guard = CoreInheritedEventWriteGuard(
        proof,
        requests[1][0],
        _candidate_two(),
    )
    # A follow-up edit of the first actor's Note revokes the inherited proof.
    repo.replace_text("Ana.md", repo.read_text("Ana.md") + "\nNueva información posterior.\n")
    with pytest.raises(WritePreflightGuardError, match="INHERITED_EVENT_SOURCE_STALE"):
        guard(
            plan("Luis").actions[0],
            (UnitTargetPreflight(0, WriteTargetOutcome.UPDATE, "fixture-person-luis", "Luis"),),
            repo,
            SCHEMA,
        )


def _candidate_two():
    from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
    from odyssey_runtime.source_scope_compiler import compile_candidate_route_bundle
    from tests.benchmarks.test_recorded_real_models_source_replay import _saved_router_outputs

    return (
        compile_candidate_route_bundle(
            validate_fact_candidate_proposal(SOURCE, _saved_router_outputs()["F16"])
        )
        .units[1]
        .context.candidates[0]
    )


def test_wrong_kind_and_unrelated_destination_rejected_even_with_carrier(tmp_path):
    _result, _repo, requests = dispatch(tmp_path)
    proof = requests[1][1]
    assert proof is not None
    candidate = _candidate_two()
    with pytest.raises(ValueError, match="Elliptical"):
        validate_event_target_fact(
            requests[1][0], candidate, plan("Atlas").actions[0].units[0], FACT, proof
        )
    with pytest.raises(ValueError, match="Elliptical"):
        validate_event_target_fact(
            requests[1][0],
            replace(candidate, kind="task"),
            plan("Luis").actions[0].units[0],
            FACT,
            proof,
        )


def test_graph_reviewer_sees_core_target_but_is_not_given_identity_authority():
    """A routed fact may omit its grammatical subject, represented by the proposed target."""
    import json

    from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
    from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
    from odyssey_runtime.source_scope_compiler import compile_candidate_route_bundle
    from tests.benchmarks.test_recorded_real_models_source_replay import _saved_router_outputs

    context = (
        compile_candidate_route_bundle(
            validate_fact_candidate_proposal(SOURCE, _saved_router_outputs()["F16"])
        )
        .units[0]
        .context
    )
    provider_calls = []

    def answer(**kwargs):
        provider_calls.append(kwargs)
        return SimpleNamespace(
            status="completed",
            usage=None,
            output_text=json.dumps(
                {
                    "candidates": [
                        {
                            "candidate_id": "candidate-1",
                            "source_quote": "Ana",
                            "fact_ordinals": [0],
                            "planned_fact_texts": [FACT],
                            "pending_reason": None,
                        }
                    ],
                }
            ),
        )

    sdk = SimpleNamespace(responses=SimpleNamespace(create=answer))
    graph = OpenAICoreCandidateAttributor(sdk).propose_graph(
        context.source,
        context,
        plan("Ana"),
    )
    assert len(provider_calls) == 1
    reviewed = json.loads(provider_calls[0]["input"][1]["content"])
    assert reviewed["original_source"] == "Ana compró entradas para el concierto"
    assert reviewed["core_proposed_targets_not_identity_proof"] == [
        {
            "fact_ordinal": 0,
            "core_proposed_target": {"entity": "Ana", "query": "Ana", "type": "person"},
        }
    ]
    assert graph.links[0].fact_ordinals == (0,)
    assert not graph.may_authorize_writes
    assert not graph.semantically_verified
    assert "CURRENT ROUTED USER SOURCE FRAGMENT" in provider_calls[0]["input"][0]["content"]
