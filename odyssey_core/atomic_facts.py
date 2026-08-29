"""Parse and render append-first Odyssey atomic Markdown facts."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_MARKER = re.compile(r"^[ \t]*<!-- odyssey:fact request=([^\s>]+) ordinal=(\d+) -->[ \t]*$")
_MARKER_PREFIX = "<!-- odyssey:fact"


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
        facts.append(
            AtomicFact(text, match.group(1), int(match.group(2)), start, offset + len(line))
        )
        offset += len(line)
    return tuple(facts)


def normalize_atomic_fact(text: str) -> str:
    """Return the conservative exact-duplicate normalization for atomic fact text."""
    return " ".join(unicodedata.normalize("NFC", text).strip().split())


def render_atomic_facts(
    facts: tuple[str, ...], request_id: str, ordinals: tuple[int, ...], now: str
) -> str:
    """Render ordered facts under one capture-date heading with hidden request-derived markers."""
    if len(facts) != len(ordinals) or not request_id.strip():
        raise AtomicFactError(
            "Atomic fact rendering requires matching facts, ordinals, and request_id"
        )
    heading = f"## Added {now[:10]}"
    blocks = [heading]
    for text, ordinal in zip(facts, ordinals, strict=True):
        if (
            not isinstance(ordinal, int)
            or ordinal < 0
            or not text.strip()
            or "\n" in text
            or "\r" in text
            or _MARKER_PREFIX in text
        ):
            raise AtomicFactError("Atomic fact rendering input is invalid")
        blocks.append(
            f"- {text.strip()}\n  <!-- odyssey:fact request={request_id} ordinal={ordinal} -->"
        )
    return "\n".join(blocks)


def append_atomic_facts(
    body: str, facts: tuple[str, ...], request_id: str, ordinals: tuple[int, ...], now: str
) -> str:
    """Append one deterministic capture section without modifying legacy or prior fact content."""
    rendered = render_atomic_facts(facts, request_id, ordinals, now)
    return rendered if not body else body + ("\n" if body.endswith("\n") else "\n\n") + rendered


def remove_atomic_fact(body: str, target: AtomicFact) -> str:
    """Remove exactly one parser-derived atomic fact block without touching adjacent Markdown."""
    facts = parse_atomic_facts(body)
    if target not in facts:
        raise AtomicFactError("Atomic fact removal target is not from this authoritative body")
    return body[: target.start] + body[target.end :]


def find_unique_atomic_fact(body: str, description: str) -> AtomicFact | None:
    """Return one exact-normalized marked fact match, or ``None`` when absent or ambiguous."""
    normalized = normalize_atomic_fact(description)
    matches = [
        fact for fact in parse_atomic_facts(body) if normalize_atomic_fact(fact.text) == normalized
    ]
    return matches[0] if len(matches) == 1 else None
