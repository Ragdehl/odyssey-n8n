#!/usr/bin/env python3
"""Create the synthetic DEV identity fixture without touching production data."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odyssey_core.identity_boundary import OdysseyUser, SelfBindingRepository
from odyssey_core.notes import Note, parse_note, serialize_note, validate_note
from odyssey_core.storage import VaultRepository

ACTOR_FORMAT = "odyssey_dev_actor"
ACTOR_VERSION = 1
USER_FILE = "dev-actor.json"
PERSON_ID = "odyssey-dev-synthetic-person"
PERSON_PATH = Path("people/odyssey-dev-synthetic-person.md")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Atomically publish restrictive DEV identity metadata."""
    encoded = (json.dumps(payload, indent=2) + "\n").encode()
    descriptor, temporary_name = tempfile.mkstemp(prefix=".dev-actor.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _load_or_create_user(path: Path) -> str:
    """Return the persistent synthetic DEV user ID, rejecting malformed state."""
    if path.exists():
        if path.is_symlink():
            raise ValueError("DEV actor state must not be a symlink")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if set(payload) != {"format", "format_version", "stable_user_id"}:
            raise ValueError("DEV actor state has an unsupported format")
        if payload["format"] != ACTOR_FORMAT or payload["format_version"] != ACTOR_VERSION:
            raise ValueError("DEV actor state has an unsupported format")
        user_id = payload["stable_user_id"]
        OdysseyUser(user_id)
        return user_id
    user_id = str(uuid4())
    OdysseyUser(user_id)
    _write_json(
        path,
        {"format": ACTOR_FORMAT, "format_version": ACTOR_VERSION, "stable_user_id": user_id},
    )
    return user_id


def _ensure_person(vault: VaultRepository, schema: dict[str, object]) -> bool:
    """Create or validate the one synthetic canonical person note."""
    if PERSON_PATH.exists() and not (vault.root / PERSON_PATH).is_symlink():
        note = vault.read_text(PERSON_PATH)
        parsed = parse_note(note)
        validate_note(parsed, schema)
        if parsed.metadata.get("id") != PERSON_ID or parsed.metadata.get("type") != "person":
            raise ValueError("DEV synthetic person target is not the expected active person")
        return False
    now = datetime.now(UTC).isoformat()
    metadata = {
        "id": PERSON_ID,
        "name": "Odyssey DEV Synthetic User",
        "type": "person",
        "created_at": now,
        "updated_at": now,
        "created_by": {"human": None, "app": "odyssey-dev-fixture"},
        "updated_by": {"human": None, "app": "odyssey-dev-fixture"},
        "revision": 1,
        "schema_version": 3,
    }
    vault.create_text(
        str(PERSON_PATH),
        serialize_note(
            Note(
                metadata=metadata,
                content="# Synthetic DEV identity\n\n- Works at Synthetic Systems.\n",
            )
        ),
    )
    return True


def _commit_note(vault: VaultRepository) -> None:
    """Record the synthetic fixture in the DEV vault's own Git history."""
    subprocess.run(["git", "-C", str(vault.root), "add", str(PERSON_PATH)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(vault.root),
            "-c",
            "user.name=Odyssey DEV fixture",
            "-c",
            "user.email=odyssey-dev-fixture@localhost",
            "commit",
            "-m",
            "odyssey-dev: add synthetic self fixture",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def main() -> int:
    """Prepare one synthetic DEV actor, person note, and stable binding."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    args = parser.parse_args()
    state_root = args.state_root.resolve()
    vault = VaultRepository(args.vault_root.resolve())
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    actor_path = state_root / USER_FILE
    user_id = _load_or_create_user(actor_path)
    created = _ensure_person(vault, schema)
    if created:
        _commit_note(vault)
    bindings = SelfBindingRepository(state_root, vault, schema)
    bindings.bind(user_id, PERSON_ID)
    print(f"stable_user_id={user_id}")
    print(f"person_note_id={PERSON_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
