"""One coordinated statement, multiple Core-owned canonical identities.

Uses actual Core write and Notes backlinks in an isolated disposable Markdown
vault. No router candidate provides IDs or constructs the persistence plan.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.application import ApplicationStatus
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.storage import VaultRepository
from tests.apps.test_fact_candidates import CASES, _from_design
from tests.runtime.test_candidate_pending_state import _existing_identity
from tests.runtime.test_temporal_user_path_e2e import (
    SCHEMA,
    ConstantEmbedder,
    _core_with_plan,
    _day_plan,
)


def _f14_proposal():
    """Read the approved F14 oracle without trusting it as a write plan."""
    case = next(item for item in CASES if item["id"] == "F14")
    proposed = validate_fact_candidate_proposal(case["source"], _from_design(case))
    return case, proposed, to_core_candidate_context(proposed)


def _core_linked_event() -> RequestPlan:
    """Independently reviewed Core plan with two references in ONE fact."""
    day = _day_plan("2026-10-03", "Hablé con Eric y Luis.", "2026-10-03").actions[0].units[0]
    day = replace(
        day,
        facts=("Hablé con {{ref:0}} y {{ref:1}}.",),
        references=(
            KnowledgeReference(1, "person", "Eric"),
            KnowledgeReference(2, "person", "Luis"),
        ),
    )
    helpers = (
        KnowledgeUnit(
            SelectionCriteria(name, name, "person", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        for name in ("Eric", "Luis")
    )
    return RequestPlan((WriteAction((day, *helpers)),), ())


def _vault_with_people(tmp_path: Path) -> VaultRepository:
    """Seed two real canonical people without touching a user's vault."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _existing_identity(vault, "Eric", "eric-id")
    _existing_identity(vault, "Luis", "luis-id")
    return VaultRepository(vault)


def _notes(repo: VaultRepository, tmp_path: Path) -> NotesQueryService:
    index = ContextIndex(tmp_path / "derived" / "context.sqlite3")
    index.rebuild(repo, SCHEMA, ConstantEmbedder())
    return NotesQueryService(repo, SCHEMA, index)


def test_f14_one_event_has_both_canonical_backlinks_without_inventing_simultaneity(
    tmp_path: Path,
) -> None:
    """A shared statement creates one fact and backlinks to both participants."""
    case, proposal, context = _f14_proposal()
    assert len(proposal.candidates) == 2
    assert proposal.candidates[0].anchors[0].text == "Ayer hablé con Eric y Luis"
    assert [
        role.anchor.text for role in proposal.candidates[0].scopes if role.role == "participants"
    ] == ["Eric y Luis"]
    assert proposal.candidates[1].state == "ambiguous_identity"
    assert context.candidates[1].state == "ambiguous_identity"

    repo = _vault_with_people(tmp_path)
    plan = _core_linked_event()
    result = _core_with_plan(repo, case["source"], "approved-f14-group", plan)
    assert result.status is ApplicationStatus.COMPLETED  # Core saw ONLY its reviewed plan
    assert len(result.action_results) == 1
    assert len(result.action_results[0].unit_results) == 3
    assert set(result.affected_stable_note_ids) == {"date:2026-10-03"}
    assert [(x.source_mention, x.stable_note_id) for x in result.canonical_reference_evidence] == [
        ("Eric", "eric-id"),
        ("Luis", "luis-id"),
    ]
    markdown = repo.read_text("calendar/days/2026-10-03.md")
    assert markdown.count("<!-- odyssey:fact request=approved-f14-group ordinal=0") == 1
    assert "Hablé con [[Eric|Eric]] y [[Luis|Luis]]." in markdown
    assert "juntos" not in markdown.lower() and "a la vez" not in markdown.lower()
    assert "cine" not in markdown.lower() and "él" not in markdown.lower()

    notes = _notes(repo, tmp_path)
    event = notes.detail("date:2026-10-03")
    assert [
        (link.text, link.target_id)
        for block in event.body_blocks
        for link in block.segments
        if link.target_id in {"eric-id", "luis-id"}
    ] == [
        ("Eric", "eric-id"),
        ("Luis", "luis-id"),
    ]
    for person in ("eric-id", "luis-id"):
        matches = [b for b in notes.backlinks(person).items if b.source.id == "date:2026-10-03"]
        assert len(matches) == 1
        assert matches[0].occurrences == 1
        assert any(
            "Hablé con Eric y Luis" in "".join(segment.text for segment in snippet.block.segments)
            for snippet in matches[0].snippets
        )


def test_explicitly_sequential_contacts_remain_two_independent_fact_candidates() -> None:
    """The F27 regression prevents over-grouping when 'después' splits actions."""
    case = next(item for item in CASES if item["id"] == "F27")
    proposal = validate_fact_candidate_proposal(case["source"], _from_design(case))
    assert len(proposal.candidates) == 3
    assert [a.text for item in proposal.candidates[:2] for a in item.anchors] == [
        "Eric",
        "Luis",
    ]
    assert proposal.candidates[2].state == "ambiguous_identity"


def test_grouped_people_do_not_collapse_two_independent_properties_into_one() -> None:
    """F09 still means two distinct subject facts; group event rule is not global."""
    case = next(item for item in CASES if item["id"] == "F09")
    proposal = validate_fact_candidate_proposal(case["source"], _from_design(case))
    assert len(proposal.candidates) == 2
    assert [item.anchors[0].text for item in proposal.candidates] == ["Marta", "Luis"]
    assert all(item.kind == "property" for item in proposal.candidates)


def test_two_project_participants_use_the_same_grouped_core_contract(tmp_path: Path) -> None:
    """One statement about 2 projects retains independent canonical links and backlinks."""
    from types import SimpleNamespace

    from odyssey_core.application import execute_request
    from odyssey_core.candidate_coverage import (
        CoreCandidateCoverageClaim,
        build_candidate_coverage_manifest,
    )
    from odyssey_core.candidate_fact_readback import readback_core_facts

    source = "Ayer revisé Odyssey y Atlas."
    proposal = validate_fact_candidate_proposal(
        source,
        {
            "version": 1,
            "units": [
                {
                    "kind": "occurrence",
                    "anchors": [{"text": source, "occurrence": 0}],
                    "scoped_source": [
                        {"role": "date", "anchor": {"text": "Ayer", "occurrence": 0}},
                        {
                            "role": "participants",
                            "anchor": {"text": "Odyssey y Atlas", "occurrence": 0},
                        },
                    ],
                    "inheritance": [],
                    "state": "candidate",
                }
            ],
        },
    )
    context = to_core_candidate_context(proposal)
    repo = _vault_with_people(tmp_path)
    _existing_identity(repo.root, "Odyssey", "odyssey-id", "project")
    _existing_identity(repo.root, "Atlas", "atlas-id", "project")
    day = _day_plan("2026-10-03", "Revisé Odyssey y Atlas.", "2026-10-03").actions[0].units[0]
    day = replace(
        day,
        facts=("Revisé {{ref:0}} y {{ref:1}}.",),
        references=(
            KnowledgeReference(1, "project", "Odyssey"),
            KnowledgeReference(2, "project", "Atlas"),
        ),
    )
    helpers = tuple(
        KnowledgeUnit(
            SelectionCriteria(name, name, "project", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        for name in ("Odyssey", "Atlas")
    )
    plan = RequestPlan((WriteAction((day, *helpers)),), ())
    manifest = build_candidate_coverage_manifest(
        source, context, plan, (CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),)
    )
    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="group-project-regression",
        now="2026-10-04T17:35:00+02:00",
        context_limit=5,
        request_id_factory=lambda: "group-projects",
        candidate_context=context,
        candidate_coverage_factory=lambda *_: manifest,
    )
    assert result.status is ApplicationStatus.COMPLETED
    receipts = readback_core_facts(source, context, plan, result, repo, SCHEMA)
    assert len(receipts.persisted_facts) == 1
    assert receipts.persisted_facts[0].status == "verified_in_markdown"
    markdown = repo.read_text("calendar/days/2026-10-03.md")
    assert "Revisé [[Odyssey|Odyssey]] y [[Atlas|Atlas]]." in markdown
    assert not any(phrase in markdown.lower() for phrase in ("juntos", "simultáneamente"))
    notes = _notes(repo, tmp_path)
    for ident in ("odyssey-id", "atlas-id"):
        assert any(item.source.id == "date:2026-10-03" for item in notes.backlinks(ident).items)
