"""Actual saved GPT-6 Router + GPT-5.6 Core dependent-fact write diagnostics.

The current Core compiler replays archived real-model responses in disposable
Markdown vaults. This is a mechanical compatibility check, NOT proof that the
now-changed model prompt would produce those outputs or that original-source
coverage authorized any write. Archived response bytes remain SHA-pinned.
"""

from __future__ import annotations

import hashlib
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

# These are the unchanged historical 2026-10-11 receipt bytes, not fresh
# provider approvals for any current Planner prompt or source revision.
_ARCHIVED_RECEIPT_SHA256 = {
    ("F23", "candidate-1"): "938b7f0a007f5a0a5d3b6918cbec9be242a3b10a8d76870a3d61b8b398d97b6b",
    ("F23", "candidate-2"): "c6094d8d875b07a9961ae8f7b4a6f52b9e52b65e5d532beb58f55532660f63f1",
    ("F26", "candidate-1"): "b50ddeab4e8572c8984a45b0745ee851a064d5c5bc531e8beb0a632c757481fc",
    ("F26", "candidate-2"): "e5cb16949477605be072d04d319cc8314e07bb6ada1cf96ab6a272df55173d21",
}


def _plans(case_id: str):
    """Replay immutable old outputs as fixtures, never approve changed inputs."""
    source, context = _observed(case_id)
    planned = []
    for uid in ("candidate-1", "candidate-2"):
        unit, request, temporal, wire = gate._request(case_id, uid)
        # The archived *authorization* no longer matches the current Planner
        # envelope. Replaying frozen model output may test Core mechanics, but
        # must never be mistaken for a newly reviewed or billable request.
        with pytest.raises(ValueError, match="Unreviewed dependent Core request"):
            gate.reviewed(case_id, uid)
        files = list(gate.RECEIPTS.glob(f"*--{case_id}--{uid}.json"))
        assert len(files) == 1
        original_bytes = files[0].read_bytes()
        assert (
            hashlib.sha256(original_bytes).hexdigest() == _ARCHIVED_RECEIPT_SHA256[(case_id, uid)]
        )
        receipt = json.loads(original_bytes)
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


def test_archived_model_replay_rejects_mutated_receipt_bytes(tmp_path, monkeypatch):
    """Replaying historical responses must not silently accept altered evidence."""
    receipts = tmp_path / "historical-receipts"
    receipts.mkdir()
    for original in gate.RECEIPTS.glob("*--F23--candidate-*.json"):
        (receipts / original.name).write_bytes(original.read_bytes())
    monkeypatch.setattr(gate, "RECEIPTS", receipts)
    target = next(receipts.glob("*--F23--candidate-2.json"))
    # A harmless whitespace edit still breaks the authentic witness SHA.
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(AssertionError):
        _plans("F23")


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
