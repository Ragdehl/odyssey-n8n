"""Reset the explicitly isolated DEV data root to P1's disposable note fixture.

This helper intentionally accepts only the fixed Phase 21 DEV roots.  It is benchmark setup,
not an Odyssey request path: callers must restart the DEV runtime afterwards so its rebuildable
indexes reflect the new canonical Markdown before timing a case.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from odyssey_core.notes import Note, serialize_note, validate_note

DEV_ROOT = Path("/data/odyssey-dev")
DEV_VAULT = DEV_ROOT / "vault"
DEV_STATE = DEV_ROOT / "state"
FIXTURE_VERSION = 1
_FIXTURE_APP = "odyssey-p1-disposable-fixture"
_STAMP = "2026-01-01T00:00:00+00:00"


class FixtureError(RuntimeError):
    """Raised when a fixture reset cannot prove that it is confined to isolated DEV data."""


def _require_exact_dev_roots(vault_root: Path, state_root: Path) -> None:
    """Reject every root except the fixed Phase 21 DEV vault and state directories."""
    if vault_root.resolve() != DEV_VAULT or state_root.resolve() != DEV_STATE:
        raise FixtureError("P1 fixture reset is restricted to the fixed isolated DEV roots")
    if not (DEV_ROOT.is_dir() and (DEV_VAULT / ".git").is_dir() and DEV_STATE.is_dir()):
        raise FixtureError("isolated DEV vault/state roots are not initialized")


def _note(note_id: str, name: str, facts: tuple[str, ...]) -> Note:
    """Build one schema-valid synthetic person note without personal content."""
    return Note(
        metadata={
            "id": note_id,
            "name": name,
            "type": "person",
            "created_at": _STAMP,
            "updated_at": _STAMP,
            "created_by": {"human": None, "app": _FIXTURE_APP},
            "updated_by": {"human": None, "app": _FIXTURE_APP},
            "revision": 1,
            "schema_version": 3,
        },
        content=f"# {name}\n\n" + "".join(f"- {fact}\n" for fact in facts),
    )


def fixture_notes(extra_facts: dict[str, list[str]] | None = None) -> dict[str, Note]:
    """Return the frozen P1 note set plus one stable synthetic self-binding target.

    Args:
        extra_facts: Case-specific disposable facts declared by ``cases.json``.

    Returns:
        Mapping from the fixed P1 person key to a fresh canonical note.

    Raises:
        FixtureError: If extra facts do not have the bounded frozen registry shape.
    """
    allowed = {"Marta", "Elena", "Pablo"}
    supplied = extra_facts or {}
    if not isinstance(supplied, dict) or set(supplied) - allowed:
        raise FixtureError("P1 fixture extra facts are invalid")
    additions: dict[str, tuple[str, ...]] = {}
    for person, facts in supplied.items():
        if (
            not isinstance(facts, list)
            or not facts
            or any(
                not isinstance(fact, str) or not fact.strip() or len(fact) > 512 for fact in facts
            )
        ):
            raise FixtureError("P1 fixture extra facts are invalid")
        additions[person] = tuple(facts)
    facts = {
        "Marta": ("Marta trabaja en Thales.", "Marta vive en Lyon."),
        "Elena": ("Elena vive en Girona.",),
        "Pablo": ("Pablo vive en Barcelona.",),
    }
    result = {
        person: _note(f"p1-{person.lower()}", person, values + additions.get(person, ()))
        for person, values in facts.items()
    }
    result["self"] = _note(
        "odyssey-dev-synthetic-person",
        "Odyssey DEV Synthetic User",
        ("Works at Synthetic Systems.",),
    )
    return result


def _clear_directory_children(root: Path, *, preserved: set[str] = frozenset()) -> None:
    """Remove only direct children beneath an already validated disposable root."""
    for child in root.iterdir():
        if child.name in preserved:
            continue
        if child.is_symlink():
            raise FixtureError(f"fixture root contains a symlink: {child.name}")
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _commit_fixture(vault_root: Path) -> str:
    """Commit the reset Markdown state so subsequent product writes have a clean Git base."""
    subprocess.run(["git", "-C", str(vault_root), "add", "-A"], check=True)
    changed = subprocess.run(
        ["git", "-C", str(vault_root), "diff", "--cached", "--quiet"], check=False
    ).returncode
    if changed not in {0, 1}:
        raise FixtureError("unable to inspect disposable DEV fixture Git state")
    if changed:
        subprocess.run(
            [
                "git",
                "-C",
                str(vault_root),
                "-c",
                "user.name=Odyssey P1 disposable fixture",
                "-c",
                "user.email=odyssey-p1-fixture@localhost",
                "commit",
                "-m",
                "odyssey-p1: reset disposable baseline fixture",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    return subprocess.check_output(
        ["git", "-C", str(vault_root), "rev-parse", "HEAD"], text=True
    ).strip()


def reset_fixture(
    schema: dict[str, Any],
    *,
    vault_root: Path = DEV_VAULT,
    state_root: Path = DEV_STATE,
    extra_facts: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    """Replace only isolated DEV fixture content and transient benchmark state.

    The persistent DEV actor and self-binding files remain in place.  All prior Markdown,
    delivery replay records, conversation turns, and pending records are disposable DEV state.
    A caller must restart the existing DEV runtime after this function returns.
    """
    _require_exact_dev_roots(vault_root, state_root)
    notes = fixture_notes(extra_facts)
    for note in notes.values():
        validate_note(note, schema)
    _clear_directory_children(vault_root, preserved={".git"})
    people = vault_root / "people"
    people.mkdir(mode=0o750)
    paths = {
        "Marta": "people/p1-marta.md",
        "Elena": "people/p1-elena.md",
        "Pablo": "people/p1-pablo.md",
        "self": "people/odyssey-dev-synthetic-person.md",
    }
    for key, path in paths.items():
        (vault_root / path).write_text(serialize_note(notes[key]), encoding="utf-8")
    for transient in (state_root / "conversations", state_root / "pending"):
        transient.mkdir(mode=0o750, exist_ok=True)
        _clear_directory_children(transient)
    return {
        "fixture_version": FIXTURE_VERSION,
        "fixture_reset_at": datetime.now(UTC).isoformat(),
        "fixture_git_commit": _commit_fixture(vault_root),
        "note_ids": ["p1-marta", "p1-elena", "p1-pablo"],
    }


def main(argv: list[str] | None = None) -> int:
    """Reset the fixed DEV root after an explicit disposable-fixture confirmation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-disposable-dev-fixture", action="store_true")
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--extra-facts-json", default="{}")
    args = parser.parse_args(argv)
    if not args.confirm_disposable_dev_fixture:
        raise SystemExit("Refusing fixture reset without --confirm-disposable-dev-fixture")
    try:
        extra_facts = json.loads(args.extra_facts_json)
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        result = reset_fixture(schema, extra_facts=extra_facts)
    except (FixtureError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"P1 disposable DEV fixture reset failed: {error}") from error
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
