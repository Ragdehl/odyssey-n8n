"""Trusted authenticated-identity normalization and durable principal mapping."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from .storage import VaultRepository

_SAFE_USER_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_FORMAT = "odyssey_identity_mapping"
_FORMAT_VERSION = 1


class IdentityBoundaryError(ValueError):
    """Indicate invalid or unsafe authenticated identity state."""


@dataclass(frozen=True, slots=True)
class ExternalPrincipal:
    """Identify one validated external authentication principal without exposing its value."""

    issuer: str
    subject: str

    def __post_init__(self) -> None:
        """Reject empty or control-bearing provider identity components."""
        for name, value in (("issuer", self.issuer), ("subject", self.subject)):
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise IdentityBoundaryError(f"external principal {name} is invalid")
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise IdentityBoundaryError(f"external principal {name} is invalid")


@dataclass(frozen=True, slots=True)
class OdysseyUser:
    """Represent an Odyssey-owned opaque user identity independent of its provider principal."""

    stable_user_id: str

    def __post_init__(self) -> None:
        """Require a generated canonical UUID rather than a provider or display identifier."""
        if (
            not isinstance(self.stable_user_id, str)
            or _SAFE_USER_ID.fullmatch(self.stable_user_id) is None
        ):
            raise IdentityBoundaryError("Odyssey user ID must be a canonical UUIDv4")

    @classmethod
    def new(cls) -> OdysseyUser:
        """Allocate one provider-independent Odyssey user ID."""
        return cls(str(uuid4()))


@dataclass(frozen=True, slots=True)
class AuthenticatedActorContext:
    """Carry only normalized trusted actor context across the runtime boundary."""

    stable_user_id: str

    def __post_init__(self) -> None:
        """Validate the Odyssey-owned identifier before it can reach Core."""
        OdysseyUser(self.stable_user_id)

    @classmethod
    def from_payload(cls, payload: object) -> AuthenticatedActorContext:
        """Parse the exact public actor shape without accepting headers or provider fields."""
        if not isinstance(payload, dict) or set(payload) != {"stable_user_id"}:
            raise IdentityBoundaryError("authenticated actor context has unsupported fields")
        return cls(payload["stable_user_id"])


class IdentityMappingRepository:
    """Atomically map validated external principals to Odyssey-owned user IDs."""

    def __init__(self, state_root: Path | str, filename: str = "identity-mappings.json") -> None:
        """Configure one existing durable state directory and mapping filename.

        Args:
            state_root: Existing non-knowledge state directory owned by this environment.
            filename: Relative JSON filename reserved for identity mappings.

        Raises:
            IdentityBoundaryError: If the root or filename is unsafe.
        """
        configured_root = Path(state_root)
        if configured_root.is_symlink():
            raise IdentityBoundaryError("identity state root must not be a symlink")
        root = configured_root.resolve()
        if not root.is_dir():
            raise IdentityBoundaryError("identity state root is unavailable")
        path = Path(filename)
        if path.is_absolute() or path.parent != Path(".") or path.name != filename:
            raise IdentityBoundaryError("identity mapping filename is unsafe")
        self._root = root
        self._path = root / filename

    def resolve_or_create(self, principal: ExternalPrincipal) -> OdysseyUser:
        """Return the existing user for a principal or publish one new mapping atomically.

        Raises:
            IdentityBoundaryError: If state is malformed, duplicated, or cannot be published.
        """
        if not isinstance(principal, ExternalPrincipal):
            raise IdentityBoundaryError("identity mapping requires an external principal")
        payload = self._read()
        matches = [item for item in payload["principals"] if _principal_matches(item, principal)]
        if len(matches) > 1:
            raise IdentityBoundaryError("external principal mapping is ambiguous")
        if matches:
            return OdysseyUser(matches[0]["odyssey_user_id"])
        user = OdysseyUser.new()
        payload["principals"].append(
            {
                "issuer": principal.issuer,
                "subject": principal.subject,
                "odyssey_user_id": user.stable_user_id,
            }
        )
        self._write(payload)
        return user

    def _read(self) -> dict[str, object]:
        """Read and strictly validate the versioned mapping state."""
        if not self._path.exists():
            return {"format": _FORMAT, "format_version": _FORMAT_VERSION, "principals": []}
        if self._path.is_symlink():
            raise IdentityBoundaryError("identity mapping must not be a symlink")
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IdentityBoundaryError("identity mapping could not be read") from error
        if (
            not isinstance(payload, dict)
            or set(payload) != {"format", "format_version", "principals"}
            or payload["format"] != _FORMAT
            or payload["format_version"] != _FORMAT_VERSION
            or not isinstance(payload["principals"], list)
        ):
            raise IdentityBoundaryError("identity mapping has an unsupported format")
        seen: set[tuple[str, str]] = set()
        for item in payload["principals"]:
            if not isinstance(item, dict) or set(item) != {"issuer", "subject", "odyssey_user_id"}:
                raise IdentityBoundaryError("identity mapping contains malformed state")
            principal = ExternalPrincipal(item["issuer"], item["subject"])
            OdysseyUser(item["odyssey_user_id"])
            key = (principal.issuer, principal.subject)
            if key in seen:
                raise IdentityBoundaryError("identity mapping contains duplicate principals")
            seen.add(key)
        return payload

    def _write(self, payload: dict[str, object]) -> None:
        """Publish complete mapping bytes with restrictive permissions in the same directory."""
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        temporary: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=".identity-bindings.", suffix=".tmp", dir=self._root
            )
            temporary = Path(name)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
            os.chmod(self._path, 0o600)
        except OSError as error:
            raise IdentityBoundaryError("identity mapping could not be written") from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


class SelfBindingError(IdentityBoundaryError):
    """Indicate invalid, missing, or ambiguous self-person binding state."""


class SelfBindingConflictError(SelfBindingError):
    """Indicate that a user is already bound to another person note."""


@dataclass(frozen=True, slots=True)
class SelfBinding:
    """Represent one Odyssey user to canonical person-note binding."""

    odyssey_user_id: str
    person_note_id: str


class SelfBindingRepository:
    """Persist guarded Odyssey-user to canonical-person bindings outside the knowledge vault."""

    def __init__(
        self,
        state_root: Path | str,
        vault: VaultRepository,
        schema: dict[str, object],
        filename: str = "self-bindings.json",
    ) -> None:
        """Configure durable self-binding state and its authoritative canonical-note lookup.

        Args:
            state_root: Existing non-knowledge state directory owned by this environment.
            vault: Canonical Markdown repository used to validate person-note targets.
            schema: Canonical note schema used when inspecting target notes.
            filename: Relative JSON filename reserved for self bindings.

        Raises:
            SelfBindingError: If the roots or filename are unsafe.
        """
        configured_root = Path(state_root)
        if configured_root.is_symlink():
            raise SelfBindingError("self-binding state root must not be a symlink")
        root = configured_root.resolve()
        if (
            not root.is_dir()
            or not isinstance(vault, VaultRepository)
            or not isinstance(schema, dict)
        ):
            raise SelfBindingError("self-binding configuration is unavailable")
        path = Path(filename)
        if path.is_absolute() or path.parent != Path(".") or path.name != filename:
            raise SelfBindingError("self-binding filename is unsafe")
        self._root = root
        self._path = root / filename
        self._vault = vault
        self._schema = schema

    def bind(self, odyssey_user_id: str, person_note_id: str) -> SelfBinding:
        """Create an idempotent initial binding after validating the active person target.

        Raises:
            SelfBindingConflictError: If the user is already bound to another note.
            SelfBindingError: If either ID or durable state is invalid.
        """
        user_id = _validate_user_id(odyssey_user_id)
        note_id = self._validate_person_target(person_note_id)
        payload = self._read()
        current = _find_binding(payload, user_id)
        if current is not None:
            if current["person_note_id"] != note_id:
                raise SelfBindingConflictError("user already has a different self binding")
            return SelfBinding(user_id, note_id)
        payload["bindings"].append({"odyssey_user_id": user_id, "person_note_id": note_id})
        self._write(payload)
        return SelfBinding(user_id, note_id)

    def rebind(
        self, odyssey_user_id: str, expected_person_note_id: str, person_note_id: str
    ) -> SelfBinding:
        """Replace a binding only when the caller supplies its exact current target.

        Raises:
            SelfBindingError: If the current binding is absent or the expected target is wrong.
        """
        user_id = _validate_user_id(odyssey_user_id)
        expected_id = _validate_note_id(expected_person_note_id)
        note_id = self._validate_person_target(person_note_id)
        payload = self._read()
        current = _find_binding(payload, user_id)
        if current is None or current["person_note_id"] != expected_id:
            raise SelfBindingError("self binding compare-and-swap precondition failed")
        current["person_note_id"] = note_id
        self._write(payload)
        return SelfBinding(user_id, note_id)

    def resolve(self, odyssey_user_id: str) -> SelfBinding:
        """Return one binding after revalidating that its target remains an active person note."""
        user_id = _validate_user_id(odyssey_user_id)
        current = _find_binding(self._read(), user_id)
        if current is None:
            raise SelfBindingError("self binding is not configured")
        note_id = self._validate_person_target(current["person_note_id"])
        return SelfBinding(user_id, note_id)

    def _validate_person_target(self, person_note_id: str) -> str:
        """Require exactly one active schema-valid canonical person note for a stable ID."""
        note_id = _validate_note_id(person_note_id)
        matches = []
        for path in self._vault.list_markdown_paths():
            try:
                note = parse_note(self._vault.read_text(path))
                validate_note(note, self._schema)
            except (NoteFormatError, NoteValidationError):
                continue
            if note.metadata.get("id") == note_id:
                matches.append(note)
        if len(matches) != 1:
            raise SelfBindingError("self binding target is unavailable or ambiguous")
        note = matches[0]
        if note.metadata.get("deleted", False) or note.metadata.get("type") != "person":
            raise SelfBindingError("self binding target is not an active person note")
        return note_id

    def _read(self) -> dict[str, object]:
        """Read and strictly validate self-binding state without repairing it."""
        if not self._path.exists():
            return {"format": "odyssey_self_bindings", "format_version": 1, "bindings": []}
        if self._path.is_symlink():
            raise SelfBindingError("self-binding state must not be a symlink")
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SelfBindingError("self-binding state could not be read") from error
        if (
            not isinstance(payload, dict)
            or set(payload) != {"format", "format_version", "bindings"}
            or payload["format"] != "odyssey_self_bindings"
            or payload["format_version"] != 1
            or not isinstance(payload["bindings"], list)
        ):
            raise SelfBindingError("self-binding state has an unsupported format")
        seen: set[str] = set()
        for item in payload["bindings"]:
            if not isinstance(item, dict) or set(item) != {"odyssey_user_id", "person_note_id"}:
                raise SelfBindingError("self-binding state contains malformed data")
            user_id = _validate_user_id(item["odyssey_user_id"])
            _validate_note_id(item["person_note_id"])
            if user_id in seen:
                raise SelfBindingError("self-binding state contains duplicate users")
            seen.add(user_id)
        return payload

    def _write(self, payload: dict[str, object]) -> None:
        """Publish complete self-binding JSON with restrictive permissions atomically."""
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        temporary: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=".self-bindings.", suffix=".tmp", dir=self._root
            )
            temporary = Path(name)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
            os.chmod(self._path, 0o600)
        except OSError as error:
            raise SelfBindingError("self-binding state could not be written") from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def _validate_user_id(value: object) -> str:
    """Validate and return one Odyssey-owned UUIDv4 string."""
    if not isinstance(value, str) or _SAFE_USER_ID.fullmatch(value) is None:
        raise SelfBindingError("Odyssey user ID is invalid")
    return value


def _validate_note_id(value: object) -> str:
    """Validate a stable note ID without treating its display name or filename as identity."""
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise SelfBindingError("person note ID is invalid")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SelfBindingError("person note ID is invalid")
    return value


def _find_binding(payload: dict[str, object], user_id: str) -> dict[str, str] | None:
    """Find one validated user binding in already-validated state."""
    for item in payload["bindings"]:
        if item["odyssey_user_id"] == user_id:
            return item
    return None


def _principal_matches(item: object, principal: ExternalPrincipal) -> bool:
    """Return whether one validated state record identifies the supplied principal."""
    return (
        isinstance(item, dict)
        and item.get("issuer") == principal.issuer
        and item.get("subject") == principal.subject
    )
