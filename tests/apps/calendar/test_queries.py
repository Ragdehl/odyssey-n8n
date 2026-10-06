"""Calendar v0 deterministic month/day projection coverage."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from odyssey_apps.calendar import CalendarQueryError, CalendarQueryService, normalize_month
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import Note, serialize_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]


class Embedder:
    model_name = "tests/calendar"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return self.embed_documents(texts)


@pytest.fixture
def schema() -> dict:
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def write(
    vault: Path,
    path: str,
    note_id: str,
    name: str,
    note_type: str,
    body: str,
    *,
    properties: dict[str, object] | None = None,
) -> None:
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        serialize_note(
            Note(
                {
                    "id": note_id,
                    "name": name,
                    "type": note_type,
                    "created_at": "2026-10-01T08:00:00+02:00",
                    "updated_at": "2026-10-01T08:00:00+02:00",
                    "created_by": {"human": None, "app": "test"},
                    "updated_by": {"human": None, "app": "test"},
                    "revision": 1,
                    "schema_version": 3,
                    **(properties or {}),
                },
                body,
            )
        ),
        encoding="utf-8",
    )


def service(tmp_path: Path, schema: dict) -> CalendarQueryService:
    vault = tmp_path / "vault"
    vault.mkdir()
    write(
        vault,
        "calendar/days/2026-10-01.md",
        "date:2026-10-01",
        "2026-10-01",
        "calendar_day",
        "- Compré una bici.",
        properties={"date": "2026-10-01"},
    )
    write(
        vault,
        "people/marta.md",
        "marta",
        "Marta",
        "person",
        "# Added [[calendar/days/2026-10-01|01-10-2026]]\n"
        "- Empezó en Airbus.\n  <!-- odyssey:fact request=r1 ordinal=0 -->\n"
        "- Confirmó el horario.\n  <!-- odyssey:fact request=r2 ordinal=0 -->",
    )
    write(
        vault,
        "journal/one.md",
        "journal-one",
        "Diario del jueves",
        "journal_entry",
        "# Added [[calendar/days/2026-10-01|01-10-2026]]\n"
        "- Hoy fue un buen día.\n"
        "- Hablé con [[people/marta|Marta]].",
        properties={"entry_date": "2026-10-01"},
    )
    write(
        vault,
        "journal/two.md",
        "journal-two",
        "Diario del viernes",
        "journal_entry",
        "Día tranquilo.",
        properties={"entry_date": "2026-10-02"},
    )
    write(
        vault,
        "journal/extra.md",
        "journal-extra",
        "Z diario extra",
        "journal_entry",
        "Otro momento del día.",
        properties={"entry_date": "2026-10-01"},
    )
    write(
        vault,
        "projects/trip.md",
        "trip",
        "Viaje",
        "project",
        "La reserva corresponde al [[calendar/days/2026-10-01|1 de octubre]].",
    )
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "runtime" / "context.sqlite3")
    index.rebuild(repository, schema, Embedder())
    notes = NotesQueryService(repository, schema, index)
    return CalendarQueryService(repository, schema, notes)


def test_month_projects_materialization_content_and_distinct_temporal_categories(
    tmp_path: Path, schema: dict
) -> None:
    calendar = service(tmp_path, schema)
    month = calendar.month("2026-10")

    assert month.month == "2026-10"
    assert len(month.days) == 31
    first = month.days[0]
    assert first.date == "2026-10-01"
    assert first.materialized is True
    assert first.has_content is True
    assert first.journal_count == 2
    assert first.captured_fact_count == 2
    assert first.reference_count == 1
    assert first.preview_total == 5
    assert [(item.kind, item.label, item.text) for item in first.previews] == [
        ("day_content", "2026-10-01", "Compré una bici."),
        ("journal", "Diario del jueves", "Hoy fue un buen día."),
        ("journal", "Z diario extra", "Otro momento del día."),
        ("capture", "Marta", "Empezó en Airbus."),
    ]
    second = month.days[1]
    assert second.materialized is False
    assert second.journal_count == 1
    assert second.captured_fact_count == 0
    assert second.reference_count == 0


def test_month_preview_is_category_ordered_source_sorted_and_strictly_bounded(
    tmp_path: Path, schema: dict
) -> None:
    """Keep the month preview presentation-only, deterministic, and capped at four rows."""
    vault = tmp_path / "vault"
    vault.mkdir()
    write(
        vault,
        "calendar/days/2026-10-01.md",
        "date:2026-10-01",
        "Day",
        "calendar_day",
        "Day text.",
        properties={"date": "2026-10-01"},
    )
    write(
        vault,
        "journal/z.md",
        "z-journal",
        "Zeta",
        "journal_entry",
        "Zeta text.",
        properties={"entry_date": "2026-10-01"},
    )
    write(
        vault,
        "journal/a.md",
        "a-journal",
        "Álpha",
        "journal_entry",
        "Álpha text.",
        properties={"entry_date": "2026-10-01"},
    )
    write(
        vault,
        "people/marta.md",
        "marta",
        "Marta",
        "person",
        "# Added [[calendar/days/2026-10-01|01-10-2026]]\n- Captura visible.",
    )
    write(
        vault,
        "projects/trip.md",
        "trip",
        "Viaje",
        "project",
        "Referencia [[calendar/days/2026-10-01|1 de octubre]].",
    )
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "runtime" / "context.sqlite3")
    index.rebuild(repository, schema, Embedder())
    calendar = CalendarQueryService(
        repository, schema, NotesQueryService(repository, schema, index)
    )

    day = calendar.month("2026-10").days[0]
    assert (day.journal_count, day.captured_fact_count, day.reference_count) == (2, 1, 1)
    assert day.preview_total == 5
    assert [(item.kind, item.label) for item in day.previews] == [
        ("day_content", "Day"),
        ("journal", "Zeta"),
        ("journal", "Álpha"),
        ("capture", "Marta"),
    ]


def test_day_keeps_own_content_journal_capture_and_explicit_reference_separate(
    tmp_path: Path, schema: dict
) -> None:
    calendar = service(tmp_path, schema)
    day = calendar.day("2026-10-01")

    assert day.materialized is True
    assert "Compré una bici." in " ".join(
        "".join(segment.text for segment in block.segments) for block in day.content
    )
    assert [item.source.id for item in day.journals] == ["journal-one", "journal-extra"]
    journal_text = " ".join(
        "".join(segment.text for segment in block.segments) for block in day.journals[0].content
    )
    assert "Hoy fue un buen día." in journal_text
    assert "Hablé con Marta." in journal_text
    assert "Added" not in journal_text
    assert [item.source.id for item in day.captures] == ["marta"]
    assert [
        "".join(segment.text for segment in block.segments) for block in day.captures[0].facts
    ] == ["Empezó en Airbus.", "Confirmó el horario."]
    assert [item.source.id for item in day.references] == ["trip"]
    assert "1 de octubre" in "".join(
        segment.text for segment in day.references[0].blocks[0].segments
    )


def test_virtual_day_remains_openable_when_only_property_relationship_exists(
    tmp_path: Path, schema: dict
) -> None:
    calendar = service(tmp_path, schema)
    day = calendar.day("2026-10-02")

    assert day.materialized is False
    assert day.content == ()
    assert [item.source.id for item in day.journals] == ["journal-two"]
    assert day.captures == ()
    assert day.references == ()
    assert not (tmp_path / "vault" / "calendar" / "days" / "2026-10-02.md").exists()


def test_journals_belong_only_to_entry_date_not_capture_chronology(
    tmp_path: Path, schema: dict
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write(
        vault,
        "journal/one.md",
        "journal-one",
        "Diario A",
        "journal_entry",
        "# Added [[calendar/days/2026-10-02|02-10-2026]]\n- Escribí esto un día después.",
        properties={"entry_date": "2026-10-01"},
    )
    write(
        vault,
        "journal/two.md",
        "journal-two",
        "Diario B",
        "journal_entry",
        "# Added [[calendar/days/2026-10-01|01-10-2026]]\n- Otra entrada del mismo día.",
        properties={"entry_date": "2026-10-01"},
    )
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "runtime" / "context.sqlite3")
    index.rebuild(repository, schema, Embedder())
    calendar = CalendarQueryService(
        repository, schema, NotesQueryService(repository, schema, index)
    )

    first = calendar.day("2026-10-01")
    assert [item.source.id for item in first.journals] == ["journal-one", "journal-two"]
    assert first.captures == ()

    second = calendar.day("2026-10-02")
    assert second.journals == ()
    assert second.captures == ()

    month = calendar.month("2026-10")
    assert month.days[0].journal_count == 2
    assert month.days[0].captured_fact_count == 0
    assert month.days[1].journal_count == 0
    assert month.days[1].captured_fact_count == 0


@pytest.mark.parametrize("value", ["", "2026-1", "2026-13", " 2026-10"])
def test_invalid_months_fail_closed(value: str) -> None:
    with pytest.raises(CalendarQueryError):
        normalize_month(value)
