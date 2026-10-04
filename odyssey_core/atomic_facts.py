"""Parse and render append-first Odyssey atomic Markdown facts."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

from odyssey_core.temporal import TemporalAnchor, TemporalValueError, calendar_day_wikilink

_MARKER = re.compile(
    r"^[ \t]*<!-- odyssey:fact request=([^\s>]+) ordinal=(\d+)"
    r"(?P<metadata>(?: [a-z_]+=[^\s>]+)*) -->[ \t]*$"
)
_MARKER_PREFIX = "<!-- odyssey:fact"
_CAPTURE_HEADING = re.compile(
    r"^# Added (?:(?P<plain>\d{2}-\d{2}-\d{4})|"
    r"\[\[calendar/days/(?P<link_date>\d{4}-\d{2}-\d{2})(?:\.md)?\|"
    r"(?P<link_label>\d{2}-\d{2}-\d{4})\]\])[ \t]*$",
    re.MULTILINE,
)
_LEVEL_ONE_HEADING = re.compile(r"^# .+$", re.MULTILINE)


class AtomicFactError(ValueError):
    """Indicate malformed Odyssey-owned atomic-fact markup."""


@dataclass(frozen=True, slots=True)
class AtomicFact:
    """Represent one parsed marker-addressable fact and its exact removal span."""

    text: str
    request_id: str
    ordinal: int
    start: int
    end: int
    recorded_at: str | None = None
    temporal_anchors: tuple[TemporalAnchor, ...] = ()

    def global_identity(self, note_id: str) -> tuple[str, str, int]:
        """Return the derived globally unique ``(note_id, request_id, ordinal)`` identity."""
        return (note_id, self.request_id, self.ordinal)

    @property
    def locator(self) -> str:
        """Return the note-scoped request/ordinal locator supplied to bounded selection."""
        return f"{self.request_id}:{self.ordinal}"


def parse_atomic_facts(body: str) -> tuple[AtomicFact, ...]:
    """Parse only Odyssey-marked list-item facts while leaving legacy Markdown untouched.

    Raises:
        AtomicFactError: If an Odyssey marker is malformed or detached from a list-item fact.
    """
    facts: list[AtomicFact] = []
    offset = 0
    lines = body.splitlines(keepends=True)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if _MARKER_PREFIX not in stripped:
            offset += len(line)
            continue
        match = _MARKER.fullmatch(stripped)
        if match is None or index == 0:
            raise AtomicFactError("Malformed Odyssey atomic-fact marker")
        fact_line = lines[index - 1]
        if not fact_line.startswith("- "):
            raise AtomicFactError("Odyssey atomic-fact marker lacks a preceding list item")
        text = fact_line[2:].strip()
        if not text:
            raise AtomicFactError("Odyssey atomic-fact text is empty")
        start = offset - len(fact_line)
        metadata = _parse_marker_metadata(match.group("metadata"))
        recorded_at = _parse_recorded_at(metadata.get("recorded_at"))
        temporal_anchors = _parse_temporal_anchors(metadata.get("temporal"))
        facts.append(
            AtomicFact(
                text,
                match.group(1),
                int(match.group(2)),
                start,
                offset + len(line),
                recorded_at,
                temporal_anchors,
            )
        )
        offset += len(line)
    return tuple(facts)


def normalize_atomic_fact(text: str) -> str:
    """Return the conservative exact-duplicate normalization for atomic fact text."""
    return " ".join(unicodedata.normalize("NFC", text).strip().split())


def _parse_marker_metadata(raw: str) -> dict[str, str]:
    """Decode the bounded extensible hidden fact metadata field set."""
    if not raw:
        return {}
    result: dict[str, str] = {}
    for token in raw.strip().split():
        if "=" not in token:
            raise AtomicFactError("Atomic fact marker metadata is malformed")
        key, value = token.split("=", 1)
        if key not in {"recorded_at", "temporal"} or not value or key in result:
            raise AtomicFactError("Atomic fact marker metadata is invalid")
        result[key] = value
    return result


def _parse_temporal_anchors(value: str | None) -> tuple[TemporalAnchor, ...]:
    """Decode zero or more semicolon-separated semantic temporal coordinates."""
    if value is None:
        return ()
    if not value or any(character.isspace() for character in value):
        raise AtomicFactError("Atomic fact temporal anchors are invalid")
    raw_values = value.split(";")
    if not raw_values or any(not item for item in raw_values):
        raise AtomicFactError("Atomic fact temporal anchors are invalid")
    try:
        anchors = tuple(TemporalAnchor.from_value(item) for item in raw_values)
    except TemporalValueError as error:
        raise AtomicFactError("Atomic fact temporal anchors are invalid") from error
    if len(anchors) != len(set(anchors)):
        raise AtomicFactError("Atomic fact temporal anchors are duplicate")
    return anchors


def _parse_recorded_at(value: str | None) -> str | None:
    """Validate and canonicalize one optional hidden fact capture timestamp."""
    if value is None:
        return None
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        raise AtomicFactError("Atomic fact recorded_at is invalid")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise AtomicFactError("Atomic fact recorded_at is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.microsecond != 0:
        raise AtomicFactError("Atomic fact recorded_at must be an offset-aware second timestamp")
    canonical = parsed.isoformat(timespec="seconds")
    if candidate != canonical:
        raise AtomicFactError("Atomic fact recorded_at is not canonical")
    return canonical


def _recorded_at_for_capture(now: str) -> str | None:
    """Return exact capture time when available; historical date-only callers remain readable."""
    if not isinstance(now, str):
        raise AtomicFactError("Atomic fact capture time is invalid")
    if "T" not in now:
        _capture_date(now)
        return None
    return _parse_recorded_at(now)


def _capture_date(now: str) -> date:
    """Return the calendar date encoded at the start of one capture timestamp."""
    try:
        return date.fromisoformat(now[:10])
    except (TypeError, ValueError) as error:
        raise AtomicFactError(
            "Atomic fact capture time must begin with a valid ISO date"
        ) from error


def _capture_heading(now: str) -> str:
    """Render one navigable capture-date heading using the deterministic Calendar Day path."""
    captured = _capture_date(now)
    visible = f"{captured.day:02d}-{captured.month:02d}-{captured.year}"
    return f"# Added {calendar_day_wikilink(captured.isoformat(), label=visible)}"


def _capture_heading_date(match: re.Match[str]) -> str | None:
    """Return the normalized day represented by one supported historical/current heading."""
    plain = match.group("plain")
    if plain is not None:
        try:
            day, month, year = (int(part) for part in plain.split("-"))
            return date(year, month, day).isoformat()
        except (TypeError, ValueError):
            return None
    link_date = match.group("link_date")
    link_label = match.group("link_label")
    if link_date is None or link_label is None:
        return None
    try:
        parsed = date.fromisoformat(link_date)
    except ValueError:
        return None
    expected = f"{parsed.day:02d}-{parsed.month:02d}-{parsed.year}"
    return parsed.isoformat() if link_label == expected else None


def capture_heading_date(line: str) -> str | None:
    """Return the ISO date represented by one supported complete Added heading line."""
    if not isinstance(line, str):
        return None
    match = _CAPTURE_HEADING.fullmatch(line.strip())
    return None if match is None else _capture_heading_date(match)


def _fact_blocks(
    facts: tuple[str, ...],
    request_id: str,
    ordinals: tuple[int, ...],
    recorded_at: str | None = None,
    temporal_anchors: tuple[tuple[TemporalAnchor, ...], ...] | None = None,
) -> tuple[str, ...]:
    """Validate and render marker-bearing list items without a capture heading."""
    if len(facts) != len(ordinals) or not request_id.strip():
        raise AtomicFactError(
            "Atomic fact rendering requires matching facts, ordinals, and request_id"
        )
    anchors_by_fact = temporal_anchors or tuple(() for _ in facts)
    if len(anchors_by_fact) != len(facts) or not all(
        isinstance(items, tuple)
        and len(items) == len(set(items))
        and all(isinstance(anchor, TemporalAnchor) for anchor in items)
        for items in anchors_by_fact
    ):
        raise AtomicFactError("Atomic fact temporal anchor rendering input is invalid")
    blocks: list[str] = []
    for text, ordinal, anchors in zip(facts, ordinals, anchors_by_fact, strict=True):
        if (
            not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal < 0
            or not isinstance(text, str)
            or not text.strip()
            or "\n" in text
            or "\r" in text
            or _MARKER_PREFIX in text
        ):
            raise AtomicFactError("Atomic fact rendering input is invalid")
        metadata = f" recorded_at={recorded_at}" if recorded_at is not None else ""
        if anchors:
            metadata += " temporal=" + ";".join(anchor.value for anchor in anchors)
        blocks.append(
            f"- {text.strip()}\n  <!-- odyssey:fact request={request_id} ordinal={ordinal}{metadata} -->"
        )
    return tuple(blocks)


def render_atomic_facts(
    facts: tuple[str, ...],
    request_id: str,
    ordinals: tuple[int, ...],
    now: str,
    *,
    temporal_anchors: tuple[tuple[TemporalAnchor, ...], ...] | None = None,
) -> str:
    """Render ordered facts under one navigable capture-date heading and hidden markers."""
    blocks = _fact_blocks(
        facts, request_id, ordinals, _recorded_at_for_capture(now), temporal_anchors
    )
    return "\n".join((_capture_heading(now), *blocks))


def append_atomic_facts(
    body: str,
    facts: tuple[str, ...],
    request_id: str,
    ordinals: tuple[int, ...],
    now: str,
    *,
    temporal_anchors: tuple[tuple[TemporalAnchor, ...], ...] | None = None,
) -> str:
    """Append facts under one capture heading per day without rewriting historical duplicates.

    If the current capture day already has one or more legacy/current Added headings, new facts join
    the last such section instead of creating another duplicate. A selected legacy plain-date heading
    is upgraded to the current navigable Calendar link while older duplicate sections remain intact.
    """
    heading = _capture_heading(now)
    blocks = _fact_blocks(
        facts, request_id, ordinals, _recorded_at_for_capture(now), temporal_anchors
    )
    rendered = "\n".join((heading, *blocks))
    if not body:
        return rendered

    capture_date = _capture_date(now).isoformat()
    matches = [
        match
        for match in _CAPTURE_HEADING.finditer(body)
        if _capture_heading_date(match) == capture_date
    ]
    if not matches:
        return body + ("\n" if body.endswith("\n") else "\n\n") + rendered

    selected = matches[-1]
    rest = body[selected.end() :]
    next_heading = _LEVEL_ONE_HEADING.search(rest)
    if next_heading is None:
        section, suffix = rest, ""
    else:
        section, suffix = rest[: next_heading.start()], rest[next_heading.start() :]
    core = section.rstrip("\n")
    trailing = section[len(core) :]
    addition = "\n".join(blocks)
    updated_section = (core + "\n" if core else "\n") + addition + trailing
    return body[: selected.start()] + heading + updated_section + suffix


def remove_atomic_fact(body: str, target: AtomicFact) -> str:
    """Remove one fact and retire its capture heading only when that section becomes empty."""
    facts = parse_atomic_facts(body)
    if target not in facts:
        raise AtomicFactError("Atomic fact removal target is not from this authoritative body")

    capture_heading = None
    for match in _CAPTURE_HEADING.finditer(body):
        if match.end() <= target.start:
            capture_heading = match
        else:
            break
    if capture_heading is None:
        return body[: target.start] + body[target.end :]

    next_heading = _LEVEL_ONE_HEADING.search(body, capture_heading.end())
    section_end = next_heading.start() if next_heading is not None else len(body)
    if target.end > section_end:
        return body[: target.start] + body[target.end :]

    remaining_section = body[capture_heading.end() : target.start] + body[target.end : section_end]
    if remaining_section.strip():
        return body[: target.start] + body[target.end :]

    prefix = body[: capture_heading.start()].rstrip()
    suffix = body[section_end:].lstrip("\n")
    if prefix and suffix:
        return prefix + "\n\n" + suffix
    return prefix or suffix


def find_unique_atomic_fact(body: str, description: str) -> AtomicFact | None:
    """Return one exact-normalized marked fact match, or ``None`` when absent or ambiguous."""
    normalized = normalize_atomic_fact(description)
    matches = [
        fact for fact in parse_atomic_facts(body) if normalize_atomic_fact(fact.text) == normalized
    ]
    return matches[0] if len(matches) == 1 else None
