"""P4 source-name hints use derived indexes without becoming identity authority."""

from __future__ import annotations

import sqlite3

import pytest

from odyssey_core import create_entity
from odyssey_core.notes import parse_note, serialize_note
from tests.runtime.test_whole_source_light_product_p4 import SCHEMA, _fixture


def _person(repo, name, identifier):
    create_entity(
        repo,
        SCHEMA,
        path=f"{identifier}.md",
        entity_id=identifier,
        metadata={"name": name, "type": "person"},
        content="",
        actor="test",
        now="2026-10-16T15:00:00+02:00",
    )


def test_indexed_hints_only_match_source_and_recheck_current_canonical_bytes(tmp_path):
    repo, _, service, _ = _fixture(tmp_path)
    _person(repo, "Clara Valls", "clara-one")
    _person(repo, "Clara Bonet", "clara-two")
    _person(repo, "Guillem Valls", "guillem")
    service.context_index.rebuild(repo, SCHEMA, service.embedder)
    hints = service._note_hints("Ayer hablé con Clara.")
    assert {item["id"] for item in hints} == {"clara-one", "clara-two"}
    assert all(item["name"].startswith("Clara") for item in hints)
    assert service._note_hints("Hoy compré pan.") == []
    before = parse_note(repo.read_text("clara-one.md"))
    before.metadata["name"] = "Otra persona"
    repo.replace_text("clara-one.md", serialize_note(before))
    with pytest.raises(ValueError, match="Canonical hints are unavailable or stale"):
        service._note_hints("Ayer hablé con Clara.")


def test_missing_index_cannot_be_taken_as_proof_a_person_does_not_exist(tmp_path):
    repo, _, service, _ = _fixture(tmp_path)
    _person(repo, "Nadia Sol", "new-outside-index")
    assert service._note_hints("Nadia está allí.") == []
    # This empty advisory result is NOT a proof of identity absence: the
    # physical Core identity validator still owns source/name resolution.
    from odyssey_core.whole_message_identity_guard import (
        UnprovenPersonIdentityError,
        reject_unproven_person_collisions,
    )

    with pytest.raises(UnprovenPersonIdentityError):
        reject_unproven_person_collisions(repo, SCHEMA, ("Nadia",))


def test_source_hint_budget_rejects_many_matches_instead_of_truncating(tmp_path):
    repo, _, service, _ = _fixture(tmp_path)
    for i in range(26):
        _person(repo, f"Clara {i:03d}", f"clara-{i}")
    service.context_index.rebuild(repo, SCHEMA, service.embedder)
    with pytest.raises(ValueError, match="Canonical hints are unavailable or stale"):
        service._note_hints("Con Clara")


def test_large_derived_index_no_longer_has_arbitrary_5000_row_note_limit(tmp_path):
    repo, _, service, _ = _fixture(tmp_path)
    _person(repo, "Irene Contexto", "irene")
    service.context_index.rebuild(repo, SCHEMA, service.embedder)
    # Seed 5001 *irrelevant* index names. They cannot become identity hints:
    # only matched entries may be returned and each is reverified physically.
    # This isolates the former 5000-row unconditional abort contract.
    with sqlite3.connect(service.context_index.path) as connection:
        base = connection.execute("SELECT embedding FROM notes LIMIT 1").fetchone()[0]
        connection.executemany(
            "INSERT INTO notes(id,path,type,primary_name,source_hash,tags,embedding) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                (
                    f"irrelevant-{i}",
                    f"no-candidate-{i}.md",
                    "person",
                    f"Irrelevante{i}",
                    "0" * 64,
                    "[]",
                    base,
                )
                for i in range(5001)
            ),
        )
    hints = service._note_hints("He conocido a Irene.")
    assert len(hints) == 1 and hints[0]["id"] == "irene"
    assert service._note_hints("He comprado pan.") == []


def test_corrupted_context_index_fails_closed(tmp_path):
    _, _, service, _ = _fixture(tmp_path)
    with sqlite3.connect(service.context_index.path) as connection:
        connection.execute("UPDATE metadata SET value = 'untrusted' WHERE key = 'format'")
    with pytest.raises(ValueError, match="Canonical hints are unavailable or stale"):
        service._note_hints("Irene")
