"""Deterministic Phase 16.5C materialization of preflighted reference markers."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .request_planning import KnowledgeReference, WriteAction
from .write_target import WriteTargetOutcome

if TYPE_CHECKING:
    from .reference_preflight import UnitTargetPreflight


_MARKER = re.compile(r"\{\{ref:(\d+)\}\}")
_WIKILINK = re.compile(r"\[\[[^\[\]#|^:%]+(?:\|[^\[\]]+)?\]\]")


class ReferenceBindingError(RuntimeError):
    """Indicate that validated reference-binding inputs violate an internal contract."""


@dataclass(frozen=True, slots=True)
class PendingReference:
    """Preserve one unresolved semantic reference for a later application boundary."""

    source_unit_index: int
    local_reference_index: int
    target_unit_index: int
    role: str
    mention: str
    reason: str
    candidate_stable_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferenceRenderingResult:
    """Contain writer-ready facts and explicit non-persisting pending references."""

    rendered_facts: tuple[tuple[str, ...], ...]
    pending_references: tuple[PendingReference, ...]


def render_reference_facts(
    action: WriteAction,
    preflight: tuple[UnitTargetPreflight, ...],
) -> ReferenceRenderingResult:
    """Replace validated local markers using only the supplied target preflight table.

    Args:
        action: Ordered validated write action containing marker-bearing facts.
        preflight: Exactly one Phase 16.5B target result per action unit.

    Returns:
        Immutable rendered facts and at most one pending record per semantic reference.

    Raises:
        ReferenceBindingError: If table ordering, target indexes, paths, or markers are unsafe.
    """
    if not isinstance(action, WriteAction):
        raise ReferenceBindingError("Reference rendering requires a WriteAction")
    if len(preflight) != len(action.units):
        raise ReferenceBindingError("Reference preflight table must match unit count exactly")
    for index, result in enumerate(preflight):
        if result.unit_index != index:
            raise ReferenceBindingError("Reference preflight table unit_index is inconsistent")

    rendered_units: list[tuple[str, ...]] = []
    pending: list[PendingReference] = []
    for source_index, unit in enumerate(action.units):
        rendered_facts: list[str] = []
        for fact in unit.facts:
            rendered_facts.append(
                _render_fact(
                    fact,
                    source_index=source_index,
                    references=unit.references,
                    preflight=preflight,
                    pending=pending,
                )
            )
        rendered_units.append(tuple(rendered_facts))
    return ReferenceRenderingResult(tuple(rendered_units), tuple(pending))


def _render_fact(
    fact: str,
    *,
    source_index: int,
    references: tuple[KnowledgeReference, ...],
    preflight: tuple[UnitTargetPreflight, ...],
    pending: list[PendingReference],
) -> str:
    """Render one fact and reject malformed or unconsumed internal markers."""
    cursor = 0
    output: list[str] = []
    while cursor < len(fact):
        marker_start = fact.find("{{ref", cursor)
        if marker_start < 0:
            output.append(fact[cursor:])
            break
        output.append(fact[cursor:marker_start])
        match = _MARKER.match(fact, marker_start)
        if match is None:
            raise ReferenceBindingError("Malformed reference marker")
        reference_index = int(match.group(1))
        if reference_index >= len(references):
            raise ReferenceBindingError("Reference marker index is out of range")
        reference = references[reference_index]
        if reference.target_index >= len(preflight):
            raise ReferenceBindingError("Reference target index is out of range")
        target = preflight[reference.target_index]
        if target.outcome in {WriteTargetOutcome.UPDATE, WriteTargetOutcome.CREATE}:
            if not target.path:
                raise ReferenceBindingError("Resolved reference target has no path")
            target_without_suffix = _wikilink_target(target.path)
            output.append(f"[[{target_without_suffix}|{reference.mention}]]")
        elif target.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION:
            output.append(reference.mention)
            if not any(
                item.source_unit_index == source_index
                and item.local_reference_index == reference_index
                for item in pending
            ):
                pending.append(
                    PendingReference(
                        source_index,
                        reference_index,
                        reference.target_index,
                        reference.role,
                        reference.mention,
                        target.reason or "Reference target needs clarification",
                        target.candidate_note_ids,
                    )
                )
        else:
            raise ReferenceBindingError("Reference target has an unsupported preflight outcome")
        cursor = match.end()
    if "{{ref" in "".join(output) or "}}" in "".join(output):
        raise ReferenceBindingError("Reference marker survived rendering")
    return "".join(output)


def _wikilink_target(path: str) -> str:
    """Validate a vault-relative Markdown path and remove only its final suffix."""
    if (
        not isinstance(path, str)
        or not path.endswith(".md")
        or not path
        or path.startswith(("/", "\\"))
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or any(character in path for character in "#|^:%[]")
    ):
        raise ReferenceBindingError("Reference target path is not a safe vault-relative .md path")
    return path.removesuffix(".md")


def required_bound_wikilinks(facts: tuple[str, ...]) -> Counter[str]:
    """Return exact bound wikilink multiplicities required by prepared writer facts."""
    return Counter(link for fact in facts for link in _WIKILINK.findall(fact))
