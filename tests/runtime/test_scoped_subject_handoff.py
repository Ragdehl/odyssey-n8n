"""Core-verified subject/predicate handoff, with real writer and negative guards."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus, WritePreflightGuardError
from odyssey_core.request_planning import (
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.scoped_subject_evidence import (
    CoreInheritedSubjectWriteGuard,
    CoreVerifiedInheritedSubject,
)
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import (
    RecordedRouter,
    _review_one_real_core_fact,
)
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault

SOURCE = "El proyecto Odyssey tiene un fallo en Router y otro en Temporal."


def _plan(fact: str, *, target: str = "Odyssey", note_type: str = "project") -> RequestPlan:
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(
                            target,
                            "El proyecto Odyssey",
                            note_type,
                            (),
                            None,
                        ),
                        "record",
                        (),
                        (),
                        (fact,),
                        (),
                    ),
                ),
            ),
        ),
        (),
    )


def test_verified_subject_transfers_to_second_core_fragment_and_two_facts_write(tmp_path):
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    seen = []

    def factory(hints, domain):
        assert domain is None

        def plan(source):
            assert hints.source == source and source != SOURCE
            seen.append((source, hints.verified_inherited_subject))
            if source == "El proyecto Odyssey tiene un fallo en Router":
                assert hints.verified_inherited_subject is None
                return _plan("Tiene un fallo en Router.")
            assert source == " y otro en Temporal."
            proof = hints.verified_inherited_subject
            assert proof is not None
            assert proof.canonical_note_id == "fixture-project-odyssey"
            assert proof.canonical_name == "Odyssey"
            assert proof.canonical_type == "project"
            assert proof.source_text == "El proyecto Odyssey"
            assert proof.predecessor_fact == "Tiene un fallo en Router."
            assert proof.original_end < len(SOURCE)
            assert "El proyecto Odyssey" not in source
            return _plan("Tiene otro fallo en Temporal.")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        SOURCE,
        router=RecordedRouter("F23"),
        temporal=None,
        core_planner_factory=factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="test-scoped-core-subject",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f23-core-subject-proof",
    )
    assert result.status is ApplicationStatus.COMPLETED, [
        (route["status"], route.get("reason")) for route in result.execution_flow["routes"]
    ]
    assert [item[0] for item in seen] == [
        "El proyecto Odyssey tiene un fallo en Router",
        " y otro en Temporal.",
    ]
    content = repo.read_text("Odyssey.md")
    assert "Tiene un fallo en Router." in content
    assert "Tiene otro fallo en Temporal." in content


def test_missing_predecessor_fact_prevents_core_reidentifying_subject(tmp_path):
    from odyssey_core.request_planning import PlannerClarification

    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    observed = []

    def factory(hints, _domain):
        def plan(source):
            observed.append(source)
            return PlannerClarification("UNREPRESENTABLE_REQUEST")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        SOURCE,
        router=RecordedRouter("F23"),
        temporal=None,
        core_planner_factory=factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="test-scoped-core-no-subject",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f23-missing-subject",
    )
    assert len(observed) == 1
    assert observed[0] == "El proyecto Odyssey tiene un fallo en Router"
    assert result.status is not ApplicationStatus.COMPLETED
    assert "Tiene otro fallo" not in repo.read_text("Odyssey.md")


def test_verified_subject_cannot_write_to_different_canonical_note(tmp_path):
    from odyssey_core.application import _current_canonical_reference
    from odyssey_core.reference_preflight import UnitTargetPreflight
    from odyssey_core.write_target import WriteTargetOutcome

    repo, *_ = fresh_corpus_vault(tmp_path)
    canonical = _current_canonical_reference(repo, SCHEMA, "fixture-project-odyssey")
    assert canonical is not None
    proof = CoreVerifiedInheritedSubject(
        "El proyecto Odyssey",
        0,
        19,
        "0" * 64,
        0,
        "fixture-project-odyssey",
        "Odyssey",
        "project",
        canonical[2],
        "Tiene un fallo en Router.",
    )
    # Guards reject the alternate target even if a model claims that its
    # output is connected to the same source grammatical subject.
    guard = CoreInheritedSubjectWriteGuard(proof)
    with pytest.raises(WritePreflightGuardError, match="INHERITED_SUBJECT"):
        guard(
            _plan("Tiene otro fallo en Temporal.").actions[0],
            (UnitTargetPreflight(0, WriteTargetOutcome.UPDATE, "fixture-project-atlas", "Atlas"),),
            repo,
            SCHEMA,
        )


def test_subject_proof_expires_if_canonical_markdown_changes(tmp_path):
    from odyssey_core.application import _current_canonical_reference
    from odyssey_core.reference_preflight import UnitTargetPreflight
    from odyssey_core.write_target import WriteTargetOutcome

    repo, *_ = fresh_corpus_vault(tmp_path)
    canonical = _current_canonical_reference(repo, SCHEMA, "fixture-project-odyssey")
    assert canonical is not None
    proof = CoreVerifiedInheritedSubject(
        "El proyecto Odyssey",
        0,
        19,
        "0" * 64,
        0,
        "fixture-project-odyssey",
        "Odyssey",
        "project",
        canonical[2],
        "Tiene un fallo en Router.",
    )
    repo.replace_text("Odyssey.md", repo.read_text("Odyssey.md") + "\nCambio posterior.\n")
    guard = CoreInheritedSubjectWriteGuard(proof)
    with pytest.raises(WritePreflightGuardError, match="INHERITED_SUBJECT_CANONICAL_STALE"):
        guard(
            _plan("Tiene otro fallo en Temporal.").actions[0],
            (
                UnitTargetPreflight(
                    0, WriteTargetOutcome.UPDATE, "fixture-project-odyssey", "Odyssey"
                ),
            ),
            repo,
            SCHEMA,
        )


def test_local_new_subject_never_inherits_predecessor_canonical_identity():
    from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
    from odyssey_runtime.source_scope_compiler import compile_candidate_route_bundle
    from tests.apps.test_fact_candidates import CASES
    from tests.benchmarks.test_recorded_real_models_source_replay import _saved_router_outputs

    source = next(row["source"] for row in CASES if row["id"] == "F16")
    bundle = compile_candidate_route_bundle(
        validate_fact_candidate_proposal(source, _saved_router_outputs()["F16"])
    )
    first, second = bundle.units
    assert "Ana" in first.context.source
    assert "Luis" in second.context.source
    assert not any(r.role == "subject" for r in second.context.source_provenance)
    assert {r.role for r in second.context.source_provenance} == {
        "predicate",
        "object",
        "transaction",
    }
    assert second.context.verified_inherited_subject is None


def test_changed_subject_cannot_reuse_unproven_purchase_predicate(tmp_path):
    """'Luis también' must not borrow Ana's canonical identity or an unproven event."""
    from odyssey_core.request_planning import PlannerClarification

    source = "Ana compró entradas para el concierto y Luis también."
    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    seen = []

    def factory(hints, _domain):
        def plan(fragment):
            seen.append(fragment)
            return PlannerClarification("UNREPRESENTABLE_REQUEST")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter("F16"),
        temporal=None,
        core_planner_factory=factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="changed-subject-guard",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f16-prohibit-lexical-write",
    )
    assert seen == ["Ana compró entradas para el concierto"]
    assert [item["status"] for item in result.execution_flow["routes"]] == [
        "needs_attention",
        "failed",
    ]
    assert "Compró entradas" not in repo.read_text("Luis.md")


def test_house_repair_inherits_verified_house_subject_without_creating_task(tmp_path):
    """A needed repair may be noted on the house, not silently marked completed."""
    source = "La casa de Toulouse tiene humedad en el sótano y necesita reparar el tejado."
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)
    seen = []

    def fact_plan(note_fact):
        unit = KnowledgeUnit(
            SelectionCriteria("La casa de Toulouse", "La casa de Toulouse", "concept", (), None),
            "record",
            (),
            (),
            (note_fact,),
            (),
        )
        return RequestPlan((WriteAction((unit,)),), ())

    def factory(hints, domain):
        assert domain is None

        def plan(fragment):
            seen.append((fragment, hints.verified_inherited_subject))
            if len(seen) == 1:
                assert hints.verified_inherited_subject is None
                return fact_plan("Tiene humedad en el sótano.")
            assert fragment == " y necesita reparar el tejado."
            assert hints.verified_inherited_subject is not None
            assert hints.verified_inherited_subject.canonical_name == "La casa de Toulouse"
            return fact_plan("Necesita reparar el tejado.")

        return SimpleNamespace(plan=plan)

    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter("F25"),
        temporal=None,
        core_planner_factory=factory,
        candidate_coverage_factory=_review_one_real_core_fact,
        repository=repo,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="house-source-subject-only",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f25-source-subject-proof",
    )
    assert len(seen) == 2
    assert result.status is ApplicationStatus.COMPLETED, [
        item["status"] for item in result.execution_flow["routes"]
    ]
    text = repo.read_text("La casa de Toulouse.md")
    assert "Tiene humedad en el sótano." in text
    assert "Necesita reparar el tejado." in text
    # This is only a factual Note update, not an autonomous Task write.
    assert repo.list_markdown_paths().count("Task.md") == 0
