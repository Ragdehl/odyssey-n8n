"""Request-scoped raw Markdown memoization never becomes knowledge/identity authority."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from odyssey_core.notes import (
    Note,
    NoteFormatError,
    parse_note,
    scoped_note_decode_cache,
    serialize_note,
)


def _markdown(name):
    return serialize_note(
        Note(
            {
                "id": "same-id",
                "type": "person",
                "name": name,
                "aliases": ["Uno", "Dos"],
                "created_by": {"human": None, "app": "test"},
            },
            "- Un hecho.\n",
        )
    )


def test_same_bytes_reuse_does_not_share_mutable_metadata():
    original = _markdown("Nuria")
    with scoped_note_decode_cache():
        first = parse_note(original)
        first.metadata["name"] = "alterada"
        first.metadata["aliases"].append("tres")
        first.metadata["created_by"]["app"] = "mutada"
        second = parse_note(original)
        assert second.metadata["name"] == "Nuria"
        assert second.metadata["aliases"] == ["Uno", "Dos"]
        assert second.metadata["created_by"]["app"] == "test"
    assert parse_note(original).metadata["name"] == "Nuria"


def test_updated_canonical_bytes_are_never_served_from_earlier_parse():
    before = _markdown("Nuria")
    after = _markdown("Nuria con cambios")
    with scoped_note_decode_cache():
        assert parse_note(before).metadata["name"] == "Nuria"
        assert parse_note(after).metadata["name"] == "Nuria con cambios"
        assert parse_note(before).metadata["name"] == "Nuria"


def test_bad_frontmatter_is_not_cached_as_valid_knowledge():
    valid = _markdown("Nuria")
    with scoped_note_decode_cache():
        parse_note(valid)
        with pytest.raises(NoteFormatError):
            parse_note('---\nname: "broken\n---\n')


def test_parallel_actor_scopes_cannot_share_or_mutate_notes():
    source = _markdown("Nuria")

    def run(suffix):
        with scoped_note_decode_cache():
            note = parse_note(source)
            note.metadata["name"] = suffix
            return parse_note(source).metadata["name"]

    with ThreadPoolExecutor(max_workers=3) as executor:
        assert list(executor.map(run, ("A", "B", "C"))) == ["Nuria"] * 3
