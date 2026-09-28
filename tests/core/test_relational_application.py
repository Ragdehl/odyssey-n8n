"""Provider-free Slice 3 contract and application evidence with synthetic Markdown."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import odyssey_core.application as application
from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.clarification import ClarificationChoice
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.reference_preflight import current_identity_guard
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
from odyssey_core.semantic import SemanticEntityCandidate
from odyssey_core.semantic_sets import SetEvidenceSelection, SetMemberOccurrence
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


class MappedIndex:
    """Return deterministic semantic candidates for selected natural-language queries."""

    def __init__(self, mapping: dict[str, tuple[SemanticEntityCandidate, ...]]) -> None:
        self.mapping = mapping

    def find_candidates(
        self, _embedder: object, reference: str, **kwargs: Any
    ) -> tuple[SemanticEntityCandidate, ...]:
        """Return only candidates assigned to the exact fixture query."""
        return self.mapping.get(reference, ())[: int(kwargs["limit"])]


class RelationshipContextEmbedder:
    """Provide deterministic local relevance vectors for shared-fact retrieval coverage."""

    model_name = "tests/relationship-context"
    model_version = "1"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed canonical fact snippets without using a provider."""
        return [self._embed(text) for text in texts]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed ordinary retrieval wording without using a provider."""
        return [self._embed(text) for text in texts]

    @staticmethod
    def _embed(text: str) -> list[float]:
        """Preserve separate entity and school dimensions for the fixture."""
        lowered = text.casefold()
        return [float("bruno" in lowered), float("colegio" in lowered), 0.25]


class FixedContextIndex:
    """Return the already-grounded ordinary Bruno target as the normal retrieval candidate."""

    def __init__(self, path: str, source_hash: str) -> None:
        """Keep current canonical provenance needed by the real context loader."""
        self.path = path
        self.source_hash = source_hash

    def find_candidates(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        """Expose one normal ranked note without granting relationship authority to this stub."""
        return (
            SimpleNamespace(
                id="bruno",
                path=self.path,
                type="person",
                primary_name="Bruno Test",
                source_hash=self.source_hash,
                similarity=1.0,
            ),
        )


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


class RelevantFactSelector:
    """Propose every fixture fact whose visible wording directly supports the relation."""

    def __init__(self, wording: str) -> None:
        """Keep the semantic relevance phrase independent from the one-choice reasoner."""
        self.wording = wording.casefold()
        self.requests: list[Any] = []

    def select(self, request: Any) -> SetEvidenceSelection:
        """Return each matching supplied fact with one bounded visible-text occurrence."""
        self.requests.append(request)
        selected = tuple(
            candidate
            for candidate in request.candidates
            if self.wording in candidate.text.casefold()
        )
        return SetEvidenceSelection(
            tuple(candidate.id for candidate in selected),
            tuple(SetMemberOccurrence(candidate.id, "literal", 0, 1) for candidate in selected),
        )


class AllFactSelector:
    """Select every supplied canonical relationship fact for Core pipeline tests."""

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def select(self, request: Any) -> SetEvidenceSelection:
        """Return the complete supplied fact batch with bounded literal evidence markers."""
        self.requests.append(request)
        return SetEvidenceSelection(
            tuple(candidate.id for candidate in request.candidates),
            tuple(
                SetMemberOccurrence(candidate.id, "literal", 0, 1)
                for candidate in request.candidates
            ),
        )


class StaticFactSelector:
    """Return one controlled relevance result for Core fail-closed regression coverage."""

    def __init__(self, outcome: SetEvidenceSelection | Exception) -> None:
        """Keep a deterministic selector response or failure for one synthetic invocation."""
        self.outcome = outcome

    def select(self, request: Any) -> SetEvidenceSelection:
        """Return the configured response without deriving a target identity."""
        del request
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


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


class MappedReasoner(FactReasoner):
    """Select a predetermined candidate ID per contextual reference wording."""

    def __init__(self, decisions: dict[str, str | None]) -> None:
        super().__init__()
        self.decisions = decisions

    def resolve(self, request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return a closed decision only when the requested candidate was supplied by Core."""
        self.requests.append(request)
        selected = self.decisions[request.reference]
        if selected is None:
            return ({"outcome": "AMBIGUOUS", "id": None}, {})
        assert selected in {candidate.id for candidate in request.candidates}
        return ({"outcome": "RESOLVED", "id": selected}, {})


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
    semantic_index: Any | None = None,
    selector: Any | None = None,
    clarification_choice: ClarificationChoice | None = None,
) -> application.ApplicationResult:
    """Execute one synthetic plan through the real Core application boundary."""
    return application.execute_request(
        "synthetic request",
        planner=SimpleNamespace(plan=lambda _request: plan),
        repository=VaultRepository(vault),
        schema=schema,
        context_index=object(),
        semantic_index=semantic_index or EmptyIndex(),
        embedder=EmptyEmbedder(),
        contextual_reasoner=reasoner or FactReasoner(),
        actor="test",
        now="2026-09-24T12:00:00Z",
        context_limit=5,
        writer=ForbiddenWriter(),
        semantic_set_selector=selector or RelevantFactSelector(_plan_relation_wording(plan)),
        authenticated_actor=ACTOR,
        self_binding_repository=SelfBinding(),
        request_id_factory=lambda: "relational-test",
        clarification_choice=clarification_choice,
    )


def _plan_relation_wording(plan: RequestPlan) -> str:
    """Extract the fixture's direct relationship wording for the deterministic selector."""
    for action in plan.actions:
        if isinstance(action, RetrieveAction) and action.plan.relational_reference is not None:
            return action.plan.relational_reference.reference
        if isinstance(action, WriteAction):
            for unit in action.units:
                if unit.target.relational_reference is not None:
                    return unit.target.relational_reference.reference
    return ""


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
    retrieval_modes = planner_result_json_schema(schema)["properties"]["result"]["anyOf"][0][
        "properties"
    ]["actions"]["items"]["anyOf"][0]["properties"]["plan"]
    assert "relational_reference" in retrieval_modes["required"]
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


def test_singular_corrobating_facts_converge_on_one_current_identity(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two current facts for the same spouse corroborate a singular self-relative read."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "people/edgar.md",
        "edgar",
        "Edgar",
        fact("Mi mujer es [[Beatriz]].", 0) + "\n\n" + fact("Mi mujer es [[Beatriz]].", 1),
    )
    write_note(vault, "people/beatriz.md", "beatriz", "Beatriz Carrero", "")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        application, "get_context", lambda *args, **kwargs: calls.append(kwargs) or object()
    )
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi mujer", source_kind="self", source_query=None)),),
        (),
    )

    selector = RelevantFactSelector("mi mujer")
    reasoner = FactReasoner()
    result = run(vault, schema, plan, reasoner=reasoner, selector=selector)

    assert result.status is application.ApplicationStatus.COMPLETED
    assert calls[0]["allowed_note_ids"] == frozenset({"beatriz"})
    assert len(selector.requests) == 1
    assert len(selector.requests[0].candidates) == 2
    assert reasoner.requests == []


def test_multi_target_singular_fact_offers_each_grounded_identity_without_guessing(
    tmp_path: Path, schema: dict
) -> None:
    """A selected multi-link child fact yields bounded existing clarification options."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "people/edgar.md",
        "edgar",
        "Edgar",
        fact("Mis hijos son [[Cloe]] y [[Bruno]].", 0),
    )
    write_note(vault, "people/cloe.md", "cloe", "Cloe", "")
    write_note(vault, "people/bruno.md", "bruno", "Bruno", "")
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hijo", source_kind="self", source_query=None)),),
        (),
    )

    result = run(vault, schema, plan, selector=RelevantFactSelector("mis hijos"))

    action = result.action_results[0]
    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert action.reason == "relational_singular_ambiguous"
    assert action.candidate_note_ids == ("cloe", "bruno")


def test_conflicting_singular_relation_targets_offer_options_only_for_reads(
    tmp_path: Path, schema: dict
) -> None:
    """A read may clarify two current targets while write preflight remains unchanged."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "people/edgar.md",
        "edgar",
        "Edgar",
        fact("Mi hija es [[Cloe]].", 0) + "\n\n" + fact("Mi hija es [[Marta]].", 1),
    )
    write_note(vault, "people/cloe.md", "cloe", "Cloe", "")
    write_note(vault, "people/marta.md", "marta", "Marta", "")
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )

    selector = RelevantFactSelector("mi hija")
    reasoner = FactReasoner()
    result = run(vault, schema, plan, reasoner=reasoner, selector=selector)

    action = result.action_results[0]
    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert action.reason == "relational_evidence_ambiguous"
    assert action.candidate_note_ids == ("cloe", "marta")
    assert len(selector.requests) == 1
    assert len(selector.requests[0].candidates) == 2
    assert reasoner.requests == []


def test_semantic_relation_wording_selects_all_relevant_facts_without_literal_matching(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep semantic spouse wording while Core, rather than the reasoner, owns identity choice."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi mujer es [[Beatriz]]."))
    write_note(vault, "people/beatriz.md", "beatriz", "Beatriz Carrero", "")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        application, "get_context", lambda *args, **kwargs: calls.append(kwargs) or object()
    )
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi pareja", source_kind="self", source_query=None)),),
        (),
    )

    result = run(vault, schema, plan, selector=RelevantFactSelector("mi mujer"))

    assert result.status is application.ApplicationStatus.COMPLETED
    assert calls[0]["allowed_note_ids"] == frozenset({"beatriz"})


def test_relational_read_rejects_invalid_or_failed_multi_fact_relevance_selection(
    tmp_path: Path, schema: dict
) -> None:
    """Fail closed when read relevance selection is outside its batch or cannot run."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Cloe]]."))
    write_note(vault, "people/cloe.md", "cloe", "Cloe", "")
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )
    invalid = StaticFactSelector(
        SetEvidenceSelection(
            ("outside-batch",), (SetMemberOccurrence("outside-batch", "literal", 0, 1),)
        )
    )
    for selector, reason in (
        (invalid, "relational_evidence_incomplete"),
        (
            StaticFactSelector(RuntimeError("selector unavailable")),
            "relational_relevance_unavailable",
        ),
    ):
        result = run(vault, schema, plan, selector=selector)
        assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
        assert result.action_results[0].reason == reason


def test_relational_read_scope_uncertainty_never_selects_one_identity(
    tmp_path: Path, schema: dict
) -> None:
    """Preserve ambiguity when the bounded relevance selector cannot establish scope."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Cloe]]."))
    write_note(vault, "people/cloe.md", "cloe", "Cloe", "")
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )

    result = run(
        vault, schema, plan, selector=StaticFactSelector(SetEvidenceSelection((), (), True))
    )

    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert result.action_results[0].reason == "relational_evidence_ambiguous"


@pytest.mark.parametrize(
    "selection",
    [
        SetEvidenceSelection(("relational-0",), ()),
        SetEvidenceSelection(
            ("relational-0",), (SetMemberOccurrence("relational-0", "unsupported", 0, 1),)
        ),
        SetEvidenceSelection(
            ("relational-0",), (SetMemberOccurrence("relational-0", "literal", 0, 10_000),)
        ),
    ],
)
def test_relational_read_requires_valid_direct_occurrence_for_every_selected_fact(
    tmp_path: Path, schema: dict, selection: SetEvidenceSelection
) -> None:
    """Reject relevance proposals without a valid direct occurrence in the supplied fact."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Cloe]]."))
    write_note(vault, "people/cloe.md", "cloe", "Cloe", "")
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )

    result = run(vault, schema, plan, selector=StaticFactSelector(selection))

    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert result.action_results[0].reason == "relational_evidence_incomplete"


def test_relational_read_with_no_relevant_fact_returns_missing_evidence(
    tmp_path: Path, schema: dict
) -> None:
    """Do not turn an empty relevance proposal into a generic ambiguous identity result."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi padre es [[Juan]]."))
    write_note(vault, "people/juan.md", "juan", "Juan", "")
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )

    result = run(vault, schema, plan, selector=StaticFactSelector(SetEvidenceSelection((), ())))

    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert result.action_results[0].reason == "relational_evidence_unavailable"


def test_relational_read_projects_selected_incoming_fact_to_its_complete_source_identity(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the established one-hop incoming source projection under multi-fact selection."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", "")
    write_note(vault, "people/cloe.md", "cloe", "Cloe", fact("Mi padre es [[Edgar]]."))
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        application, "get_context", lambda *args, **kwargs: calls.append(kwargs) or object()
    )
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )

    result = run(vault, schema, plan, selector=RelevantFactSelector("mi padre"))

    assert result.status is application.ApplicationStatus.COMPLETED
    assert calls[0]["allowed_note_ids"] == frozenset({"cloe"})


def test_relational_read_rejects_dangling_or_more_than_four_selected_targets(
    tmp_path: Path, schema: dict
) -> None:
    """Do not turn malformed or unbounded selected target sets into a partial answer."""
    dangling = tmp_path / "dangling"
    dangling.mkdir()
    write_note(dangling, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Missing]]."))
    singular = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )
    dangling_result = run(dangling, schema, singular, selector=RelevantFactSelector("mi hija"))
    assert dangling_result.action_results[0].reason == "relational_evidence_incomplete"

    crowded = tmp_path / "crowded"
    crowded.mkdir()
    names = ("A", "B", "C", "D", "E")
    for name in names:
        write_note(crowded, f"people/{name.lower()}.md", name.lower(), name, "")
    links = " y ".join(f"[[{name}]]" for name in names)
    write_note(crowded, "people/edgar.md", "edgar", "Edgar", fact(f"Mis hijos son {links}."))
    crowded_result = run(
        crowded,
        schema,
        RequestPlan(
            (
                RetrieveAction(
                    relational_selection("mi hijo", source_kind="self", source_query=None)
                ),
            ),
            (),
        ),
        selector=RelevantFactSelector("mis hijos"),
    )
    assert crowded_result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert crowded_result.action_results[0].reason == "relational_evidence_ambiguous"
    assert crowded_result.action_results[0].candidate_note_ids == ()


def test_relational_clarification_rechecks_source_and_target_guards(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chosen relational identity cannot survive changed source or target Markdown."""
    vault = tmp_path / "vault"
    vault.mkdir()
    source_body = fact("Mi hija es [[Cloe]].", 0) + "\n\n" + fact("Mi hija es [[Marta]].", 1)
    write_note(vault, "people/edgar.md", "edgar", "Edgar", source_body)
    write_note(vault, "people/cloe.md", "cloe", "Cloe", "")
    write_note(vault, "people/marta.md", "marta", "Marta", "")
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )
    initial = run(vault, schema, plan, selector=RelevantFactSelector("mi hija"))
    action = initial.action_results[0]
    assert action.relational_evidence_guard is not None
    choice = ClarificationChoice(
        "cloe",
        current_identity_guard(VaultRepository(vault), schema, "cloe"),
        action.relational_evidence_guard,
    )

    write_note(vault, "people/cloe.md", "cloe", "Cloe", fact("Cloe vive en Lyon."))
    stale_target = run(
        vault,
        schema,
        plan,
        selector=RelevantFactSelector("mi hija"),
        clarification_choice=choice,
    )
    assert stale_target.action_results[0].reason == "clarification_evidence_changed"

    write_note(vault, "people/cloe.md", "cloe", "Cloe", "")
    write_note(vault, "people/edgar.md", "edgar", "Edgar", fact("Mi hija es [[Cloe]]."))
    stale_source = run(
        vault,
        schema,
        plan,
        selector=RelevantFactSelector("mi hija"),
        clarification_choice=choice,
    )
    assert stale_source.action_results[0].reason == "clarification_evidence_changed"

    # A fresh continuation re-resolves the same bounded options and may authorize only
    # the selected stable identity after both source and target guards match again.
    write_note(vault, "people/edgar.md", "edgar", "Edgar", source_body)
    current_choice = ClarificationChoice(
        "cloe",
        current_identity_guard(VaultRepository(vault), schema, "cloe"),
        run(vault, schema, plan, selector=RelevantFactSelector("mi hija"))
        .action_results[0]
        .relational_evidence_guard,
    )
    # The empty fixture target produces no presentation context, so observe the exact
    # identity authority handed to retrieval at the Core/application boundary.
    allowed: list[frozenset[str]] = []
    monkeypatch.setattr(
        application,
        "get_context",
        lambda *args, **kwargs: allowed.append(kwargs["allowed_note_ids"]) or object(),
    )
    resumed = run(
        vault,
        schema,
        plan,
        selector=RelevantFactSelector("mi hija"),
        clarification_choice=current_choice,
    )

    assert resumed.status is application.ApplicationStatus.COMPLETED
    assert allowed == [frozenset({"cloe"})]


def test_ordinary_named_read_enriches_bruno_with_one_linked_shared_source_fact(
    tmp_path: Path, schema: dict
) -> None:
    """Keep a shared school fact once on Cena while exposing it to an ordinary Bruno read."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/clara.md", "clara", "Clara Test", "")
    write_note(vault, "people/marta.md", "marta", "Marta Test", "")
    write_note(vault, "people/bruno.md", "bruno", "Bruno Test", fact("Bruno Test vive en París."))
    source_fact = (
        "Todos fuimos al colegio Laia con [[people/clara|Clara Test]], "
        "[[people/bruno|Bruno Test]] y [[people/marta|Marta Test]]."
    )
    write_note(
        vault,
        "journal/cena.md",
        "cena",
        "Cena",
        fact(source_fact),
        note_type="journal_entry",
    )
    repository = VaultRepository(vault)
    bruno_path = "people/bruno.md"
    bruno_raw = repository.read_text(bruno_path)
    plan = RequestPlan(
        (
            RetrieveAction(
                SelectionCriteria(
                    "Bruno Test", "¿A qué colegio fue Bruno Test?", "person", (), None
                )
            ),
        ),
        (),
    )

    result = application.execute_request(
        "¿A qué colegio fue Bruno Test?",
        planner=SimpleNamespace(plan=lambda _request: plan),
        repository=repository,
        schema=schema,
        context_index=FixedContextIndex(
            bruno_path, hashlib.sha256(bruno_raw.encode("utf-8")).hexdigest()
        ),
        semantic_index=EmptyIndex(),
        embedder=RelationshipContextEmbedder(),
        contextual_reasoner=FactReasoner(),
        actor="test",
        now="2026-09-24T12:00:00Z",
        context_limit=1,
        writer=ForbiddenWriter(),
        request_id_factory=lambda: "ordinary-backlink-read",
    )

    retrieval = result.action_results[0].retrieval
    assert result.action_results[0].status is application.ActionStatus.COMPLETED
    assert retrieval is not None
    assert [item.id for item in retrieval.items] == ["bruno"]
    assert [(item.target_id, item.source_id, item.content) for item in retrieval.related_items] == [
        ("bruno", "cena", source_fact)
    ]
    assert repository.read_text(bruno_path) == bruno_raw
    assert "colegio Laia" not in bruno_raw


def test_relational_resolution_keeps_later_than_32_current_fact_candidates_reachable(
    tmp_path: Path, schema: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permit bounded multi-fact relevance selection to reach a late current relation."""
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
    selector = RelevantFactSelector("mi hija")
    plan = RequestPlan(
        (RetrieveAction(relational_selection("mi hija", source_kind="self", source_query=None)),),
        (),
    )
    result = run(vault, schema, plan, reasoner=FactReasoner(), selector=selector)
    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert len(selector.requests[0].candidates) == 34
    assert selector.requests[0].candidates[-1].text == "Mi hija es Chloe."
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
    unresolved = decide_write_target(
        unit,
        repository=VaultRepository(vault),
        schema=schema,
        semantic_index=EmptyIndex(),
        embedder=EmptyEmbedder(),
        contextual_reasoner=FactReasoner("UNRESOLVED"),
        semantic_limit=5,
    )
    assert unresolved.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION
    assert "Vive en Lyon." not in parse_note((vault / "people/chloe.md").read_text()).content
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


def test_qualified_self_relation_narrows_candidates_then_uses_backlink_evidence(
    tmp_path: Path, schema: dict
) -> None:
    """Use the self relationship as a universe, then resolve a rich qualifier from backlinks."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "people/edgar.md",
        "edgar",
        "Edgar",
        fact("Mis hijas son [[people/cloe|Cloe]] y [[people/marta|Marta]].")
        + "\n\n"
        + fact("[[people/cloe|Cloe]] es mi hija mayor.", 1),
    )
    write_note(vault, "people/cloe.md", "cloe", "Cloe", "")
    write_note(vault, "people/marta.md", "marta", "Marta", "")
    before_self = (vault / "people/edgar.md").read_bytes()
    before_marta = (vault / "people/marta.md").read_bytes()
    query = "mi hija mayor"
    selection = SelectionCriteria(
        None,
        query,
        "person",
        (),
        None,
        relational_reference=RelationalReference("mi hija", "self", None, "one"),
    )
    unit = KnowledgeUnit(selection, "record", (), (), ("Adora el chocolate.",), ())
    reasoner = MatchingFactReasoner("mi hija mayor")
    selector = AllFactSelector()

    result = run(
        vault,
        schema,
        RequestPlan((WriteAction((unit,)),), ()),
        reasoner=reasoner,
        selector=selector,
    )

    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert result.affected_stable_note_ids == ("cloe",)
    assert (vault / "people/edgar.md").read_bytes() == before_self
    assert (vault / "people/marta.md").read_bytes() == before_marta
    assert "Adora el chocolate." in parse_note((vault / "people/cloe.md").read_text()).content
    assert len(selector.requests) == 1
    assert selector.requests[0].query == "mi hija"
    assert len(reasoner.requests) == 1
    assert reasoner.requests[0].reference == query
    supplied = {candidate.id: candidate.evidence for candidate in reasoner.requests[0].candidates}
    assert set(supplied) == {"cloe", "marta"}
    assert "incoming; source=Edgar (person)" in supplied["cloe"]
    assert "mi hija mayor" in supplied["cloe"].casefold()
    assert "mi hija mayor" not in supplied["marta"].casefold()


def test_qualified_existing_source_relation_can_start_from_incoming_backlinks(
    tmp_path: Path, schema: dict
) -> None:
    """Find Bruno's related people from incoming links before applying the full target description."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/bruno.md", "bruno", "Bruno", "")
    write_note(
        vault,
        "people/marta.md",
        "marta",
        "Marta",
        fact("[[people/bruno|Bruno]] es mi amigo.") + "\n\n" + fact("Vive en Lyon.", 1),
    )
    write_note(
        vault,
        "people/ana.md",
        "ana",
        "Ana",
        fact("[[people/bruno|Bruno]] es mi amigo.") + "\n\n" + fact("Vive en París.", 1),
    )
    before_bruno = (vault / "people/bruno.md").read_bytes()
    before_ana = (vault / "people/ana.md").read_bytes()
    query = "el amigo de Bruno que vive en Lyon"
    selection = SelectionCriteria(
        None,
        query,
        "person",
        (),
        None,
        relational_reference=RelationalReference("los amigos de Bruno", "existing", "Bruno", "one"),
    )
    unit = KnowledgeUnit(selection, "record", (), (), ("Se muda a Toulouse.",), ())
    reasoner = MatchingFactReasoner("Vive en Lyon")
    selector = AllFactSelector()

    result = run(
        vault,
        schema,
        RequestPlan((WriteAction((unit,)),), ()),
        reasoner=reasoner,
        selector=selector,
    )

    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert result.affected_stable_note_ids == ("marta",)
    assert (vault / "people/bruno.md").read_bytes() == before_bruno
    assert (vault / "people/ana.md").read_bytes() == before_ana
    assert "Se muda a Toulouse." in parse_note((vault / "people/marta.md").read_text()).content
    assert len(selector.requests) == 1
    assert selector.requests[0].query == "los amigos de Bruno"
    assert len(reasoner.requests) == 1
    assert reasoner.requests[0].reference == query
    assert {candidate.id for candidate in reasoner.requests[0].candidates} == {"marta", "ana"}


def test_qualified_relation_ambiguity_never_writes_or_escapes_anchor_scope(
    tmp_path: Path, schema: dict
) -> None:
    """Keep a rich relational WRITE fail-closed when qualifiers do not select one member."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "people/edgar.md",
        "edgar",
        "Edgar",
        fact("Mis hijas son [[people/cloe|Cloe]] y [[people/marta|Marta]]."),
    )
    write_note(vault, "people/cloe.md", "cloe", "Cloe", fact("Le gusta pintar."))
    write_note(vault, "people/marta.md", "marta", "Marta", fact("Le gusta pintar."))
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    query = "mi hija a la que le gusta pintar"
    selection = SelectionCriteria(
        None,
        query,
        "person",
        (),
        None,
        relational_reference=RelationalReference("mi hija", "self", None, "one"),
    )
    unit = KnowledgeUnit(selection, "record", (), (), ("Viaja mañana.",), ())
    reasoner = MappedReasoner({query: None})

    result = run(
        vault,
        schema,
        RequestPlan((WriteAction((unit,)),), ()),
        reasoner=reasoner,
        selector=AllFactSelector(),
    )

    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert result.affected_stable_note_ids == ()
    assert all(path.read_bytes() == content for path, content in before.items())
    action_result = result.action_results[0]
    assert action_result.reason == "relational_evidence_ambiguous"
    assert set(action_result.candidate_note_ids) == {"cloe", "marta"}
    assert {candidate.id for candidate in reasoner.requests[0].candidates} == {"cloe", "marta"}


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


def test_descriptive_possessive_target_updates_resolved_child_not_self(
    tmp_path: Path, schema: dict
) -> None:
    """Treat first-person possessive wording as identity evidence, not self write ownership."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault,
        "people/edgar.md",
        "edgar",
        "Edgar",
        fact("Mis hijos son [[people/cloe|Cloe]] y [[people/bruno|Bruno]]."),
    )
    write_note(vault, "people/cloe.md", "cloe", "Cloe", fact("Le gusta el fútbol."))
    write_note(vault, "people/bruno.md", "bruno", "Bruno", fact("Le gusta el ajedrez."))
    before_self = (vault / "people/edgar.md").read_bytes()
    before_bruno = (vault / "people/bruno.md").read_bytes()
    query = "mi hijo al que le gusta el fútbol"
    index = MappedIndex(
        {query: (SemanticEntityCandidate("edgar", "people/edgar.md", "person", "Edgar", 0.91),)}
    )
    reasoner = MappedReasoner({query: "cloe"})
    unit = KnowledgeUnit(
        SelectionCriteria(None, query, "person", (), None),
        "record",
        (),
        (),
        ("Adora el chocolate.",),
        (),
    )

    result = run(
        vault,
        schema,
        RequestPlan((WriteAction((unit,)),), ()),
        reasoner=reasoner,
        semantic_index=index,
    )

    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert result.affected_stable_note_ids == ("cloe",)
    assert (vault / "people/edgar.md").read_bytes() == before_self
    assert (vault / "people/bruno.md").read_bytes() == before_bruno
    assert "Adora el chocolate." in parse_note((vault / "people/cloe.md").read_text()).content
    supplied = {candidate.id for candidate in reasoner.requests[0].candidates}
    assert supplied == {"edgar", "cloe", "bruno"}


def test_semantic_fact_reference_resolves_existing_note_without_lookup_write(
    tmp_path: Path, schema: dict
) -> None:
    """Lower a descriptive provider reference to Core lookup and materialize only the source fact."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/bruno.md", "bruno", "Bruno", "")
    write_note(
        vault,
        "people/marta.md",
        "marta",
        "Marta",
        fact("Ayer cenó con Edgar y vive en Lyon."),
    )
    before_marta = (vault / "people/marta.md").read_bytes()
    reference_query = "la amiga con la que cenamos ayer"
    raw = {
        "actions": [
            {
                "kind": "write",
                "units": [
                    {
                        "target": {
                            "entity": "Bruno",
                            "query": "Bruno",
                            "type": "person",
                            "filters": [],
                            "link_scope": None,
                            "self_target": None,
                            "relational_reference": None,
                        },
                        "cardinality": "one",
                        "destination_type": None,
                        "intent": "record",
                        "properties": [],
                        "tag_changes": [],
                        "facts": ["Fue al concierto con {{ref:0}}."],
                        "references": [
                            {
                                "selection": {
                                    "entity": None,
                                    "query": reference_query,
                                    "type": "person",
                                    "filters": [],
                                },
                                "role": "companion",
                                "mention": "la amiga con la que cenamos ayer",
                            }
                        ],
                    }
                ],
            }
        ],
        "limitations": [],
    }
    plan = validate_request_plan(raw, schema)
    action = plan.actions[0]
    assert isinstance(action, WriteAction)
    assert len(action.units) == 2
    assert action.units[1].reference_lookup_only is True
    index = MappedIndex(
        {
            reference_query: (
                SemanticEntityCandidate("marta", "people/marta.md", "person", "Marta", 0.93),
            )
        }
    )
    reasoner = MappedReasoner({reference_query: "marta"})

    result = run(vault, schema, plan, reasoner=reasoner, semantic_index=index)

    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert result.affected_stable_note_ids == ("bruno",)
    bruno = parse_note((vault / "people/bruno.md").read_text()).content
    assert "[[people/marta|la amiga con la que cenamos ayer]]" in bruno
    assert (vault / "people/marta.md").read_bytes() == before_marta
    assert len(list(vault.rglob("*.md"))) == 2
    unit_results = result.action_results[0].unit_results
    assert unit_results[1].operation == "REFERENCE_BOUND"
    assert unit_results[1].materially_affected is False


def test_ambiguous_semantic_reference_defers_source_write_without_guessing(
    tmp_path: Path, schema: dict
) -> None:
    """Require clarification before a new semantic reference can affect the source fact."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/bruno.md", "bruno", "Bruno", "")
    write_note(vault, "people/marta.md", "marta", "Marta", fact("Vive en Lyon."))
    write_note(vault, "people/ana.md", "ana", "Ana", fact("Vive en Lyon."))
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    reference_query = "la amiga que vive en Lyon"
    raw = {
        "actions": [
            {
                "kind": "write",
                "units": [
                    {
                        "target": {
                            "entity": "Bruno",
                            "query": "Bruno",
                            "type": "person",
                            "filters": [],
                            "link_scope": None,
                            "self_target": None,
                            "relational_reference": None,
                        },
                        "cardinality": "one",
                        "destination_type": None,
                        "intent": "record",
                        "properties": [],
                        "tag_changes": [],
                        "facts": ["Fue al cine con {{ref:0}}."],
                        "references": [
                            {
                                "selection": {
                                    "entity": None,
                                    "query": reference_query,
                                    "type": "person",
                                    "filters": [],
                                },
                                "role": "companion",
                                "mention": "la amiga que vive en Lyon",
                            }
                        ],
                    }
                ],
            }
        ],
        "limitations": [],
    }
    plan = validate_request_plan(raw, schema)
    index = MappedIndex(
        {
            reference_query: (
                SemanticEntityCandidate("marta", "people/marta.md", "person", "Marta", 0.9),
                SemanticEntityCandidate("ana", "people/ana.md", "person", "Ana", 0.89),
            )
        }
    )
    reasoner = MappedReasoner({reference_query: None})

    result = run(vault, schema, plan, reasoner=reasoner, semantic_index=index)

    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert result.affected_stable_note_ids == ()
    assert all(path.read_bytes() == content for path, content in before.items())
    assert len(list(vault.rglob("*.md"))) == 3
    source_result, lookup_result = result.action_results[0].unit_results
    assert source_result.status is application.UnitStatus.DEFERRED
    assert source_result.reason == "DEPENDENCY_FAILED"
    assert lookup_result.reason == "ambiguous_existing_reference"
    assert set(lookup_result.candidates) == {"marta", "ana"}


def test_self_relationship_fact_uses_semantic_references_without_pairwise_writes(
    tmp_path: Path, schema: dict
) -> None:
    """Write one self fact linking several existing participants and leave participant notes untouched."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", "")
    write_note(vault, "people/axel.md", "axel", "Axel", "")
    write_note(vault, "people/denis.md", "denis", "Denis", "")
    before_axel = (vault / "people/axel.md").read_bytes()
    before_denis = (vault / "people/denis.md").read_bytes()
    raw = {
        "actions": [
            {
                "kind": "write",
                "units": [
                    {
                        "target": {
                            "entity": None,
                            "query": "yo",
                            "type": "person",
                            "filters": [],
                            "link_scope": None,
                            "self_target": "self",
                            "relational_reference": None,
                        },
                        "cardinality": "one",
                        "destination_type": None,
                        "intent": "record",
                        "properties": [],
                        "tag_changes": [],
                        "facts": ["{{ref:0}} y {{ref:1}} son mis compañeros de trabajo."],
                        "references": [
                            {
                                "selection": {
                                    "entity": "Axel",
                                    "query": "Axel",
                                    "type": "person",
                                    "filters": [],
                                },
                                "role": "coworker",
                                "mention": "Axel",
                            },
                            {
                                "selection": {
                                    "entity": "Denis",
                                    "query": "Denis",
                                    "type": "person",
                                    "filters": [],
                                },
                                "role": "coworker",
                                "mention": "Denis",
                            },
                        ],
                    }
                ],
            }
        ],
        "limitations": [],
    }
    plan = validate_request_plan(raw, schema)

    result = run(vault, schema, plan)

    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert result.affected_stable_note_ids == ("edgar",)
    self_content = parse_note((vault / "people/edgar.md").read_text()).content
    assert "[[people/axel|Axel]]" in self_content
    assert "[[people/denis|Denis]]" in self_content
    assert (vault / "people/axel.md").read_bytes() == before_axel
    assert (vault / "people/denis.md").read_bytes() == before_denis
    assert len(list(vault.rglob("*.md"))) == 3


def test_schema_backed_missing_reference_is_created_and_linked(
    tmp_path: Path, schema: dict
) -> None:
    """Create a missing typed project reference, then bind it into the self fact atomically."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(vault, "people/edgar.md", "edgar", "Edgar", "")
    write_note(vault, "people/axel.md", "axel", "Axel", "")
    write_note(vault, "people/denis.md", "denis", "Denis", "")
    before_axel = (vault / "people/axel.md").read_bytes()
    before_denis = (vault / "people/denis.md").read_bytes()
    raw = {
        "actions": [
            {
                "kind": "write",
                "units": [
                    {
                        "target": {
                            "entity": None,
                            "query": "yo",
                            "type": "person",
                            "filters": [],
                            "link_scope": None,
                            "self_target": "self",
                            "relational_reference": None,
                        },
                        "cardinality": "one",
                        "destination_type": None,
                        "intent": "record",
                        "properties": [],
                        "tag_changes": [],
                        "facts": ["{{ref:0}} y {{ref:1}} son mis compañeros en {{ref:2}}."],
                        "references": [
                            {
                                "selection": {
                                    "entity": "Axel",
                                    "query": "Axel",
                                    "type": "person",
                                    "filters": [],
                                },
                                "role": "coworker",
                                "mention": "Axel",
                            },
                            {
                                "selection": {
                                    "entity": "Denis",
                                    "query": "Denis",
                                    "type": "person",
                                    "filters": [],
                                },
                                "role": "coworker",
                                "mention": "Denis",
                            },
                            {
                                "selection": {
                                    "entity": "Faro",
                                    "query": "el proyecto Faro",
                                    "type": "project",
                                    "filters": [],
                                },
                                "role": "project",
                                "mention": "el proyecto Faro",
                            },
                        ],
                    }
                ],
            }
        ],
        "limitations": [],
    }
    plan = validate_request_plan(raw, schema)

    result = run(vault, schema, plan)

    assert result.status is application.ApplicationStatus.COMPLETED, result.action_results
    assert "edgar" in result.affected_stable_note_ids
    assert len(result.affected_stable_note_ids) == 2
    project_paths = [
        path
        for path in vault.rglob("*.md")
        if parse_note(path.read_text()).metadata.get("type") == "project"
    ]
    assert len(project_paths) == 1
    project_note = parse_note(project_paths[0].read_text())
    assert project_note.metadata["name"] == "Faro"
    assert project_note.content == ""
    assert project_note.metadata["id"] in result.affected_stable_note_ids
    self_content = parse_note((vault / "people/edgar.md").read_text()).content
    project_link = project_paths[0].with_suffix("").relative_to(vault).as_posix()
    assert "[[people/axel|Axel]]" in self_content
    assert "[[people/denis|Denis]]" in self_content
    assert f"[[{project_link}|el proyecto Faro]]" in self_content
    assert (vault / "people/axel.md").read_bytes() == before_axel
    assert (vault / "people/denis.md").read_bytes() == before_denis
    assert len(list(vault.rglob("*.md"))) == 4


def test_new_reference_is_rolled_back_when_consuming_fact_cannot_be_written(
    tmp_path: Path, schema: dict
) -> None:
    """Do not leave a new typed reference behind when its only source target is ambiguous."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write_note(
        vault, "people/cloe.md", "cloe", "Cloe", fact("Le gusta ver detectives de animales.")
    )
    write_note(
        vault,
        "people/bruno.md",
        "bruno",
        "Bruno Test",
        fact("Le gusta ver detectives de animales."),
    )
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    target_query = "mi hija a la que le gusta ver detectives de animales"
    raw = {
        "actions": [
            {
                "kind": "write",
                "units": [
                    {
                        "target": {
                            "entity": None,
                            "query": target_query,
                            "type": "person",
                            "filters": [],
                            "link_scope": None,
                            "self_target": None,
                            "relational_reference": None,
                        },
                        "cardinality": "one",
                        "destination_type": None,
                        "intent": "record",
                        "properties": [],
                        "tag_changes": [],
                        "facts": ["Trabaja en {{ref:0}}."],
                        "references": [
                            {
                                "selection": {
                                    "entity": "Aurora",
                                    "query": "el proyecto Aurora",
                                    "type": "project",
                                    "filters": [],
                                },
                                "role": "project",
                                "mention": "el proyecto Aurora",
                            }
                        ],
                    }
                ],
            }
        ],
        "limitations": [],
    }
    plan = validate_request_plan(raw, schema)
    index = MappedIndex(
        {
            target_query: (
                SemanticEntityCandidate("cloe", "people/cloe.md", "person", "Cloe", 0.95),
                SemanticEntityCandidate("bruno", "people/bruno.md", "person", "Bruno Test", 0.94),
            )
        }
    )
    reasoner = MappedReasoner({target_query: None})

    result = run(vault, schema, plan, reasoner=reasoner, semantic_index=index)

    assert result.status is application.ApplicationStatus.NEEDS_ATTENTION
    assert result.affected_stable_note_ids == ()
    assert len(list(vault.rglob("*.md"))) == 2
    assert all(path.read_bytes() == content for path, content in before.items())
    source_result, project_result = result.action_results[0].unit_results
    assert source_result.status is application.UnitStatus.DEFERRED
    assert source_result.reason == "ambiguous_existing_target"
    assert project_result.status is application.UnitStatus.DEFERRED
    assert project_result.reason == "DEPENDENT_FACT_NOT_WRITTEN"
