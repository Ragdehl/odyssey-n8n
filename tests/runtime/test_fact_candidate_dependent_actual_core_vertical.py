"""Actual saved GPT-6 Router + GPT-5.6 Core dependent-fact write diagnostics.

The existing Core compiler is replayed against immutable REAL model outputs.
Normal mechanics run only in disposable Markdown vaults. This test explicitly
distinguishes ordinary Core mechanical execution from the still-blocked full
original-source candidate coverage required for runtime activation.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_core_live import run_dependent_live as gate
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.context import ContextIndex
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import RequestPlan
from odyssey_core.storage import VaultRepository
from tests.core.test_candidate_dependencies_observed import _observed
from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner
from tests.runtime.test_candidate_pending_state import NOW, _existing_identity
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder


def _plans(case_id: str):
    """Compile exact saved real GPT-5.6 outputs through existing normal Core."""
    source, context = _observed(case_id)
    planned = []
    for uid in ("candidate-1", "candidate-2"):
        unit, request, temporal, wire = gate.reviewed(case_id, uid)
        files = list(gate.RECEIPTS.glob(f"*--{case_id}--{uid}.json"))
        assert len(files) == 1
        receipt = json.loads(files[0].read_text(encoding="utf-8"))
        assert receipt["mode"] == "LIVE_CORE_DEPENDENT_PLAN_ONLY"
        assert receipt["provider_status"] == "completed"
        assert receipt["validation"] == "local_compiler_accepted"
        assert receipt["outcome"] == "PLAN"
        assert receipt["fact_count"] == 1
        assert receipt["may_write_notes"] is False
        fake, calls = _sdk_fake(json.loads(receipt["raw_model_response"]))
        core = OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=temporal)
        if case_id == "F26":
            core.max_output_tokens = 1280
        compiled = core.plan(request)
        assert isinstance(compiled, RequestPlan)
        assert len(calls) == 1
        assert calls[0]["input"][1]["content"] == request
        assert calls[0]["max_output_tokens"] == wire["max_output_tokens"]
        assert unit.candidate_id == uid
        planned.append((request, compiled))
    return source, context, planned


def _vault(tmp_path: Path, *, existing_report: bool):
    """Produce synthetic canonical identities and a functioning Core index."""
    root = tmp_path / "vault"
    root.mkdir()
    _existing_identity(root, "Ana", "ana-id", "person")
    _existing_identity(root, "Odyssey", "odyssey-id", "project")
    _existing_identity(root, "Router", "router-id", "project")
    if existing_report:
        _existing_identity(root, "El informe", "report-id", "document")
    repo = VaultRepository(root)
    index = ContextIndex(tmp_path / "derived" / "context.sqlite3")
    index.rebuild(repo, SCHEMA, ConstantEmbedder())
    return repo, index


def _replay(repo, index, case_id, plans, *, discover_missing=False):
    """Sequential normal Core execution; never original-source-authorized."""
    results = []
    for ordinal, (request, plan) in enumerate(plans):
        result = execute_request(
            request,
            planner=SimpleNamespace(plan=lambda _, selected=plan: selected),
            repository=repo,
            schema=SCHEMA,
            context_index=index,
            semantic_index=EmptyIndex() if discover_missing else object(),
            embedder=ConstantEmbedder(),
            contextual_reasoner=UnresolvedReasoner() if discover_missing else object(),
            actor="synthetic-dependent-model-replay",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda step=ordinal: f"{case_id}-real-model-{step}",
        )
        results.append(result)
        if result.status is not ApplicationStatus.COMPLETED:
            break
        index.rebuild(repo, SCHEMA, ConstantEmbedder())
    return results


@pytest.mark.parametrize("case_id", ["F23", "F26"])
def test_full_original_source_coverage_still_blocks_direct_activation(case_id):
    """Do not mistake model PLAN for original-source semantic write proof."""
    source, context, plans = _plans(case_id)
    joined = RequestPlan(tuple(a for _request, p in plans for a in p.actions), ())
    claims = tuple(
        CoreCandidateCoverageClaim(f"candidate-{i + 1}", "planned_fact", i) for i in range(2)
    )
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(source, context, joined, claims)


def test_f23_two_model_facts_write_to_one_original_project_in_isolated_vault(tmp_path):
    _source, _context, plans = _plans("F23")
    repo, index = _vault(tmp_path, existing_report=False)
    results = _replay(repo, index, "F23", plans)
    assert len(results) == 2
    assert all(r.status is ApplicationStatus.COMPLETED for r in results)
    assert [r.affected_stable_note_ids for r in results] == [
        ("odyssey-id",),
        ("odyssey-id",),
    ]
    text = repo.read_text("Odyssey.md")
    assert text.count("<!-- odyssey:fact request=F23-real-model-") == 2
    assert "Tiene un fallo en [[Router|Router]]." in text
    assert "Tiene otro fallo en Temporal." in text
    assert repo.read_text("Router.md").count("Tiene un fallo") == 0


def test_f26_existing_document_is_reused_by_both_core_model_plans(tmp_path):
    _source, _context, plans = _plans("F26")
    repo, index = _vault(tmp_path, existing_report=True)
    results = _replay(repo, index, "F26", plans)
    assert len(results) == 2
    assert all(r.status is ApplicationStatus.COMPLETED for r in results)
    assert results[0].affected_stable_note_ids == ("report-id",)
    assert results[1].affected_stable_note_ids == ("date:2026-10-04",)
    note = repo.read_text("El informe.md")
    assert "Llegó [[calendar/days/2026-10-03|03-10-2026]]." in note
    today = repo.read_text("calendar/days/2026-10-04.md")
    assert "Envié [[El informe|El informe]] a [[Ana|Ana]]." in today
    assert repo.read_text("Ana.md").count("Envié") == 0
    assert sum(path.endswith("El informe.md") for path in repo.list_markdown_paths()) == 1


def test_f26_document_create_then_followup_reuses_same_created_id(tmp_path):
    _source, _context, plans = _plans("F26")
    repo, index = _vault(tmp_path, existing_report=False)
    results = _replay(repo, index, "F26", plans, discover_missing=True)
    assert len(results) == 2
    assert all(r.status is ApplicationStatus.COMPLETED for r in results)
    created_id = results[0].affected_stable_note_ids[0]
    assert created_id != "ana-id" and created_id != "date:2026-10-03"
    doc_paths = [
        path
        for path in repo.list_markdown_paths()
        if parse_note(repo.read_text(path)).metadata.get("type") == "document"
    ]
    assert len(doc_paths) == 1
    assert parse_note(repo.read_text(doc_paths[0])).metadata["id"] == created_id
    today = repo.read_text("calendar/days/2026-10-04.md")
    assert "Envié " in today and "Ana" in today
    assert "el informe" in today.casefold()
    assert created_id in today
    assert all(
        parse_note(repo.read_text(path)).metadata.get("id") != "report-id"
        for path in repo.list_markdown_paths()
    )


@pytest.mark.parametrize("case_id,existing_report", [("F23", False), ("F26", True), ("F26", False)])
def test_real_dependency_attestation_checks_actual_stable_ids_after_core_writes(
    tmp_path, case_id, existing_report
):
    """Core's actual model and physical canonical ID satisfy a separate audit."""
    from odyssey_core.candidate_dependency_attestation import (
        attest_two_dependent_core_plans,
        review_persisted_dependency,
    )

    source, context, entries = _plans(case_id)
    plans = tuple(p for _request, p in entries)
    proof = attest_two_dependent_core_plans(source, context, plans)
    assert not proof.canonical_reuse_verified
    assert not proof.may_write_notes

    repo, index = _vault(tmp_path, existing_report=existing_report)
    results = tuple(
        _replay(
            repo,
            index,
            case_id,
            entries,
            discover_missing=(case_id == "F26" and not existing_report),
        )
    )
    certified = review_persisted_dependency(source, context, plans, proof, results, repo)
    assert certified.canonical_reuse_verified
    assert not certified.may_write_notes
    assert certified.source_digest == proof.source_digest
    assert certified.candidate_ids == proof.candidate_ids


def test_document_reference_cannot_be_certified_from_similar_names_alone(tmp_path):
    """The exact linked Markdown note must match the first Core stable ID."""
    from odyssey_core.candidate_dependency_attestation import (
        DependentFactAttestationError,
        attest_two_dependent_core_plans,
        review_persisted_dependency,
    )

    source, context, entries = _plans("F26")
    plans = tuple(plan for _, plan in entries)
    proof = attest_two_dependent_core_plans(source, context, plans)
    repo, index = _vault(tmp_path, existing_report=True)
    results = tuple(_replay(repo, index, "F26", entries))

    day = tmp_path / "vault" / "calendar/days/2026-10-04.md"
    original = day.read_text(encoding="utf-8")
    assert "[[El informe|El informe]]" in original
    day.write_text(
        original.replace("[[El informe|El informe]]", "[[Ana|El informe]]"),
        encoding="utf-8",
    )
    with pytest.raises(DependentFactAttestationError, match="same canonical"):
        review_persisted_dependency(source, context, plans, proof, results, repo)


def test_missing_or_forged_original_fact_marker_blocks_persisted_proof(tmp_path):
    from odyssey_core.candidate_dependency_attestation import (
        DependentFactAttestationError,
        attest_two_dependent_core_plans,
        review_persisted_dependency,
    )

    source, context, entries = _plans("F23")
    plans = tuple(plan for _, plan in entries)
    proof = attest_two_dependent_core_plans(source, context, plans)
    repo, index = _vault(tmp_path, existing_report=False)
    results = tuple(_replay(repo, index, "F23", entries))
    note = tmp_path / "vault" / "Odyssey.md"
    saved = note.read_text(encoding="utf-8")
    assert "request=F23-real-model-1" in saved
    note.write_text(
        saved.replace("request=F23-real-model-1", "request=unrelated"),
        encoding="utf-8",
    )
    with pytest.raises(DependentFactAttestationError, match="marker"):
        review_persisted_dependency(source, context, plans, proof, results, repo)
