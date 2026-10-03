from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from odyssey_core import (
    KnowledgeUnit,
    SelectionCriteria,
    WriteTargetDecision,
    WriteTargetOutcome,
    create_entity,
    materialize_update,
)
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]


class ConstantEmbedder:
    """Keep the end-to-end derived index deterministic without a model/provider dependency."""

    model_name = "tests/temporal-e2e"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]


def test_write_to_markdown_day_materialization_and_backlinks_end_to_end(tmp_path: Path) -> None:
    """Exercise the real deterministic write→Day→index→detail/backlink path without a provider."""
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "people").mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        schema,
        path="people/marta.md",
        entity_id="marta",
        metadata={"name": "Marta", "type": "person"},
        content="Legacy context.",
        actor="fixture",
        now="2026-09-30T10:00:00+02:00",
    )
    decision = WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id="marta")

    first = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "amend",
        (),
        (),
        ("Marta empieza el [[calendar/days/2026-10-05|05-10-2026]].",),
        (),
    )
    materialize_update(
        first,
        decision,
        repository=repository,
        schema=schema,
        actor="odyssey-test",
        now="2026-10-01T09:00:00+02:00",
        request_id="req-1",
        fact_ordinals=(0,),
    )

    second = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "amend",
        (),
        (),
        ("Marta confirmó el horario.",),
        (),
    )
    materialize_update(
        second,
        decision,
        repository=repository,
        schema=schema,
        actor="odyssey-test",
        now="2026-10-01T18:00:00+02:00",
        request_id="req-2",
        fact_ordinals=(0,),
    )

    source = parse_note(repository.read_text("people/marta.md"))
    assert source.content.count("# Added [[calendar/days/2026-10-01|01-10-2026]]") == 1
    assert "request=req-1 ordinal=0" in source.content
    assert "request=req-2 ordinal=0" in source.content
    assert repository.list_markdown_paths() == [
        "calendar/days/2026-10-01.md",
        "calendar/days/2026-10-05.md",
        "people/marta.md",
    ]

    index = ContextIndex(tmp_path / "runtime" / "context.sqlite3")
    assert index.rebuild(repository, schema, ConstantEmbedder()) == 3
    notes = NotesQueryService(repository, schema, index)

    # Calendar-managed Days remain outside the ordinary Notes feed.
    assert [item.id for item in notes.query(mode="feed").items] == ["marta"]

    detail = notes.detail("marta")
    linked = [
        (segment.text, segment.target_id, segment.target_type)
        for block in detail.body_blocks
        for segment in block.segments
        if segment.target_id is not None
    ]
    assert ("01-10-2026", "date:2026-10-01", "calendar_day") in linked
    assert ("05-10-2026", "date:2026-10-05", "calendar_day") in linked

    capture = notes.backlinks("date:2026-10-01")
    assert capture.total == 1
    assert capture.items[0].source.id == "marta"
    assert capture.items[0].occurrences == 1
    assert capture.items[0].snippets[0].block.kind == "heading"

    semantic_day = notes.backlinks("date:2026-10-05")
    assert semantic_day.total == 1
    assert semantic_day.items[0].source.id == "marta"
    assert semantic_day.items[0].occurrences == 1
    snippet = semantic_day.items[0].snippets[0]
    assert snippet.heading is not None
    assert "".join(segment.text for segment in snippet.heading) == "Added 01-10-2026"
    assert (
        "".join(segment.text for segment in snippet.block.segments)
        == "Marta empieza el 05-10-2026."
    )
