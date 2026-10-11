"""Permanent 27-message corpus and canonical note-vault regressions.

Every regression starts from the SAME committed, validated Markdown snapshot.
Provider replay uses authentic recorded Router/Core outputs, never API calls.
A source-only replay is not misreported as a full semantic model validation.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.candidate_dependencies import (
    CandidateDependencyError,
    trace_core_candidate_dependencies,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.context import ContextIndex
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_runtime.complete_source_handoff import execute_complete_message_with_core
from tests.apps.test_fact_candidates import CASES
from tests.benchmarks.test_recorded_real_models_source_replay import (
    _FULL_CORE,
    _saved_router_outputs,
)
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/full_message_corpus_v1"
MANIFEST = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))


def fresh_corpus_vault(tmp_path: Path):
    """Copy, validate and index ONLY versioned canonical test Notes.

    The production vault, state, runtime and personal note roots are never used.
    A new temp root for every test prevents accumulated writes contaminating
    later tests and lets regression failures be reproduced exactly.
    """
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE / "vault", vault)
    repo = VaultRepository(vault)
    assert len(repo.list_markdown_paths()) == len(MANIFEST["seeded_notes"])
    for row in MANIFEST["seeded_notes"]:
        note = parse_note(repo.read_text(row["path"]))
        validate_note(note, SCHEMA)
        assert note.metadata["id"] == row["id"]
        assert note.metadata["name"] == row["name"]
        assert note.metadata["type"] == row["type"]
    embedder = ConstantEmbedder()
    context_index = ContextIndex(tmp_path / "context.sqlite3")
    semantic_index = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    context_index.rebuild(repo, SCHEMA, embedder)
    semantic_index.rebuild(repo, SCHEMA, embedder)
    return repo, context_index, semantic_index, embedder


def _vault_snapshot(repo: VaultRepository) -> dict[str, str]:
    """Capture all canonical Markdown bytes before an isolated request."""
    return {path: repo.read_text(path) for path in repo.list_markdown_paths()}


def test_corpus_manifest_is_complete_versioned_and_independent_of_real_user_notes():
    assert MANIFEST["version"] == 1
    assert MANIFEST["case_design"] == "benchmarks/application_router/fact_units_v2.design.json"
    assert MANIFEST["case_ids"] == [case["id"] for case in CASES]
    assert len(CASES) == 27
    assert len(MANIFEST["seeded_notes"]) >= 10
    assert len({x["id"] for x in MANIFEST["seeded_notes"]}) == len(MANIFEST["seeded_notes"])
    assert all(x["id"].startswith("fixture-") for x in MANIFEST["seeded_notes"])


@pytest.mark.parametrize("case", CASES, ids=lambda x: x["id"])
def test_all_27_saved_real_gpt6_router_replies_against_clean_canonical_corpus(case, tmp_path: Path):
    """Exercise actual Router adapter with REAL saved provider reply, no billing."""
    repo, _context, _semantic, _embedder = fresh_corpus_vault(tmp_path)
    before = _vault_snapshot(repo)
    sdk, calls = _sdk_fake(_saved_router_outputs()[case["id"]])
    proposal = OpenAIFactCandidateRouter(sdk, prompt_revision="v3").propose(case["source"])
    assert proposal.source == case["source"]
    assert len(calls) == 1
    assert calls[0]["input"][1]["content"] == case["source"]
    assert calls[0]["model"] == "gpt-6-luna"
    assert calls[0]["store"] is False
    assert len(proposal.candidates) >= 1
    # This is a historical source provenance defect. Expected FAIL CLOSED
    # is a test oracle, never a case-specific production code branch.
    from odyssey_apps.fact_candidate_core import to_core_candidate_context

    context = to_core_candidate_context(proposal)
    if case["id"] == "F27":
        with pytest.raises(CandidateDependencyError):
            trace_core_candidate_dependencies(case["source"], context)
    else:
        assert len(trace_core_candidate_dependencies(case["source"], context)) == len(
            proposal.candidates
        )
    assert _vault_snapshot(repo) == before


@pytest.mark.parametrize("swapped_owner", [False, True])
def test_historical_real_core_plan_runs_full_writer_against_seeded_canonical_people(
    tmp_path: Path,
    swapped_owner: bool,
):
    """Replay real Core output with independently scoped graph review; verify physical Notes."""
    case = next(item for item in CASES if item["id"] == "F09")
    saved = _saved_router_outputs()
    real_plans = json.loads(_FULL_CORE.read_text(encoding="utf-8"))
    [core_reply] = [
        json.loads(entry["raw_model_response"])
        for entry in real_plans["results"]
        if entry["case"] == case["id"] and entry["provider_status"] == "completed"
    ]
    core_sdk, core_calls = _sdk_fake(core_reply)
    router_sdk, router_calls = _sdk_fake(saved[case["id"]])
    # These are independently reviewed graph claims about the historical Core
    # output. They live ONLY in tests; production obtains claims from Core's
    # actual reviewer and always validates them before writing.
    attribution_sdk, attribution_calls = _sdk_fake(
        {
            "candidates": [
                {
                    "candidate_id": f"candidate-{i}",
                    "source_quote": name,
                    "fact_ordinals": [2 - i if swapped_owner else i - 1],
                    "planned_fact_texts": ["Vive en Lyon."],
                    "pending_reason": None,
                }
                for i, name in enumerate(("Marta", "Luis"), start=1)
            ]
        }
    )
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    before = _vault_snapshot(repo)
    captured = {}

    def core_factory(context, domain):
        assert domain is None  # No time language in this original message.
        captured["context"] = context
        ordinary = OpenAILunaExperimentalPlanner(
            core_sdk,
            SCHEMA,
            CLOCK,
            candidate_context=context,
        )

        class RecordingPlanner:
            """Only capture the normal compiled plan for canonical readback."""

            def plan(self, source):
                plan = ordinary.plan(source)
                captured["plan"] = plan
                return plan

            def __getattr__(self, name):
                return getattr(ordinary, name)

        return RecordingPlanner()

    result = execute_complete_message_with_core(
        case["source"],
        router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        temporal=None,  # A no-temporal message does not need a fake time mention.
        core_planner_factory=core_factory,
        core_candidate_attributor=OpenAICoreCandidateAttributor(attribution_sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="synthetic-corpus-test",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "corpus-real-core-f09",
    )
    if swapped_owner:
        assert result.status is ApplicationStatus.NEEDS_ATTENTION
        assert result.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
        assert _vault_snapshot(repo) == before
        return
    assert result.status is ApplicationStatus.COMPLETED, (
        result.clarification_code,
        result.planning_error,
        [(x.name, x.outcome, x.error_category) for x in result.operational.stages],
    )
    assert [len(x) for x in (router_calls, core_calls, attribution_calls)] == [1, 1, 1]
    assert core_calls[0]["input"][1]["content"] == case["source"]
    readback = readback_core_facts(
        case["source"], captured["context"], captured["plan"], result, repo, SCHEMA
    )
    assert [fact.status for fact in readback.persisted_facts] == [
        "verified_in_markdown",
        "verified_in_markdown",
    ]
    after = _vault_snapshot(repo)
    # Core's normal capture heading materializes the matching Calendar Day.
    # No additional person or project identities may be fabricated.
    assert set(after) - set(before) == {"calendar/days/2026-10-04.md"}
    assert "Vive en Lyon." in after["Marta.md"]
    assert "Vive en Lyon." in after["Luis.md"]
    assert all(after[path] == before[path] for path in set(before) - {"Marta.md", "Luis.md"})


def test_corpus_vault_is_reset_before_every_regression(tmp_path: Path):
    repo, *_ = fresh_corpus_vault(tmp_path / "first")
    before = _vault_snapshot(repo)
    path = repo.root / "Ana.md"
    path.write_text("corrupt disposable test data", encoding="utf-8")
    assert _vault_snapshot(repo) != before
    fresh, *_ = fresh_corpus_vault(tmp_path / "second")
    assert _vault_snapshot(fresh) == before


def test_historical_real_core_relationship_preserves_canonical_reference_and_backlink(
    tmp_path: Path,
):
    """Use the same graph reviewer on a saved real linked Core plan and seeded notes."""
    from odyssey_core.note_queries import NotesQueryService

    case = next(item for item in CASES if item["id"] == "F10")
    [core_reply] = [
        json.loads(entry["raw_model_response"])
        for entry in json.loads(_FULL_CORE.read_text(encoding="utf-8"))["results"]
        if entry["case"] == case["id"] and entry["provider_status"] == "completed"
    ]
    core_sdk, core_calls = _sdk_fake(core_reply)
    router_sdk, router_calls = _sdk_fake(_saved_router_outputs()[case["id"]])
    review_sdk, review_calls = _sdk_fake(
        {
            "candidates": [
                {
                    "candidate_id": "candidate-1",
                    "source_quote": "se conocieron",
                    "fact_ordinals": [0],
                    "planned_fact_texts": ["Se conoció con {{ref:0}} en Lyon."],
                    "pending_reason": None,
                }
            ]
        }
    )
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    captured = {}

    def core_factory(context, domain):
        assert domain is None
        captured["context"] = context
        ordinary = OpenAILunaExperimentalPlanner(core_sdk, SCHEMA, CLOCK, candidate_context=context)

        class RecordingPlanner:
            def plan(self, source):
                result = ordinary.plan(source)
                captured["plan"] = result
                return result

            def __getattr__(self, name):
                return getattr(ordinary, name)

        return RecordingPlanner()

    result = execute_complete_message_with_core(
        case["source"],
        router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        temporal=None,
        core_planner_factory=core_factory,
        core_candidate_attributor=OpenAICoreCandidateAttributor(review_sdk),
        repository=repo,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="synthetic-corpus-test",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "corpus-real-core-relationship",
    )
    assert result.status is ApplicationStatus.COMPLETED, (
        result.clarification_code,
        [(a.status, a.reason) for a in result.action_results],
    )
    assert [len(calls) for calls in (router_calls, core_calls, review_calls)] == [1, 1, 1]
    verified = readback_core_facts(
        case["source"], captured["context"], captured["plan"], result, repo, SCHEMA
    )
    assert [f.status for f in verified.persisted_facts] == ["verified_in_markdown"]
    assert "Se conoció con [[Luis|Luis]] en Lyon." in repo.read_text("Marta.md")
    # The real composition refreshes derived Notes indexes after writes;
    # this isolated direct adapter does not own that indexing lifecycle.
    context_index.rebuild(repo, SCHEMA, embedder)
    notes = NotesQueryService(repo, SCHEMA, context_index)
    assert any(
        backlink.source.id == "fixture-person-marta"
        for backlink in notes.backlinks("fixture-person-luis").items
    )
