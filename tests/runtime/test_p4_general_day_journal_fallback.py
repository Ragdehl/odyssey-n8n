"""Generic completed recollections use the existing Core/Temporal Day writer.

No new semantic router/fallback. Recorded provider suggestions, but genuine
source coverage, Core identity/writer, physical Markdown and E3 replay.
"""

from __future__ import annotations

import pytest

from odyssey_core import create_entity
from odyssey_core.notes import parse_note
from tests.runtime.test_whole_source_light_product_p4 import (
    SCHEMA,
    RecordedClient,
    _fixture,
)


def _reviewed_day(source: str, date: str, *, known_name: bool = False):
    """Only semantic provider outputs are recorded; all mutation gates remain real."""
    route = {
        "capabilities": ["core", "temporal"],
        "self_relation_span": None,
        "self_relation_spans": [],
        "interpretation": "joint",
        "reason": "single",
        "app_scopes": [],
    }
    plan = {
        "entities": [],
        "facts": [
            {
                "meaning": source,
                "kind": "record",
                "subject": "self",
                "date": date,
                "daypart": None,
                "participants": ["Manu"] if known_name else [],
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
                "reviewed_text": (source.replace("Manu", "{{ref:0}}") if known_name else source),
                "date": date,
                "reference_names": ["Manu"] if known_name else [],
                "supported": True,
            }
        ],
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
    return [route, plan, review, speaker, speaker]


@pytest.mark.parametrize(
    ("source", "day", "person_note"),
    [
        ("Hoy he visto a Manu.", "2026-10-16", False),
        ("He visto a Manu.", "2026-10-16", False),
        ("Ayer vi a Manu.", "2026-10-15", False),
        ("Hoy he dado un paseo por el parque.", "2026-10-16", False),
        ("Hoy he visto a Manu.", "2026-10-16", True),
    ],
)
def test_narrated_day_persists_without_becoming_event_or_task(tmp_path, source, day, person_note):
    repo, actor, executor, runtime = _fixture(tmp_path)
    executor.event_delegate = lambda *_: pytest.fail("A completed recollection is not an Event")
    if person_note:
        create_entity(
            repo,
            SCHEMA,
            path="Manu.md",
            entity_id="person-manu",
            metadata={"name": "Manu", "type": "person"},
            content="",
            actor="synthetic",
            now="2026-10-16T09:00:00+02:00",
        )
        executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
        executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.client = RecordedClient(_reviewed_day(source, day, known_name=person_note))
    request_id = "journal-general-day"
    received = runtime.execute_product(source, request_id, "main", actor)
    assert received["status"] == "completed", received
    assert executor.client.calls[0] == "odyssey_light_capability_route_events_v1"
    assert received["execution_flow"]["routes"][0]["capability"] == "core"
    written = [parse_note(repo.read_text(p)) for p in repo.list_markdown_paths()]
    days = [note for note in written if note.metadata.get("type") == "calendar_day"]
    # Temporal may also materialize today's empty Day as a calendar reference
    # when a historical assertion is saved yesterday; only the historical
    # Day should contain the new fact.
    written_days = [n for n in days if f"odyssey:fact request={request_id}" in n.content]
    assert len(written_days) == 1 and written_days[0].metadata["id"] == f"date:{day}"
    assert written_days[0].content.count(f"odyssey:fact request={request_id}") == 1
    assert all(not n.content for n in days if n.metadata["id"] != f"date:{day}")
    if person_note:
        assert "[[" in written_days[0].content and "Manu" in written_days[0].content
    elif "Manu" in source:
        assert "Manu" in written_days[0].content
    else:
        assert "paseo" in written_days[0].content
    assert len([n for n in written if n.metadata.get("type") == "person"]) == (
        2 if person_note else 1
    )
    assert not [n for n in written if n.metadata.get("type") == "event"]
    assert not [n for n in written if n.metadata.get("type") == "task"]
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    again = runtime.execute_product(source, request_id, "main", actor)
    assert again["delivery_replayed"] is True
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_model_route_hypothesis_alone_does_not_fabricate_day_note(tmp_path):
    """Wrong Events classification cannot be accepted as permission to write."""
    repo, actor, executor, runtime = _fixture(tmp_path)
    source = "Hoy he visto a Manu."
    executor.event_delegate = lambda *_: pytest.fail(
        "Never silently reclassify a wrong Events proposal as a verified Core write"
    )
    executor.client = RecordedClient(
        [
            {
                "capabilities": ["events", "core"],
                "self_relation_span": None,
                "self_relation_spans": [],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
            }
        ]
    )
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "wrong-event-hypothesis", "main", actor)
    assert result["status"] == "needs_attention"
    assert not result["affected_stable_note_ids"]
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


@pytest.mark.parametrize(
    ("source", "relation_span"),
    [
        ("Hoy han venido mis padres de visita a mi casa", "mis padres"),
        ("Hoy he ido al parque con mis primos", "mis primos"),
        ("Aujourd'hui mes parents sont venus à la maison", "mes parents"),
        ("Hoy compré patatas fritas para mis compañeros", "mis compañeros"),
        ("Hoy he ordenado mis cartas del cajón", "mis cartas"),
    ],
)
def test_untrusted_router_mentions_do_not_block_faithful_core_journal(
    tmp_path, source, relation_span
):
    """No Router mention can force identity linking or prevent a literal fact."""
    repo, actor, executor, runtime = _fixture(tmp_path)
    executor.event_delegate = lambda *_: pytest.fail(
        "Past visit is not an Events lifecycle operation"
    )
    rows = _reviewed_day(source, "2026-10-16")
    rows[0]["self_relation_spans"] = [relation_span]
    executor.client = RecordedClient(rows)
    result = runtime.execute_product(source, "family-literal-day", "main", actor)
    assert result["status"] == "completed", result
    assert len(executor.client.calls) == 5
    days = [
        parse_note(repo.read_text(p))
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata.get("type") == "calendar_day"
    ]
    assert len(days) == 1
    assert relation_span in days[0].content
    assert days[0].content.count("[[") == 2  # Added Day and authenticated SELF only
    assert (
        len(
            [
                p
                for p in repo.list_markdown_paths()
                if parse_note(repo.read_text(p)).metadata.get("type") == "person"
            ]
        )
        == 1
    )
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    assert runtime.execute_product(source, "family-literal-day", "main", actor)["delivery_replayed"]
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


@pytest.mark.parametrize(
    "unsafe",
    [
        "fabricated_reference",
        "invented_entity",
        "wrong_app",
        "rewritten_relation",
        "invented_participant",
    ],
)
def test_family_literal_fallback_rejects_unverified_writes(tmp_path, unsafe):
    source = "Hoy han venido mis padres de visita a mi casa"
    repo, actor, executor, runtime = _fixture(tmp_path)
    rows = _reviewed_day(source, "2026-10-16")
    rows[0]["self_relation_spans"] = ["mis padres"]
    if unsafe == "fabricated_reference":
        rows[2]["facts"][0]["reference_names"] = ["Madre desconocida"]
        rows[2]["facts"][0]["reviewed_text"] = "Hoy han venido {{ref:0}} de visita a mi casa"
    elif unsafe == "invented_entity":
        rows[1]["entities"] = [{"name": "Madre desconocida"}]
    elif unsafe == "rewritten_relation":
        rows[2]["facts"][0]["reviewed_text"] = "Hoy han venido de visita a mi casa"
    elif unsafe == "invented_participant":
        rows[1]["facts"][0]["participants"] = ["Madre desconocida"]
    else:
        rows[0]["capabilities"] = ["events"]
    executor.client = RecordedClient(rows)
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(source, "family-unsafe-" + unsafe, "main", actor)
    if unsafe in {"invented_entity", "invented_participant"}:
        # Discard unused untrusted suggestions rather than failing a valid
        # journal: physical output remains literal, no invented Person.
        assert result["status"] == "completed", result
        notes = [parse_note(repo.read_text(path)) for path in repo.list_markdown_paths()]
        assert len([n for n in notes if n.metadata.get("type") == "person"]) == 1
        day = next(n for n in notes if n.metadata.get("type") == "calendar_day")
        assert "Hoy han venido mis padres" in day.content
        assert "Madre desconocida" not in day.content
    else:
        assert result["status"] == "needs_attention"
        assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
