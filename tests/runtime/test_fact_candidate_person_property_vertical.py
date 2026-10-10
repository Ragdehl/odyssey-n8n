"""F09: actual saved GPT-6 candidate evidence to independent canonical person facts.

Core owns both named targets and fact texts; no user-vault access or provider calls.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.context import ContextIndex
from odyssey_core.request_planning import (
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.storage import VaultRepository
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW, _existing_identity
from tests.runtime.test_temporal_user_path_e2e import SCHEMA, ConstantEmbedder

EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "benchmarks/fact_candidate_v2_live/results/20261010T193754Z.json"
)


def _context():
    """Replay genuine source-validated GPT-6 F09 evidence without a model call."""
    case = next(c for c in CASES if c["id"] == "F09")
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert data["prompt_revision"] == "v3"
    proposal = validate_fact_candidate_proposal(case["source"], data["raw_router_json"]["F09"])
    return case["source"], to_core_candidate_context(proposal)


def _core_plan():
    """Core-owned semantic fixture: one independent write per existing person."""
    return RequestPlan(
        (
            WriteAction(
                tuple(
                    KnowledgeUnit(
                        SelectionCriteria(name, name, "person", (), None),
                        "record",
                        (),
                        (),
                        (f"{name} vive en Lyon.",),
                        (),
                    )
                    for name in ("Marta", "Luis")
                )
            ),
        ),
        (),
    )


def _claims():
    return (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
        CoreCandidateCoverageClaim("candidate-2", "planned_fact", 1),
    )


def _repo(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _existing_identity(vault, "Marta", "marta-id")
    _existing_identity(vault, "Luis", "luis-id")
    repo = VaultRepository(vault)
    index = ContextIndex(tmp_path / "derived" / "context.sqlite3")
    index.rebuild(repo, SCHEMA, ConstantEmbedder())
    return repo, index


def test_actual_f09_router_properties_write_to_two_existing_distinct_people(
    tmp_path: Path,
) -> None:
    """One source predicate must not merge Marta and Luis's canonical facts."""
    source, context = _context()
    plan = _core_plan()
    manifest = build_candidate_coverage_manifest(source, context, plan, _claims())
    repo, index = _repo(tmp_path)
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=object(),
        embedder=ConstantEmbedder(),
        contextual_reasoner=object(),
        actor="synthetic-property-gate",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f09-property-synthetic",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert set(result.affected_stable_note_ids) == {"marta-id", "luis-id"}
    for name, other in (("Marta", "Luis"), ("Luis", "Marta")):
        text = repo.read_text(f"{name}.md")
        assert f"{name} vive en Lyon." in text
        assert f"{other} vive en Lyon." not in text
        assert text.count("<!-- odyssey:fact request=f09-property-synthetic") == 1
    physical = readback_core_facts(source, context, plan, result, repo, SCHEMA)
    assert [item.status for item in physical.persisted_facts] == [
        "verified_in_markdown",
        "verified_in_markdown",
    ]


@pytest.mark.parametrize("mutation", ["swap_facts", "duplicate_marta", "drop_luis"])
def test_f09_wrong_core_property_assignment_cannot_write(tmp_path: Path, mutation: str) -> None:
    """Lexical attribution remains independently checked before any mutation."""
    source, context = _context()
    plan = _core_plan()
    action = plan.actions[0]
    marta, luis = action.units
    if mutation == "swap_facts":
        altered = (replace(marta, facts=luis.facts), replace(luis, facts=marta.facts))
    elif mutation == "duplicate_marta":
        altered = (marta, replace(luis, facts=marta.facts))
    else:
        altered = (marta,)
    changed = RequestPlan((WriteAction(altered),), ())
    repo, _index = _repo(tmp_path)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(source, context, changed, _claims())
    assert {p: repo.read_text(p) for p in before} == before
