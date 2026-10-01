"""Deterministic Calendar v0 projections over canonical Odyssey Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from odyssey_core.atomic_facts import capture_heading_date
from odyssey_core.note_queries import NoteBodyBlock, NotesQueryError, NotesQueryService, NoteSummary
from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.storage import NoteUnavailableError, VaultRepository
from odyssey_core.temporal import (
    CALENDAR_DAY_TYPE,
    CalendarDayRepository,
    TemporalValueError,
    calendar_day_id,
    calendar_day_link_dates,
    normalize_iso_date,
)

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_LEVEL_ONE_HEADING = re.compile(r"^#\s+")


class CalendarQueryError(RuntimeError):
    """Indicate that a Calendar projection cannot be grounded safely."""


@dataclass(frozen=True, slots=True)
class CalendarMonthDay:
    date: str
    materialized: bool
    has_content: bool
    journal_count: int
    captured_fact_count: int
    reference_count: int


@dataclass(frozen=True, slots=True)
class CalendarMonth:
    month: str
    days: tuple[CalendarMonthDay, ...]


@dataclass(frozen=True, slots=True)
class CalendarCapture:
    source: NoteSummary
    facts: tuple[NoteBodyBlock, ...]


@dataclass(frozen=True, slots=True)
class CalendarReference:
    source: NoteSummary
    blocks: tuple[NoteBodyBlock, ...]


@dataclass(frozen=True, slots=True)
class CalendarDayView:
    date: str
    materialized: bool
    content: tuple[NoteBodyBlock, ...]
    journals: tuple[NoteSummary, ...]
    captures: tuple[CalendarCapture, ...]
    references: tuple[CalendarReference, ...]


@dataclass(frozen=True, slots=True)
class _ScannedNote:
    id: str
    type: str
    entry_date: str | None
    calendar_date: str | None
    body: str
    capture_counts: dict[str, int]
    explicit_dates: tuple[str, ...]


def normalize_month(value: str) -> str:
    """Return one exact YYYY-MM calendar month."""
    if not isinstance(value, str) or _MONTH.fullmatch(value) is None:
        raise CalendarQueryError("Calendar month must use YYYY-MM")
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError as error:
        raise CalendarQueryError("Calendar month is invalid") from error
    if parsed.strftime("%Y-%m") != value:
        raise CalendarQueryError("Calendar month must be canonical")
    return value


def _month_dates(value: str) -> tuple[str, ...]:
    month = normalize_month(value)
    current = date.fromisoformat(f"{month}-01")
    result: list[str] = []
    while current.strftime("%Y-%m") == month:
        result.append(current.isoformat())
        current += timedelta(days=1)
    return tuple(result)


def _capture_counts(body: str) -> dict[str, int]:
    """Count visible list-item facts under supported Added headings."""
    counts: dict[str, int] = {}
    current: str | None = None
    for raw in body.splitlines():
        line = raw.strip()
        detected = capture_heading_date(line)
        if detected is not None:
            current = detected
            counts.setdefault(current, 0)
            continue
        if _LEVEL_ONE_HEADING.match(line):
            current = None
            continue
        if current is not None and line.startswith("- ") and line[2:].strip():
            counts[current] = counts.get(current, 0) + 1
    return counts


def _without_capture_headings(body: str) -> str:
    """Remove only Added heading lines so their chronology links are not semantic references."""
    return "\n".join(raw for raw in body.splitlines() if capture_heading_date(raw.strip()) is None)


def _visible_heading_date(block: NoteBodyBlock) -> str | None:
    if block.kind != "heading":
        return None
    text = "".join(segment.text for segment in block.segments).strip()
    match = re.fullmatch(r"Added (\d{2})-(\d{2})-(\d{4})", text)
    if match is None:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _capture_blocks(
    blocks: tuple[NoteBodyBlock, ...], target_date: str
) -> tuple[NoteBodyBlock, ...]:
    result: list[NoteBodyBlock] = []
    current: str | None = None
    for block in blocks:
        heading_date = _visible_heading_date(block)
        if block.kind == "heading":
            current = heading_date
            continue
        if current == target_date and block.kind == "list_item":
            result.append(block)
    return tuple(result)


def _reference_blocks(
    blocks: tuple[NoteBodyBlock, ...], target_id: str
) -> tuple[NoteBodyBlock, ...]:
    return tuple(
        block
        for block in blocks
        if block.kind != "heading"
        and any(segment.target_id == target_id for segment in block.segments)
    )


class CalendarQueryService:
    """Project virtual/materialized Calendar Days without giving the browser Markdown authority."""

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        notes_service: NotesQueryService,
    ) -> None:
        self.repository = repository
        self.schema = schema
        self.notes_service = notes_service

    def _scan(self) -> tuple[_ScannedNote, ...]:
        scanned: list[_ScannedNote] = []
        for path in self.repository.list_markdown_paths():
            try:
                note = parse_note(self.repository.read_text(path))
                validate_note(note, self.schema)
            except (NoteUnavailableError, NoteFormatError, NoteValidationError, OSError) as error:
                raise CalendarQueryError(
                    "Calendar cannot inspect invalid canonical state"
                ) from error
            if note.metadata.get("deleted") is True:
                continue
            body = note.content
            try:
                explicit_dates = calendar_day_link_dates(_without_capture_headings(body))
            except TemporalValueError as error:
                raise CalendarQueryError("Calendar encountered an invalid temporal link") from error
            note_type = str(note.metadata["type"])
            scanned.append(
                _ScannedNote(
                    id=str(note.metadata["id"]),
                    type=note_type,
                    entry_date=(
                        str(note.metadata["entry_date"])
                        if note_type == "journal_entry"
                        and note.metadata.get("entry_date") is not None
                        else None
                    ),
                    calendar_date=(
                        str(note.metadata["date"])
                        if note_type == CALENDAR_DAY_TYPE and note.metadata.get("date") is not None
                        else None
                    ),
                    body=body,
                    capture_counts=_capture_counts(body),
                    explicit_dates=explicit_dates,
                )
            )
        return tuple(scanned)

    def month(self, value: str) -> CalendarMonth:
        """Return every day in one month with bounded deterministic activity indicators."""
        month = normalize_month(value)
        dates = _month_dates(month)
        state = {
            value: {
                "materialized": False,
                "has_content": False,
                "journal_count": 0,
                "captured_fact_count": 0,
                "reference_count": 0,
            }
            for value in dates
        }
        for note in self._scan():
            if note.calendar_date in state:
                state[note.calendar_date]["materialized"] = True
                state[note.calendar_date]["has_content"] = bool(note.body.strip())
            if note.entry_date in state:
                state[note.entry_date]["journal_count"] += 1
            for captured_date, count in note.capture_counts.items():
                if captured_date in state:
                    state[captured_date]["captured_fact_count"] += count
            for referenced_date in note.explicit_dates:
                if referenced_date in state:
                    state[referenced_date]["reference_count"] += 1
        return CalendarMonth(
            month,
            tuple(CalendarMonthDay(date=value, **state[value]) for value in dates),
        )

    def day(self, value: str) -> CalendarDayView:
        """Return one virtual or materialized Day split into the approved semantic categories."""
        try:
            normalized = normalize_iso_date(value)
            resolved = CalendarDayRepository(self.repository, self.schema).resolve(normalized)
        except (TemporalValueError, RuntimeError, ValueError) as error:
            raise CalendarQueryError("Calendar day is unavailable") from error
        target_id = calendar_day_id(normalized)
        content: tuple[NoteBodyBlock, ...] = ()
        if resolved.materialized:
            try:
                content = self.notes_service.detail(target_id).body_blocks
            except NotesQueryError as error:
                raise CalendarQueryError("Calendar day detail is unavailable") from error

        journals: list[NoteSummary] = []
        captures: list[CalendarCapture] = []
        references: list[CalendarReference] = []
        for note in self._scan():
            relevant_capture = note.capture_counts.get(normalized, 0) > 0
            relevant_reference = normalized in note.explicit_dates
            relevant_journal = note.type == "journal_entry" and note.entry_date == normalized
            if not (relevant_capture or relevant_reference or relevant_journal):
                continue
            try:
                detail = self.notes_service.detail(note.id)
            except NotesQueryError as error:
                raise CalendarQueryError("Calendar related note is unavailable") from error
            if relevant_journal:
                journals.append(detail.note)
            if relevant_capture:
                facts = _capture_blocks(detail.body_blocks, normalized)
                if facts:
                    captures.append(CalendarCapture(detail.note, facts))
            if relevant_reference:
                blocks = _reference_blocks(detail.body_blocks, target_id)
                if blocks:
                    references.append(CalendarReference(detail.note, blocks))

        def summary_key(summary: NoteSummary) -> tuple[str, str]:
            return (summary.name.casefold(), summary.id)

        journals.sort(key=summary_key)
        captures.sort(key=lambda item: summary_key(item.source))
        references.sort(key=lambda item: summary_key(item.source))
        return CalendarDayView(
            normalized,
            resolved.materialized,
            content,
            tuple(journals),
            tuple(captures),
            tuple(references),
        )
