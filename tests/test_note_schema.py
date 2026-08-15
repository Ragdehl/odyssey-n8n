"""Behavioral tests for Odyssey's canonical note schema contract."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scripts.validate_note_schema import SchemaValidationError, load_schema, validate_schema

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = REPOSITORY_ROOT / "config" / "note-schema.json"


class NoteSchemaValidationTests(unittest.TestCase):
    """Verify valid schema definitions pass and malformed definitions fail clearly."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the canonical schema once for isolated mutation in each test."""
        cls.schema = load_schema(CANONICAL_SCHEMA)

    def assert_invalid(self, schema: object, message: str) -> None:
        """Assert that a malformed Odyssey schema fails with an expected explanation.

        Args:
            schema: Candidate schema expected to be invalid.
            message: Regular expression that should match the validation error.

        Returns:
            None.
        """
        with self.assertRaisesRegex(SchemaValidationError, message):
            validate_schema(schema)

    def type_definition(self, type_id: str) -> dict:
        """Return one canonical note type definition by its stable identifier.

        Args:
            type_id: Canonical note type identifier to find.

        Returns:
            The matching type definition.

        Raises:
            StopIteration: If the canonical registry does not contain the requested type.
        """
        return next(note_type for note_type in self.schema["types"] if note_type["id"] == type_id)

    def test_valid_canonical_schema_passes(self) -> None:
        """Accept the checked-in canonical schema as a valid contract."""
        validate_schema(copy.deepcopy(self.schema))

    def test_invalid_json_fails(self) -> None:
        """Reject a schema file that cannot be parsed as JSON."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text("{invalid", encoding="utf-8")
            with self.assertRaisesRegex(SchemaValidationError, "cannot read valid JSON"):
                load_schema(path)

    def test_duplicate_type_id_fails(self) -> None:
        """Reject ambiguous type registries containing the same stable ID twice."""
        schema = copy.deepcopy(self.schema)
        schema["types"].append(copy.deepcopy(schema["types"][0]))
        self.assert_invalid(schema, "duplicate type id")

    def test_type_missing_properties_fails(self) -> None:
        """Require every note type to declare its domain-property collection."""
        schema = copy.deepcopy(self.schema)
        del schema["types"][0]["properties"]
        self.assert_invalid(schema, "missing required fields.*properties")

    def test_invalid_properties_value_fails(self) -> None:
        """Reject a note type whose domain properties are not an array."""
        schema = copy.deepcopy(self.schema)
        schema["types"][0]["properties"] = "not-an-array"
        self.assert_invalid(schema, "properties must be an array")

    def test_duplicate_property_id_fails(self) -> None:
        """Reject duplicate property IDs within one note type."""
        schema = copy.deepcopy(self.schema)
        property_definition = copy.deepcopy(self.type_definition("person")["properties"][0])
        schema["types"][0]["properties"] = [property_definition, copy.deepcopy(property_definition)]
        self.assert_invalid(schema, "duplicate property id")

    def test_property_missing_required_definition_field_fails(self) -> None:
        """Reject a property definition missing part of its lightweight contract."""
        schema = copy.deepcopy(self.schema)
        property_definition = copy.deepcopy(self.type_definition("person")["properties"][0])
        del property_definition["description"]
        schema["types"][0]["properties"] = [property_definition]
        self.assert_invalid(schema, "missing required fields.*description")

    def test_invalid_property_id_fails(self) -> None:
        """Reject property IDs that cannot serve as stable machine identifiers."""
        schema = copy.deepcopy(self.schema)
        property_definition = copy.deepcopy(self.type_definition("person")["properties"][0])
        property_definition["id"] = "Invalid-ID"
        schema["types"][0]["properties"] = [property_definition]
        self.assert_invalid(schema, "invalid id")

    def test_invalid_property_required_value_fails(self) -> None:
        """Require a property's required marker to be an actual boolean."""
        schema = copy.deepcopy(self.schema)
        property_definition = copy.deepcopy(self.type_definition("person")["properties"][0])
        property_definition["required"] = "false"
        schema["types"][0]["properties"] = [property_definition]
        self.assert_invalid(schema, "required must be boolean")

    def test_journal_entry_date_exists_and_is_required(self) -> None:
        """Record a journal entry's subject date as required structured information."""
        journal_entry = self.type_definition("journal_entry")
        entry_date = next(
            item for item in journal_entry["properties"] if item["id"] == "entry_date"
        )
        self.assertEqual(entry_date["value_type"], "date")
        self.assertIs(entry_date["required"], True)

    def test_person_birth_date_is_optional(self) -> None:
        """Keep a person's known birth date optional in the initial contract."""
        person = self.type_definition("person")
        birth_date = next(item for item in person["properties"] if item["id"] == "birth_date")
        self.assertEqual(birth_date["value_type"], "date")
        self.assertIs(birth_date["required"], False)

    def test_person_relationship_to_user_is_optional(self) -> None:
        """Keep the person's relationship to the user optional."""
        person = self.type_definition("person")
        relationship = next(
            item for item in person["properties"] if item["id"] == "relationship_to_user"
        )
        self.assertEqual(relationship["value_type"], "string")
        self.assertIs(relationship["required"], False)

    def test_duplicate_subtype_id_fails(self) -> None:
        """Reject duplicate controlled subtype IDs within a parent type."""
        schema = copy.deepcopy(self.schema)
        subtype = {"id": "example", "name": "Example", "description": "Test subtype."}
        schema["types"][0]["subtypes"] = [subtype, copy.deepcopy(subtype)]
        self.assert_invalid(schema, "duplicate subtype id")

    def test_invalid_subtypes_value_fails(self) -> None:
        """Require every note type's controlled subtype registry to be an array."""
        schema = copy.deepcopy(self.schema)
        schema["types"][0]["subtypes"] = "not-an-array"
        self.assert_invalid(schema, "subtypes must be an array")

    def test_duplicate_metadata_field_id_fails(self) -> None:
        """Reject ambiguous universal metadata definitions with duplicate IDs."""
        schema = copy.deepcopy(self.schema)
        schema["metadata_fields"].append(copy.deepcopy(schema["metadata_fields"][0]))
        self.assert_invalid(schema, "duplicate metadata field id")

    def test_metadata_field_missing_definition_field_fails(self) -> None:
        """Reject universal metadata that omits part of the field contract."""
        schema = copy.deepcopy(self.schema)
        del schema["metadata_fields"][0]["value_type"]
        self.assert_invalid(schema, "missing required fields.*value_type")

    def test_invalid_metadata_required_value_fails(self) -> None:
        """Require universal metadata required markers to be booleans."""
        schema = copy.deepcopy(self.schema)
        schema["metadata_fields"][0]["required"] = 1
        self.assert_invalid(schema, "required must be boolean")

    def test_missing_identity_metadata_fails(self) -> None:
        """Require the stable identity field that makes every Odyssey note addressable."""
        schema = copy.deepcopy(self.schema)
        schema["metadata_fields"] = [
            field for field in schema["metadata_fields"] if field["id"] != "id"
        ]
        self.assert_invalid(schema, "must define the id field")

    def test_optional_identity_metadata_fails(self) -> None:
        """Require stable identity on every Odyssey note."""
        schema = copy.deepcopy(self.schema)
        identity = next(field for field in schema["metadata_fields"] if field["id"] == "id")
        identity["required"] = False
        self.assert_invalid(schema, "field 'id' must be required")

    def test_missing_type_metadata_fails(self) -> None:
        """Require every Odyssey note to participate in the controlled type model."""
        schema = copy.deepcopy(self.schema)
        schema["metadata_fields"] = [
            field for field in schema["metadata_fields"] if field["id"] != "type"
        ]
        self.assert_invalid(schema, "must define the type field")

    def test_optional_type_metadata_fails(self) -> None:
        """Require a controlled type selection on every Odyssey note."""
        schema = copy.deepcopy(self.schema)
        note_type = next(field for field in schema["metadata_fields"] if field["id"] == "type")
        note_type["required"] = False
        self.assert_invalid(schema, "field 'type' must be required")

    def test_uncontrolled_type_metadata_fails(self) -> None:
        """Require note types to come from the canonical registry."""
        schema = copy.deepcopy(self.schema)
        note_type = next(field for field in schema["metadata_fields"] if field["id"] == "type")
        note_type["constraints"]["controlled"] = False
        self.assert_invalid(schema, "type must be controlled by the canonical types registry")

    def test_required_subtype_metadata_fails(self) -> None:
        """Keep controlled subtype selection optional for Odyssey notes."""
        schema = copy.deepcopy(self.schema)
        subtype = next(field for field in schema["metadata_fields"] if field["id"] == "subtype")
        subtype["required"] = True
        self.assert_invalid(schema, "field 'subtype' must be optional")

    def test_missing_subtype_metadata_fails(self) -> None:
        """Preserve Odyssey's optional controlled-subtype capability in the metadata model."""
        schema = copy.deepcopy(self.schema)
        schema["metadata_fields"] = [
            field for field in schema["metadata_fields"] if field["id"] != "subtype"
        ]
        self.assert_invalid(schema, "must define the optional subtype field")

    def test_uncontrolled_subtype_metadata_fails(self) -> None:
        """Require subtype values to remain controlled by a registry."""
        schema = copy.deepcopy(self.schema)
        subtype = next(field for field in schema["metadata_fields"] if field["id"] == "subtype")
        subtype["constraints"]["controlled"] = False
        self.assert_invalid(schema, "subtype must be controlled by its parent type")

    def test_subtype_with_wrong_parent_fails(self) -> None:
        """Require subtype values to be selected from their note type's own registry."""
        schema = copy.deepcopy(self.schema)
        subtype = next(field for field in schema["metadata_fields"] if field["id"] == "subtype")
        subtype["constraints"]["parent_field"] = "id"
        self.assert_invalid(schema, "subtype must be controlled by its parent type")

    def test_subtype_allowing_unregistered_values_fails(self) -> None:
        """Reject subtype policies that permit values outside the parent registry."""
        schema = copy.deepcopy(self.schema)
        subtype = next(field for field in schema["metadata_fields"] if field["id"] == "subtype")
        subtype["constraints"]["allow_unregistered"] = True
        self.assert_invalid(schema, "disallow unregistered values")


if __name__ == "__main__":
    unittest.main()
