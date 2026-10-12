"""Source-only shape checks for a linear correction/supersession chain.

This module deliberately knows no Core plan, Temporal result, or canonical
identity. It prevents correction gates drifting on a *linear* Router
hypothesis before those authorities are applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _Span(Protocol):
    text: str
    start: int
    end: int


class _Role(Protocol):
    role: str
    span: _Span


class _Inheritance(Protocol):
    role: str
    from_unit: int


class _Candidate(Protocol):
    kind: str
    state: str
    roles: tuple[_Role, ...]
    inherits: tuple[_Inheritance, ...]


@dataclass(frozen=True, slots=True)
class CorrectionChain:
    """Describe a validated consecutive source replacement chain."""

    objects: tuple[_Span, ...]
    times: tuple[_Span, ...]
    predicate: _Span
    date: _Span
    polarity: _Span


def _one_role(candidate: _Candidate, role: str) -> _Span | None:
    found = [item.span for item in candidate.roles if item.role == role]
    return found[0] if len(found) == 1 else None


def correction_chain(candidates: tuple[_Candidate, ...]) -> CorrectionChain | None:
    """Return a proven linear chain, or ``None`` for every unsupported shape.

    The first candidate owns date, predicate and polarity. Every later
    candidate replaces the immediately preceding object's exact original span
    and inherits predicate/date from that immediate predecessor. Immediate
    links rule out jumps and forks; inherited evidence may still be
    transitively rooted in the first candidate. This is source structure only,
    never grammar or write proof.
    """
    if len(candidates) < 2 or any(
        c.kind != "occurrence" or c.state != "candidate" for c in candidates
    ):
        return None
    if any(
        role.role in {"condition", "modality"}
        for candidate in candidates
        for role in candidate.roles
    ):
        return None
    first = candidates[0]
    predicate = _one_role(first, "predicate")
    date = _one_role(first, "date")
    polarity = _one_role(first, "polarity")
    if predicate is None or date is None or polarity is None:
        return None
    objects: list[_Span] = []
    times: list[_Span] = []
    for position, candidate in enumerate(candidates):
        object_span = _one_role(candidate, "object")
        time_span = _one_role(candidate, "time")
        if object_span is None or time_span is None:
            return None
        if position and any(role.role == "polarity" for role in candidate.roles):
            return None
        if position:
            replacement = _one_role(candidate, "replacement")
            previous = objects[-1]
            if replacement is None or (
                replacement.text,
                replacement.start,
                replacement.end,
            ) != (previous.text, previous.start, previous.end):
                return None
            required = {("predicate", position), ("date", position)}
            actual = {(edge.role, edge.from_unit) for edge in candidate.inherits}
            if not required <= actual:
                return None
        objects.append(object_span)
        times.append(time_span)
    if len({(item.text, item.start, item.end) for item in objects}) != len(objects):
        return None
    if len({item.text for item in times}) != len(times):
        return None
    return CorrectionChain(tuple(objects), tuple(times), predicate, date, polarity)
