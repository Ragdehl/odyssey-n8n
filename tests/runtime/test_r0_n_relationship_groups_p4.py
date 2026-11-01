"""G03: independent canonical SELF group proofs must not have a magic 8 limit.

Model calls are recorded/synthetic; Core identity proof, actual P4, E3,
physical Markdown readback and replay use production paths and a temp vault.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core import create_entity
from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.notes import parse_note, serialize_note
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient, _fixture


@pytest.mark.parametrize(
    "count, tamper",
    [
        (1, None),
        (8, None),
        (9, None),
        (9, "invented_group"),
        (9, "duplicated_without_source_occurrence"),
    ],
)
@pytest.mark.parametrize("note_type", ["person", "project", "document", "concept"])
def test_more_than_eight_source_attested_self_group_links_can_reach_same_writer(
    count, tamper, note_type, tmp_path
):
    repo, actor, service, runtime = _fixture(tmp_path)
    anchors = [f"mi grupo{i:02d}" for i in range(count)]
    names = [f"Entidad{i:02d}" for i in range(count)]
    for i, name in enumerate(names):
        create_entity(
            repo,
            service.schema,
            path=f"{name}.md",
            entity_id=f"group-{i}",
            metadata={"name": name, "type": note_type},
            content="",
            actor="fixture",
            now="2026-10-16T08:00:00+02:00",
        )
    original = parse_note(repo.read_text("self.md"))
    facts = [f"{anchor} es [[{name}]]." for anchor, name in zip(anchors, names, strict=True)]
    repo.replace_text(
        "self.md",
        serialize_note(
            replace(
                original,
                content=render_atomic_facts(
                    tuple(facts), "test-proof", tuple(range(count)), "2026-10-16"
                ),
            )
        ),
    )
    service.context_index.rebuild(repo, service.schema, service.embedder)
    service.semantic_index.rebuild(repo, service.schema, service.embedder)
    source = "Hoy estuve con " + ", ".join(anchors) + "."
    text = "Hoy estuve con " + ", ".join("{{ref:" + str(i) + "}}" for i in range(count)) + "."
    plan_fact = {
        "meaning": source,
        "kind": "record",
        "subject": "yo",
        "date": "2026-10-16",
        "daypart": None,
        "participants": names,
        "source_evidence": source,
        "dependent_on_fact_index": None,
        "needs_clarification": False,
    }
    speaker = {
        "facts": [
            {
                "ordinal": 0,
                "role": "self_participant",
                "assertion": "asserted",
                "source_quote": source,
            }
        ]
    }
    messages = [
        {
            "capabilities": ["core", "temporal"],
            "interpretation": "joint",
            "reason": "shared_subject",
            "self_relation_span": None,
            "self_relation_spans": anchors,
            "app_scopes": [],
        },
        {"entities": [], "facts": [plan_fact], "unresolved": []},
        {
            "approved": True,
            "complete": True,
            "reason": None,
            "facts": [
                {
                    "ordinal": 0,
                    "source_quote": source,
                    "kind": "record",
                    "reviewed_text": text,
                    "date": "2026-10-16",
                    "reference_names": names,
                    "supported": True,
                }
            ],
        },
        speaker,
        speaker,
    ]
    if tamper == "invented_group":
        messages[0]["self_relation_spans"] = [*anchors[:-1], "mi grupo999"]
    elif tamper == "duplicated_without_source_occurrence":
        messages[0]["self_relation_spans"] = [*anchors[:-1], anchors[0]]
    service.client = RecordedClient(messages[:1] if tamper else messages)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    request_id = f"r0-n-groups-{count}-{note_type}-{tamper}"
    result = runtime.execute_product(source, request_id, "main", actor)
    if tamper:
        assert result["status"] == "needs_attention", (result, service.client.calls)
        assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
        return
    assert result["status"] == "completed", (result, service.client.calls)
    rendered = parse_note(repo.read_text("calendar/days/2026-10-16.md")).content
    assert all("[[" + name in rendered for name in names)
    assert "{{ref:" not in rendered
    snapshot = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    replay = runtime.execute_product(source, request_id, "main", actor)
    assert replay["delivery_replayed"] is True
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == snapshot
