"""Provider-free Slice 3 contract and application evidence with synthetic Markdown."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import odyssey_core.application as application
from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RelationalReference,
    RequestPlan,
    RequestPlanningError,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
    compact_planner_result_json_schema,
    planner_result_json_schema,
    validate_request_plan,
)
from odyssey_core.storage import VaultRepository
from odyssey_core.write_target import WriteTargetOutcome, decide_write_target

ROOT = Path(__file__).resolve().parents[2]
ACTOR = AuthenticatedActorContext("8c1a06bc-17cc-4f81-a026-e3ba04c971e5")


class EmptyIndex:
    """Return no semantic candidates when exact source identity is expected."""

    def find_candidates(self, *args: Any, **kwargs: Any) -> tuple[()]:
        """Prevent synthetic tests from using a derived index as authority."""
        return ()


class EmptyEmbedder:
    """Satisfy the injected embedding boundary without a provider call."""

    model_name = "tests"
    model_version = "1"


class FactReasoner:
    """Select one supplied fact or abstain with the real contextual result shape."""

    def __init__(self, outcome: str = "RESOLVED") -> None:
        """Configure one deterministic candidate decision."""
        self.outcome = outcome
        self.requests: list[Any] = []

    def resolve(self, request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return only a candidate locator supplied by current Core evidence."""
        self.requests.append(request)
        return (
            {
                "outcome": self.outcome,
                "id": request.candidates[0].id if self.outcome == "RESOLVED" else None,
            },
            {},
        )


class MatchingFactReasoner(FactReasoner):
    """Select a supplied candidate by visible canonical fact wording for fixture coverage."""

    def __init__(self, wording: str) -> None:
        """Require the fixture's contextual boundary to receive and choose one later fact."""
        super().__init__()
        self.wording = wording.casefold()

    def resolve(self, request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """Resolve only a candidate actually supplied by Core to this test double."""
        self.requests.append(request)
        candidate = next(
            item for item in request.candidates if self.wording in item.evidence.casefold()
        )
        return ({"outcome": "RESOLVED", "id": candidate.id}, {})


class ForbiddenWriter:
    """Reject unexpected free-form writer use for atomic fixture facts."""

    def write(self, request: Any) -> Any:
        """Fail if a relationship write bypasses atomic materialization."""
        raise AssertionError("unexpected writer call")


class SelfBinding:
    """Bind the synthetic authenticated human to the Edgar note."""

    def resolve(self, stable_user_id: str) -> Any:
        """Return one fixed person-note ID after checking the authenticated actor."""
        assert stable_user_id == ACTOR.stable_user_id
        return SimpleNamespace(person_note_id="edgar")


@pytest.fixture
def schema() -> dict[str, Any]:
    """Load the production note schema without using personal data."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def write_note(
    vault: Path, path: str, note_id: str, name: str, body: str, *, note_type: str = "person"
) -> None:
    """Create one schema-valid disposable canonical note."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {
        "id": note_id,
        "name": name,
        "type": note_type,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-09-23T00:00:00Z",
        "created_by": {"human": None, "app": "test"},
        "updated_by": {"human": None, "app": "test"},
        "revision": 1,
        "schema_version": 3,
        "aliases": [],
        "tags": [],
    }
    if note_type == "journal_entry":
        metadata["entry_date"] = "2026-09-23"
    target.write_text(serialize_note(Note(metadata, body)), encoding="utf-8")


def fact(text: str, ordinal: int = 0) -> str:
    """Render one canonical marker-bearing fact block."""
    return render_atomic_facts((text,), "fixture", (ordinal,), "2026-09-23")


def relational_selection(
    reference: str, *, source_kind: str, source_query: str | None, members: str = "one"
) -> SelectionCriteria:
    """Build a validated-shaped model interpretation without stable IDs."""
    return SelectionCriteria(
        None,
        reference,
        "person" if members == "one" else None,
        (),
        None,
        relational_reference=RelationalReference(reference, source_kind, source_query, members),
    )


def run(
    vault: Path,
    schema: dict[str, Any],
    plan: RequestPlan,
    *,
    reasoner: FactReasoner | None = None,
) -> application.ApplicationResult:
    """Execute one synthetic plan through the real Core application boundary."""
    return application.execute_request(
        "synthetic request",
        planner=SimpleNamespace(plan=lambda _request: plan),
        repository=VaultRepository(vault),
        schema=schema,
        context_index=object(),
        semantic_index=EmptyIndex(),
        embedder=EmptyEmbedder(),
        contextual_reasoner=reasoner or FactReasoner(),
        actor="test",
        now="2026-09-24T12:00:00Z",
        context_limit=5,
        writer=ForbiddenWriter(),
        authenticated_actor=ACTOR,
        self_binding_repository=SelfBinding(),
        request_id_factory=lambda: "relational-test",
    )


def test_model_contract_preserves_relational_intent_and_legacy_selection(schema: dict) -> None:
    """Accept bounded relational wording in both schemas and retain ordinary selectors."""
    selection = {
        "entity": None,
        "query": "¿Dónde vive mi hija?",
        "type": "person",
        "filters": [],
        "link_scope": None,
        "self_target": None,
        "relational_reference": {
            "reference": "mi hija",
            "source_kind": "self",
            "source_query": None,
            "members": "one",
        },
    }
    payload = {"actions": [{"kind": "retrieve", "plan": selection}], "limitations": []}
    plan = validate_request_plan(payload, schema)
    assert isinstance(plan.actions[0], RetrieveAction)
    assert plan.actions[0].plan.relational_reference == RelationalReference(
        "mi hija", "self", None, "one"
    )
    with pytest.raises(RequestPlanningError):
        validate_request_plan(dict(payload, presentation_intent="note_set"), schema)
    assert (
        "relational_reference"
        in planner_result_json_schema(schema)["properties"]["result"]["anyOf"][0]["properties"][
            "actions"
        ]["items"]["anyOf"][0]["properties"]["plan"]["required"]
    )
    assert (
        "relational_reference"
        in compact_planner_result_json_schema(schema)["$defs"]["selection"]["required"]
    )
    legacy = dict(selection, relational_reference=None)
    assert (
        validate_request_plan(
            {"actions": [{"kind": "retrieve", "plan": legacy}], "limitations": []}, schema
        )
        .actions[0]
        .plan.relational_reference
        is None
    )
    invalid = dict(
        selection, relational_reference={**selection["relational_reference"], "target_id": "chloe"}
    )
    with pytest.raises(RequestPlanningError):
        validate_request_plan(
            {"actions": [{"kind": "retrieve", "plan": invalid}], "limitations": []}, schema
        )
    for unsafe_source in ("people/chloe.md", "8c1a06bc-17cc-4f81-a026-e3ba04c971e5"):
        unsafe = dict(
            selection,
            relational_reference={
                **selection["relational_reference"],
                "source_kind": "existing",
                "source_query": unsafe_source,
            },
        )
        with pytest.raises(RequestPlanningError):
            validate_request_plan(
                {"actions": [{"kind": "retrieve", "plan": unsafe}], "limitations": []}, schema
            )


def test_r1_singular_relational_read_uses_current_member_only(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route a relational read to Chloe from Edgar's current linked fact."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Chloe]]."))
    write_note(vault, "people/chloe.md", "chloe", "Chloe", fact("Chloe vive en Lyon."))
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        application, "get_context", lambda *args, **kwargs: calls.append(kwargs) or object()
    )
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )
    result = run(vault, schema, plan)
    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert calls[0]["allowed_note_ids"] == frozenset({"chloe"})
    assert len(list(vault.rglob("*.md"))) == 2


def test_relational_resolution_keeps_later_than_32_current_fact_candidates_reachable(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permit Core's contextual boundary to choose a valid relation after 32 other facts."""
    vault = tmp_path / "vault"
    vault.mkdir()
    other_facts: list[str] = []
    for ordinal in range(33):
        name = f"Persona {ordinal}"
        note_id = f"persona-{ordinal}"
        write_note(vault, f"people/{note_id}.md", note_id, name, "")
        other_facts.append(fact(f"Conoce a [[people/{note_id}|{name}]].", ordinal))
    write_note(vault, "people/chloe.md", "chloe", "Chloe", "")
    other_facts.append(fact("Mi hija es [[Chloe]].", 33))
    write_note(vault, "people/edgar.md", "edgar", "Edgar", "\n\n".join(other_facts))
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        application, "get_context", lambda *args, **kwargs: calls.append(kwargs) or object()
    )
    reasoner = MatchingFactReasoner("Mi hija es Chloe")
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )
    result = run(vault, schema, plan, reasoner=reasoner)
    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert len(reasoner.requests[0].candidates) == 34
    assert reasoner.requests[0].candidates[-1].evidence == "Mi hija es Chloe."
    assert calls[0]["allowed_note_ids"] == frozenset({"chloe"})


def test_complete_set_relational_read_restricts_retrieval_to_every_current_member(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass an exact complete parent set to existing retrieval without an aggregate engine."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault, "people/edgar.md", "edgar", "Edgar", fact("Mis padres son [[Ana]] y [[Luis]].")
    )
    write_note(vault, "people/ana.md", "ana", "Ana", "")
    write_note(vault, "people/luis.md", "luis", "Luis", "")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        application, "get_context", lambda *args, **kwargs: calls.append(kwargs) or object()
    )
    plan = RequestPlan(
        (
            RetrieveAction(
                relational_selection(
                    "mis padres", source_kind="self", source_query=None, members="complete_set"
                )
            ),
        ),
        (),
    )
    result = run(vault, schema, plan)
    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert calls[0]["allowed_note_ids"] == frozenset({"ana", "luis"})


def test_incomplete_complete_set_read_defers_without_calling_retrieval(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep plural relation retrieval all-or-clarify when a current member is missing."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault, "people/edgar.md", "edgar", "Edgar", fact("Mis padres son [[Ana]] y [[Luis]].")
    )
    write_note(vault, "people/ana.md", "ana", "Ana", "")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        application,
        "get_context",
        lambda *args, **kwargs: calls.append(kwargs) or pytest.fail("partial retrieval invoked"),
    )
    plan = RequestPlan(
        (
            RetrieveAction(
                relational_selection(
                    "mis padres", source_kind="self", source_query=None, members="complete_set"
                )
            ),
        ),
        (),
    )
    result = run(vault, schema, plan)
    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert result.action_results[0].reason == "relational_evidence_incomplete"
    assert calls == []


def test_w1_singular_relational_write_updates_child_and_never_creates(
    tmp_path: Path, schema: dict
) -> None:
    """Write the user's fact on the existing child through relationship-only preflight."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Chloe]]."))
    write_note(vault, "people/chloe.md", "chloe", "Chloe", "")
    selection = relational_selection("mi hija", source_kind="self", source_query=None)
    unit = KnowledgeUnit(selection, "record", (), (), ("Vive en Lyon.",), ())
    ordinary = decide_write_target(
        unit,
        repository=VaultRepository(vault),
        schema=schema,
        semantic_index=EmptyIndex(),
        embedder=EmptyEmbedder(),
        contextual_reasoner=FactReasoner(),
        semantic_limit=5,
    )
    assert ordinary.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION
    result = run(vault, schema, RequestPlan((WriteAction((unit,)),), ()))
    assert result.status is application.ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("chloe",)
    assert "Vive en Lyon." in parse_note((vault / "people/chloe.md").read_text()).content
    assert len(list(vault.rglob("*.md"))) == 2


def test_singular_relational_target_preserves_explicit_named_reference(
    tmp_path: Path, schema: dict
) -> None:
    """Keep the inherited KnowledgeReference path for a fact on a resolved relation member."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/marta.md", "marta", "Marta", fact("Mi amiga es [[Ana]]."))
    write_note(vault, "people/ana.md", "ana", "Ana", "")
    write_note(vault, "organizations/airbus.md", "airbus", "Airbus", "", note_type="concept")
    action = WriteAction(
        (
            KnowledgeUnit(
                relational_selection("mi amiga", source_kind="existing", source_query="Marta"),
                "record",
                (),
                (),
                ("Trabaja en {{ref:0}}.",),
                (KnowledgeReference(1, "organization", "Airbus"),),
            ),
            KnowledgeUnit(
                SelectionCriteria("Airbus", "Airbus", "concept", (), None),
                "record",
                (),
                (),
                (),
                (),
            ),
        )
    )
    before_airbus = (vault / "organizations/airbus.md").read_bytes()
    result = run(vault, schema, RequestPlan((action,), ()))
    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert "ana" in result.affected_stable_note_ids
    assert (
        "[[organizations/airbus|Airbus]]"
        in parse_note((vault / "people/ana.md").read_text()).content
    )
    assert (vault / "organizations/airbus.md").read_bytes() == before_airbus


def test_opposite_viewpoint_link_can_ground_singular_target(tmp_path: Path, schema: dict) -> None:
    """Use a current incoming child-to-parent fact without writing an inverse fact."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", "")
    write_note(
        vault,
        "people/chloe.md",
        "chloe",
        "Chloe",
        fact("Mi padre es [[people/edgar|Edgar]]."),
    )
    unit = KnowledgeUnit(
        relational_selection("mi hija", source_kind="self", source_query=None),
        "record",
        (),
        (),
        ("Vive en Lyon.",),
        (),
    )
    before_source = (vault / "people/edgar.md").read_bytes()
    reasoner = FactReasoner()
    result = run(vault, schema, RequestPlan((WriteAction((unit,)),), ()), reasoner=reasoner)
    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert result.affected_stable_note_ids == ("chloe",)
    assert (vault / "people/edgar.md").read_bytes() == before_source
    assert "Vive en Lyon." in parse_note((vault / "people/chloe.md").read_text()).content
    assert "people/edgar" not in reasoner.requests[0].candidates[0].evidence


def test_w2_complete_set_writes_one_source_fact_and_no_member_notes(
    tmp_path: Path, schema: dict
) -> None:
    """Expand complete participants into Slice 2's exact member-binding path."""
    vault = tmp_path / "vault"
    vault.mkdir()
    for name in ("Marta", "Juan", "Pedro"):
        write_note(vault, f"people/{name.lower()}.md", name.lower(), name, "")
    write_note(
        vault,
        "events/visit.md",
        "visit",
        "Visita",
        fact("Asistieron [[Marta]], [[Juan]] y [[Pedro]]."),
        note_type="journal_entry",
    )
    before = {
        name: (vault / f"people/{name.lower()}.md").read_bytes()
        for name in ("Marta", "Juan", "Pedro")
    }
    selection = relational_selection(
        "todos los que estaban ayer",
        source_kind="existing",
        source_query="Visita",
        members="complete_set",
    )
    unit = KnowledgeUnit(
        selection, "record", (), (), ("Todos los que estaban ayer fuimos al colegio Laia.",), ()
    )
    result = run(vault, schema, RequestPlan((WriteAction((unit,)),), ()))
    assert result.status is application.ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("visit",)
    content = parse_note((vault / "events/visit.md").read_text()).content
    assert "Todos los que estaban ayer fuimos al colegio Laia." in content
    assert all(f"[[people/{name.lower()}|{name}]]" in content for name in before)
    assert all(
        (vault / f"people/{name.lower()}.md").read_bytes() == before[name] for name in before
    )
    assert len(list(vault.rglob("*.md"))) == 4


def test_c1_ambiguity_defers_without_mutation(tmp_path: Path, schema: dict) -> None:
    """Abstain when two current linked facts could ground the singular relation."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "people/edgar.md",
        "edgar",
        "Edgar",
        fact("Mi hija es [[Chloe]].") + "\n\n" + fact("Mi hija es [[Marta]].", 1),
    )
    write_note(vault, "people/chloe.md", "chloe", "Chloe", "")
    write_note(vault, "people/marta.md", "marta", "Marta", "")
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    unit = KnowledgeUnit(
        relational_selection("mi hija", source_kind="self", source_query=None),
        "record",
        (),
        (),
        ("Vive en Lyon.",),
        (),
    )
    result = run(vault, schema, RequestPlan((WriteAction((unit,)),), ()))
    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert all(path.read_bytes() == content for path, content in before.items())


def test_w1_stale_source_between_resolution_and_preflight_defers(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-ground the fact locator immediately before authorizing a fact-bearing target."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Chloe]]."))
    write_note(vault, "people/chloe.md", "chloe", "Chloe", "")
    before_child = (vault / "people/chloe.md").read_bytes()
    original = application.resolve_relational_reference

    def stale_after_resolution(selection: SelectionCriteria, **kwargs: Any) -> Any:
        """Change only the disposable source after Core first resolves its locator."""
        resolved = original(selection, **kwargs)
        write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Marta]]."))
        return resolved

    monkeypatch.setattr(application, "resolve_relational_reference", stale_after_resolution)
    unit = KnowledgeUnit(
        relational_selection("mi hija", source_kind="self", source_query=None),
        "record",
        (),
        (),
        ("Vive en Lyon.",),
        (),
    )
    result = run(vault, schema, RequestPlan((WriteAction((unit,)),), ()))
    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert (vault / "people/chloe.md").read_bytes() == before_child
    assert len(list(vault.rglob("*.md"))) == 2


def test_c2_incomplete_set_defers_all_without_source_mutation(tmp_path: Path, schema: dict) -> None:
    """A stale participant link cannot produce a partial subset or source write."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/marta.md", "marta", "Marta", "")
    write_note(
        vault,
        "events/visit.md",
        "visit",
        "Visita",
        fact("Asistieron [[Marta]] y [[Pedro]]."),
        note_type="journal_entry",
    )
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    unit = KnowledgeUnit(
        relational_selection(
            "todos los que estaban ayer",
            source_kind="existing",
            source_query="Visita",
            members="complete_set",
        ),
        "record",
        (),
        (),
        ("Fuimos al colegio Laia.",),
        (),
    )
    result = run(vault, schema, RequestPlan((WriteAction((unit,)),), ()))
    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert all(path.read_bytes() == content for path, content in before.items())


def test_s1_named_and_s2_self_writes_keep_ordinary_targeting(tmp_path: Path, schema: dict) -> None:
    """Leave named Marta and the authenticated human on their established write paths."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", "")
    write_note(vault, "people/marta.md", "marta", "Marta", "")
    named = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "record",
        (),
        (),
        ("Vive en Lyon.",),
        (),
    )
    self_unit = KnowledgeUnit(
        SelectionCriteria(None, "yo", "person", (), None, self_target="self"),
        "record",
        (),
        (),
        ("Vivo en Toulouse.",),
        (),
    )
    result = run(vault, schema, RequestPlan((WriteAction((named,)), WriteAction((self_unit,))), ()))
    assert result.status is application.ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("marta", "edgar")
    assert "Vive en Lyon." in parse_note((vault / "people/marta.md").read_text()).content
    assert "Vivo en Toulouse." in parse_note((vault / "people/edgar.md").read_text()).content


def test_s3_semantic_s4_named_reference_s5_bulk_remain_non_relational(schema: dict) -> None:
    """Keep ordinary query, explicit KnowledgeReference, and all_matching contracts intact."""
    descriptive = SelectionCriteria(None, "la tienda de la esquina", None, (), None)
    assert descriptive.relational_reference is None
    named = SelectionCriteria("Marta", "Marta", "person", (), None)
    airbus = SelectionCriteria("Airbus", "Airbus", "organization", (), None)
    action = WriteAction(
        (
            KnowledgeUnit(
                named,
                "record",
                (),
                (),
                ("Marta conoce {{ref:0}}.",),
                (KnowledgeReference(1, "organization", "Airbus"),),
            ),
            KnowledgeUnit(airbus, "record", (), (), (), ()),
        )
    )
    assert action.units[0].references[0].mention == "Airbus"
    assert all(unit.target.relational_reference is None for unit in action.units)
    bulk = KnowledgeUnit(
        SelectionCriteria(None, "all matching notes", "person", (), None),
        "record",
        (),
        (),
        ("Checked today.",),
        (),
        cardinality="all_matching",
    )
    assert bulk.cardinality == "all_matching"
    assert bulk.target.relational_reference is None
    assert (
        validate_request_plan(
            {
                "actions": [
                    {
                        "kind": "retrieve",
                        "plan": {
                            "entity": None,
                            "query": descriptive.query,
                            "type": None,
                            "filters": [],
                            "link_scope": None,
                            "self_target": None,
                            "relational_reference": None,
                        },
                    }
                ],
                "limitations": [],
            },
            schema,
        )
        .actions[0]
        .plan.relational_reference
        is None
    )
