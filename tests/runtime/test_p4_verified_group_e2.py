"""P4 whole-source group memberships require current authenticated Core SELF fact."""

from __future__ import annotations

import copy
from dataclasses import replace

from odyssey_core import create_entity
from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.notes import parse_note, serialize_note
from tests.runtime.test_whole_source_light_product_p4 import (
    SCHEMA,
    RecordedClient,
    _actual_snapshot,
    _fixture,
)


def _family(tmp_path):
    repo, actor, service, runtime = _fixture(tmp_path)
    for name in ("Cloe", "Bruno"):
        create_entity(
            repo,
            SCHEMA,
            path=f"{name}.md",
            entity_id=f"child-{name}",
            metadata={"name": name, "type": "person"},
            content="",
            actor="fixture",
            now="2026-10-16T15:00:00+02:00",
        )
    prior = parse_note(repo.read_text("self.md"))
    body = render_atomic_facts(
        ("Mis hijos son [[Cloe]] y [[Bruno]].",), "family", (0,), "2026-10-16"
    )
    repo.replace_text("self.md", serialize_note(replace(prior, content=body)))
    service.context_index.rebuild(repo, SCHEMA, service.embedder)
    service.semantic_index.rebuild(repo, SCHEMA, service.embedder)
    return repo, actor, service, runtime


def _responses(span="Mis hijos"):
    source, router, proposed, reviewed = _actual_snapshot("maya_simple")
    router, proposed, reviewed = (
        copy.deepcopy(router),
        copy.deepcopy(proposed),
        copy.deepcopy(reviewed),
    )
    source = "Mis hijos comieron helado hoy."
    router["self_relation_span"] = span
    router["capabilities"] = ["core", "temporal"]
    proposed["entities"] = []
    proposed["unresolved"] = []
    proposed["facts"] = [
        {
            "meaning": "Mis hijos comieron helado hoy.",
            "kind": "record",
            "subject": "mis hijos",
            "date": "2026-10-16",
            "daypart": None,
            "participants": ["Cloe", "Bruno"],
            "source_evidence": "Mis hijos comieron helado hoy.",
            "dependent_on_fact_index": None,
            "needs_clarification": False,
        }
    ]
    reviewed["approved"] = True
    reviewed["complete"] = True
    reviewed["facts"] = [
        {
            "ordinal": 0,
            "kind": "record",
            "date": "2026-10-16",
            "supported": True,
            "source_quote": source,
            "reviewed_text": "{{ref:0}} y {{ref:1}} comieron helado hoy.",
            "reference_names": ["Cloe", "Bruno"],
        }
    ]
    speaker = {
        "facts": [{"ordinal": 0, "role": "other", "assertion": "asserted", "source_quote": source}]
    }
    return source, [router, proposed, reviewed, speaker, speaker]


def test_core_verified_group_expands_only_existing_children_and_replays(tmp_path):
    repo, actor, service, runtime = _family(tmp_path)
    source, outputs = _responses()
    service.client = RecordedClient(outputs)
    result = runtime.execute_product(source, "group-verified", "main", actor)
    assert result["status"] == "completed", result
    notes = [parse_note(repo.read_text(path)) for path in repo.list_markdown_paths()]
    day = [n for n in notes if n.metadata["id"] == "date:2026-10-16"]
    assert len(day) == 1
    assert "[[Cloe" in day[0].content and "[[Bruno" in day[0].content
    assert len([n for n in notes if n.metadata["type"] == "person"]) == 3
    previous = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    assert runtime.execute_product(source, "group-verified", "main", actor)["delivery_replayed"]
    assert previous == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_invented_or_unattested_group_never_writes(tmp_path):
    repo, actor, service, runtime = _family(tmp_path)
    source, outputs = _responses("mis primos")
    service.client = RecordedClient(outputs[:1])
    previous = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "group-unproven", "main", actor)
    assert result["status"] == "needs_attention"
    assert previous == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_relationship_mutation_during_real_review_never_promotes_stale_member_set(tmp_path):
    """Simulate external actor editing canonical SELF while model review runs."""
    repo, actor, service, runtime = _family(tmp_path)
    source, responses = _responses()
    client = RecordedClient(responses)
    original_create = client.create

    def change_self_mid_review(**kwargs):
        result = original_create(**kwargs)
        if kwargs["text"]["format"]["name"] == "odyssey_speaker_full_B":
            previous = parse_note(repo.read_text("self.md"))
            changed = render_atomic_facts(
                ("Mis hijos son [[Cloe]].",), "family", (0,), "2026-10-16"
            )
            repo.replace_text("self.md", serialize_note(replace(previous, content=changed)))
        return result

    client.create = change_self_mid_review
    service.client = client
    result = runtime.execute_product(source, "family-relation-stale", "main", actor)
    assert result["status"] == "needs_attention", result
    assert not any(
        "odyssey:fact request=family-relation-stale" in repo.read_text(p)
        for p in repo.list_markdown_paths()
    )
