"""Filesystem contract tests for Odyssey Core's VaultRepository."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from odyssey_core.storage import (
    InvalidNotePath,
    NoteAlreadyExistsError,
    NoteUnavailableError,
    VaultAccessError,
    VaultRepository,
)


class VaultRepositoryTests(unittest.TestCase):
    """Verify contained deterministic access using isolated temporary vaults."""

    def setUp(self) -> None:
        """Create an isolated valid vault for each repository contract test."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.vault = Path(self.temporary_directory.name) / "vault"
        self.vault.mkdir()
        self.repository = VaultRepository(self.vault)

    def tearDown(self) -> None:
        """Remove the isolated vault and every test entry it contains."""
        self.temporary_directory.cleanup()

    def test_constructor_accepts_a_valid_temporary_vault(self) -> None:
        """Construct a repository from an existing usable directory."""
        self.assertEqual(self.repository.list_markdown_paths(), [])

    def test_constructor_rejects_missing_and_non_directory_roots(self) -> None:
        """Fail clearly when the configured vault root cannot serve as a directory."""
        missing = Path(self.temporary_directory.name) / "missing"
        regular_file = Path(self.temporary_directory.name) / "file"
        regular_file.write_text("not a directory", encoding="utf-8")

        with self.assertRaisesRegex(VaultAccessError, "Vault root is unavailable"):
            VaultRepository(missing)
        with self.assertRaisesRegex(VaultAccessError, "Vault root is unusable"):
            VaultRepository(regular_file)

    def test_rejects_unsafe_or_non_markdown_paths(self) -> None:
        """Reject traversal, absolute, backslash, empty, and non-Markdown caller paths."""
        invalid_paths = (
            "",
            "../outside.md",
            "people/../../outside.md",
            "/absolute.md",
            "C:/absolute.md",
            "people\\carlos.md",
            "people/carlos.txt",
        )
        for path in invalid_paths:
            with self.subTest(path=path), self.assertRaises(InvalidNotePath):
                self.repository.read_text(path)

    def test_reads_root_and_nested_utf8_text_unchanged(self) -> None:
        """Return exact raw UTF-8 Markdown from root-level and nested notes."""
        root_content = "# Café\n\nLínea final\n"
        nested_content = "---\nid: mañana\n---\n\n# Niño 👋"
        (self.vault / "root.md").write_text(root_content, encoding="utf-8", newline="")
        people = self.vault / "people"
        people.mkdir()
        (people / "niño.md").write_text(nested_content, encoding="utf-8", newline="")

        self.assertEqual(self.repository.read_text("root.md"), root_content)
        self.assertEqual(self.repository.read_text("people/niño.md"), nested_content)

    def test_reads_literal_names_that_are_not_glob_selectors(self) -> None:
        """Treat glob metacharacters as ordinary filename characters on the local filesystem."""
        literal_name = "[draft]*question?.md"
        (self.vault / literal_name).write_text("literal", encoding="utf-8")

        self.assertEqual(self.repository.read_text(literal_name), "literal")

    def test_read_reports_missing_note_and_directory_as_unavailable(self) -> None:
        """Distinguish valid unavailable note targets from invalid caller paths."""
        (self.vault / "directory.md").mkdir()

        with self.assertRaises(NoteUnavailableError):
            self.repository.read_text("missing.md")
        with self.assertRaises(NoteUnavailableError):
            self.repository.read_text("directory.md")

    def test_read_rejects_an_outside_vault_symlink_without_leaking_root(self) -> None:
        """Fail closed when a valid relative note path resolves outside the configured vault."""
        outside = Path(self.temporary_directory.name) / "outside.md"
        outside.write_text("outside secret", encoding="utf-8")
        (self.vault / "escape.md").symlink_to(outside)

        with self.assertRaises(NoteUnavailableError) as raised:
            self.repository.read_text("escape.md")
        self.assertNotIn(str(outside), str(raised.exception))
        self.assertNotIn(str(self.vault), str(raised.exception))

    def test_creates_root_note_with_exact_utf8_content(self) -> None:
        """Create a new root-level Markdown file with unchanged UTF-8 text."""
        content = "# Café ☕\n\nTexto\n"

        self.repository.create_text("created.md", content)

        self.assertEqual((self.vault / "created.md").read_text(encoding="utf-8"), content)

    def test_creates_nested_note_only_when_parent_exists(self) -> None:
        """Create within an existing parent and never invent a missing directory tree."""
        (self.vault / "people").mkdir()
        self.repository.create_text("people/carlos.md", "# Carlos")

        self.assertEqual((self.vault / "people/carlos.md").read_text(encoding="utf-8"), "# Carlos")
        with self.assertRaises(VaultAccessError):
            self.repository.create_text("missing/note.md", "# Missing")
        self.assertFalse((self.vault / "missing").exists())

    def test_create_accepts_text_only(self) -> None:
        """Reject non-text content before any target is created."""
        with self.assertRaisesRegex(TypeError, "must be text"):
            self.repository.create_text("invalid.md", b"bytes")  # type: ignore[arg-type]
        self.assertFalse((self.vault / "invalid.md").exists())

    def test_create_refuses_overwrite_and_preserves_original_content(self) -> None:
        """Use exclusive creation so an existing target is never replaced."""
        target = self.vault / "existing.md"
        target.write_text("original", encoding="utf-8")

        with self.assertRaises(NoteAlreadyExistsError):
            self.repository.create_text("existing.md", "replacement")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_create_rejects_unsafe_path_and_outside_symlink_parent(self) -> None:
        """Fail closed for caller traversal and parents resolving outside the vault."""
        outside_directory = Path(self.temporary_directory.name) / "outside"
        outside_directory.mkdir()
        (self.vault / "escape").symlink_to(outside_directory, target_is_directory=True)

        with self.assertRaises(InvalidNotePath):
            self.repository.create_text("../outside.md", "unsafe")
        with self.assertRaises(VaultAccessError) as raised:
            self.repository.create_text("escape/note.md", "unsafe")
        self.assertFalse((outside_directory / "note.md").exists())
        self.assertNotIn(str(outside_directory), str(raised.exception))

    def test_lists_empty_vault(self) -> None:
        """Return an empty list when the vault contains no Markdown files."""
        self.assertEqual(self.repository.list_markdown_paths(), [])

    def test_lists_only_regular_markdown_paths_in_lexical_order(self) -> None:
        """Return deterministic vault-relative POSIX paths without reading contents."""
        (self.vault / "zeta.md").write_text("z", encoding="utf-8")
        (self.vault / "ignored.txt").write_text("ignored", encoding="utf-8")
        nested = self.vault / "alpha" / "deep"
        nested.mkdir(parents=True)
        (nested / "first.md").write_text("first", encoding="utf-8")
        (self.vault / "root.md").write_text("root", encoding="utf-8")

        self.assertEqual(
            self.repository.list_markdown_paths(),
            ["alpha/deep/first.md", "root.md", "zeta.md"],
        )
        self.assertTrue(
            all(
                "\\" not in path and not path.startswith("/")
                for path in self.repository.list_markdown_paths()
            )
        )

    def test_listing_excludes_outside_symlink_files_and_directories(self) -> None:
        """Never follow or expose Markdown reachable only through outside-vault symlinks."""
        outside_directory = Path(self.temporary_directory.name) / "outside"
        outside_directory.mkdir()
        outside_note = outside_directory / "outside.md"
        outside_note.write_text("outside", encoding="utf-8")
        (self.vault / "file-link.md").symlink_to(outside_note)
        (self.vault / "directory-link").symlink_to(outside_directory, target_is_directory=True)
        (self.vault / "inside.md").write_text("inside", encoding="utf-8")

        self.assertEqual(self.repository.list_markdown_paths(), ["inside.md"])


if __name__ == "__main__":
    unittest.main()
