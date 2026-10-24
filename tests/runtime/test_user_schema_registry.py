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
    with pytest.raises(UserSchemaError, match="receipt|history is incomplete"):
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
    with pytest.raises(UserSchemaError, match="existing type metadata|query fields"):
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


def test_runtime_lease_prevents_publishing_while_an_old_generation_serves(
    tmp_path: Path,
) -> None:
    """Do not allow partial v4 schema publication into an active v3 composition."""
    first, second = registry(tmp_path), registry(tmp_path)
    proposal = first.preview(type_change(), expected_revision=0)
    with first.serving_generation(0):
        assert second.snapshot()[0] == 0
        with pytest.raises(UserSchemaError, match="SCHEMA_RUNTIME_ACTIVE"):
            second.publish(type_change(), confirm(proposal))
        assert first.snapshot()[0] == 0
    second.publish(type_change(), confirm(proposal))
    assert first.snapshot()[0] == 1
    with pytest.raises(UserSchemaError, match="SCHEMA_RUNTIME_GENERATION_STALE"):
        first.serving_generation(0).__enter__()
    with first.serving_generation(1):
        assert "book" in ordinary_type_ids(first.snapshot()[1])


def test_orphaned_next_revision_receipt_is_not_silently_ignored(tmp_path: Path) -> None:
    user = registry(tmp_path)
    proposal = user.preview(type_change(), expected_revision=0)
    user.publish(type_change(), confirm(proposal))
    # Mimic the crash window after the immutable receipt, before pointer swap.
    (tmp_path / "user-schema/history/r000002-orphan.json").write_text("{}", encoding="utf-8")
    with pytest.raises(UserSchemaError, match="history is incomplete"):
        registry(tmp_path).snapshot()
    with pytest.raises(UserSchemaError, match="history is incomplete"):
        registry(tmp_path).publish(
            property_change(), SchemaConfirmation("synthetic-actor", "another-request", 1, "0" * 64)
        )


def test_running_lease_rejects_symlink_swap(tmp_path: Path) -> None:
    user = registry(tmp_path)
    lock = tmp_path / "user-schema/.runtime-generation.lock"
    lock.symlink_to(tmp_path / "target")
    with pytest.raises(UserSchemaError, match="lease is a symlink"):
        with user.serving_generation(0):
            pass


def test_runtime_lease_blocks_publication_from_separate_process(tmp_path: Path) -> None:
    """Exercise OS process-level flock, not merely competing Python threads."""
    import subprocess
    import sys

    user = registry(tmp_path)
    script = """
import json, sys
from pathlib import Path
from odyssey_apps.events.schema import EVENT_SCHEMA_EXTENSION
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_runtime.user_schema_registry import UserSchemaRegistry, SchemaConfirmation, UserSchemaError
base = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
user = UserSchemaRegistry(Path(sys.argv[1]), base, (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION))
change = {"operation": "add_type", "type": {
 "id": "book", "name": "Book", "description": "Book note", "examples": [], "properties": []}}
proposal = user.preview(change, expected_revision=0)
try:
 user.publish(change, SchemaConfirmation("synthetic-actor", "cross-process", 0, proposal.proposal_hash))
except UserSchemaError as error:
 print(str(error))
else:
 print("UNEXPECTED_PUBLICATION")
"""
    with user.serving_generation(0):
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path), str(ROOT / "config/note-schema.json")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        assert result.stdout.strip() == "SCHEMA_RUNTIME_ACTIVE"
        assert user.snapshot()[0] == 0


def test_nonfilterable_calendar_field_id_cannot_gain_incompatible_filter_type(
    tmp_path: Path,
) -> None:
    """Calendar Day `date` is not filterable but still contributes physical index rows."""
    user = registry(tmp_path)
    person_date = {
        "operation": "add_property",
        "type_id": "person",
        "property": {"id": "date", "value_type": "integer", "description": "An invalid date field"},
    }
    with pytest.raises(UserSchemaError, match="conflicts with existing type metadata"):
        user.preview(person_date, expected_revision=0)
    new_type = type_change("My Year", "year_book")
    new_type["type"]["properties"] = [
        {"id": "date", "value_type": "string", "description": "Incompatible date text"}
    ]
    with pytest.raises(UserSchemaError, match="conflicts with existing type metadata"):
        user.preview(new_type, expected_revision=0)
    assert user.snapshot()[0] == 0


def test_matching_existing_property_type_can_be_reused(tmp_path: Path) -> None:
    user = registry(tmp_path)
    change = {
        "operation": "add_property",
        "type_id": "person",
        "property": {"id": "date", "value_type": "date", "description": "Date of a person event."},
    }
    assert user.preview(change, expected_revision=0).effective_schema["schema_version"] == 3


def _set_dev_schema_test_paths(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setenv("ODYSSEY_USER_SCHEMA_ENABLED", "1")
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    for key, path in (
        ("ODYSSEY_STATE_ROOT", root),
        ("ODYSSEY_VAULT_ROOT", root.parent / "vault"),
        ("ODYSSEY_RUNTIME_ROOT", root.parent / "runtime"),
        ("ODYSSEY_PENDING_ROOT", root / "pending"),
        ("ODYSSEY_EMBEDDING_CACHE", root.parent / "embedding-cache"),
    ):
        monkeypatch.setenv(key, str(path))


def test_full_runtime_factory_acquires_exclusive_lease_before_any_index_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stale bootstrap must not rebuild source-shared indexes during publication."""
    from odyssey_runtime import composition

    user = registry(tmp_path)
    proposal = user.preview(type_change(), expected_revision=0)
    confirmation = confirm(proposal)
    _set_dev_schema_test_paths(monkeypatch, tmp_path)
    inside = []

    def fake_build():
        inside.append("building-indexes")
        with pytest.raises(UserSchemaError, match="SCHEMA_RUNTIME_ACTIVE"):
            user.publish(type_change(), confirmation)
        with pytest.raises(UserSchemaError, match="SCHEMA_PUBLICATION_IN_PROGRESS"):
            with user.serving_generation(0):
                pass
        return "synthetic-assembled-runtime"

    monkeypatch.setattr(composition, "_build_runtime_from_environment_unlocked", fake_build)
    assert composition.build_runtime_from_environment() == "synthetic-assembled-runtime"
    assert inside == ["building-indexes"]
    assert user.snapshot()[0] == 0
    user.publish(type_change(), confirmation)
    assert user.snapshot()[0] == 1


def test_failed_bootstrap_releases_generation_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from odyssey_runtime import composition

    _set_dev_schema_test_paths(monkeypatch, tmp_path)

    def fail_boot():
        raise RuntimeError("synthetic index rebuild failure")

    monkeypatch.setattr(composition, "_build_runtime_from_environment_unlocked", fail_boot)
    with pytest.raises(RuntimeError, match="synthetic index rebuild failure"):
        composition.build_runtime_from_environment()
    # A crashed bootstrap cannot hold the activation lock indefinitely.
    user = registry(tmp_path)
    proposal = user.preview(type_change(), expected_revision=0)
    user.publish(type_change(), confirm(proposal))
    assert user.snapshot()[0] == 1


@pytest.mark.parametrize("light_source", ["0", "1"])
def test_dev_bootstrap_denies_protected_paths_before_any_filesystem_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, light_source: str
) -> None:
    from odyssey_runtime import composition

    protected = tmp_path / "protected-storage"
    unsafe_root = protected / "state"
    _set_dev_schema_test_paths(monkeypatch, tmp_path / "safe-state")
    monkeypatch.setenv("ODYSSEY_STATE_ROOT", str(unsafe_root))
    monkeypatch.setenv("ODYSSEY_LIGHT_SOURCE_V1", light_source)
    monkeypatch.setattr(composition, "_USER_SCHEMA_PROTECTED_ROOT", protected)
    monkeypatch.setattr(composition, "_build_runtime_from_environment_unlocked", lambda: 1)
    with pytest.raises(ValueError, match="production storage"):
        composition.build_runtime_from_environment()
    assert not protected.exists()  # no mkdir, chmod, or lock was attempted


def test_first_schema_bootstrap_creates_missing_safe_dev_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from odyssey_runtime import composition

    fresh = tmp_path / "new-dev" / "state"
    _set_dev_schema_test_paths(monkeypatch, fresh)
    monkeypatch.setattr(composition, "_build_runtime_from_environment_unlocked", lambda: "OK")
    assert not fresh.exists()
    assert composition.build_runtime_from_environment() == "OK"
    assert fresh.is_dir()
    assert (fresh / "user-schema/.runtime-generation.lock").is_file()


def test_schema_bootstrap_rejects_symlink_root_without_following_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from odyssey_runtime import composition

    target = tmp_path / "trusted"
    target.mkdir()
    alias = tmp_path / "symlink-state"
    alias.symlink_to(target, target_is_directory=True)
    _set_dev_schema_test_paths(monkeypatch, alias)
    monkeypatch.setattr(composition, "_build_runtime_from_environment_unlocked", lambda: "BAD")
    with pytest.raises(ValueError, match="symlink"):
        composition.build_runtime_from_environment()
    assert not (target / "user-schema").exists()


def test_confirm_queues_without_changing_active_schema_and_boot_activates_once(
    tmp_path: Path,
) -> None:
    user = registry(tmp_path)
    change = property_change()
    proposed = user.preview(change, expected_revision=0)
    confirmed = confirm(proposed, "explicit-click-id")
    receipt = user.request_activation(change, confirmed)
    assert receipt == {
        "status": "queued",
        "request_id": "explicit-click-id",
        "revision": 0,
        "next_revision": 1,
    }
    assert user.snapshot()[0] == 0
    assert not (tmp_path / "user-schema/current.json").exists()
    assert user.activation_status("synthetic-actor", "explicit-click-id") == receipt
    assert user.request_activation(change, confirmed) == receipt
    with pytest.raises(UserSchemaError, match="ALREADY_PENDING"):
        user.request_activation(
            type_change(),
            SchemaConfirmation(
                "synthetic-actor",
                "second",
                0,
                user.preview(type_change(), expected_revision=0).proposal_hash,
            ),
        )
    with pytest.raises(UserSchemaError, match="not found"):
        user.activation_status("another-actor", "explicit-click-id")
    assert registry(tmp_path).activate_pending_at_boot() is True
    assert registry(tmp_path).activate_pending_at_boot() is False
    rev, composed = registry(tmp_path).snapshot()
    assert rev == 1
    validate_note(_person_note(), composed)
    assert user.request_activation(change, confirmed)["status"] == "active"
    assert user.activation_status("synthetic-actor", "explicit-click-id") == {
        "status": "active",
        "request_id": "explicit-click-id",
        "revision": 1,
    }
    assert not (tmp_path / "user-schema/pending-activation.json").exists()


def test_activation_crash_after_receipt_and_before_removal_is_idempotent(tmp_path: Path) -> None:
    user = registry(tmp_path)
    change = type_change()
    proposed = user.preview(change, expected_revision=0)
    confirmed = confirm(proposed)
    user.request_activation(change, confirmed)
    user.activate_pending_at_boot()
    # Restore the already-acknowledged, perfectly matching pending record to
    # simulate process crash between publication and pending cleanup.
    from odyssey_runtime.user_schema_registry import _atomic_publish

    _atomic_publish(
        tmp_path / "user-schema/pending-activation.json",
        {
            "change": change,
            "actor_id": confirmed.actor_id,
            "request_id": confirmed.request_id,
            "expected_revision": confirmed.expected_revision,
            "proposal_hash": confirmed.proposal_hash,
        },
        immutable=False,
    )
    assert registry(tmp_path).activate_pending_at_boot() is False
    assert user.snapshot()[0] == 1
    assert len(list((tmp_path / "user-schema/history").glob("*.json"))) == 1


def test_actor_bound_schema_confirm_and_status_are_feature_gated(tmp_path: Path) -> None:
    from odyssey_core.identity_boundary import AuthenticatedActorContext, OdysseyUser
    from odyssey_runtime.composition import RuntimeComposition

    user = registry(tmp_path)
    proposal = user.preview(property_change(), expected_revision=0)
    actor = AuthenticatedActorContext(OdysseyUser.new().stable_user_id)
    payload = {
        "change": property_change(),
        "expected_revision": 0,
        "request_id": "actor-confirmation",
        "proposal_hash": proposal.proposal_hash,
    }
    runtime = RuntimeComposition(
        core_execute=lambda *_a, **_kw: None,
        refresh_indexes=lambda: None,
        notes_service=object(),  # type: ignore[arg-type]
        user_schema_registry=user,
        schema_activation_enabled=True,
        user_schema_revision=0,
    )
    with pytest.raises(ValueError, match="unavailable"):
        runtime.notes("schema_confirm", payload)
    with pytest.raises(ValueError, match="payload"):
        runtime.notes("schema_confirm", {**payload, "actor_id": "forged"}, actor)
    result = runtime.notes("schema_confirm", payload, actor)
    assert result["status"] == "queued"
    assert (
        runtime.notes("schema_status", {"request_id": "actor-confirmation"}, actor)["status"]
        == "queued"
    )
    assert runtime.notes("schema_status", {}, actor) == {"revision": 0, "status": "ready"}
    other = AuthenticatedActorContext(OdysseyUser.new().stable_user_id)
    with pytest.raises(UserSchemaError, match="not found"):
        runtime.notes("schema_status", {"request_id": "actor-confirmation"}, other)
    runtime.schema_activation_enabled = False
    with pytest.raises(ValueError, match="unavailable"):
        runtime.notes("schema_confirm", payload, actor)
    assert user.snapshot()[0] == 0


def test_schema_approval_rejects_changed_draft_stale_revision_and_duplicate_actor(
    tmp_path: Path,
) -> None:
    user = registry(tmp_path)
    change = type_change()
    draft = user.preview(change, expected_revision=0)
    ack = confirm(draft, "click-one")
    altered = type_change("Different Book", "book")
    with pytest.raises(UserSchemaError, match="PROPOSAL_CHANGED"):
        user.request_activation(altered, ack)
    with pytest.raises(UserSchemaError, match="REVISION_STALE"):
        user.request_activation(
            change, SchemaConfirmation("synthetic-actor", "click-one", 3, draft.proposal_hash)
        )
    assert not (tmp_path / "user-schema/pending-activation.json").exists()
    user.request_activation(change, ack)
    with pytest.raises(UserSchemaError, match="ALREADY_PENDING"):
        user.request_activation(
            change, SchemaConfirmation("other-actor", "click-one", 0, draft.proposal_hash)
        )
    assert user.activation_status("synthetic-actor", "click-one")["status"] == "queued"
    assert user.snapshot()[0] == 0


def test_tampered_pending_envelope_fails_closed_before_boot_writes(tmp_path: Path) -> None:
    user = registry(tmp_path)
    change = type_change()
    draft = user.preview(change, expected_revision=0)
    user.request_activation(change, confirm(draft))
    pending = tmp_path / "user-schema/pending-activation.json"
    forged = json.loads(pending.read_text(encoding="utf-8"))
    forged["change"]["type"]["name"] = "Forged title"
    pending.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(UserSchemaError, match="proposal changed"):
        user.activate_pending_at_boot()
    assert user.snapshot()[0] == 0
    assert len(list((tmp_path / "user-schema/history").glob("*.json"))) == 0


def test_stale_pending_cannot_override_unrelated_published_revision(tmp_path: Path) -> None:
    user = registry(tmp_path)
    to_stage = type_change()
    pending = user.preview(to_stage, expected_revision=0)
    user.request_activation(to_stage, confirm(pending))
    other = property_change()
    preview = user.preview(other, expected_revision=0)
    with pytest.raises(UserSchemaError, match="ALREADY_PENDING"):
        user.publish(other, confirm(preview, "independent-publication"))
    assert user.snapshot()[0] == 0
    assert user.activate_pending_at_boot() is True
    assert user.snapshot()[0] == 1
    assert "book" in ordinary_type_ids(user.snapshot()[1])


def test_schema_confirmation_disabled_by_default_on_composed_runtime(tmp_path: Path) -> None:
    from odyssey_core.identity_boundary import AuthenticatedActorContext, OdysseyUser
    from odyssey_runtime.composition import RuntimeComposition

    runtime = RuntimeComposition(
        core_execute=lambda *_a, **_kw: None,
        refresh_indexes=lambda: None,
        notes_service=object(),  # type: ignore[arg-type]
        user_schema_registry=registry(tmp_path),
        user_schema_revision=0,
    )
    actor = AuthenticatedActorContext(OdysseyUser.new().stable_user_id)
    with pytest.raises(ValueError, match="unavailable"):
        runtime.notes("schema_status", {}, actor)
    with pytest.raises(ValueError, match="unavailable"):
        runtime.notes("schema_confirm", {}, actor)


def test_confirm_replay_reports_original_revision_after_later_schema_changes(
    tmp_path: Path,
) -> None:
    user = registry(tmp_path)
    a = property_change()
    first = user.preview(a, expected_revision=0)
    user.request_activation(a, confirm(first, "first-ack"))
    user.activate_pending_at_boot()
    b = type_change()
    second = user.preview(b, expected_revision=1)
    user.request_activation(b, confirm(second, "second-ack"))
    user.activate_pending_at_boot()
    assert user.snapshot()[0] == 2
    assert user.request_activation(a, confirm(first, "first-ack")) == {
        "status": "active",
        "request_id": "first-ack",
        "revision": 1,
    }
    assert user.activation_status("synthetic-actor", "second-ack") == {
        "status": "active",
        "request_id": "second-ack",
        "revision": 2,
    }


def test_confirm_prechecks_exact_published_size_before_queuing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid but oversized next revision must never strand the managed restart."""
    import odyssey_runtime.user_schema_registry as schema_mod

    user = registry(tmp_path)
    proposed = user.preview(type_change(), expected_revision=0)
    monkeypatch.setattr(schema_mod, "_MAX_BYTES", 160)
    with pytest.raises(UserSchemaError, match="size limit"):
        user.request_activation(type_change(), confirm(proposed))
    assert user.snapshot()[0] == 0
    assert not (tmp_path / "user-schema/pending-activation.json").exists()
    assert not list((tmp_path / "user-schema/history").glob("*.json"))


def test_completed_ack_replay_requires_original_change_and_base_revision(
    tmp_path: Path,
) -> None:
    user = registry(tmp_path)
    initial = type_change()
    proposed = user.preview(initial, expected_revision=0)
    confirmation = confirm(proposed, "same-click")
    user.request_activation(initial, confirmation)
    user.activate_pending_at_boot()
    with pytest.raises(UserSchemaError, match="ALREADY_PUBLISHED"):
        user.request_activation(type_change("Other Title", "other_book"), confirmation)
    with pytest.raises(UserSchemaError, match="ALREADY_PUBLISHED"):
        user.request_activation(
            initial,
            SchemaConfirmation(
                confirmation.actor_id,
                confirmation.request_id,
                1,
                confirmation.proposal_hash,
            ),
        )
    assert user.request_activation(initial, confirmation) == {
        "status": "active",
        "request_id": "same-click",
        "revision": 1,
    }
    assert user.snapshot()[0] == 1
