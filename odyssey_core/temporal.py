"""Deterministic temporal primitives and Core-owned Day materialization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from odyssey_core.notes import Note, NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.persistence import ActorInput, EntityAlreadyExistsError, create_entity
from odyssey_core.storage import NoteAlreadyExistsError, NoteUnavailableError, VaultRepository

CALENDAR_DAY_TYPE = "calendar_day"
_CALENDAR_ROOT = ("calendar", "days")


class TemporalValueError(ValueError):
    """Indicate a non-canonical or unsupported temporal value."""


class CalendarDayCollisionError(RuntimeError):
    """Indicate that canonical vault state conflicts with one deterministic Calendar Day."""


@dataclass(frozen=True, slots=True)
class DateRange:
    """Represent one normalized half-open calendar-date range."""

    start: str
    end_exclusive: str

    def __post_init__(self) -> None:
        """Protect the public half-open range invariant even for direct construction."""
        start = date.fromisoformat(normalize_iso_date(self.start))
        end = date.fromisoformat(normalize_iso_date(self.end_exclusive))
        if start >= end:
            raise TemporalValueError("Calendar range must have a positive half-open span")


@dataclass(frozen=True, slots=True)
class TemporalAnchor:
    """Represent one semantic temporal coordinate independent of capture time.

    ``date`` is always present. ``time`` and ``offset`` are either both absent or both present.
    Exact times preserve second precision internally; ``display_time`` keeps the ordinary HH:MM
    presentation when seconds are zero.
    """

    date: str
    time: str | None = None
    offset: str | None = None

    def __post_init__(self) -> None:
        normalized_date = normalize_iso_date(self.date)
        object.__setattr__(self, "date", normalized_date)
        if self.time is None and self.offset is None:
            return
        if self.time is None or self.offset is None:
            raise TemporalValueError("Temporal anchor time and offset must be supplied together")
        value = f"{normalized_date}T{self.time}{self.offset}"
        normalized = normalize_iso_datetime(value)
        parsed = datetime.fromisoformat(normalized)
        object.__setattr__(self, "time", parsed.time().isoformat(timespec="seconds"))
        object.__setattr__(self, "offset", normalized[-6:])

    @classmethod
    def from_value(cls, value: str) -> TemporalAnchor:
        """Decode one canonical date or offset-aware exact date-time evidence value."""
        try:
            return cls(normalize_iso_date(value))
        except TemporalValueError:
            normalized = normalize_iso_datetime(value)
            parsed = datetime.fromisoformat(normalized)
            return cls(
                parsed.date().isoformat(),
                parsed.time().isoformat(timespec="seconds"),
                normalized[-6:],
            )

    @property
    def value(self) -> str:
        """Return the canonical durable evidence representation."""
        if self.time is None:
            return self.date
        assert self.offset is not None
        return f"{self.date}T{self.time}{self.offset}"

    @property
    def display_time(self) -> str | None:
        """Return a compact human clock label without discarding non-zero seconds."""
        if self.time is None:
            return None
        return self.time[:5] if self.time.endswith(":00") else self.time


@dataclass(frozen=True, slots=True)
class CalendarDay:
    """Describe one deterministic Day whether or not canonical Markdown exists yet."""

    date: str
    id: str
    path: str
    materialized: bool
    note: Note | None = None


def normalize_iso_date(value: str) -> str:
    """Return an exact ISO calendar date, rejecting alternate or lossy representations."""
    if not isinstance(value, str) or len(value) != 10:
        raise TemporalValueError("Calendar date must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise TemporalValueError("Calendar date is invalid") from error
    if parsed.isoformat() != value:
        raise TemporalValueError("Calendar date must use canonical YYYY-MM-DD")
    return value


def normalize_iso_datetime(value: str, *, timezone: str | None = None) -> str:
    """Return one canonical offset-aware ISO date-time, optionally validated in an IANA zone.

    The model-facing temporal contract may interpret natural wording, but Core remains the authority
    for normalized value shape.  Exact instants use second precision and an explicit UTC offset.
    When ``timezone`` is supplied, the offset must be valid for that local wall time in that zone;
    impossible DST wall times and fabricated offsets therefore fail closed.
    """
    if (
        not isinstance(value, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?[+-]\d{2}:\d{2}", value) is None
    ):
        raise TemporalValueError(
            "Temporal date-time must use YYYY-MM-DDTHH:MM[:SS] with an explicit UTC offset"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise TemporalValueError("Temporal date-time is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TemporalValueError("Temporal date-time requires an explicit UTC offset")
    if parsed.microsecond != 0:
        raise TemporalValueError("Temporal date-time supports second precision only")
    if timezone is not None:
        if not isinstance(timezone, str) or not timezone.strip() or timezone != timezone.strip():
            raise TemporalValueError("Temporal timezone must be a valid IANA timezone")
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise TemporalValueError("Temporal timezone must be a valid IANA timezone") from error
        localized = parsed.astimezone(zone)
        wall_time = parsed.replace(tzinfo=None)
        if (
            localized.replace(tzinfo=None) != wall_time
            or localized.utcoffset() != parsed.utcoffset()
        ):
            raise TemporalValueError(
                "Temporal date-time offset does not match the supplied timezone"
            )
    return parsed.isoformat(timespec="seconds")


def calendar_day_id(value: str) -> str:
    """Return the stable logical identity shared by virtual and materialized Days."""
    return f"date:{normalize_iso_date(value)}"


def calendar_day_path(value: str) -> str:
    """Return the deterministic Calendar Day Markdown path for one date."""
    return f"calendar/days/{normalize_iso_date(value)}.md"


def calendar_day_label(value: str) -> str:
    """Return the canonical human-readable label for one Calendar Day."""
    normalized = normalize_iso_date(value)
    parsed = date.fromisoformat(normalized)
    return f"{parsed.day:02d}-{parsed.month:02d}-{parsed.year}"


def calendar_day_wikilink(value: str, *, label: str | None = None) -> str:
    """Render one ordinary wikilink to the deterministic Calendar Day path."""
    normalized = normalize_iso_date(value)
    if label is None:
        label = calendar_day_label(normalized)
    if (
        not isinstance(label, str)
        or not label.strip()
        or "\n" in label
        or "\r" in label
        or "|" in label
        or "]]" in label
    ):
        raise TemporalValueError("Calendar Day link label is invalid")
    target = calendar_day_path(normalized).removesuffix(".md")
    return f"[[{target}|{label.strip()}]]"


_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
_CALENDAR_LINK_PREFIX = "calendar/days/"


def calendar_day_link_dates(markdown: str) -> tuple[str, ...]:
    """Return unique Calendar Day dates explicitly linked from canonical Markdown.

    A target inside the reserved ``calendar/days/`` namespace must be an exact deterministic Day
    path. Malformed reserved targets fail closed instead of becoming unresolved ordinary links.
    """
    if not isinstance(markdown, str):
        raise TypeError("Markdown must be text")
    dates: list[str] = []
    reserved_occurrences = markdown.count("[[calendar/days/")
    matched_reserved = 0
    for match in _WIKILINK.finditer(markdown):
        target = match.group(1).strip()
        if not target.startswith(_CALENDAR_LINK_PREFIX):
            continue
        matched_reserved += 1
        without_extension = target.removesuffix(".md")
        candidate = without_extension.removeprefix(_CALENDAR_LINK_PREFIX)
        normalized = normalize_iso_date(candidate)
        if without_extension != calendar_day_path(normalized).removesuffix(".md"):
            raise TemporalValueError("Calendar Day link target is not canonical")
        if normalized not in dates:
            dates.append(normalized)
    if matched_reserved != reserved_occurrences:
        raise TemporalValueError("Calendar Day link markup is malformed")
    return tuple(dates)


def _parsed(value: str) -> date:
    """Parse one value only after exact canonical validation."""
    return date.fromisoformat(normalize_iso_date(value))


def _range(start: date, end_exclusive: date) -> DateRange:
    """Serialize an internal half-open range to the public canonical date contract."""
    return DateRange(start.isoformat(), end_exclusive.isoformat())


def day_range(value: str) -> DateRange:
    """Return the half-open range containing exactly one calendar day."""
    start = _parsed(value)
    try:
        return _range(start, start + timedelta(days=1))
    except OverflowError as error:
        raise TemporalValueError("Calendar day range exceeds supported dates") from error


def week_range(value: str) -> DateRange:
    """Return the Monday-through-Sunday week containing one date."""
    current = _parsed(value)
    start = current - timedelta(days=current.weekday())
    try:
        return _range(start, start + timedelta(days=7))
    except OverflowError as error:
        raise TemporalValueError("Calendar week range exceeds supported dates") from error


def month_range(value: str) -> DateRange:
    """Return the half-open calendar month containing one date."""
    current = _parsed(value)
    start = current.replace(day=1)
    if start.year == 9999 and start.month == 12:
        raise TemporalValueError("Calendar month range exceeds supported dates")
    end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return _range(start, end)


def year_range(value: str) -> DateRange:
    """Return the half-open calendar year containing one date."""
    current = _parsed(value)
    if current.year == 9999:
        raise TemporalValueError("Calendar year range exceeds supported dates")
    return _range(date(current.year, 1, 1), date(current.year + 1, 1, 1))


def _load_day_note(
    repository: VaultRepository, schema: dict[str, Any], path: str, expected_date: str
) -> Note:
    """Load one deterministic Day path and verify its Core-owned deterministic identity metadata."""
    try:
        note = parse_note(repository.read_text(path))
        validate_note(note, schema)
    except (NoteUnavailableError, NoteFormatError, NoteValidationError, OSError) as error:
        raise CalendarDayCollisionError(
            "Calendar Day path is occupied by unusable state"
        ) from error
    expected_id = calendar_day_id(expected_date)
    if (
        note.metadata.get("id") != expected_id
        or note.metadata.get("type") != CALENDAR_DAY_TYPE
        or note.metadata.get("date") != expected_date
        or note.metadata.get("deleted") is True
    ):
        raise CalendarDayCollisionError(
            "Calendar Day path conflicts with its deterministic identity"
        )
    return note


def _path_is_occupied(repository: VaultRepository, path: str) -> bool:
    """Return whether the deterministic target already has any filesystem entry."""
    target = repository.root.joinpath(*path.split("/"))
    try:
        return target.exists() or target.is_symlink()
    except OSError as error:
        raise CalendarDayCollisionError("Calendar Day path cannot be inspected safely") from error


def _assert_unique_day_identity(
    repository: VaultRepository,
    schema: dict[str, Any],
    *,
    expected_path: str,
    expected_date: str,
) -> None:
    """Reject misplaced duplicate Day identity/date claims elsewhere in canonical Markdown."""
    expected_id = calendar_day_id(expected_date)
    for path in repository.list_markdown_paths():
        if path == expected_path:
            continue
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError, OSError) as error:
            raise CalendarDayCollisionError(
                "Calendar Day uniqueness cannot be verified against invalid canonical state"
            ) from error
        if note.metadata.get("id") == expected_id or (
            note.metadata.get("type") == CALENDAR_DAY_TYPE
            and note.metadata.get("date") == expected_date
            and note.metadata.get("deleted") is not True
        ):
            raise CalendarDayCollisionError("Calendar Day identity is already claimed elsewhere")


def _ensure_calendar_day_directory(repository: VaultRepository) -> None:
    """Create only the fixed Calendar Day directory tree after containment checks."""
    root = repository.root
    current = root
    for part in _CALENDAR_ROOT:
        candidate = current / part
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise CalendarDayCollisionError(
                "Calendar directory cannot be resolved safely"
            ) from error
        if not resolved.is_relative_to(root):
            raise CalendarDayCollisionError("Calendar directory escapes the canonical vault")
        if candidate.exists():
            if not candidate.is_dir():
                raise CalendarDayCollisionError("Calendar directory path is occupied")
        else:
            try:
                candidate.mkdir()
            except OSError as error:
                raise CalendarDayCollisionError("Calendar directory cannot be created") from error
        current = candidate.resolve(strict=True)


class CalendarDayRepository:
    """Resolve and materialize Core-owned Days without semantic entity search."""

    def __init__(self, repository: VaultRepository, schema: dict[str, Any]) -> None:
        """Bind one authoritative vault and schema that keeps deterministic Days in Core."""
        try:
            definition = next(item for item in schema["types"] if item["id"] == CALENDAR_DAY_TYPE)
        except (KeyError, StopIteration, TypeError) as error:
            raise ValueError("Canonical schema does not define Calendar Day") from error
        if definition.get("managed_by") != "core":
            raise ValueError("Calendar Day is not managed by Core")
        self.repository = repository
        self.schema = schema

    def resolve(self, value: str) -> CalendarDay:
        """Resolve one date directly as virtual or validated materialized canonical Day."""
        normalized = normalize_iso_date(value)
        path = calendar_day_path(normalized)
        identity = calendar_day_id(normalized)
        _assert_unique_day_identity(
            self.repository,
            self.schema,
            expected_path=path,
            expected_date=normalized,
        )
        if not _path_is_occupied(self.repository, path):
            return CalendarDay(normalized, identity, path, False, None)
        note = _load_day_note(self.repository, self.schema, path, normalized)
        return CalendarDay(normalized, identity, path, True, note)

    def materialize(
        self, value: str, *, actor: ActorInput, now: str, content: str = ""
    ) -> CalendarDay:
        """Create one canonical Day with optional initial content, or return an existing Day."""
        if not isinstance(content, str):
            raise TypeError("Calendar Day content must be text")
        current = self.resolve(value)
        if current.materialized:
            return current
        _ensure_calendar_day_directory(self.repository)
        try:
            create_entity(
                self.repository,
                self.schema,
                path=current.path,
                entity_id=current.id,
                metadata={
                    "name": current.date,
                    "type": CALENDAR_DAY_TYPE,
                    "date": current.date,
                },
                content=content,
                actor=actor,
                now=now,
            )
        except (EntityAlreadyExistsError, NoteAlreadyExistsError) as error:
            try:
                raced = self.resolve(current.date)
            except CalendarDayCollisionError:
                raise CalendarDayCollisionError(
                    "Concurrent Calendar Day materialization produced conflicting state"
                ) from error
            if raced.materialized:
                return raced
            raise CalendarDayCollisionError(
                "Calendar Day identity was claimed during materialization"
            ) from error
        return self.resolve(current.date)


def materialize_calendar_day_links(
    markdown: str,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: ActorInput,
    now: str,
    previous_markdown: str = "",
) -> tuple[CalendarDay, ...]:
    """Materialize only Calendar Day targets newly introduced by one canonical Markdown write."""
    return _materialize_calendar_day_links(
        markdown,
        repository=repository,
        schema=schema,
        actor=actor,
        now=now,
        previous_markdown=previous_markdown,
        skip_dates=(),
    )


def _materialize_calendar_day_links(
    markdown: str,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: ActorInput,
    now: str,
    previous_markdown: str,
    skip_dates: tuple[str, ...],
) -> tuple[CalendarDay, ...]:
    """Support atomic self-linking Day creation without exposing a public materialization bypass."""
    skipped = frozenset(normalize_iso_date(value) for value in skip_dates)
    current_dates = calendar_day_link_dates(markdown)
    previous_dates = frozenset(calendar_day_link_dates(previous_markdown))
    day_repository = CalendarDayRepository(repository, schema)
    return tuple(
        day_repository.materialize(value, actor=actor, now=now)
        for value in current_dates
        if value not in previous_dates and value not in skipped
    )
