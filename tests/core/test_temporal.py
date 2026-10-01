"""Deterministic Temporal Foundation and Calendar Day repository tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal import (
    CalendarDayCollisionError,
    CalendarDayRepository,
    DateRange,
    TemporalValueError,
    calendar_day_id,
    calendar_day_path,
    day_range,
    month_range,
    normalize_iso_date,
    week_range,
    year_range,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def schema() -> dict:
    """Load the production schema containing the Calendar-managed Day type."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Create one isolated authoritative Markdown vault."""
    target = tmp_path / "vault"
    target.mkdir()
    return target


def canonical_note(
    *,
    note_id: str,
    note_type: str,
    name: str,
    properties: dict[str, object] | None = None,
    deleted: bool | None = None,
) -> str:
    """Serialize one valid canonical fixture with optional Calendar metadata."""
    metadata: dict[str, object] = {
        "id": note_id,
        "name": name,
        "type": note_type,
        "created_at": "2026-10-01T12:00:00+02:00",
        "updated_at": "2026-10-01T12:00:00+02:00",
        "created_by": {"human": None, "app": "test"},
        "updated_by": {"human": None, "app": "test"},
        "revision": 1,
        "schema_version": 3,
        **(properties or {}),
    }
    if deleted is not None:
        metadata["deleted"] = deleted
    return serialize_note(Note(metadata, ""))


def test_strict_iso_date_identity_path_and_ranges() -> None:
    """Normalize exact dates and derive deterministic identities plus half-open views."""
    assert normalize_iso_date("2026-10-01") == "2026-10-01"
    assert normalize_iso_date("2024-02-29") == "2024-02-29"
    assert calendar_day_id("2026-10-01") == "date:2026-10-01"
    assert calendar_day_path("2026-10-01") == "calendar/days/2026-10-01.md"
    assert day_range("2026-10-01") == DateRange("2026-10-01", "2026-10-02")
    assert week_range("2026-10-04") == DateRange("2026-09-28", "2026-10-05")
    assert month_range("2026-12-31") == DateRange("2026-12-01", "2027-01-01")
    assert year_range("2026-10-01") == DateRange("2026-01-01", "2027-01-01")


@pytest.mark.parametrize(
    "value",
    ["", "2026-1-01", "20261001", " 2026-10-01", "2026-02-29", "2026-13-01"],
)
def test_noncanonical_or_invalid_dates_fail_closed(value: str) -> None:
    """Reject ambiguous, padded, compact, and impossible date inputs."""
    with pytest.raises(TemporalValueError):
        normalize_iso_date(value)


def test_supported_range_overflow_fails_closed() -> None:
    """Avoid inventing non-ISO year 10000 boundaries."""
    with pytest.raises(TemporalValueError):
        day_range("9999-12-31")
    with pytest.raises(TemporalValueError):
        month_range("9999-12-01")
    with pytest.raises(TemporalValueError):
        year_range("9999-01-01")


def test_virtual_day_resolution_creates_no_markdown_or_directory(vault: Path, schema: dict) -> None:
    """Address every date without pre-materializing the Calendar namespace."""
    days = CalendarDayRepository(VaultRepository(vault), schema)

    resolved = days.resolve("2026-10-01")

    assert resolved.date == "2026-10-01"
    assert resolved.id == "date:2026-10-01"
    assert resolved.path == "calendar/days/2026-10-01.md"
    assert resolved.materialized is False
    assert resolved.note is None
    assert not (vault / "calendar").exists()


def test_materialization_creates_one_canonical_day_and_is_idempotent(
    vault: Path, schema: dict
) -> None:
    """Materialize the deterministic identity once without changing it on repeat calls."""
    days = CalendarDayRepository(VaultRepository(vault), schema)
    actor = {"human": "user-1", "app": "calendar"}

    first = days.materialize("2026-10-01", actor=actor, now="2026-10-01T12:30:00+02:00")
    target = vault / "calendar" / "days" / "2026-10-01.md"
    original = target.read_text(encoding="utf-8")
    second = days.materialize("2026-10-01", actor=actor, now="2026-10-01T13:00:00+02:00")

    assert first.materialized is True
    assert second.materialized is True
    assert first.id == second.id == "date:2026-10-01"
    assert target.read_text(encoding="utf-8") == original
    assert VaultRepository(vault).list_markdown_paths() == ["calendar/days/2026-10-01.md"]

    parsed = parse_note(original)
    assert parsed.metadata["id"] == "date:2026-10-01"
    assert parsed.metadata["type"] == "calendar_day"
    assert parsed.metadata["date"] == "2026-10-01"
    assert parsed.metadata["name"] == "2026-10-01"
    assert parsed.metadata["created_by"] == actor
    assert parsed.metadata["updated_by"] == actor
    assert parsed.metadata["revision"] == 1
    assert parsed.content == ""


def test_resolve_reuses_existing_matching_day(vault: Path, schema: dict) -> None:
    """Load a valid deterministic Day directly without semantic resolution."""
    target = vault / "calendar" / "days"
    target.mkdir(parents=True)
    (target / "2026-10-01.md").write_text(
        canonical_note(
            note_id="date:2026-10-01",
            note_type="calendar_day",
            name="Thursday",
            properties={"date": "2026-10-01"},
        ),
        encoding="utf-8",
    )

    resolved = CalendarDayRepository(VaultRepository(vault), schema).resolve("2026-10-01")

    assert resolved.materialized is True
    assert resolved.note is not None
    assert resolved.note.metadata["name"] == "Thursday"


@pytest.mark.parametrize(
    ("note_id", "note_type", "properties", "deleted"),
    [
        ("other", "concept", {}, None),
        ("other", "calendar_day", {"date": "2026-10-01"}, None),
        ("date:2026-10-01", "calendar_day", {"date": "2026-10-02"}, None),
        ("date:2026-10-01", "calendar_day", {"date": "2026-10-01"}, True),
    ],
)
def test_deterministic_path_mismatch_fails_closed(
    vault: Path,
    schema: dict,
    note_id: str,
    note_type: str,
    properties: dict[str, object],
    deleted: bool | None,
) -> None:
    """Never reinterpret or overwrite conflicting canonical state at a Day path."""
    target = vault / "calendar" / "days"
    target.mkdir(parents=True)
    (target / "2026-10-01.md").write_text(
        canonical_note(
            note_id=note_id,
            note_type=note_type,
            name="Collision",
            properties=properties,
            deleted=deleted,
        ),
        encoding="utf-8",
    )

    with pytest.raises(CalendarDayCollisionError):
        CalendarDayRepository(VaultRepository(vault), schema).resolve("2026-10-01")


def test_malformed_deterministic_path_fails_closed(vault: Path, schema: dict) -> None:
    """Treat malformed Markdown at the Day path as a collision, never as a virtual Day."""
    target = vault / "calendar" / "days"
    target.mkdir(parents=True)
    (target / "2026-10-01.md").write_text("---\nid: broken\n", encoding="utf-8")

    with pytest.raises(CalendarDayCollisionError):
        CalendarDayRepository(VaultRepository(vault), schema).resolve("2026-10-01")


def test_misplaced_day_identity_or_date_claim_fails_closed(vault: Path, schema: dict) -> None:
    """Reject duplicate logical Day ownership outside the deterministic Calendar path."""
    archive = vault / "archive"
    archive.mkdir()
    (archive / "day.md").write_text(
        canonical_note(
            note_id="date:2026-10-01",
            note_type="calendar_day",
            name="Misplaced",
            properties={"date": "2026-10-01"},
        ),
        encoding="utf-8",
    )

    with pytest.raises(CalendarDayCollisionError, match="claimed elsewhere"):
        CalendarDayRepository(VaultRepository(vault), schema).resolve("2026-10-01")


def test_calendar_directory_symlink_escape_is_rejected_before_write(
    tmp_path: Path, schema: dict
) -> None:
    """Never create Calendar content through a managed-directory symlink outside the vault."""
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault / "calendar").symlink_to(outside, target_is_directory=True)
    days = CalendarDayRepository(VaultRepository(vault), schema)

    with pytest.raises(CalendarDayCollisionError, match="escapes"):
        days.materialize("2026-10-01", actor="calendar", now="2026-10-01T12:00:00+02:00")

    assert not (outside / "days").exists()


def test_direct_date_range_construction_preserves_half_open_invariant() -> None:
    """Reject reversed, empty, or noncanonical ranges even outside helper constructors."""
    with pytest.raises(TemporalValueError):
        DateRange("2026-10-01", "2026-10-01")
    with pytest.raises(TemporalValueError):
        DateRange("2026-10-02", "2026-10-01")
    with pytest.raises(TemporalValueError):
        DateRange("2026-1-01", "2026-10-01")


def test_day_repository_requires_calendar_managed_schema(vault: Path, schema: dict) -> None:
    """Fail before virtual resolution when the schema does not delegate the type to Calendar."""
    changed = json.loads(json.dumps(schema))
    day = next(item for item in changed["types"] if item["id"] == "calendar_day")
    del day["managed_by"]

    with pytest.raises(ValueError, match="not delegated"):
        CalendarDayRepository(VaultRepository(vault), changed)
