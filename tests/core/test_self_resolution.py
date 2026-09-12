"""Deterministic Phase 22E self-target resolution coverage."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import odyssey_core.application as application
from odyssey_core import (
    ActionStatus,
    ApplicationStatus,
    AuthenticatedActorContext,
    KnowledgeUnit,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    SelfBindingRepository,
    UnitStatus,
    WriteAction,
    create_entity,
    execute_request,
    validate_request_plan,
)
from odyssey_core.notes import parse_note, serialize_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"


def person(repository: VaultRepository, note_id: str, path: str, name: str = "Edgar") -> None:
    """Create one synthetic canonical person for self-resolution scenarios."""
    create_entity(
        repository,
        SCHEMA,
        path=path,
        entity_id=note_id,
        metadata={"name": name, "type": "person"},
        content=f"# {name}\n",
        actor="synthetic-test",
        now="2026-09-12T10:00:00+02:00",
    )


def self_selection(query: str = "where work") -> SelectionCriteria:
    """Build a validated direct SELF selection without a name or alias."""
    return SelectionCriteria(None, query, "person", (), None, "self")


def binding_setup(tmp_path: Path) -> tuple[VaultRepository, SelfBindingRepository]:
    """Create a synthetic vault and guarded self-binding repository."""
    (tmp_path / "vault" / "people").mkdir(parents=True)
    vault = VaultRepository(tmp_path / "vault")
    state = tmp_path / "state"
    state.mkdir()
    return vault, SelfBindingRepository(state, vault, SCHEMA)


def test_self_read_resolves_binding_before_identity_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SELF retrieval passes only the bound stable note ID to context retrieval."""
    vault, bindings = binding_setup(tmp_path)
    person(vault, "person-edgar", "people/edgar.md")
    person(vault, "person-other", "people/other.md", name="Edgar")
    bindings.bind(USER_A, "person-edgar")
    calls: list[dict[str, Any]] = []

    def fake_context(*args: Any, **kwargs: Any) -> object:
        """Capture the deterministic retrieval restriction without semantic work."""
        calls.append(kwargs)
        return SimpleNamespace(items=("person-edgar",))

    monkeypatch.setattr(application, "get_context", fake_context)
    plan = RequestPlan((RetrieveAction(self_selection("where work")),), ())
    result = execute_request(
        "¿Dónde trabajo?",
        planner=SimpleNamespace(plan=lambda request: plan),
        repository=vault,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="odyssey-runtime",
        authenticated_actor=AuthenticatedActorContext(USER_A),
        self_binding_repository=bindings,
        now="2026-09-12T11:00:00+02:00",
        context_limit=5,
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert calls[0]["allowed_note_ids"] == frozenset({"person-edgar"})


def test_self_write_updates_bound_note_and_never_same_name_note(tmp_path: Path) -> None:
    """SELF writes update the binding target rather than an equal-name person."""
    vault, bindings = binding_setup(tmp_path)
    person(vault, "person-edgar", "people/edgar.md")
    person(vault, "person-other", "people/other.md", name="Edgar")
    bindings.bind(USER_A, "person-edgar")
    unit = KnowledgeUnit(self_selection(), "amend", (), (), ("Works at Airbus.",), ())
    plan = RequestPlan((WriteAction((unit,)),), ())
    result = execute_request(
        "Apunta que trabajo en Airbus.",
        planner=SimpleNamespace(plan=lambda request: plan),
        repository=vault,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="odyssey-runtime",
        authenticated_actor=AuthenticatedActorContext(USER_A),
        self_binding_repository=bindings,
        now="2026-09-12T11:00:00+02:00",
        context_limit=5,
        request_id_factory=lambda: "request-self-write",
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert result.action_results[0].unit_results[0].stable_note_id == "person-edgar"
    assert "Works at Airbus." in vault.read_text("people/edgar.md")
    assert "Works at Airbus." not in vault.read_text("people/other.md")


def test_self_binding_survives_rename_and_filename_change(tmp_path: Path) -> None:
    """Stable self resolution is independent of a person's display name and path."""
    vault, bindings = binding_setup(tmp_path)
    person(vault, "person-edgar", "people/edgar.md")
    bindings.bind(USER_A, "person-edgar")
    note = parse_note(vault.read_text("people/edgar.md"))
    note.metadata["name"] = "E. García"
    vault.create_text("people/e-garcia.md", serialize_note(note))
    (vault.root / "people/edgar.md").unlink()
    assert bindings.resolve(USER_A).person_note_id == "person-edgar"


def test_self_read_without_actor_or_binding_is_deferred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A self retrieval cannot invoke ordinary identity search without trusted binding state."""
    vault, bindings = binding_setup(tmp_path)
    person(vault, "person-edgar", "people/edgar.md")
    called = False

    def unexpected_context(*args: Any, **kwargs: Any) -> object:
        """Fail if self resolution falls through to retrieval."""
        nonlocal called
        called = True
        return SimpleNamespace(items=())

    monkeypatch.setattr(application, "get_context", unexpected_context)
    plan = RequestPlan((RetrieveAction(self_selection()),), ())
    result = execute_request(
        "¿Dónde trabajo?",
        planner=SimpleNamespace(plan=lambda request: plan),
        repository=vault,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="odyssey-runtime",
        now="2026-09-12T11:00:00+02:00",
        context_limit=5,
        self_binding_repository=bindings,
    )
    assert result.action_results[0].status is ActionStatus.DEFERRED
    assert result.action_results[0].reason == "self_identity_unavailable"
    assert not called


@pytest.mark.parametrize("case", ("missing_actor", "missing_binding", "deleted", "non_person"))
def test_self_resolution_fail_closed_without_fallback_create(tmp_path: Path, case: str) -> None:
    """Invalid self identity never falls through to a new person CREATE."""
    vault, bindings = binding_setup(tmp_path)
    person(vault, "person-edgar", "people/edgar.md")
    if case in {"deleted", "non_person"}:
        bindings.bind(USER_A, "person-edgar")
        note = parse_note(vault.read_text("people/edgar.md"))
        note.metadata["deleted"] = True if case == "deleted" else False
        if case == "non_person":
            note.metadata["type"] = "concept"
        vault.replace_text("people/edgar.md", serialize_note(note))
    actor = None if case == "missing_actor" else AuthenticatedActorContext(USER_A)
    unit = KnowledgeUnit(self_selection(), "record", (), (), ("Synthetic fact.",), ())
    result = execute_request(
        "Apunta un dato sobre mí.",
        planner=SimpleNamespace(plan=lambda request: RequestPlan((WriteAction((unit,)),), ())),
        repository=vault,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="odyssey-runtime",
        authenticated_actor=actor,
        self_binding_repository=bindings,
        now="2026-09-12T11:00:00+02:00",
        context_limit=5,
    )
    assert result.action_results[0].status is ActionStatus.DEFERRED
    assert result.action_results[0].unit_results[0].status is UnitStatus.DEFERRED
    assert set(vault.list_markdown_paths()) == {"people/edgar.md"}


def test_two_users_resolve_to_distinct_person_notes(tmp_path: Path) -> None:
    """Each Odyssey user resolves only through its own durable binding."""
    vault, bindings = binding_setup(tmp_path)
    person(vault, "person-a", "people/a.md", name="Same Name")
    person(vault, "person-b", "people/b.md", name="Same Name")
    bindings.bind(USER_A, "person-a")
    bindings.bind(USER_B, "person-b")
    assert bindings.resolve(USER_A).person_note_id == "person-a"
    assert bindings.resolve(USER_B).person_note_id == "person-b"


def test_relational_target_remains_ordinary_selection() -> None:
    """The self signal is explicit; possessive or relational language is not keyword-routed."""
    selection = SelectionCriteria(None, "mi hermano", "person", (), None)
    assert selection.self_target is None


def test_planner_contract_accepts_only_semantic_self_signal() -> None:
    """Planner output carries SELF intent without any user or note identity values."""
    payload = {
        "actions": [
            {
                "kind": "retrieve",
                "plan": {
                    "entity": None,
                    "query": "where work",
                    "type": "person",
                    "filters": [],
                    "link_scope": None,
                    "self_target": "self",
                },
            }
        ],
        "limitations": [],
    }
    plan = validate_request_plan(payload, SCHEMA)
    assert plan.actions[0].plan.self_target == "self"  # type: ignore[union-attr]
    assert "person-edgar" not in repr(plan)
    assert "stable_user_id" not in repr(plan)
