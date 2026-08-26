"""Focused review sentinels for the hardened Phase 16.5C boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from odyssey_core import (
    KnowledgeReference,
    KnowledgeUnit,
    MaterializationError,
    ReferenceBindingError,
    SelectionCriteria,
    UnitTargetPreflight,
    WriteAction,
    WriteTargetDecision,
    WriteTargetOutcome,
    materialize_update,
    render_reference_facts,
    validate_rendered_facts,
)
from odyssey_core.materialization import WriterOutputError, _validate_bound_wikilinks
from odyssey_core.reference_preflight import _safe_creation_name
from odyssey_core.storage import VaultRepository


def _unit(
    fact: str,
    *,
    mention: str = "Marta",
    intent: str = "amend",
) -> KnowledgeUnit:
    """Build one marker-bearing unit for boundary tests."""
    return KnowledgeUnit(
        SelectionCriteria("Bea", "Bea", "person", (), None),
        intent,
        (),
        (),
        (fact,),
        (KnowledgeReference(1, "person", mention),),
    )


def _target(index: int, path: str) -> UnitTargetPreflight:
    """Build one safely resolved preflight target."""
    return UnitTargetPreflight(
        index,
        WriteTargetOutcome.UPDATE,
        stable_id=f"id-{index}",
        canonical_name=f"Name {index}",
        path=path,
    )


def test_renderer_rejects_display_text_that_breaks_wikilink_syntax() -> None:
    """Occurrence wording must never create an ambiguous pipe-delimited wikilink."""
    action = WriteAction(
        (
            _unit("Hablé con {{ref:0}}.", mention="A | B"),
            KnowledgeUnit(
                SelectionCriteria("A", "A", "person", (), None), "record", (), (), ("fact",), ()
            ),
        )
    )
    with pytest.raises(ReferenceBindingError, match="display text"):
        render_reference_facts(
            action,
            (_target(0, "people/Bea.md"), _target(1, "people/A - id.md")),
        )


@pytest.mark.parametrize(
    "rendered",
    [
        "Bea se ha mudado a París.",
        "Bea habló con [[people/Marta - id|Otra Marta]].",
        "Prefijo Bea habló con [[people/Marta - id|Marta]].",
    ],
)
def test_rendered_fact_validation_rejects_changes_outside_marker(rendered: str) -> None:
    """Prepared facts may alter only the reference marker occurrence itself."""
    unit = _unit("Bea habló con {{ref:0}}.")
    with pytest.raises(ReferenceBindingError):
        validate_rendered_facts(unit, (rendered,))


def test_rendered_fact_validation_accepts_bound_link_or_plain_pending_mention() -> None:
    """Both safe resolved links and unresolved plain mentions preserve the source skeleton."""
    unit = _unit("Bea habló con {{ref:0}}.")
    validate_rendered_facts(unit, ("Bea habló con [[people/Marta - id|Marta]].",))
    validate_rendered_facts(unit, ("Bea habló con Marta.",))


def test_materializer_rejects_unrelated_rendered_fact_before_repository_access(
    tmp_path: Path,
) -> None:
    """A wrong rendered-facts tuple cannot be attached to a different KnowledgeUnit."""
    with pytest.raises(MaterializationError, match="do not match"):
        materialize_update(
            _unit("Bea habló con {{ref:0}}."),
            WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id="missing"),
            repository=VaultRepository(tmp_path),
            schema={},
            actor="test",
            now="2026-08-26T20:00:00+02:00",
            rendered_facts=("Bea se ha mudado a París.",),
        )


def test_writer_link_guard_detects_anchor_or_block_links_invented_by_writer() -> None:
    """The broad output detector must not miss Obsidian anchor/block wikilinks."""
    required = "[[people/Marta - id|Marta]]"
    with pytest.raises(WriterOutputError, match="invented"):
        _validate_bound_wikilinks(
            "# Bea",
            f"# Bea\n- Bea habló con {required}.\n- Invented [[Other#Section]].",
            (f"Bea habló con {required}.",),
            "amend",
        )
    with pytest.raises(WriterOutputError, match="invented"):
        _validate_bound_wikilinks(
            "# Bea",
            f"# Bea\n- Bea habló con {required}.\n- Invented [[Other^block]].",
            (f"Bea habló con {required}.",),
            "amend",
        )


def test_remove_intent_may_drop_requested_link_but_cannot_invent_another() -> None:
    """Remove may remove the linked fact without granting authority to add unrelated links."""
    existing = "# Bea\n- Bea habló con [[people/Marta - id|Marta]]."
    _validate_bound_wikilinks(
        existing,
        "# Bea",
        ("Bea habló con [[people/Marta - id|Marta]].",),
        "remove",
    )
    with pytest.raises(WriterOutputError, match="invented"):
        _validate_bound_wikilinks(
            existing,
            "# Bea\n- [[Other#Section]]",
            ("Bea habló con [[people/Marta - id|Marta]].",),
            "remove",
        )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("CON", "CON_"),
        ("CON.txt", "CON_.txt"),
        ("NUL.md", "NUL_.md"),
        ("COM0.log", "COM0_.log"),
        ("LPT9.data", "LPT9_.data"),
    ],
)
def test_reserved_windows_device_stems_are_sanitized_before_extension(
    name: str, expected: str
) -> None:
    """Windows device names remain unsafe even when followed by an extension."""
    assert _safe_creation_name(name) == expected
