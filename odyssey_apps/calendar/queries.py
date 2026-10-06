"""Deterministic Calendar v0 projections over canonical Odyssey Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from odyssey_core.atomic_facts import (
    AtomicFact,
    AtomicFactError,
    capture_heading_date,
    parse_atomic_facts,
)
from odyssey_core.note_queries import (
    NoteBodyBlock,
    NoteDetail,
    NotesQueryError,
    NotesQueryService,
    NoteSummary,
)
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
_MONTH_PREVIEW_LIMIT = 6
_MONTH_PREVIEW_LABEL_LIMIT = 80
_MONTH_PREVIEW_TEXT_LIMIT = 120


class CalendarQueryError(RuntimeError):
    """Indicate that a Calendar projection cannot be grounded safely."""


@dataclass(frozen=True, slots=True)
class CalendarMonthPreview:
    """Represent one presentation-only semantic source preview for a Calendar month Day."""

    kind: str
    source_type: str
    label: str
    text: str | None


@dataclass(frozen=True, slots=True)
class CalendarMonthDay:
    """Represent one month Day with stable activity counts and bounded previews."""

    date: str
    materialized: bool
    has_content: bool
    journal_count: int
    captured_fact_count: int
    reference_count: int
    task_count: int = 0
    preview_total: int = 0
    previews: tuple[CalendarMonthPreview, ...] = ()


@dataclass(frozen=True, slots=True)
class CalendarMonth:
    """Represent Calendar's deterministic projection for one calendar month."""

    month: str
    days: tuple[CalendarMonthDay, ...]


@dataclass(frozen=True, slots=True)
class CalendarScheduleItem:
    """Represent one grounded all-day or timed item in a bounded schedule projection."""

    kind: str
    source_id: str
    source_type: str
    label: str
    text: str | None
    role: str
    start_time: str | None = None
    end_time: str | None = None


@dataclass(frozen=True, slots=True)
class CalendarScheduleDay:
    """Represent one date in a bounded 1/3/7-day schedule window."""

    date: str
    all_day: tuple[CalendarScheduleItem, ...]
    timed: tuple[CalendarScheduleItem, ...]


@dataclass(frozen=True, slots=True)
class CalendarSchedule:
    """Represent one deterministic consecutive Calendar schedule window."""

    start_date: str
    day_count: int
    days: tuple[CalendarScheduleDay, ...]


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
    revision: int
    source_hash: str


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
    name: str
    type: str
    entry_date: str | None
    calendar_date: str | None
    body: str
    metadata: dict[str, Any]
    atomic_facts: tuple[AtomicFact, ...]
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


def _bounded_preview_text(value: str, limit: int) -> str:
    """Normalize and bound one non-authoritative month-preview display string."""
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"


def _preview_text(blocks: tuple[NoteBodyBlock, ...]) -> str | None:
    """Return one bounded visible Core-rendered snippet without exposing Markdown."""
    for block in blocks:
        if block.kind == "heading":
            continue
        text = "".join(segment.text for segment in block.segments)
        if text.strip():
            return _bounded_preview_text(text, _MONTH_PREVIEW_TEXT_LIMIT)
    return None


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
                atomic_facts = parse_atomic_facts(body)
            except (TemporalValueError, AtomicFactError) as error:
                raise CalendarQueryError(
                    "Calendar encountered invalid temporal evidence"
                ) from error
            note_type = str(note.metadata["type"])
            scanned.append(
                _ScannedNote(
                    id=str(note.metadata["id"]),
                    name=str(note.metadata["name"]),
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
                    metadata=dict(note.metadata),
                    atomic_facts=atomic_facts,
                    capture_counts=_capture_counts(body),
                    explicit_dates=explicit_dates,
                    calendar_roles=_calendar_roles_for_note(dict(note.metadata), self.schema),
                )
            )
        return tuple(scanned)

    def month(self, value: str) -> CalendarMonth:
        """Return every day with preserved counts and four ordered visible source previews."""
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
                "candidates": {
                    "day_content": [],
                    "journal": [],
                    "capture": [],
                    "task": [],
                    "reference": [],
                },
            }
            for item in dates
        }
        scanned = self._scan()
        scanned_by_id = {note.id: note for note in scanned}
        for note in scanned:
            if note.calendar_date in state:
                state[note.calendar_date]["materialized"] = True
                state[note.calendar_date]["has_content"] = bool(note.body.strip())
                if note.body.strip():
                    state[note.calendar_date]["candidates"]["day_content"].append(note.id)
            if note.entry_date in state:
                state[note.entry_date]["journal_count"] += 1
                state[note.entry_date]["candidates"]["journal"].append(note.id)
            if note.type != "journal_entry":
                for captured_date, count in note.capture_counts.items():
                    if captured_date in state:
                        state[captured_date]["captured_fact_count"] += count
                        if count:
                            state[captured_date]["candidates"]["capture"].append(note.id)
            for referenced_date in note.explicit_dates:
                if referenced_date in state:
                    state[referenced_date]["reference_count"] += 1
                    if not (note.type == "journal_entry" and note.entry_date == referenced_date):
                        state[referenced_date]["candidates"]["reference"].append(note.id)
            if note.type == "task":
                for scheduled_date in note.calendar_roles:
                    if scheduled_date in state:
                        state[scheduled_date]["task_count"] += 1
                        state[scheduled_date]["candidates"]["task"].append(note.id)

        details: dict[str, NoteDetail] = {}

        def detail(note_id: str) -> NoteDetail:
            """Resolve one related source through the existing Core Note detail boundary."""
            if note_id not in details:
                try:
                    details[note_id] = self.notes_service.detail(note_id)
                except NotesQueryError as error:
                    raise CalendarQueryError("Calendar preview source is unavailable") from error
            return details[note_id]

        def preview(kind: str, note_id: str, target_date: str) -> CalendarMonthPreview:
            """Build one visible category preview through Core-resolved presentation blocks."""
            scanned_note = scanned_by_id[note_id]
            blocks = detail(note_id).body_blocks
            if kind == "journal":
                blocks = _journal_blocks(blocks)
            elif kind == "capture":
                blocks = _capture_blocks(blocks, target_date)
            elif kind == "reference":
                blocks = _reference_blocks(blocks, calendar_day_id(target_date))
            return CalendarMonthPreview(
                kind,
                scanned_note.type,
                _bounded_preview_text(scanned_note.name, _MONTH_PREVIEW_LABEL_LIMIT),
                _preview_text(blocks),
            )

        result: list[CalendarMonthDay] = []
        for item in dates:
            day_state = state[item]
            ordered_ids: list[tuple[str, str]] = []
            for kind in ("day_content", "journal", "capture", "task", "reference"):
                source_ids = day_state["candidates"][kind]
                source_ids.sort(
                    key=lambda source_id: (
                        scanned_by_id[source_id].name.casefold(),
                        source_id,
                    )
                )
                ordered_ids.extend((kind, source_id) for source_id in source_ids)
            public_state = {key: value for key, value in day_state.items() if key != "candidates"}
            result.append(
                CalendarMonthDay(
                    date=item,
                    **public_state,
                    preview_total=len(ordered_ids),
                    previews=tuple(
                        preview(kind, source_id, item)
                        for kind, source_id in ordered_ids[:_MONTH_PREVIEW_LIMIT]
                    ),
                )
            )
        return CalendarMonth(
            month,
            tuple(result),
        )

    def schedule(self, start_date: str, day_count: int) -> CalendarSchedule:
        """Return one deterministic 1/3/7-day schedule from grounded temporal evidence."""
        try:
            normalized = normalize_iso_date(start_date)
        except TemporalValueError as error:
            raise CalendarQueryError("Calendar schedule start date is invalid") from error
        if day_count not in {1, 3, 7}:
            raise CalendarQueryError("Calendar schedule day count is unsupported")

        start = date.fromisoformat(normalized)
        dates = tuple((start + timedelta(days=offset)).isoformat() for offset in range(day_count))
        state: dict[str, dict[str, list[CalendarScheduleItem]]] = {
            item: {"all_day": [], "timed": []} for item in dates
        }

        def timed_coordinate(value: str) -> tuple[str, str]:
            try:
                instant = datetime.fromisoformat(value)
            except ValueError as error:
                raise CalendarQueryError(
                    "Calendar encountered invalid timed scheduling metadata"
                ) from error
            if instant.tzinfo is None or instant.utcoffset() is None:
                raise CalendarQueryError("Calendar encountered naive timed scheduling metadata")
            return instant.date().isoformat(), instant.strftime("%H:%M")

        def add_task(note: _ScannedNote) -> None:
            metadata = note.metadata
            planned_date: str | None = None
            planned_start_time: str | None = None
            planned_start = metadata.get("planned_start_at")
            if isinstance(planned_start, str):
                planned_date, planned_start_time = timed_coordinate(planned_start)
                start_time = planned_start_time
                end_time: str | None = None
                planned_end = metadata.get("planned_end_at")
                if isinstance(planned_end, str):
                    end_date, candidate_end = timed_coordinate(planned_end)
                    if end_date == planned_date and candidate_end > start_time:
                        end_time = candidate_end
                if planned_date in state:
                    state[planned_date]["timed"].append(
                        CalendarScheduleItem(
                            "task",
                            note.id,
                            note.type,
                            _bounded_preview_text(note.name, _MONTH_PREVIEW_LABEL_LIMIT),
                            None,
                            "planned",
                            start_time,
                            end_time,
                        )
                    )

            deadline_date: str | None = None
            deadline = metadata.get("deadline_at")
            if isinstance(deadline, str):
                if len(deadline) == 10:
                    try:
                        deadline_date = normalize_iso_date(deadline)
                    except TemporalValueError as error:
                        raise CalendarQueryError(
                            "Calendar encountered invalid task deadline"
                        ) from error
                    if deadline_date in state:
                        state[deadline_date]["all_day"].append(
                            CalendarScheduleItem(
                                "task",
                                note.id,
                                note.type,
                                _bounded_preview_text(note.name, _MONTH_PREVIEW_LABEL_LIMIT),
                                None,
                                "deadline",
                            )
                        )
                else:
                    deadline_date, deadline_time = timed_coordinate(deadline)
                    if deadline_date in state and not (
                        deadline_date == planned_date and deadline_time == planned_start_time
                    ):
                        state[deadline_date]["timed"].append(
                            CalendarScheduleItem(
                                "task",
                                note.id,
                                note.type,
                                _bounded_preview_text(note.name, _MONTH_PREVIEW_LABEL_LIMIT),
                                None,
                                "deadline",
                                deadline_time,
                            )
                        )

            target = metadata.get("target_date")
            if isinstance(target, str):
                try:
                    target_date = normalize_iso_date(target)
                except TemporalValueError as error:
                    raise CalendarQueryError(
                        "Calendar encountered invalid task target date"
                    ) from error
                if target_date not in {planned_date, deadline_date} and target_date in state:
                    state[target_date]["all_day"].append(
                        CalendarScheduleItem(
                            "task",
                            note.id,
                            note.type,
                            _bounded_preview_text(note.name, _MONTH_PREVIEW_LABEL_LIMIT),
                            None,
                            "target",
                        )
                    )

        for note in self._scan():
            if note.type == "task":
                add_task(note)
            for fact in note.atomic_facts:
                for anchor in fact.temporal_anchors:
                    if anchor.date not in state:
                        continue
                    item = CalendarScheduleItem(
                        "fact",
                        note.id,
                        note.type,
                        _bounded_preview_text(note.name, _MONTH_PREVIEW_LABEL_LIMIT),
                        _bounded_preview_text(fact.text, _MONTH_PREVIEW_TEXT_LIMIT),
                        "semantic_time" if anchor.time is not None else "semantic_date",
                        anchor.display_time,
                    )
                    state[anchor.date]["timed" if anchor.time is not None else "all_day"].append(
                        item
                    )

        result: list[CalendarScheduleDay] = []
        for item in dates:
            all_day = state[item]["all_day"]
            timed = state[item]["timed"]
            all_day.sort(key=lambda entry: (entry.label.casefold(), entry.source_id, entry.role))
            timed.sort(
                key=lambda entry: (
                    entry.start_time or "99:99",
                    entry.label.casefold(),
                    entry.source_id,
                    entry.role,
                )
            )
            result.append(CalendarScheduleDay(item, tuple(all_day), tuple(timed)))
        return CalendarSchedule(normalized, day_count, tuple(result))

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
                tasks.append(
                    CalendarTask(
                        detail.note,
                        note.calendar_roles[normalized],
                        detail.revision,
                        detail.source_hash,
                    )
                )

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
