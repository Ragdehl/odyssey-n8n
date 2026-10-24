"""Draft/confirm compatible user note-schema extensions, without editing Git or Markdown.

This is an internal trusted-composition boundary, NOT an authenticated public API.
The future UI must authenticate the actor and obtain explicit user confirmation
before constructing a SchemaConfirmation. No model output grants that permission.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import unicodedata
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odyssey_apps.schema_extensions import ApplicationSchemaExtension, compose_application_schema
from odyssey_core.context import _filter_definitions
from odyssey_core.filtering import supported_filter_operators
from scripts.validate_note_schema import ID_PATTERN, SchemaValidationError, validate_schema

_FORMAT = "odyssey_user_schema"
_FORMAT_VERSION = 1
_MAX_BYTES = 131072
_MAX_CHANGES = 100
_MAX_TYPES = 50
_MAX_PROPERTIES = 40
_PROPERTY_TYPES = frozenset({"string", "integer", "date", "array[string]"})
_TYPE_KEYS = frozenset({"id", "name", "description", "examples", "properties"})
_PROPERTY_KEYS = frozenset({"id", "value_type", "description"})


class UserSchemaError(ValueError):
    """Reject unsafe, stale or incompatible schema edits and stored state."""


@dataclass(frozen=True, slots=True)
class SchemaPreview:
    """Validated proposal; a digest binds its exact operation and base revision."""

    revision: int
    next_revision: int
    proposal_hash: str
    operation: str
    affected_type_id: str
    effective_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SchemaConfirmation:
    """Trusted host/UI assertion of explicit user approval, never an LLM output."""

    actor_id: str
    request_id: str
    expected_revision: int
    proposal_hash: str


class UserSchemaRegistry:
    """Validated additive user registry with atomic CAS publication and durable history.

    One registry belongs to one trusted vault/user scope; callers MUST bind the
    state directory and the authenticated actor themselves. Runtime composition
    can read :meth:`snapshot` now; enabling hot reload is a separate integration.
    """

    def __init__(
        self,
        state_root: Path,
        base_schema: Mapping[str, Any],
        application_extensions: tuple[ApplicationSchemaExtension, ...] = (),
    ) -> None:
        if not state_root.is_dir() or state_root.is_symlink():
            raise UserSchemaError("Trusted schema state root is unavailable")
        self._root = state_root.resolve() / "user-schema"
        if self._root.is_symlink():
            raise UserSchemaError("Schema registry path is a symlink")
        self._root.mkdir(mode=0o700, exist_ok=True)
        self._root.chmod(0o700)
        self._history = self._root / "history"
        if self._history.is_symlink():
            raise UserSchemaError("Schema history path is a symlink")
        self._history.mkdir(mode=0o700, exist_ok=True)
        self._base = deepcopy(dict(base_schema))
        self._apps = application_extensions
        try:
            validate_schema(compose_application_schema(self._base, self._apps))
        except (SchemaValidationError, ValueError) as error:
            raise UserSchemaError("Base/application schema is invalid") from error

    @contextmanager
    def _locked(self) -> Iterator[None]:
        path = self._root / ".lock"
        if path.is_symlink():
            raise UserSchemaError("Schema lock is a symlink")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @contextmanager
    def _generation_lease(self, *, serving: bool) -> Iterator[None]:
        """Share a generation while serving; publication needs exclusive ownership.

        The lease spans *the entire HTTP server lifetime*, not one request.
        Without that boundary a published v4 user registry could silently
        diverge from the Core/Apps/Notes schema captured by a running process.
        """
        lock = self._root / ".runtime-generation.lock"
        if lock.is_symlink():
            raise UserSchemaError("Schema runtime lease is a symlink")
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                mode = fcntl.LOCK_SH if serving else fcntl.LOCK_EX
                fcntl.flock(fd, mode | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise UserSchemaError(
                    "SCHEMA_PUBLICATION_IN_PROGRESS" if serving else "SCHEMA_RUNTIME_ACTIVE"
                ) from error
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @contextmanager
    def serving_generation(self, expected_revision: int) -> Iterator[None]:
        """Keep an exact boot-composed schema active until the server stops.

        This intentionally opts for a controlled restart, not an unsafe
        dict replacement of captured Core/Writer/App/index dependencies.
        """
        with self._generation_lease(serving=True):
            revision, _ = self.snapshot()
            if revision != expected_revision:
                raise UserSchemaError("SCHEMA_RUNTIME_GENERATION_STALE")
            yield

    @staticmethod
    def _blank() -> dict[str, Any]:
        return {
            "format": _FORMAT,
            "format_version": _FORMAT_VERSION,
            "revision": 0,
            "changes": [],
            "confirmations": [],
        }

    def _read(self) -> dict[str, Any]:
        current = self._root / "current.json"
        if current.is_symlink():
            raise UserSchemaError("Schema registry is a symlink")
        if not current.exists():
            # Losing the published pointer must not silently resurrect revision 0.
            # An orphan receipt may also indicate a crash between the two atomic
            # publishes; require explicit recovery rather than guess its status.
            if any(self._history.iterdir()):
                raise UserSchemaError("Schema publication pointer is missing")
            return self._blank()
        try:
            if current.stat().st_size > _MAX_BYTES:
                raise UserSchemaError("Schema registry exceeds size limit")
            state = json.loads(current.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as error:
            raise UserSchemaError("Schema registry cannot be read") from error
        if (
            not isinstance(state, dict)
            or set(state) != {"format", "format_version", "revision", "changes", "confirmations"}
            or state["format"] != _FORMAT
            or state["format_version"] != _FORMAT_VERSION
        ):
            raise UserSchemaError("Schema registry format is invalid")
        rev = state["revision"]
        if (
            not isinstance(rev, int)
            or isinstance(rev, bool)
            or rev < 1
            or not isinstance(state["changes"], list)
            or len(state["changes"]) != rev
            or rev > _MAX_CHANGES
            or not isinstance(state["confirmations"], list)
            or len(state["confirmations"]) != rev
        ):
            raise UserSchemaError("Schema registry revision is invalid")
        for confirmation in state["confirmations"]:
            if (
                not isinstance(confirmation, dict)
                or set(confirmation) != {"actor_id", "request_id", "proposal_hash"}
                or not all(isinstance(x, str) and x for x in confirmation.values())
            ):
                raise UserSchemaError("Schema confirmation history is invalid")
        if len({x["request_id"] for x in state["confirmations"]}) != rev:
            raise UserSchemaError("Schema confirmation replay is invalid")
        # An orphan future receipt means the publisher crashed between the
        # durable journal and the pointer. Never let another publisher reuse
        # that revision or silently ignore an incomplete commit.
        if len(tuple(self._history.iterdir())) != rev:
            raise UserSchemaError("Schema publication history is incomplete")
        # A committed revision must have an immutable matching on-disk receipt.
        digest = _digest(state)
        receipt = self._history / f"r{rev:06d}-{digest[:16]}.json"
        if receipt.is_symlink() or not receipt.is_file():
            raise UserSchemaError("Schema publication receipt is missing")
        try:
            if receipt.stat().st_size > _MAX_BYTES or receipt.read_bytes() != _encoded(state):
                raise UserSchemaError("Schema publication receipt differs")
        except OSError as error:
            raise UserSchemaError("Schema publication receipt is unreadable") from error
        return state

    def _compose(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        schema = compose_application_schema(self._base, self._apps)
        if len(changes) > _MAX_CHANGES:
            raise UserSchemaError("Too many schema changes")
        for item in changes:
            schema, _ = _apply(schema, item)
        try:
            validate_schema(schema)
            # Retrieval has a single field-ID registry across note types: a
            # collision of value types/constraints cannot be deferred until a
            # user first filters or runs an index rebuild.
            _filter_definitions(schema)
        except (SchemaValidationError, ValueError) as error:
            raise UserSchemaError("Composed schema or query fields are invalid") from error
        return schema

    def snapshot(self) -> tuple[int, dict[str, Any]]:
        """Read a consistent effective schema and user-registry revision."""
        with self._locked():
            state = self._read()
            return state["revision"], self._compose(state["changes"])

    def preview(self, change: Mapping[str, Any], *, expected_revision: int) -> SchemaPreview:
        """Validate untrusted suggestion without writing canonical state."""
        with self._locked():
            state = self._read()
            if state["revision"] != expected_revision:
                raise UserSchemaError("SCHEMA_REVISION_STALE")
            canonical = _roundtrip(change)
            effective = self._compose([*state["changes"], canonical])
            return SchemaPreview(
                expected_revision,
                expected_revision + 1,
                _digest({"revision": expected_revision, "change": canonical}),
                canonical["operation"],
                _affected(canonical),
                effective,
            )

    def publish(self, change: Mapping[str, Any], confirmation: SchemaConfirmation) -> SchemaPreview:
        """Publish one explicitly approved change via durable revision/receipt CAS.

        The host must verify this confirmation against a real authenticated UI
        action. This method does not accept arbitrary 'approved' model flags.
        """
        if not isinstance(confirmation, SchemaConfirmation) or not all(
            isinstance(s, str) and s and len(s) <= 128
            for s in (confirmation.actor_id, confirmation.request_id, confirmation.proposal_hash)
        ):
            raise UserSchemaError("Trusted confirmation required")
        canonical = _roundtrip(change)
        # Serialize other publishers first; contention for the serving lease
        # then means an active runtime, not a rival publication in progress.
        with self._locked(), self._generation_lease(serving=False):
            state = self._read()
            known = {x["request_id"]: x for x in state["confirmations"]}
            if confirmation.request_id in known:
                raise UserSchemaError("SCHEMA_REQUEST_ALREADY_PUBLISHED")
            if state["revision"] != confirmation.expected_revision:
                raise UserSchemaError("SCHEMA_REVISION_STALE")
            digest = _digest({"revision": state["revision"], "change": canonical})
            if digest != confirmation.proposal_hash:
                raise UserSchemaError("SCHEMA_PROPOSAL_CHANGED")
            effective = self._compose([*state["changes"], canonical])
            updated = {
                **state,
                "revision": state["revision"] + 1,
                "changes": [*state["changes"], canonical],
                "confirmations": [
                    *state["confirmations"],
                    {
                        "actor_id": confirmation.actor_id,
                        "request_id": confirmation.request_id,
                        "proposal_hash": digest,
                    },
                ],
            }
            if len(_encoded(updated)) > _MAX_BYTES:
                raise UserSchemaError("Schema registry exceeds size limit")
            receipt = self._history / (f"r{updated['revision']:06d}-{_digest(updated)[:16]}.json")
            _atomic_publish(receipt, updated, immutable=True)
            _atomic_publish(self._root / "current.json", updated, immutable=False)
            return SchemaPreview(
                state["revision"],
                updated["revision"],
                digest,
                canonical["operation"],
                _affected(canonical),
                effective,
            )


def _roundtrip(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise UserSchemaError("Schema change must be an object")
    try:
        payload = _encoded(dict(value))
        if len(payload) > 16384:
            raise UserSchemaError("Schema change is too large")
        return json.loads(payload)
    except (TypeError, ValueError, RecursionError) as error:
        raise UserSchemaError("Schema change cannot be represented as JSON") from error


def _apply(schema: dict[str, Any], change: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if not isinstance(change, dict):
        raise UserSchemaError("Invalid schema change")
    op = change.get("operation")
    types = schema["types"]
    universal_ids = {x["id"] for x in schema["metadata_fields"]}
    if op == "add_type":
        _keys(change, {"operation", "type"})
        raw = change["type"]
        if not isinstance(raw, dict) or set(raw) != _TYPE_KEYS:
            raise UserSchemaError("New type has unsupported fields")
        if not isinstance(raw["id"], str) or ID_PATTERN.fullmatch(raw["id"]) is None:
            raise UserSchemaError("Invalid type identifier")
        _text(raw["name"])
        _text(raw["description"])
        if (
            not isinstance(raw["examples"], list)
            or len(raw["examples"]) > 12
            or any(not isinstance(x, str) or len(x) > 240 for x in raw["examples"])
        ):
            raise UserSchemaError("Invalid type examples")
        if not isinstance(raw["properties"], list) or len(raw["properties"]) > _MAX_PROPERTIES:
            raise UserSchemaError("Too many or invalid type properties")
        for field in raw["properties"]:
            _new_property(field, universal_ids)
        if len(types) >= _MAX_TYPES:
            raise UserSchemaError("Too many types")
        if any(x["id"] == raw["id"] or _label(x["name"]) == _label(raw["name"]) for x in types):
            raise UserSchemaError("Type collides with existing registry")
        types.append(
            {**deepcopy(raw), "properties": [_normal_property(p) for p in raw["properties"]]}
        )
        affected = raw["id"]
    elif op == "add_property":
        _keys(change, {"operation", "type_id", "property"})
        owner = _ordinary_type(types, change["type_id"])
        _new_property(change["property"], universal_ids)
        field = change["property"]
        if any(p["id"] == field["id"] for p in owner["properties"]):
            raise UserSchemaError("Property already exists")
        if len(owner["properties"]) >= _MAX_PROPERTIES:
            raise UserSchemaError("Too many properties")
        owner["properties"].append(_normal_property(field))
        affected = owner["id"]
    elif op == "edit_type_text":
        _keys(change, {"operation", "type_id", "name", "description"})
        owner = _ordinary_type(types, change["type_id"])
        _text(change["name"])
        _text(change["description"])
        if any(
            x["id"] != owner["id"] and _label(x["name"]) == _label(change["name"]) for x in types
        ):
            raise UserSchemaError("Type name already exists")
        owner["name"], owner["description"] = change["name"], change["description"]
        affected = owner["id"]
    elif op == "edit_property_description":
        _keys(change, {"operation", "type_id", "property_id", "description"})
        owner = _ordinary_type(types, change["type_id"])
        _text(change["description"])
        field = next((x for x in owner["properties"] if x["id"] == change["property_id"]), None)
        if field is None:
            raise UserSchemaError("Unknown property")
        field["description"] = change["description"]
        affected = owner["id"]
    else:
        raise UserSchemaError("Unsupported schema operation")
    try:
        validate_schema(schema)
    except (SchemaValidationError, TypeError) as error:
        raise UserSchemaError("Schema change is invalid") from error
    return schema, affected


def _ordinary_type(types: list[dict[str, Any]], type_id: str) -> dict[str, Any]:
    owner = next((x for x in types if x["id"] == type_id), None)
    if owner is None or "managed_by" in owner or owner.get("planner_writable") is False:
        raise UserSchemaError("Type is unavailable for user schema edits")
    return owner


def _new_property(field: Any, universal_ids: set[str]) -> None:
    if not isinstance(field, dict) or set(field) != _PROPERTY_KEYS:
        raise UserSchemaError("New property has unsupported fields")
    if not isinstance(field["id"], str) or ID_PATTERN.fullmatch(field["id"]) is None:
        raise UserSchemaError("Invalid property identifier")
    if field["id"] in universal_ids:
        raise UserSchemaError("Property conflicts with universal metadata")
    _text(field["description"])
    if not isinstance(field["value_type"], str) or field["value_type"] not in _PROPERTY_TYPES:
        raise UserSchemaError("Property type has no supported query operators")
    if not supported_filter_operators({"value_type": field["value_type"]}):
        raise UserSchemaError("Property cannot be queried")


def _normal_property(field: dict[str, Any]) -> dict[str, Any]:
    return {**deepcopy(field), "required": False, "filterable": True}


def _keys(value: dict[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise UserSchemaError("Schema change has unexpected or missing fields")


def _text(value: Any) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise UserSchemaError("Invalid user-facing schema text")


def _label(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()


def _affected(change: dict[str, Any]) -> str:
    return change["type"]["id"] if change["operation"] == "add_type" else change["type_id"]


def _encoded(payload: Any) -> bytes:
    return (
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _digest(payload: Any) -> str:
    return hashlib.sha256(_encoded(payload)).hexdigest()


def _atomic_publish(destination: Path, payload: dict[str, Any], *, immutable: bool) -> None:
    data = _encoded(payload)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=".schema-", delete=False
        ) as handle:
            temp_name = handle.name
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if immutable:
            try:
                os.link(temp_name, destination)
            except FileExistsError:
                if destination.is_symlink() or destination.read_bytes() != data:
                    raise UserSchemaError("Schema history revision conflicts") from None
        else:
            if destination.is_symlink():
                raise UserSchemaError("Schema current path is a symlink")
            os.replace(temp_name, destination)
            temp_name = None
        parent_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
