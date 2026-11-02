"""P4 whole-source records link arbitrary schema types through real Core/E3."""

from __future__ import annotations

import pytest

from odyssey_core import create_entity
from odyssey_core.notes import parse_note
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient, _fixture, _speaker


@pytest.mark.parametrize("note_type", ("person", "project", "document", "concept", "equipment"))
def test_full_core_e3_markdown_reference_uses_schema_type_not_person_default(tmp_path, note_type):
    repository, actor, service, runtime = _fixture(tmp_path)
    if note_type == "equipment":
        from copy import deepcopy

        service.schema = deepcopy(service.schema)
        extra = deepcopy(next(item for item in service.schema["types"] if item["id"] == "concept"))
        extra["id"] = "equipment"
        extra["name"] = "Equipment"
        service.schema["types"].append(extra)
        from odyssey_core.identity_boundary import SelfBindingRepository

        service.bindings = SelfBindingRepository(tmp_path / "state", repository, service.schema)
    create_entity(
        repository,
        service.schema,
        path="Atlas.md",
        entity_id="atlas-target",
        metadata={"name": "Atlas", "type": note_type},
        content="",
        actor="fixture",
        now="2026-10-16T12:00:00+02:00",
    )
    service.context_index.rebuild(repository, service.schema, service.embedder)
    service.semantic_index.rebuild(repository, service.schema, service.embedder)
    source = "Hoy revisé Atlas."
    routing = {
        "capabilities": ["core", "temporal"],
        "interpretation": "joint",
        "reason": "single",
        "self_relation_span": None,
        "app_scopes": [],
    }
    proposal = {
        "entities": [
            {
                "mention": "Atlas",
                "canonical_name": None,
                "note_type": note_type,
                "confidence": "explicit",
            }
        ],
        "facts": [
            {
                "meaning": "Hoy revisé Atlas",
                "kind": "record",
                "subject": "yo",
                "date": "2026-10-16",
                "daypart": None,
                "participants": ["Atlas"],
                "source_evidence": source,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
        ],
        "unresolved": [],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "source_quote": source,
                "kind": "record",
                "reviewed_text": "Hoy revisé {{ref:0}}.",
                "date": "2026-10-16",
                "reference_names": ["Atlas"],
                "supported": True,
            }
        ],
    }

    class AssertCatalogClient(RecordedClient):
        def create(self, **kwargs):
            if kwargs["text"]["format"]["name"] == "odyssey_light_shared_semantic_plan_v1":
                assert note_type in str(kwargs["input"]), (
                    "Active NoteSchema type omitted from model input"
                )
            return super().create(**kwargs)

    service.client = AssertCatalogClient(
        [routing, proposal, review, _speaker(source, proposal, base=1), _speaker(source, proposal)]
    )
    payload = (source, f"schema-type-{note_type}", "main", actor)
    result = runtime.execute_product(*payload)
    assert result["status"] == "completed", result
    linked = parse_note(repository.read_text("calendar/days/2026-10-16.md"))
    assert "[[Atlas|Atlas]]" in linked.content
    assert parse_note(repository.read_text("Atlas.md")).metadata["type"] == note_type
    assert len([path for path in repository.list_markdown_paths() if path == "Atlas.md"]) == 1
    original = {path: repository.read_text(path) for path in repository.list_markdown_paths()}
    replay = runtime.execute_product(*payload)
    assert replay["delivery_replayed"] is True
    assert {
        path: repository.read_text(path) for path in repository.list_markdown_paths()
    } == original


def test_model_type_guess_does_not_disambiguate_equal_names_without_core_proof(tmp_path):
    repository, actor, service, runtime = _fixture(tmp_path)
    for note_type in ("person", "document"):
        create_entity(
            repository,
            service.schema,
            path=f"Atlas-{note_type}.md",
            entity_id=f"atlas-{note_type}",
            metadata={"name": "Atlas", "type": note_type},
            content="",
            actor="fixture",
            now="2026-10-16T12:00:00+02:00",
        )
    service.context_index.rebuild(repository, service.schema, service.embedder)
    service.semantic_index.rebuild(repository, service.schema, service.embedder)
    source = "Hoy revisé Atlas."
    routing = {
        "capabilities": ["core", "temporal"],
        "interpretation": "joint",
        "reason": "single",
        "self_relation_span": None,
        "app_scopes": [],
    }
    proposal = {
        "entities": [
            {
                "mention": "Atlas",
                "canonical_name": None,
                "note_type": "document",
                "confidence": "explicit",
            }
        ],
        "facts": [
            {
                "meaning": "Hoy revisé Atlas",
                "kind": "record",
                "subject": "yo",
                "date": "2026-10-16",
                "daypart": None,
                "participants": ["Atlas"],
                "source_evidence": source,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
        ],
        "unresolved": [],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "source_quote": source,
                "kind": "record",
                "reviewed_text": "Hoy revisé {{ref:0}}.",
                "date": "2026-10-16",
                "reference_names": ["Atlas"],
                "supported": True,
            }
        ],
    }
    service.client = RecordedClient(
        [routing, proposal, review, _speaker(source, proposal, base=1), _speaker(source, proposal)]
    )
    before = {path: repository.read_text(path) for path in repository.list_markdown_paths()}
    outcome = runtime.execute_product(source, "type-disambiguated", "main", actor)
    assert outcome["status"] == "needs_attention", outcome
    assert {path: repository.read_text(path) for path in repository.list_markdown_paths()} == before


def test_verified_canonical_relationship_can_disambiguate_homonyms_of_different_note_types(
    tmp_path,
):
    from odyssey_core.atomic_facts import render_atomic_facts
    from odyssey_core.notes import Note, serialize_note

    repository, actor, service, runtime = _fixture(tmp_path)
    for note_type in ("person", "project"):
        create_entity(
            repository,
            service.schema,
            path=f"Atlas-{note_type}.md",
            entity_id=f"atlas-{note_type}",
            metadata={"name": "Atlas", "type": note_type},
            content="",
            actor="fixture",
            now="2026-10-16T12:00:00+02:00",
        )
    self_note = parse_note(repository.read_text("self.md"))
    own_fact = render_atomic_facts(
        ("El proyecto Atlas es [[Atlas-project|Atlas]].",),
        "canonical-project-evidence",
        (0,),
        "2026-10-16",
    )
    repository.replace_text("self.md", serialize_note(Note(self_note.metadata, own_fact)))
    service.context_index.rebuild(repository, service.schema, service.embedder)
    service.semantic_index.rebuild(repository, service.schema, service.embedder)
    source = "Hoy he revisado el proyecto Atlas."
    routing = {
        "capabilities": ["core", "temporal"],
        "interpretation": "joint",
        "reason": "single",
        "self_relation_span": "el proyecto Atlas",
        "app_scopes": [],
    }
    proposal = {
        "entities": [
            {
                "mention": "Atlas",
                "canonical_name": None,
                "note_type": "project",
                "confidence": "explicit",
            }
        ],
        "facts": [
            {
                "meaning": "Hoy he revisado el proyecto Atlas",
                "kind": "record",
                "subject": "yo",
                "date": "2026-10-16",
                "daypart": None,
                "participants": ["Atlas"],
                "source_evidence": source,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
        ],
        "unresolved": [],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "source_quote": source,
                "kind": "record",
                "reviewed_text": "Hoy he revisado {{ref:0}}.",
                "date": "2026-10-16",
                "reference_names": ["Atlas"],
                "supported": True,
            }
        ],
    }
    service.client = RecordedClient(
        [routing, proposal, review, _speaker(source, proposal, base=1), _speaker(source, proposal)]
    )
    before = {p: repository.read_text(p) for p in repository.list_markdown_paths()}
    result = runtime.execute_product(source, "verified-cross-type-link", "main", actor)
    assert result["status"] == "completed", result
    written = parse_note(repository.read_text("calendar/days/2026-10-16.md"))
    assert "[[Atlas-project|Atlas]]" in written.content
    assert "[[Atlas-person|Atlas]]" not in written.content
    assert before["Atlas-project.md"] == repository.read_text("Atlas-project.md")
    assert before["Atlas-person.md"] == repository.read_text("Atlas-person.md")
