"""Full synthetic-vault replay using REAL saved GPT-6 Router and GPT-5.6 Core outputs.

This is provider-free CI evidence, not live production deployment. The Core
planner's exact raw model response is revalidated through its normal compiler
and then Core performs real canonical Markdown writes in disposable notes.
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
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_person_property_vertical import _repo
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "benchmarks/fact_candidate_v2_live/results/20261010T193754Z.json"
CORE = ROOT / "benchmarks/fact_candidate_core_live/results/20261010T200525Z.json"


def _real_frozen_plan(case_id: str):
    """Recompile exact observed Core JSON with the actual production parser."""
    model = json.loads(CORE.read_text(encoding="utf-8"))
    router = json.loads(ROUTER.read_text(encoding="utf-8"))
    assert model["mode"] == "LIVE_CORE_PLAN_ONLY"
    assert router["prompt_revision"] == "v3"
    sample = next(c for c in CASES if c["id"] == case_id)
    record = next(c for c in model["results"] if c["case"] == case_id)
    assert record["validation"] == "source_and_local_plan_valid"
    proposal = validate_fact_candidate_proposal(
        sample["source"], router["raw_router_json"][case_id]
    )
    context = to_core_candidate_context(proposal)
    fake, sdk_calls = _sdk_fake(json.loads(record["raw_model_response"]))
    result = OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, candidate_context=context).plan(
        sample["source"]
    )
    assert isinstance(result, RequestPlan)
    assert len(sdk_calls) == 1 and sdk_calls[0]["model"] == "gpt-5.6-luna"
    claims = tuple(
        CoreCandidateCoverageClaim(f"candidate-{i + 1}", "planned_fact", i)
        for i in range(len(context.candidates))
    )
    return sample["source"], context, result, claims


def _execute(tmp_path: Path, source, context, plan, claims, request_id: str):
    """Execute the independently checked plan only against test-local Person notes."""
    manifest = build_candidate_coverage_manifest(source, context, plan, claims)
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
        actor="f09-f10-synthetic-model-replay",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: request_id,
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
    )
    return repo, index, result


@pytest.mark.parametrize("case_id,count", [("F09", 2), ("F10", 1)])
def test_observed_core_model_plan_writes_verified_person_facts(
    tmp_path: Path, case_id: str, count: int
) -> None:
    """Actual provider-created plans survive real Core write and readback."""
    source, context, plan, claims = _real_frozen_plan(case_id)
    repo, index, result = _execute(
        tmp_path, source, context, plan, claims, f"{case_id.lower()}-real-core-model"
    )
    assert result.status is ApplicationStatus.COMPLETED
    readback = readback_core_facts(source, context, plan, result, repo, SCHEMA)
    assert len(readback.persisted_facts) == count
    assert all(item.status == "verified_in_markdown" for item in readback.persisted_facts)
    if case_id == "F09":
        assert set(result.affected_stable_note_ids) == {"marta-id", "luis-id"}
        for name in ("Marta", "Luis"):
            markdown = repo.read_text(f"{name}.md")
            assert "\n- Vive en Lyon.\n" in markdown
            assert markdown.count("<!-- odyssey:fact request=f09-real-core-model") == 1
        assert not result.canonical_reference_evidence
    else:
        assert result.affected_stable_note_ids == ("marta-id",)
        assert [
            (ev.source_mention, ev.stable_note_id) for ev in result.canonical_reference_evidence
        ] == [("Luis", "luis-id")]
        note = repo.read_text("Marta.md")
        assert note.count("<!-- odyssey:fact request=f10-real-core-model") == 1
        assert "Se conoció con [[Luis|Luis]] en Lyon." in note
        assert "Se conoció" not in repo.read_text("Luis.md")
        # The Day file is a capture-day header, never an invented event date.
        assert "Se conoció" not in repo.read_text("calendar/days/2026-10-04.md")
        index.rebuild(repo, SCHEMA, ConstantEmbedder())
        matches = [
            item
            for item in NotesQueryService(repo, SCHEMA, index).backlinks("luis-id").items
            if item.source.id == "marta-id"
        ]
        assert len(matches) == 1 and matches[0].occurrences == 1


@pytest.mark.parametrize(
    "mutation", ["swap_target", "duplicate_target", "wrong_city", "unsupported_denial"]
)
def test_observed_f09_local_validator_blocks_untrusted_person_fact_mutations(
    tmp_path: Path, mutation: str
) -> None:
    """Subject attribution and independent location proof remain fail-closed."""
    source, context, plan, claims = _real_frozen_plan("F09")
    action = plan.actions[0]
    marta, luis = action.units
    if mutation == "swap_target":
        new_units = (replace(marta, target=luis.target), replace(luis, target=marta.target))
    elif mutation == "duplicate_target":
        new_units = (marta, replace(luis, target=marta.target))
    elif mutation == "wrong_city":
        new_units = (replace(marta, facts=("Vive en París.",)), luis)
    else:
        new_units = (replace(marta, facts=("No vive en Lyon.",)), luis)
    wrong = RequestPlan((WriteAction(new_units),), ())
    repo, _index = _repo(tmp_path)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(source, context, wrong, claims)
    assert {p: repo.read_text(p) for p in before} == before


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_subject",
        "wrong_helper",
        "wrong_city",
        "wrong_predicate",
        "duplicate_relation",
        "new_date",
        "mutating_helper",
    ],
)
def test_observed_f10_mutual_fact_mutations_fail_before_any_write(
    tmp_path: Path, mutation: str
) -> None:
    """A mutual relation cannot be reassigned or split into invented events."""
    source, context, plan, claims = _real_frozen_plan("F10")
    relation, helper = plan.actions[0].units
    if mutation == "wrong_subject":
        relation = replace(
            relation, target=replace(relation.target, entity="Carlos", query="Carlos")
        )
    elif mutation == "wrong_helper":
        helper = replace(helper, target=replace(helper.target, entity="Carlos", query="Carlos"))
    elif mutation == "wrong_city":
        relation = replace(relation, facts=("Se conoció con {{ref:0}} en París.",))
    elif mutation == "wrong_predicate":
        relation = replace(relation, facts=("Se separó de {{ref:0}} en Lyon.",))
    elif mutation == "new_date":
        relation = replace(relation, facts=("Se conoció con {{ref:0}} en Lyon en 2020.",))
    elif mutation == "mutating_helper":
        helper = replace(helper, reference_lookup_only=False, facts=("Vive en París.",))
    else:
        relation = replace(relation, facts=(relation.facts[0], relation.facts[0]))
    wrong = RequestPlan((WriteAction((relation, helper)),), ())
    repo, _index = _repo(tmp_path)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    with pytest.raises(ValueError):
        build_candidate_coverage_manifest(source, context, wrong, claims)
    assert {p: repo.read_text(p) for p in before} == before


def test_reverse_storage_of_f10_same_single_relation_is_valid_source_evidence() -> None:
    """The reciprocal relation must not require arbitrary storage on Marta."""
    source, context, plan, claims = _real_frozen_plan("F10")
    first, helper = plan.actions[0].units
    switched = replace(
        first,
        target=helper.target,
        references=(replace(first.references[0], mention="Marta"),),
        facts=("Se conoció con {{ref:0}} en Lyon.",),
    )
    reverse_helper = replace(helper, target=first.target)
    reversed_plan = RequestPlan((WriteAction((switched, reverse_helper)),), ())
    manifest = build_candidate_coverage_manifest(source, context, reversed_plan, claims)
    assert len(manifest.claims) == 1


def test_observed_f09_can_create_two_missing_singular_people_without_conflating_them(
    tmp_path: Path,
) -> None:
    """Do not weaken the approved singular-person CREATE lifecycle."""
    from odyssey_core.context import ContextIndex
    from odyssey_core.notes import parse_note
    from odyssey_core.storage import VaultRepository
    from tests.core.test_reference_preflight import EmptyIndex, UnresolvedReasoner

    source, context, plan, claims = _real_frozen_plan("F09")
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = VaultRepository(vault)
    index = ContextIndex(tmp_path / "derived" / "context.sqlite3")
    index.rebuild(repo, SCHEMA, ConstantEmbedder())
    manifest = build_candidate_coverage_manifest(source, context, plan, claims)
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=EmptyIndex(),
        embedder=ConstantEmbedder(),
        contextual_reasoner=UnresolvedReasoner(),
        actor="f09-synthetic-new-person",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f09-new-person-lifecycle",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert [unit.operation for action in result.action_results for unit in action.unit_results] == [
        "CREATED",
        "CREATED",
    ]
    persons = [
        parse_note((vault / name).read_text(encoding="utf-8"))
        for name in repo.list_markdown_paths()
        if not name.startswith("calendar/")
    ]
    assert {note.metadata["name"] for note in persons} == {"Marta", "Luis"}
    assert len({note.metadata["id"] for note in persons}) == 2
    assert all(note.metadata["type"] == "person" for note in persons)
    assert all("Vive en Lyon." in note.content for note in persons)
    receipt = readback_core_facts(source, context, plan, result, repo, SCHEMA)
    assert all(item.status == "verified_in_markdown" for item in receipt.persisted_facts)
