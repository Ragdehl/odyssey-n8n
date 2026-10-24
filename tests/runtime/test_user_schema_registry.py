"""Additive user-schema snapshots before any authenticated UI is connected."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from odyssey_apps.events.schema import EVENT_SCHEMA_EXTENSION
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_core.context import _filter_definitions
from odyssey_core.notes import Note, NoteValidationError, validate_note
from odyssey_core.schema_types import ordinary_type_ids
from odyssey_runtime.user_schema_registry import (
    SchemaConfirmation,
    UserSchemaError,
    UserSchemaRegistry,
)

ROOT = Path(__file__).resolve().parents[2]


def registry(tmp_path: Path) -> UserSchemaRegistry:
    return UserSchemaRegistry(
        tmp_path,
        json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8")),
        (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION),
    )


def property_change(kind: str = "string") -> dict:
    return {
        "operation": "add_property",
        "type_id": "person",
        "property": {
            "id": "occupation",
            "value_type": kind,
            "description": "Current occupation when known.",
        },
    }


def type_change(name: str = "Book", id_: str = "book") -> dict:
    return {
        "operation": "add_type",
        "type": {
            "id": id_,
            "name": name,
            "description": "Independent identifiable written work.",
            "examples": ["A novel"],
            "properties": [
                {
                    "id": "page_count",
                    "value_type": "integer",
                    "description": "Number of pages when known.",
                },
            ],
        },
    }


def confirm(preview, request_id: str = "schema-request-one") -> SchemaConfirmation:
    return SchemaConfirmation(
        "synthetic-actor", request_id, preview.revision, preview.proposal_hash
    )


def _person_note() -> Note:
    return Note(
        {
            "id": "person-1",
            "name": "A person",
            "type": "person",
            "created_at": "2026-10-24T16:00:00+00:00",
            "updated_at": "2026-10-24T16:00:00+00:00",
            "created_by": {"human": "synthetic-actor", "app": "odyssey"},
            "updated_by": {"human": "synthetic-actor", "app": "odyssey"},
            "revision": 1,
            "schema_version": 3,
        },
        "- Synthetic fact.\n",
    )


def test_empty_registry_reuses_app_types_and_does_not_touch_base(tmp_path: Path) -> None:
    user = registry(tmp_path)
    revision, schema = user.snapshot()
    assert revision == 0
    assert "task" not in ordinary_type_ids(schema)
    assert "event" not in ordinary_type_ids(schema)
    assert "person" in ordinary_type_ids(schema)
    assert not (tmp_path / "user-schema/current.json").exists()


def test_preview_add_optional_filterable_property_preserves_old_note(tmp_path: Path) -> None:
    user = registry(tmp_path)
    before_revision, before_schema = user.snapshot()
    before = _person_note()
    validate_note(before, before_schema)
    preview = user.preview(property_change(), expected_revision=0)
    assert (preview.revision, preview.next_revision) == (0, 1)
    assert not (tmp_path / "user-schema/current.json").exists()
    field = next(
        x
        for x in next(t for t in preview.effective_schema["types"] if t["id"] == "person")[
            "properties"
        ]
        if x["id"] == "occupation"
    )
    assert field == {
        "id": "occupation",
        "value_type": "string",
        "description": "Current occupation when known.",
        "required": False,
        "filterable": True,
    }
    assert preview.effective_schema["schema_version"] == 3
    validate_note(before, preview.effective_schema)
    assert "occupation" in _filter_definitions(preview.effective_schema)
    with pytest.raises(NoteValidationError, match="Unknown metadata"):
        validate_note(
            Note({**before.metadata, "occupation": "Teacher"}, before.content), before_schema
        )
    result = user.publish(property_change(), confirm(preview))
    assert result.next_revision == 1
    assert user.snapshot()[0] == 1
    validate_note(before, user.snapshot()[1])
    validate_note(
        Note({**before.metadata, "occupation": "Teacher"}, before.content), user.snapshot()[1]
    )


def test_new_type_carries_optional_queryable_properties_and_survives_reload(tmp_path: Path) -> None:
    user = registry(tmp_path)
    p = user.preview(type_change(), expected_revision=0)
    user.publish(type_change(), confirm(p))
    other = registry(tmp_path)
    revision, schema = other.snapshot()
    assert revision == 1
    assert "book" in ordinary_type_ids(schema)
    assert "book" in {x["id"] for x in schema["types"]}
    assert (
        next(x for x in schema["types"] if x["id"] == "book")["properties"][0]["required"] is False
    )
    assert "page_count" in _filter_definitions(schema)
    assert len(list((tmp_path / "user-schema/history").glob("*.json"))) == 1
    assert schema["schema_version"] == 3
    assert _person_note().metadata["type"] == "person"  # no reclassification


def test_can_edit_display_description_without_changing_stable_identity(tmp_path: Path) -> None:
    user = registry(tmp_path)
    updated = {
        "operation": "edit_type_text",
        "type_id": "person",
        "name": "Persona",
        "description": "An individual with an identity.",
    }
    p = user.preview(updated, expected_revision=0)
    user.publish(updated, confirm(p))
    change = {
        "operation": "edit_property_description",
        "type_id": "person",
        "property_id": "occupation",
        "description": "Professional activity.",
    }
    p2 = user.preview(property_change(), expected_revision=1)
    user.publish(property_change(), confirm(p2, "second-request"))
    p3 = user.preview(change, expected_revision=2)
    user.publish(change, confirm(p3, "third-request"))
    rev, schema = user.snapshot()
    assert rev == 3
    person = next(x for x in schema["types"] if x["id"] == "person")
    assert person["name"] == "Persona"
    assert person["properties"][0]["id"] == "occupation"
    assert person["properties"][0]["description"] == "Professional activity."
    validate_note(_person_note(), schema)


@pytest.mark.parametrize(
    "change",
    [
        {
            "operation": "add_property",
            "type_id": "calendar_day",
            "property": {"id": "nickname", "value_type": "string", "description": "Nickname"},
        },
        {
            "operation": "add_property",
            "type_id": "task",
            "property": {"id": "nickname", "value_type": "string", "description": "Nickname"},
        },
        {
            "operation": "add_property",
            "type_id": "journal_entry",
            "property": {"id": "nickname", "value_type": "string", "description": "Nickname"},
        },
        {
            "operation": "add_property",
            "type_id": "person",
            "property": {"id": "id", "value_type": "string", "description": "Not allowed"},
        },
        {
            "operation": "add_property",
            "type_id": "person",
            "property": {
                "id": "alive",
                "value_type": "boolean",
                "description": "Not queryable yet",
            },
        },
        {
            "operation": "add_property",
            "type_id": "person",
            "property": {
                "id": "occupation",
                "value_type": "string",
                "description": "Occupational",
                "required": True,
            },
        },
        {
            "operation": "add_type",
            "type": {
                "id": "task",
                "name": "Task",
                "description": "Wrong",
                "examples": [],
                "properties": [],
            },
        },
        {
            "operation": "add_type",
            "type": {
                "id": "person2",
                "name": "Person",
                "description": "Duplicate",
                "examples": [],
                "properties": [],
            },
        },
        {
            "operation": "add_type",
            "type": {
                "id": "hotel",
                "name": "Hotel",
                "description": "A hotel",
                "examples": [],
                "managed_by": "core",
                "properties": [],
            },
        },
        {"operation": "remove_type", "type_id": "person"},
    ],
)
def test_rejects_unsafe_user_schema_changes(tmp_path: Path, change: dict) -> None:
    user = registry(tmp_path)
    with pytest.raises(UserSchemaError):
        user.preview(change, expected_revision=0)
    assert user.snapshot()[0] == 0


def test_user_registry_revision_and_confirmation_are_bound(tmp_path: Path) -> None:
    user = registry(tmp_path)
    change = property_change()
    preview = user.preview(change, expected_revision=0)
    with pytest.raises(UserSchemaError, match="confirmation"):
        user.publish(change, None)  # type: ignore[arg-type]
    with pytest.raises(UserSchemaError, match="PROPOSAL_CHANGED"):
        user.publish(change, SchemaConfirmation("person-1", "request-1", 0, "bad"))
    with pytest.raises(UserSchemaError, match="PROPOSAL_CHANGED"):
        user.publish(
            {**change, "property": {**change["property"], "description": "Something else"}},
            confirm(preview),
        )
    assert user.snapshot()[0] == 0
    user.publish(change, confirm(preview))
    with pytest.raises(UserSchemaError, match="ALREADY_PUBLISHED"):
        user.publish(change, confirm(preview))
    with pytest.raises(UserSchemaError, match="REVISION_STALE"):
        user.preview(type_change(), expected_revision=0)
    assert user.snapshot()[0] == 1


def test_two_registry_instances_serialize_writes(tmp_path: Path) -> None:
    first, second = registry(tmp_path), registry(tmp_path)
    p = first.preview(type_change(), expected_revision=0)
    q = second.preview(property_change(), expected_revision=0)

    def commit_first() -> str:
        try:
            first.publish(type_change(), confirm(p, "first"))
            return "ok"
        except UserSchemaError as error:
            return str(error)

    def commit_second() -> str:
        try:
            second.publish(property_change(), confirm(q, "second"))
            return "ok"
        except UserSchemaError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(commit_first)
        b = executor.submit(commit_second)
        results = {a.result(), b.result()}
    assert results == {"ok", "SCHEMA_REVISION_STALE"}
    assert first.snapshot()[0] == 1


def test_corrupt_current_state_fails_closed(tmp_path: Path) -> None:
    user = registry(tmp_path)
    p = user.preview(type_change(), expected_revision=0)
    user.publish(type_change(), confirm(p))
    current = tmp_path / "user-schema/current.json"
    current.write_text('{"unsafe":true}', encoding="utf-8")
    with pytest.raises(UserSchemaError, match="format"):
        registry(tmp_path).snapshot()


def test_missing_receipt_fails_closed(tmp_path: Path) -> None:
    user = registry(tmp_path)
    p = user.preview(type_change(), expected_revision=0)
    user.publish(type_change(), confirm(p))
    receipt = next((tmp_path / "user-schema/history").glob("*.json"))
    receipt.unlink()
    with pytest.raises(UserSchemaError, match="receipt"):
        registry(tmp_path).snapshot()


def test_existing_parent_must_be_real_not_symlink(tmp_path: Path) -> None:
    unsafe = tmp_path / "symlink"
    unsafe.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(UserSchemaError, match="root"):
        registry(unsafe)


@pytest.mark.parametrize("identifier", [[], {}, None, 12, "Invalid-ID", "", "bad key"])
def test_malformed_property_identifier_fails_cleanly(tmp_path: Path, identifier: object) -> None:
    change = property_change()
    change["property"]["id"] = identifier
    with pytest.raises(UserSchemaError, match="identifier"):
        registry(tmp_path).preview(change, expected_revision=0)


@pytest.mark.parametrize("name", ["BOOK", "Ｂｏｏｋ", " book "])
def test_normalized_type_name_collision_is_rejected(tmp_path: Path, name: str) -> None:
    user = registry(tmp_path)
    first = user.preview(type_change(), expected_revision=0)
    user.publish(type_change(), confirm(first))
    with pytest.raises(UserSchemaError, match="collides"):
        user.preview(type_change(name, "a_second_book"), expected_revision=1)


def test_corrupted_duplicate_history_replay_is_rejected(tmp_path: Path) -> None:
    user = registry(tmp_path)
    p = user.preview(type_change(), expected_revision=0)
    user.publish(type_change(), confirm(p))
    with pytest.raises(UserSchemaError, match="ALREADY_PUBLISHED"):
        user.publish(type_change(), confirm(p))
    current = tmp_path / "user-schema/current.json"
    assert current.stat().st_mode & 0o077 == 0
    assert (tmp_path / "user-schema/history").stat().st_mode & 0o077 == 0


def test_preview_cannot_expand_object_or_boolean_fields_without_query_support(
    tmp_path: Path,
) -> None:
    user = registry(tmp_path)
    for kind in ["boolean", "object", "unknown", [], None]:
        with pytest.raises(UserSchemaError, match="query operators"):
            user.preview(property_change(kind), expected_revision=0)
    assert user.snapshot()[0] == 0


def test_reject_unconfirmed_changes_to_app_owned_descriptions(tmp_path: Path) -> None:
    user = registry(tmp_path)
    change = {
        "operation": "edit_type_text",
        "type_id": "event",
        "name": "An Event",
        "description": "Cannot edit app policy",
    }
    with pytest.raises(UserSchemaError, match="unavailable"):
        user.preview(change, expected_revision=0)


def test_missing_current_pointer_with_retained_history_fails_closed(tmp_path: Path) -> None:
    user = registry(tmp_path)
    p = user.preview(type_change(), expected_revision=0)
    user.publish(type_change(), confirm(p))
    (tmp_path / "user-schema/current.json").unlink()
    with pytest.raises(UserSchemaError, match="pointer is missing"):
        registry(tmp_path).snapshot()


def test_runtime_notes_schema_preview_needs_authenticated_actor_and_does_not_publish(
    tmp_path: Path,
) -> None:
    from odyssey_core.identity_boundary import AuthenticatedActorContext, OdysseyUser
    from odyssey_runtime.composition import RuntimeComposition

    user = registry(tmp_path)
    runtime = RuntimeComposition(
        core_execute=lambda *_args, **_kwargs: None,
        refresh_indexes=lambda: None,
        notes_service=object(),  # type: ignore[arg-type]
        user_schema_registry=user,
    )
    data = {"change": property_change(), "expected_revision": 0}
    with pytest.raises(ValueError, match="authenticated actor"):
        runtime.notes("schema_preview", data)
    actor = AuthenticatedActorContext(OdysseyUser.new().stable_user_id)
    result = runtime.notes("schema_preview", data, actor)
    assert result["affected_type_id"] == "person"
    assert result["revision"] == 0
    assert result["next_revision"] == 1
    assert result["type_preview"]["properties"][0]["id"] == "occupation"
    assert len(result["proposal_hash"]) == 64
    assert "metadata_fields" not in result
    assert user.snapshot()[0] == 0
    assert not (tmp_path / "user-schema/current.json").exists()
    with pytest.raises(ValueError, match="payload"):
        runtime.notes("schema_preview", {**data, "approved": True}, actor)
    with pytest.raises(ValueError, match="payload"):
        runtime.notes("schema_preview", {**data, "expected_revision": True}, actor)
    with pytest.raises(UserSchemaError, match="REVISION_STALE"):
        runtime.notes("schema_preview", {**data, "expected_revision": 5}, actor)
    assert user.snapshot()[0] == 0


def test_runtime_notes_schema_preview_feature_disabled_is_closed(tmp_path: Path) -> None:
    from odyssey_core.identity_boundary import AuthenticatedActorContext, OdysseyUser
    from odyssey_runtime.composition import RuntimeComposition

    runtime = RuntimeComposition(
        core_execute=lambda *_args, **_kwargs: None,
        refresh_indexes=lambda: None,
        notes_service=object(),  # type: ignore[arg-type]
    )
    actor = AuthenticatedActorContext(OdysseyUser.new().stable_user_id)
    with pytest.raises(ValueError, match="disabled"):
        runtime.notes("schema_preview", {"change": type_change(), "expected_revision": 0}, actor)


def test_cross_type_property_filter_value_mismatch_is_rejected_at_preview(tmp_path: Path) -> None:
    """A single global filter ID cannot silently mix string and numeric values."""
    user = registry(tmp_path)
    first = user.preview(property_change("string"), expected_revision=0)
    user.publish(property_change("string"), confirm(first))
    conflicting = type_change()
    conflicting["type"]["properties"][0]["id"] = "occupation"
    with pytest.raises(UserSchemaError, match="query fields"):
        user.preview(conflicting, expected_revision=1)
    assert user.snapshot()[0] == 1


def test_cross_type_same_filter_contract_remains_supported(tmp_path: Path) -> None:
    """Reusing a field ID with the same value contract is not inherently unsafe."""
    user = registry(tmp_path)
    p = user.preview(property_change(), expected_revision=0)
    user.publish(property_change(), confirm(p))
    kind = type_change()
    kind["type"]["properties"][0].update({"id": "occupation", "value_type": "string"})
    q = user.preview(kind, expected_revision=1)
    assert q.effective_schema["schema_version"] == 3
