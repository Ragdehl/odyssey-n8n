"""Real Core relation re-grounding for a whole-message group reference."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.notes import Note, serialize_note
from odyssey_core.storage import VaultRepository
from odyssey_core.whole_message_relationship_proof import (
    WholeSourceRelationshipError,
    recheck_self_relationship,
    verify_self_relationship,
)

SCHEMA = json.loads((Path(__file__).parents[2] / "config/note-schema.json").read_text())


def _write(root: Path, name: str, identifier: str, body: str):
    text = serialize_note(
        Note(
            {
                "id": identifier,
                "name": name,
                "type": "person",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "created_by": {"human": None, "app": "test"},
                "updated_by": {"human": None, "app": "test"},
                "revision": 1,
                "schema_version": 3,
                "aliases": [],
                "tags": [],
            },
            body,
        )
    )
    (root / f"{name}.md").write_text(text)


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    _write(
        root,
        "Yo",
        "self-id",
        render_atomic_facts(("Mis hijos son [[Cloe]] y [[Bruno]].",), "family", (0,), "2026-10-16"),
    )
    _write(root, "Cloe", "child-1", "")
    _write(root, "Bruno", "child-2", "")
    repo = VaultRepository(root)
    state = tmp_path / "state"
    state.mkdir()
    actor = AuthenticatedActorContext(str(uuid4()))
    bindings = SelfBindingRepository(state, repo, SCHEMA)
    bindings.bind(actor.stable_user_id, "self-id")
    return root, repo, actor, bindings


def test_verified_self_relation_reuses_exact_real_child_ids(corpus):
    _root, repo, actor, bindings = corpus
    evidence = verify_self_relationship(
        "Mis hijos comieron helado.",
        "Mis hijos",
        repository=repo,
        schema=SCHEMA,
        actor=actor,
        bindings=bindings,
    )
    assert evidence.source_id == "self-id"
    assert set(evidence.members) == {("child-1", "Cloe"), ("child-2", "Bruno")}
    recheck_self_relationship(
        evidence, repository=repo, schema=SCHEMA, actor=actor, bindings=bindings
    )


@pytest.mark.parametrize("span", ["Cloe", "mis primos", "mis", "", "Bruno"])
def test_unattested_or_missing_relation_does_not_create_member_proof(corpus, span):
    _root, repo, actor, bindings = corpus
    with pytest.raises((ValueError, WholeSourceRelationshipError)):
        verify_self_relationship(
            "Mis hijos comieron helado.",
            span,
            repository=repo,
            schema=SCHEMA,
            actor=actor,
            bindings=bindings,
        )


def test_previous_proof_rejects_changed_canonical_fact(corpus):
    root, repo, actor, bindings = corpus
    evidence = verify_self_relationship(
        "Mis hijos comieron helado.",
        "Mis hijos",
        repository=repo,
        schema=SCHEMA,
        actor=actor,
        bindings=bindings,
    )
    _write(
        root,
        "Yo",
        "self-id",
        render_atomic_facts(("Mis hijos son [[Cloe]].",), "family", (0,), "2026-10-16"),
    )
    with pytest.raises(WholeSourceRelationshipError):
        recheck_self_relationship(
            evidence, repository=repo, schema=SCHEMA, actor=actor, bindings=bindings
        )


def test_other_user_does_not_inherit_self_relation(corpus):
    _root, repo, _actor, bindings = corpus
    stranger = AuthenticatedActorContext(str(uuid4()))
    with pytest.raises(ValueError):
        verify_self_relationship(
            "Mis hijos comieron helado.",
            "Mis hijos",
            repository=repo,
            schema=SCHEMA,
            actor=stranger,
            bindings=bindings,
        )
