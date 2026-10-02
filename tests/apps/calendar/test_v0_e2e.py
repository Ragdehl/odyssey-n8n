"""Provider-free Calendar v0 backend end-to-end contract."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from odyssey_apps.calendar import CalendarQueryService
from odyssey_core import (
    KnowledgeUnit,
    SelectionCriteria,
    WriteTargetDecision,
    WriteTargetOutcome,
    create_entity,
    materialize_update,
    update_entity,
)
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]


class ConstantEmbedder:
    model_name = "tests/calendar-v0-e2e"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]


def test_real_write_chronology_journal_and_day_projection_end_to_end(tmp_path: Path) -> None:
    """Run canonical persistence through Calendar month/Day projection without provider shortcuts."""
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "people").mkdir()
    (vault / "journal").mkdir()
    repository = VaultRepository(vault)

    create_entity(
        repository,
        schema,
        path="people/marta.md",
        entity_id="marta",
        metadata={"name": "Marta", "type": "person"},
        content="",
        actor="fixture",
        now="2026-09-30T09:00:00+02:00",
    )
    unit = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "amend",
        (),
        (),
        ("Marta empieza el [[calendar/days/2026-10-05|05-10-2026]].",),
        (),
    )
    materialize_update(
        unit,
        WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id="marta"),
        repository=repository,
        schema=schema,
        actor="odyssey-test",
        now="2026-10-01T10:00:00+02:00",
        request_id="calendar-e2e",
        fact_ordinals=(0,),
    )

    capture_path = "calendar/days/2026-10-01.md"
    capture_note = parse_note(repository.read_text(capture_path))
    update_entity(
        repository,
        schema,
        path=capture_path,
        expected_id="date:2026-10-01",
        expected_revision=capture_note.metadata["revision"],
        set_metadata={},
        remove_metadata=(),
        content="- Compré una bici.",
        actor="calendar-test",
        now="2026-10-01T11:00:00+02:00",
    )
    create_entity(
        repository,
        schema,
        path="journal/2026-10-01.md",
        entity_id="journal-2026-10-01",
        metadata={"name": "Diario 1 octubre", "type": "journal_entry", "entry_date": "2026-10-01"},
        content="Buen día.",
        actor="fixture",
        now="2026-10-01T20:00:00+02:00",
    )

    index = ContextIndex(tmp_path / "runtime" / "context.sqlite3")
    assert index.rebuild(repository, schema, ConstantEmbedder()) == 4
    notes = NotesQueryService(repository, schema, index)
    calendar = CalendarQueryService(repository, schema, notes)

    october = calendar.month("2026-10")
    first = october.days[0]
    fifth = october.days[4]
    assert (first.date, first.materialized, first.has_content) == ("2026-10-01", True, True)
    assert first.journal_count == 1
    assert first.captured_fact_count == 1
    assert first.reference_count == 0
    assert fifth.date == "2026-10-05"
    assert fifth.materialized is True
    assert fifth.reference_count == 1

    day = calendar.day("2026-10-01")
    assert day.materialized is True
    assert [journal.source.id for journal in day.journals] == ["journal-2026-10-01"]
    assert [capture.source.id for capture in day.captures] == ["marta"]
    assert "Compré una bici." in " ".join(
        "".join(segment.text for segment in block.segments) for block in day.content
    )

    happened = calendar.day("2026-10-05")
    assert [reference.source.id for reference in happened.references] == ["marta"]
    assert happened.captures == ()
