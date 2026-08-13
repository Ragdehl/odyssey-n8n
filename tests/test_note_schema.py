from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scripts.validate_note_schema import SchemaValidationError, load_schema, validate_schema


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = REPOSITORY_ROOT / "config" / "note-schema.json"


class NoteSchemaValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_schema(CANONICAL_SCHEMA)

    def assert_invalid(self, schema: object, message: str) -> None:
        with self.assertRaisesRegex(SchemaValidationError, message):
            validate_schema(schema)

    def test_valid_canonical_schema_passes(self) -> None:
        validate_schema(copy.deepcopy(self.schema))

    def test_canonical_schema_has_exact_initial_type_ids(self) -> None:
        self.assertEqual(
            {note_type["id"] for note_type in self.schema["types"]},
            {"concept", "project", "task", "store", "product", "purchase", "recipe", "document"},
        )

    def test_invalid_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text("{invalid", encoding="utf-8")
            with self.assertRaisesRegex(SchemaValidationError, "cannot read valid JSON"):
                load_schema(path)

    def test_duplicate_type_id_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["types"].append(copy.deepcopy(schema["types"][0]))
        self.assert_invalid(schema, "duplicate type id")

    def test_missing_required_type_field_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        del schema["types"][0]["description"]
        self.assert_invalid(schema, "missing required fields")

    def test_invalid_type_id_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["types"][0]["id"] = "Invalid-ID"
        self.assert_invalid(schema, "invalid id")

    def test_invalid_examples_value_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["types"][0]["examples"] = "not-an-array"
        self.assert_invalid(schema, "examples must be an array of strings")

    def test_duplicate_subtype_id_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        subtype = {"id": "example", "name": "Example", "description": "Test subtype."}
        schema["types"][0]["subtypes"] = [subtype, copy.deepcopy(subtype)]
        self.assert_invalid(schema, "duplicate subtype id")

    def test_missing_required_canonical_metadata_field_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["metadata_fields"] = [
            field for field in schema["metadata_fields"] if field["id"] != "revision"
        ]
        self.assert_invalid(schema, "missing required canonical metadata fields")

    def test_duplicate_metadata_field_id_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["metadata_fields"].append(copy.deepcopy(schema["metadata_fields"][0]))
        self.assert_invalid(schema, "duplicate metadata field id")

    def test_invalid_schema_version_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["schema_version"] = 0
        self.assert_invalid(schema, "schema_version must be a positive integer")

    def test_uncontrolled_type_field_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        type_field = next(field for field in schema["metadata_fields"] if field["id"] == "type")
        type_field["constraints"]["controlled"] = False
        self.assert_invalid(schema, "type must be controlled")

    def test_inconsistent_subtype_policy_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        subtype = next(field for field in schema["metadata_fields"] if field["id"] == "subtype")
        subtype["constraints"]["allow_unregistered"] = True
        self.assert_invalid(schema, "subtype must be optional, controlled")


if __name__ == "__main__":
    unittest.main()
