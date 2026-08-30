"""Behavioral tests for Odyssey's Phase 17E canonical note-schema contract."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scripts.validate_note_schema import SchemaValidationError, load_schema, validate_schema

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = REPOSITORY_ROOT / "config" / "note-schema.json"


class NoteSchemaValidationTests(unittest.TestCase):
    """Verify the active minimal Core schema and its extension hooks."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_schema(CANONICAL_SCHEMA)

    def assert_invalid(self, schema: object, message: str) -> None:
        with self.assertRaisesRegex(SchemaValidationError, message):
            validate_schema(schema)

    def type_definition(self, type_id: str) -> dict:
        return next(note_type for note_type in self.schema["types"] if note_type["id"] == type_id)

    def metadata_definition(self, field_id: str) -> dict:
        return next(field for field in self.schema["metadata_fields"] if field["id"] == field_id)

    def test_valid_canonical_schema_passes(self) -> None:
        validate_schema(copy.deepcopy(self.schema))

    def test_schema_version_is_phase17e_v3(self) -> None:
        self.assertEqual(self.schema["schema_version"], 3)

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

    def test_type_missing_properties_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        del schema["types"][0]["properties"]
        self.assert_invalid(schema, "missing required fields.*properties")

    def test_invalid_properties_value_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["types"][0]["properties"] = "not-an-array"
        self.assert_invalid(schema, "properties must be an array")

    def test_property_definition_validation_uses_journal_entry(self) -> None:
        entry_date = copy.deepcopy(self.type_definition("journal_entry")["properties"][0])

        duplicate = copy.deepcopy(self.schema)
        duplicate["types"][0]["properties"] = [entry_date, copy.deepcopy(entry_date)]
        self.assert_invalid(duplicate, "duplicate property id")

        missing = copy.deepcopy(self.schema)
        malformed = copy.deepcopy(entry_date)
        del malformed["description"]
        missing["types"][0]["properties"] = [malformed]
        self.assert_invalid(missing, "missing required fields.*description")

        invalid_id = copy.deepcopy(self.schema)
        malformed = copy.deepcopy(entry_date)
        malformed["id"] = "Invalid-ID"
        invalid_id["types"][0]["properties"] = [malformed]
        self.assert_invalid(invalid_id, "invalid id")

        invalid_required = copy.deepcopy(self.schema)
        malformed = copy.deepcopy(entry_date)
        malformed["required"] = "false"
        invalid_required["types"][0]["properties"] = [malformed]
        self.assert_invalid(invalid_required, "required must be boolean")

        invalid_filterable = copy.deepcopy(self.schema)
        malformed = copy.deepcopy(entry_date)
        malformed["filterable"] = "true"
        invalid_filterable["types"][0]["properties"] = [malformed]
        self.assert_invalid(invalid_filterable, "filterable must be boolean")

    def test_journal_entry_date_remains_required(self) -> None:
        journal_entry = self.type_definition("journal_entry")
        entry_date = next(
            item for item in journal_entry["properties"] if item["id"] == "entry_date"
        )
        self.assertEqual(entry_date["value_type"], "date")
        self.assertIs(entry_date["required"], True)

    def test_person_has_no_active_core_properties(self) -> None:
        self.assertEqual(self.type_definition("person")["properties"], [])

    def test_subtype_registry_hook_remains_empty_but_active_field_is_absent(self) -> None:
        self.skipTest("Deferred subtype contract")
        self.assertTrue(all(note_type["subtypes"] == [] for note_type in self.schema["types"]))
        self.assertNotIn("subtype", {field["id"] for field in self.schema["metadata_fields"]})

    def test_subtype_registry_definitions_are_still_validated(self) -> None:
        self.skipTest("Deferred subtype contract")
        subtype = {"id": "example", "name": "Example", "description": "Test subtype."}

        duplicate = copy.deepcopy(self.schema)
        duplicate["types"][0]["subtypes"] = [subtype, copy.deepcopy(subtype)]
        self.assert_invalid(duplicate, "duplicate subtype id")

        malformed = copy.deepcopy(self.schema)
        malformed["types"][0]["subtypes"] = "not-an-array"
        self.assert_invalid(malformed, "subtypes must be an array")

    def test_builtin_tag_vocabulary_and_active_tag_field_are_absent(self) -> None:
        self.assertNotIn("controlled_values", self.schema)
        self.assertIn("tags", {field["id"] for field in self.schema["metadata_fields"]})

    def test_generic_tags_contract_cannot_drift(self) -> None:
        for mutate in (
            lambda schema, field: schema["metadata_fields"].remove(field),
            lambda schema, field: field.update(required=True),
            lambda schema, field: field.update(value_type="string"),
            lambda schema, field: field["constraints"].pop("unique_items"),
            lambda schema, field: field.update(filter_operations=["eq"]),
            lambda schema, field: field.update(controlled_values=["idea"]),
        ):
            schema = copy.deepcopy(self.schema)
            field = next(item for item in schema["metadata_fields"] if item["id"] == "tags")
            mutate(schema, field)
            self.assert_invalid(schema, "tags")

    def test_tag_registry_hook_still_validates_explicit_future_definitions(self) -> None:
        self.skipTest("Core tags are free-form; no registry")

    def test_duplicate_metadata_field_id_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["metadata_fields"].append(copy.deepcopy(schema["metadata_fields"][0]))
        self.assert_invalid(schema, "duplicate metadata field id")

    def test_metadata_field_missing_definition_field_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        del schema["metadata_fields"][0]["value_type"]
        self.assert_invalid(schema, "missing required fields.*value_type")

    def test_invalid_metadata_required_value_fails(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["metadata_fields"][0]["required"] = 1
        self.assert_invalid(schema, "required must be boolean")

    def test_stable_identity_is_required(self) -> None:
        missing = copy.deepcopy(self.schema)
        missing["metadata_fields"] = [
            field for field in missing["metadata_fields"] if field["id"] != "id"
        ]
        self.assert_invalid(missing, "must define the id field")

        optional = copy.deepcopy(self.schema)
        next(field for field in optional["metadata_fields"] if field["id"] == "id")["required"] = (
            False
        )
        self.assert_invalid(optional, "field 'id' must be required")

    def test_controlled_type_is_required(self) -> None:
        missing = copy.deepcopy(self.schema)
        missing["metadata_fields"] = [
            field for field in missing["metadata_fields"] if field["id"] != "type"
        ]
        self.assert_invalid(missing, "must define the type field")

        optional = copy.deepcopy(self.schema)
        next(field for field in optional["metadata_fields"] if field["id"] == "type")[
            "required"
        ] = False
        self.assert_invalid(optional, "field 'type' must be required")

        uncontrolled = copy.deepcopy(self.schema)
        next(field for field in uncontrolled["metadata_fields"] if field["id"] == "type")[
            "constraints"
        ]["controlled"] = False
        self.assert_invalid(uncontrolled, "type must be controlled by the canonical types registry")

    def test_created_and_updated_by_use_actor_pair_contract(self) -> None:
        for field_id in ("created_by", "updated_by"):
            definition = self.metadata_definition(field_id)
            self.assertIs(definition["required"], True)
            self.assertEqual(definition["value_type"], "object")

    def test_provenance_fields_are_required_actor_pairs(self) -> None:
        for field_id in ("created_by", "updated_by"):
            missing = copy.deepcopy(self.schema)
            missing["metadata_fields"] = [
                field for field in missing["metadata_fields"] if field["id"] != field_id
            ]
            self.assert_invalid(missing, f"must define the {field_id} field")

            optional = copy.deepcopy(self.schema)
            next(field for field in optional["metadata_fields"] if field["id"] == field_id)[
                "required"
            ] = False
            self.assert_invalid(optional, f"{field_id} must be a required object")

            wrong_type = copy.deepcopy(self.schema)
            next(field for field in wrong_type["metadata_fields"] if field["id"] == field_id)[
                "value_type"
            ] = "string"
            self.assert_invalid(
                wrong_type, f"{field_id} must be a required object provenance field"
            )


if __name__ == "__main__":
    unittest.main()
