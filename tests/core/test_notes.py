"""Tests for generic notes, constrained Markdown, and note-instance validation."""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from odyssey_core.notes import (
    Note,
    NoteFormatError,
    NoteValidationError,
    parse_note,
    serialize_note,
    validate_note,
)


CANONICAL_SCHEMA = Path(__file__).resolve().parents[2] / "config" / "note-schema.json"


class NoteModelTests(unittest.TestCase):
    """Verify the generic note contains no filesystem or type hierarchy concerns."""

    def test_note_represents_generic_metadata_and_content(self) -> None:
        """Keep metadata and Markdown together without type-specific subclasses."""
        note = Note(metadata={"id": "note-1", "type": "person"}, content="Hello")

        self.assertEqual(note.metadata["type"], "person")
        self.assertEqual(note.content, "Hello")

    def test_note_identity_does_not_include_a_filesystem_path(self) -> None:
        """Represent logical identity in metadata independently of vault placement."""
        note = Note(metadata={"id": "stable-id"}, content="")

        self.assertFalse(hasattr(note, "path"))
        self.assertEqual(note.metadata["id"], "stable-id")


class MarkdownCodecTests(unittest.TestCase):
    """Verify deterministic supported frontmatter and unchanged Markdown bodies."""

    def test_serialize_note_is_canonical_and_orders_keys(self) -> None:
        """Emit delimiters, sorted keys, canonical scalars, and one body separator."""
        note = Note(
            metadata={
                "zeta": None,
                "active": True,
                "ratio": 1.5,
                "count": 2,
                "aliases": [],
                "name": 'Café "Odyssey"\nline',
            },
            content="# Body\n",
        )

        self.assertEqual(
            serialize_note(note),
            "---\n"
            "active: true\n"
            "aliases: []\n"
            "count: 2\n"
            'name: "Café \\"Odyssey\\"\\nline"\n'
            "ratio: 1.5\n"
            "zeta: null\n"
            "---\n\n"
            "# Body\n",
        )

    def test_populated_arrays_and_false_are_canonical(self) -> None:
        """Serialize flat arrays using canonical scalar representations."""
        note = Note(metadata={"items": ["uno", 2, False, None]}, content="")

        self.assertEqual(
            serialize_note(note),
            '---\nitems: ["uno", 2, false, null]\n---\n\n',
        )

    def test_parse_supported_human_edited_values_and_block_array(self) -> None:
        """Accept compatible unquoted, single-quoted, numeric, and block-array forms."""
        parsed = parse_note(
            "---\r\n"
            "aliases:\r\n"
            "  - 'Ada''s work'\r\n"
            "  - simple name\r\n"
            "enabled: FALSE\r\n"
            "nothing: ~\r\n"
            "score: -2.5e2\r\n"
            "---\r\n\r\n"
            "Body\r\n"
        )

        self.assertEqual(parsed.metadata["aliases"], ["Ada's work", "simple name"])
        self.assertIs(parsed.metadata["enabled"], False)
        self.assertIsNone(parsed.metadata["nothing"])
        self.assertEqual(parsed.metadata["score"], -250.0)
        self.assertEqual(parsed.content, "Body\r\n")

    def test_round_trip_preserves_values_unicode_and_body(self) -> None:
        """Preserve supported values and interpret no ordinary Markdown body syntax."""
        body = "# Café 🧭\n\nSee [[Ada Lovelace]].\n\n---\n\n`code: [still body]`\n"
        note = Note(
            metadata={
                "aliases": ["Analytical Engine", "机器"],
                "enabled": False,
                "number": 4,
                "optional": None,
                "title": "Odyssey",
            },
            content=body,
        )

        parsed = parse_note(serialize_note(note))
        reparsed = parse_note(serialize_note(parsed))

        self.assertEqual(parsed, note)
        self.assertEqual(reparsed, parsed)
        self.assertEqual(parsed.content, body)

    def test_round_trip_preserves_positive_and_negative_float_zero(self) -> None:
        """Keep zero-valued floats distinct from integers and retain the negative sign."""
        note = Note(metadata={"negative_zero": -0.0, "zero": 0.0}, content="")

        parsed = parse_note(serialize_note(note))

        self.assertIsInstance(parsed.metadata["zero"], float)
        self.assertIsInstance(parsed.metadata["negative_zero"], float)
        self.assertEqual(math.copysign(1.0, parsed.metadata["zero"]), 1.0)
        self.assertEqual(math.copysign(1.0, parsed.metadata["negative_zero"]), -1.0)

    def test_content_need_not_have_a_heading_or_be_non_empty(self) -> None:
        """Accept empty and ordinary prose bodies without domain interpretation."""
        self.assertEqual(parse_note('---\nid: "x"\n---\n\n').content, "")
        self.assertEqual(parse_note('---\nid: "x"\n---\n\nplain text').content, "plain text")

    def test_missing_or_malformed_delimiters_fail(self) -> None:
        """Reject absent, indented, or unclosed frontmatter delimiters."""
        malformed = ["plain Markdown", " ---\nid: x\n---\n", "---\nid: x\nbody"]
        for markdown in malformed:
            with self.subTest(markdown=markdown), self.assertRaises(NoteFormatError):
                parse_note(markdown)

    def test_duplicate_keys_fail(self) -> None:
        """Reject duplicate metadata rather than silently choosing a value."""
        with self.assertRaisesRegex(NoteFormatError, "Duplicate"):
            parse_note("---\nid: one\nid: two\n---\n")

    def test_malformed_quoted_values_fail(self) -> None:
        """Reject broken double and single quoted strings."""
        values = ['"unclosed', '"bad\\q"', "'bad'quote'"]
        for value in values:
            with self.subTest(value=value), self.assertRaises(NoteFormatError):
                parse_note(f"---\nvalue: {value}\n---\n")

    def test_nested_mappings_and_arrays_fail(self) -> None:
        """Reject nested data structures outside Odyssey's flat format."""
        values = ["{nested: value}", "[[1, 2]]", "[one, {two: three}]", ""]
        for value in values:
            markdown = f"---\nvalue: {value}\n  child: nested\n---\n"
            with self.subTest(value=value), self.assertRaises(NoteFormatError):
                parse_note(markdown)

    def test_unsupported_yaml_constructs_fail(self) -> None:
        """Reject tags, anchors, aliases, multiline scalars, and inline comments."""
        values = ["!tag value", "&anchor value", "*anchor", "|", ">", "value # comment"]
        for value in values:
            with self.subTest(value=value), self.assertRaises(NoteFormatError):
                parse_note(f"---\nvalue: {value}\n---\n")

    def test_serializer_rejects_nested_and_non_finite_values(self) -> None:
        """Refuse values that the constrained codec cannot round-trip."""
        for value in ({"nested": "mapping"}, [["nested"]], float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(NoteFormatError):
                serialize_note(
                    Note(metadata={"value": value}, content="")  # type: ignore[dict-item]
                )

    def test_serializer_rejects_invalid_metadata_keys(self) -> None:
        """Return a format error for invalid key syntax or non-string keys."""
        for metadata in ({"bad key": "value"}, {1: "value"}):
            with self.subTest(metadata=metadata), self.assertRaises(NoteFormatError):
                serialize_note(Note(metadata=metadata, content=""))  # type: ignore[arg-type]


class NoteValidationTests(unittest.TestCase):
    """Verify isolated note instances against the checked-in canonical schema."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the canonical registry once without duplicating it in Python tests."""
        cls.schema = json.loads(CANONICAL_SCHEMA.read_text(encoding="utf-8"))

    def valid_metadata(self, note_type: str = "concept") -> dict[str, object]:
        """Build the universal valid metadata baseline for one canonical type.

        Args:
            note_type: Canonical type ID to place in the generic metadata.

        Returns:
            Fresh mutable metadata satisfying universal fields.
        """
        return {
            "id": "01JTEST",
            "type": note_type,
            "created_at": "2026-08-15T10:30:00+02:00",
            "updated_at": "2026-08-15T08:30:00Z",
            "created_by": "test",
            "updated_by": "test",
            "revision": 1,
            "schema_version": self.schema["schema_version"],
        }

    def assert_invalid(self, metadata: dict[str, object], message: str = "") -> None:
        """Assert metadata fails canonical note-instance validation.

        Args:
            metadata: Candidate metadata expected to be invalid.
            message: Optional regular expression for the validation error.
        """
        context = (
            self.assertRaisesRegex(NoteValidationError, message)
            if message
            else self.assertRaises(NoteValidationError)
        )
        with context:
            validate_note(Note(metadata=metadata, content=""), self.schema)  # type: ignore[arg-type]

    def test_fully_valid_generic_note_passes(self) -> None:
        """Accept a generic Note using a controlled canonical type."""
        validate_note(
            Note(metadata=self.valid_metadata(), content="[[linked note]]"),  # type: ignore[arg-type]
            self.schema,
        )

    def test_every_required_universal_field_is_enforced(self) -> None:
        """Reject omission of each required universal field from the canonical schema."""
        required = [field["id"] for field in self.schema["metadata_fields"] if field["required"]]
        for field_id in required:
            metadata = self.valid_metadata()
            del metadata[field_id]
            with self.subTest(field_id=field_id):
                self.assert_invalid(metadata, "Missing required")

    def test_unknown_metadata_and_type_fail(self) -> None:
        """Reject fields and note types absent from the supplied canonical registry."""
        metadata = self.valid_metadata()
        metadata["relation"] = "typed-edge"
        self.assert_invalid(metadata, "Unknown metadata")

        metadata = self.valid_metadata("spaceship")
        self.assert_invalid(metadata, "Unknown note type")

    def test_subtype_must_belong_to_selected_parent(self) -> None:
        """Reject unregistered subtypes under the selected canonical type."""
        metadata = self.valid_metadata()
        metadata["subtype"] = "invented"
        self.assert_invalid(metadata, "not registered")

    def test_integer_fields_reject_bool_and_enforce_minimum(self) -> None:
        """Treat booleans as non-integers and require positive versions and revisions."""
        for field_id, value in (
            ("revision", True),
            ("revision", 0),
            ("schema_version", False),
            ("schema_version", 0),
        ):
            metadata = self.valid_metadata()
            metadata[field_id] = value
            with self.subTest(field_id=field_id, value=value):
                self.assert_invalid(metadata)

    def test_aliases_require_string_array_and_unique_items(self) -> None:
        """Enforce the canonical aliases type and uniqueness constraint."""
        metadata = self.valid_metadata()
        metadata["aliases"] = ["one", "two"]
        validate_note(Note(metadata=metadata, content=""), self.schema)  # type: ignore[arg-type]

        for aliases in ("one", ["one", 2], ["same", "same"]):
            metadata = self.valid_metadata()
            metadata["aliases"] = aliases
            with self.subTest(aliases=aliases):
                self.assert_invalid(metadata)

    def test_date_and_date_time_formats(self) -> None:
        """Accept real ISO values and reject invalid dates, times, and missing offsets."""
        person = self.valid_metadata("person")
        person["birth_date"] = "2000-02-29"
        validate_note(Note(metadata=person, content=""), self.schema)  # type: ignore[arg-type]

        for birth_date in ("2001-02-29", "2026-8-15", "2026-08-15T00:00:00Z"):
            person = self.valid_metadata("person")
            person["birth_date"] = birth_date
            with self.subTest(birth_date=birth_date):
                self.assert_invalid(person)
        for created_at in ("not-a-date", "2026-08-15", "2026-08-15T10:30:00"):
            metadata = self.valid_metadata()
            metadata["created_at"] = created_at
            with self.subTest(created_at=created_at):
                self.assert_invalid(metadata)

    def test_person_optional_properties_are_type_specific(self) -> None:
        """Accept declared person fields and reject them on another note type."""
        person = self.valid_metadata("person")
        person.update({"birth_date": "1815-12-10", "relationship_to_user": "historical"})
        validate_note(Note(metadata=person, content=""), self.schema)  # type: ignore[arg-type]

        concept = self.valid_metadata()
        concept["birth_date"] = "1815-12-10"
        self.assert_invalid(concept, "Unknown metadata")

    def test_journal_entry_requires_entry_date(self) -> None:
        """Enforce the selected type's required structured property."""
        journal = self.valid_metadata("journal_entry")
        self.assert_invalid(journal, "Missing required type")
        journal["entry_date"] = "2026-08-15"
        validate_note(Note(metadata=journal, content=""), self.schema)  # type: ignore[arg-type]

    def test_note_schema_version_must_match_supplied_schema(self) -> None:
        """Reject otherwise valid notes written for another canonical schema version."""
        metadata = self.valid_metadata()
        metadata["schema_version"] = self.schema["schema_version"] + 1
        self.assert_invalid(metadata, "incompatible")

    def test_non_empty_universal_strings_are_enforced(self) -> None:
        """Apply declared non-empty constraints without inventing prose requirements."""
        for field_id in ("id", "created_by", "updated_by"):
            metadata = self.valid_metadata()
            metadata[field_id] = "   "
            with self.subTest(field_id=field_id):
                self.assert_invalid(metadata, "must not be empty")


if __name__ == "__main__":
    unittest.main()
