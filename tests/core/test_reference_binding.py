"""Deterministic Phase 16.5C reference rendering tests."""

from __future__ import annotations

import pytest

from odyssey_core import (
    KnowledgeReference,
    KnowledgeUnit,
    PendingReference,
    ReferenceBindingError,
    ReferenceRenderingResult,
    SelectionCriteria,
    UnitTargetPreflight,
    WriteAction,
    WriteTargetOutcome,
    render_reference_facts,
)


def unit(facts: tuple[str, ...], refs: tuple[KnowledgeReference, ...] = ()) -> KnowledgeUnit:
    """Build a minimal validated-shaped unit for renderer tests."""
    return KnowledgeUnit(
        SelectionCriteria(None, "unit", "person", (), None), "record", (), (), facts, refs
    )


def target(
    index: int, outcome: WriteTargetOutcome, *, path: str | None = None
) -> UnitTargetPreflight:
    """Build one deterministic preflight fixture."""
    return UnitTargetPreflight(
        index, outcome, stable_id="id", canonical_name="Canonical", path=path
    )


def test_resolved_update_and_preallocated_create_render_authoritative_paths() -> None:
    """Render UPDATE and CREATE links without requiring either link target to be persisted."""
    action = WriteAction(
        (
            unit(
                ("Compré {{ref:0}} y elegí {{ref:0}}.",),
                (KnowledgeReference(1, "product", "Leche Pascual"),),
            ),
            unit(("fact",)),
        )
    )
    result = render_reference_facts(
        action,
        (
            target(0, WriteTargetOutcome.UPDATE, path="people/Marta.md"),
            target(1, WriteTargetOutcome.CREATE, path="products/Leche Pascual - full-id.md"),
        ),
    )
    assert result.rendered_facts == (
        (
            "Compré [[products/Leche Pascual - full-id|Leche Pascual]] y elegí [[products/Leche Pascual - full-id|Leche Pascual]].",
        ),
        ("fact",),
    )
    assert result.pending_references == ()


def test_mention_is_display_text_and_two_references_keep_folders() -> None:
    """Use occurrence wording exactly, even when it differs from canonical identity."""
    action = WriteAction(
        (
            unit(
                ("Hablé con {{ref:0}} sobre {{ref:1}}.",),
                (
                    KnowledgeReference(1, "person", "la amiga de Laura"),
                    KnowledgeReference(2, "place", "Toulouse"),
                ),
            ),
            unit(("person",)),
            unit(("place",)),
        )
    )
    result = render_reference_facts(
        action,
        (
            target(0, WriteTargetOutcome.UPDATE, path="source.md"),
            target(1, WriteTargetOutcome.UPDATE, path="people/Marta García.md"),
            target(2, WriteTargetOutcome.CREATE, path="places/Toulouse - id.md"),
        ),
    )
    assert (
        result.rendered_facts[0][0]
        == "Hablé con [[people/Marta García|la amiga de Laura]] sobre [[places/Toulouse - id|Toulouse]]."
    )


def test_ambiguous_reference_becomes_plain_mention_once_pending() -> None:
    """Keep ambiguity readable and emit one pending record despite repeated markers."""
    action = WriteAction(
        (
            unit(
                ("Hablé con {{ref:0}} y llamé a {{ref:0}}.",),
                (KnowledgeReference(1, "person", "Marta"),),
            ),
            unit(("target",)),
        )
    )
    result = render_reference_facts(
        action,
        (
            target(0, WriteTargetOutcome.UPDATE, path="source.md"),
            UnitTargetPreflight(
                1,
                WriteTargetOutcome.NEEDS_CLARIFICATION,
                candidate_note_ids=("marta-g", "marta-l"),
                reason="multiple matches",
            ),
        ),
    )
    assert result.rendered_facts == (("Hablé con Marta y llamé a Marta.",), ("target",))
    assert result.pending_references == (
        PendingReference(0, 0, 1, "person", "Marta", "multiple matches", ("marta-g", "marta-l")),
    )


def test_unresolved_reference_without_candidates_is_explicit_pending() -> None:
    """Preserve an unresolved mention without inventing a target."""
    result = render_reference_facts(
        WriteAction(
            (
                unit(("Vi a {{ref:0}}.",), (KnowledgeReference(1, "person", "Marta"),)),
                unit(("target",)),
            )
        ),
        (
            target(0, WriteTargetOutcome.UPDATE, path="source.md"),
            UnitTargetPreflight(1, WriteTargetOutcome.NEEDS_CLARIFICATION, reason="unresolved"),
        ),
    )
    assert result.pending_references[0].candidate_stable_ids == ()
    assert result.rendered_facts == (("Vi a Marta.",), ("target",))


def test_no_references_are_byte_for_byte_unchanged() -> None:
    """Return facts exactly when no semantic references are present."""
    facts = ("  exact  spacing\n", "plain")
    assert render_reference_facts(
        WriteAction((unit(facts),)), (target(0, WriteTargetOutcome.CREATE, path="x.md"),)
    ) == ReferenceRenderingResult((facts,), ())


@pytest.mark.parametrize(
    "table",
    [
        (),
        (target(1, WriteTargetOutcome.CREATE, path="x.md"),),
        (
            target(0, WriteTargetOutcome.CREATE, path="x.md"),
            target(1, WriteTargetOutcome.CREATE, path="y.md"),
        ),
    ],
)
def test_preflight_table_shape_is_fail_closed(table: tuple[UnitTargetPreflight, ...]) -> None:
    """Reject short, extra, and inconsistently indexed preflight tables."""
    with pytest.raises(ReferenceBindingError):
        render_reference_facts(WriteAction((unit(("fact",)),)), table)


@pytest.mark.parametrize(
    "path", ["missing", "/absolute.md", "../escape.md", "folder\\file.md", "unsafe#target.md"]
)
def test_unsafe_target_paths_are_rejected(path: str) -> None:
    """Never silently rewrite an unsafe authoritative path into a wikilink target."""
    with pytest.raises(ReferenceBindingError):
        render_reference_facts(
            WriteAction((unit(("{{ref:0}}",), (KnowledgeReference(1, "x", "mention"),)),)),
            (
                target(0, WriteTargetOutcome.CREATE, path="source.md"),
                target(1, WriteTargetOutcome.UPDATE, path=path),
            ),
        )


def test_malformed_marker_does_not_survive() -> None:
    """Reject malformed internal markers rather than passing them to a writer."""
    with pytest.raises(ReferenceBindingError):
        render_reference_facts(
            WriteAction((unit(("bad {{ref:x}}",)),)),
            (target(0, WriteTargetOutcome.CREATE, path="x.md"),),
        )
