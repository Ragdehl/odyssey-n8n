"""Deterministic Calendar v0 projections over canonical Odyssey Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
    """Represent bounded Calendar activity indicators for one date."""

    date: str
    materialized: bool
    has_content: bool
    journal_count: int
    captured_fact_count: int
    reference_count: int
    task_count: int = 0


@dataclass(frozen=True, slots=True)
class CalendarMonth:
    """Represent Calendar's deterministic projection for one calendar month."""

    month: str
    days: tuple[CalendarMonthDay, ...]


@dataclass(frozen=True, slots=True)
class CalendarJournal:
    """Represent a journal's semantic association with one Calendar day."""

    source: NoteSummary
    content: tuple[NoteBodyBlock, ...]


@dataclass(frozen=True, slots=True)
class CalendarCapture:
    """Represent atomic facts captured on one Calendar day."""

    source: NoteSummary
    facts: tuple[NoteBodyBlock, ...]


@dataclass(frozen=True, slots=True)
class CalendarReference:
    """Represent explicit canonical references to one Calendar day."""

    source: NoteSummary
    blocks: tuple[NoteBodyBlock, ...]


@dataclass(frozen=True, slots=True)
class CalendarTask:
    """Represent one canonical Task projected onto a Calendar day by scheduling metadata."""

    source: NoteSummary
    roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CalendarDayView:
    """Represent Calendar's category-preserving projection for one virtual or materialized day."""

    date: str
    materialized: bool
    content: tuple[NoteBodyBlock, ...]
    journals: tuple[CalendarJournal, ...]
    captures: tuple[CalendarCapture, ...]
    references: tuple[CalendarReference, ...]
    tasks: tuple[CalendarTask, ...] = ()


@dataclass(frozen=True, slots=True)
class _ScannedNote:
    """Hold validated Markdown facts needed by the bounded Calendar scan."""

    id: str
    type: str
    entry_date: str | None
    calendar_date: str | None
    body: str
    capture_counts: dict[str, int]
    explicit_dates: tuple[str, ...]
    calendar_roles: dict[str, tuple[str, ...]]


def _calendar_roles_for_note(
    metadata: dict[str, Any], schema: dict[str, Any]
) -> dict[str, tuple[str, ...]]:
    """Project schema-declared calendar-role metadata into local ISO dates.

    The application that owns a type declares which of its properties are calendar coordinates.
    Calendar reads that canonical declaration rather than hard-coding Tasks lifecycle fields.
    """
    note_type = metadata.get("type")
    definition = next(
        (item for item in schema.get("types", ()) if item.get("id") == note_type),
        None,
    )
    if not isinstance(definition, dict):
        return {}
    by_date: dict[str, list[str]] = {}
    for property_ in definition.get("properties", ()):
        if not isinstance(property_, dict):
            continue
        role = property_.get("calendar_role")
        field = property_.get("id")
        if not isinstance(role, str) or not role or not isinstance(field, str):
            continue
        value = metadata.get(field)
        if not isinstance(value, str):
            continue
        try:
            if len(value) == 10:
                projected = date.fromisoformat(value).isoformat()
            else:
                instant = datetime.fromisoformat(value)
                if instant.tzinfo is None:
                    raise ValueError("calendar date-time must be offset-aware")
                projected = instant.date().isoformat()
        except ValueError as error:
            raise CalendarQueryError("Calendar encountered invalid scheduling metadata") from error
        by_date.setdefault(projected, []).append(role)
    return {key: tuple(dict.fromkeys(value)) for key, value in by_date.items()}


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
    """Return every ISO date within one validated calendar month."""
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
    """Remove only chronology headings so they are not semantic temporal references."""
    return "\n".join(raw for raw in body.splitlines() if capture_heading_date(raw.strip()) is None)


def _visible_heading_date(block: NoteBodyBlock) -> str | None:
    """Return the normalized date from one rendered Added heading, if present."""
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
    """Return fact blocks captured beneath one requested Added heading."""
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
    """Return visible blocks with a Core-resolved link to the requested day."""
    return tuple(
        block
        for block in blocks
        if block.kind != "heading"
        and any(segment.target_id == target_id for segment in block.segments)
    )


def _journal_blocks(blocks: tuple[NoteBodyBlock, ...]) -> tuple[NoteBodyBlock, ...]:
    """Return journal content without capture chronology already projected separately."""
    return tuple(block for block in blocks if _visible_heading_date(block) is None)


class CalendarQueryService:
    """Project virtual/materialized Calendar Days without giving the browser Markdown authority."""

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        notes_service: NotesQueryService,
    ) -> None:
        """Bind validated Core read services used by Calendar's deterministic projections."""
        self.repository = repository
        self.schema = schema
        self.notes_service = notes_service

    def _scan(self) -> tuple[_ScannedNote, ...]:
        """Read validated canonical Markdown into Calendar's bounded projection inputs."""
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
                    calendar_roles=_calendar_roles_for_note(dict(note.metadata), self.schema),
                )
            )
        return tuple(scanned)

    def month(self, value: str) -> CalendarMonth:
        """Return every day in one month with bounded deterministic activity indicators."""
        month = normalize_month(value)
        dates = _month_dates(month)
        state = {
            item: {
                "materialized": False,
                "has_content": False,
                "journal_count": 0,
                "captured_fact_count": 0,
                "reference_count": 0,
                "task_count": 0,
            }
            for item in dates
        }
        for note in self._scan():
            if note.calendar_date in state:
                state[note.calendar_date]["materialized"] = True
                state[note.calendar_date]["has_content"] = bool(note.body.strip())
            if note.entry_date in state:
                state[note.entry_date]["journal_count"] += 1
            if note.type != "journal_entry":
                for captured_date, count in note.capture_counts.items():
                    if captured_date in state:
                        state[captured_date]["captured_fact_count"] += count
            for referenced_date in note.explicit_dates:
                if referenced_date in state:
                    state[referenced_date]["reference_count"] += 1
            if note.type == "task":
                for scheduled_date in note.calendar_roles:
                    if scheduled_date in state:
                        state[scheduled_date]["task_count"] += 1
        return CalendarMonth(
            month,
            tuple(CalendarMonthDay(date=item, **state[item]) for item in dates),
        )

    def day(self, value: str) -> CalendarDayView:
        """Return one virtual or materialized Day split into approved semantic categories."""
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

        journals: list[CalendarJournal] = []
        captures: list[CalendarCapture] = []
        references: list[CalendarReference] = []
        tasks: list[CalendarTask] = []
        for note in self._scan():
            relevant_capture = note.capture_counts.get(normalized, 0) > 0
            relevant_reference = normalized in note.explicit_dates
            relevant_journal = note.type == "journal_entry" and note.entry_date == normalized
            relevant_task = note.type == "task" and normalized in note.calendar_roles
            if not (relevant_capture or relevant_reference or relevant_journal or relevant_task):
                continue
            try:
                detail = self.notes_service.detail(note.id)
            except NotesQueryError as error:
                raise CalendarQueryError("Calendar related note is unavailable") from error
            if relevant_journal:
                journals.append(CalendarJournal(detail.note, _journal_blocks(detail.body_blocks)))
            # Journal entries belong to their semantic entry_date in Calendar. Their
            # capture chronology remains available to Odyssey history, but must not
            # duplicate the journal under another Day's "Captured" projection.
            if relevant_capture and note.type != "journal_entry":
                facts = _capture_blocks(detail.body_blocks, normalized)
                if facts:
                    captures.append(CalendarCapture(detail.note, facts))
            if relevant_reference and not relevant_journal:
                blocks = _reference_blocks(detail.body_blocks, target_id)
                if blocks:
                    references.append(CalendarReference(detail.note, blocks))
            if relevant_task:
                tasks.append(CalendarTask(detail.note, note.calendar_roles[normalized]))

        def summary_key(summary: NoteSummary) -> tuple[str, str]:
            return (summary.name.casefold(), summary.id)

        journals.sort(key=lambda item: summary_key(item.source))
        captures.sort(key=lambda item: summary_key(item.source))
        references.sort(key=lambda item: summary_key(item.source))
        tasks.sort(key=lambda item: summary_key(item.source))
        return CalendarDayView(
            normalized,
            resolved.materialized,
            content,
            tuple(journals),
            tuple(captures),
            tuple(references),
            tuple(tasks),
        )
