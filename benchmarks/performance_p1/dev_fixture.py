"""Reset the dedicated P1 data root to P1's disposable note fixture.

This helper intentionally accepts only the fixed P1 fixture root and requires an explicit identity
marker created outside this program. It is benchmark setup, not an Odyssey request path: callers
must restart the dedicated P1 runtime afterwards so its rebuildable indexes reflect the new
canonical Markdown before timing a case.
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

P1_ROOT = Path("/data/odyssey-p1-fixture")
P1_VAULT = P1_ROOT / "vault"
P1_STATE = P1_ROOT / "state"
MANUAL_DEV_ROOT = Path("/data/odyssey-dev")
PRODUCTION_ROOT = Path("/data/odyssey")
DISPOSABLE_MARKER = P1_ROOT / ".p1-disposable-fixture"
FIXTURE_IDENTITY = "odyssey-p1-disposable-fixture-v1\n"
FIXTURE_VERSION = 1
_FIXTURE_APP = "odyssey-p1-disposable-fixture"
_STAMP = "2026-01-01T00:00:00+00:00"


class FixtureError(RuntimeError):
    """Raised when a fixture reset cannot prove that it is confined to the P1 fixture root."""


def _is_within(candidate: Path, root: Path) -> bool:
    """Return whether one resolved path is the protected root or one of its descendants."""
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _require_exact_p1_roots(vault_root: Path, state_root: Path) -> None:
    """Reject every destructive target except the marked dedicated P1 fixture root."""
    resolved_vault = vault_root.resolve()
    resolved_state = state_root.resolve()
    protected_roots = (MANUAL_DEV_ROOT.resolve(), PRODUCTION_ROOT.resolve())
    if any(
        _is_within(candidate, protected)
        for candidate in (resolved_vault, resolved_state)
        for protected in protected_roots
    ):
        raise FixtureError("P1 fixture reset must not overlap manual DEV or production data")
    if vault_root != P1_VAULT or state_root != P1_STATE:
        raise FixtureError("P1 fixture reset is restricted to the dedicated P1 fixture root")
    if not (
        P1_ROOT.is_dir()
        and not P1_ROOT.is_symlink()
        and (P1_VAULT / ".git").is_dir()
        and not P1_VAULT.is_symlink()
        and P1_STATE.is_dir()
        and not P1_STATE.is_symlink()
        and DISPOSABLE_MARKER.is_file()
        and not DISPOSABLE_MARKER.is_symlink()
    ):
        raise FixtureError(
            "dedicated P1 fixture is not explicitly initialized and marked disposable"
        )
    try:
        marker = DISPOSABLE_MARKER.read_text(encoding="utf-8")
    except OSError as error:
        raise FixtureError("dedicated P1 fixture identity is unavailable") from error
    if marker != FIXTURE_IDENTITY:
        raise FixtureError("dedicated P1 fixture identity is invalid")
    try:
        git_root = Path(
            subprocess.check_output(
                ["git", "-C", str(P1_VAULT), "rev-parse", "--show-toplevel"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        ).resolve()
        subprocess.check_output(
            ["git", "-C", str(P1_VAULT), "rev-parse", "--verify", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise FixtureError("dedicated P1 fixture Git baseline is unavailable") from error
    if git_root != P1_VAULT.resolve():
        raise FixtureError("dedicated P1 fixture Git root is invalid")


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
    vault_root: Path = P1_VAULT,
    state_root: Path = P1_STATE,
    extra_facts: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    """Replace only explicitly marked dedicated P1 fixture content and transient state.

    The fixture-local actor and self-binding files remain in place. All prior Markdown,
    delivery replay records, conversation turns, and pending records are disposable only when
    the external marker precondition has been deliberately established. A caller must restart
    the dedicated P1 runtime after this function returns.
    """
    _require_exact_p1_roots(vault_root, state_root)
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
    """Reset the fixed P1 root after explicit disposable-fixture confirmation and marker."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-disposable-p1-fixture", action="store_true")
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--extra-facts-json", default="{}")
    args = parser.parse_args(argv)
    if not args.confirm_disposable_p1_fixture:
        raise SystemExit("Refusing fixture reset without --confirm-disposable-p1-fixture")
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
