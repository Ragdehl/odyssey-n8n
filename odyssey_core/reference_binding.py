"""Deterministic Phase 16.5C materialization of preflighted reference markers."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .request_planning import KnowledgeReference, KnowledgeUnit, WriteAction
from .write_target import WriteTargetOutcome

if TYPE_CHECKING:
    from .reference_preflight import UnitTargetPreflight


_MARKER = re.compile(r"\{\{ref:(\d+)\}\}")
_ANY_WIKILINK = re.compile(r"\[\[[^\[\]\r\n]+\]\]")
_RENDERED_WIKILINK = re.compile(r"\[\[([^\[\]|\r\n]+)\|([^\[\]|\r\n]+)\]\]")


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
        ReferenceBindingError: If table ordering, target indexes, paths, mentions, or markers are
            unsafe.
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


def validate_rendered_facts(unit: KnowledgeUnit, rendered_facts: tuple[str, ...]) -> None:
    """Verify that prepared facts differ from source facts only at validated reference markers.

    The materializer does not reopen identity resolution. It does, however, verify the structural
    hand-off: literal source text must remain byte-for-byte identical and every marker replacement
    must be either that reference's exact mention or one safe ``[[target|mention]]`` value.

    Args:
        unit: Original validated marker-bearing knowledge unit.
        rendered_facts: Phase 16.5C facts supplied to materialization.

    Raises:
        ReferenceBindingError: If the rendered facts are not a faithful marker-only projection.
    """
    if (
        not isinstance(rendered_facts, tuple)
        or len(rendered_facts) != len(unit.facts)
        or not all(isinstance(fact, str) for fact in rendered_facts)
    ):
        raise ReferenceBindingError("Rendered facts do not match the KnowledgeUnit shape")
    for source, rendered in zip(unit.facts, rendered_facts, strict=True):
        _validate_rendered_fact(source, rendered, unit.references)


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
            mention = _wikilink_display(reference.mention)
            output.append(f"[[{target_without_suffix}|{mention}]]")
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
    rendered = "".join(output)
    if "{{ref" in rendered or "}}" in rendered:
        raise ReferenceBindingError("Reference marker survived rendering")
    return rendered


def _validate_rendered_fact(
    source: str, rendered: str, references: tuple[KnowledgeReference, ...]
) -> None:
    """Validate one marker-only rendering without knowing or re-resolving target identity."""
    matches = list(_MARKER.finditer(source))
    if not matches:
        if rendered != source:
            raise ReferenceBindingError("Reference-free fact changed during rendering")
        return
    cursor = 0
    pattern: list[str] = ["^"]
    reference_indexes: list[int] = []
    for match in matches:
        literal = source[cursor : match.start()]
        pattern.append(re.escape(literal))
        pattern.append("(.*?)")
        reference_indexes.append(int(match.group(1)))
        cursor = match.end()
    pattern.append(re.escape(source[cursor:]))
    pattern.append("$")
    rendered_match = re.match("".join(pattern), rendered, flags=re.DOTALL)
    if rendered_match is None:
        raise ReferenceBindingError("Rendered fact changed text outside reference markers")
    for reference_index, replacement in zip(
        reference_indexes, rendered_match.groups(), strict=True
    ):
        if reference_index >= len(references):
            raise ReferenceBindingError("Reference marker index is out of range")
        mention = references[reference_index].mention
        if replacement == mention:
            continue
        link_match = _RENDERED_WIKILINK.fullmatch(replacement)
        if link_match is None or link_match.group(2) != mention:
            raise ReferenceBindingError("Reference marker was not replaced by its exact mention")
        _wikilink_target(f"{link_match.group(1)}.md")
        _wikilink_display(link_match.group(2))
    if "{{ref" in rendered or "}}" in rendered:
        raise ReferenceBindingError("Reference marker survived rendering")


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


def _wikilink_display(mention: str) -> str:
    """Return exact display text only when it cannot break Odyssey's wikilink syntax."""
    if (
        not isinstance(mention, str)
        or not mention
        or any(character in mention for character in "|[]\r\n")
        or any(ord(character) < 32 or ord(character) == 127 for character in mention)
    ):
        raise ReferenceBindingError("Reference mention cannot safely form wikilink display text")
    return mention


def required_bound_wikilinks(facts: tuple[str, ...]) -> Counter[str]:
    """Return exact wikilink multiplicities for prepared facts or authoritative Markdown."""
    return Counter(link for fact in facts for link in _ANY_WIKILINK.findall(fact))
