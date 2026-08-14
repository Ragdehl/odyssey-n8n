"""Contained raw-text filesystem access for the Odyssey Markdown vault."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath


class InvalidNotePath(ValueError):
    """Indicate that a caller supplied an invalid vault-relative note path."""


class NoteUnavailableError(OSError):
    """Indicate that a valid note path cannot identify an accessible note file."""


class NoteAlreadyExistsError(OSError):
    """Indicate that create-only storage refused an existing target."""


class VaultAccessError(OSError):
    """Indicate an unexpected or unsafe filesystem access outcome."""


class VaultRepository:
    """Provide contained raw Markdown text access beneath one configured vault root."""

    def __init__(self, vault_root: str | os.PathLike[str]) -> None:
        """Configure a repository for an existing usable vault directory.

        Args:
            vault_root: Filesystem directory that contains authoritative Markdown notes.

        Raises:
            VaultAccessError: If the root is missing, not a directory, or unusable.
        """
        try:
            root = Path(vault_root).resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError, TypeError):
            raise VaultAccessError("Vault root is unavailable") from None

        if not root.is_dir() or not os.access(root, os.R_OK | os.W_OK | os.X_OK):
            raise VaultAccessError("Vault root is unusable")
        self._root = root

    @staticmethod
    def _validate_note_path(path: str) -> PurePosixPath:
        """Return a normalized literal POSIX Markdown path after caller validation.

        Args:
            path: Caller-supplied path relative to the configured vault.

        Returns:
            A normalized relative POSIX path ending in ``.md``.

        Raises:
            InvalidNotePath: If the value is unsafe, ambiguous, absolute, or not Markdown.
        """
        if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
            raise InvalidNotePath("Invalid note path")
        if path.startswith("/") or (len(path) >= 3 and path[0].isalpha() and path[1:3] == ":/"):
            raise InvalidNotePath("Invalid note path")

        normalized = PurePosixPath(path)
        if not normalized.parts or ".." in normalized.parts or normalized.suffix != ".md":
            raise InvalidNotePath("Invalid note path")
        return normalized

    def read_text(self, path: str) -> str:
        """Read one contained Markdown file as unchanged UTF-8 text.

        Args:
            path: Vault-relative POSIX Markdown path.

        Returns:
            Raw Markdown text exactly as decoded from UTF-8.

        Raises:
            InvalidNotePath: If the caller path violates the repository contract.
            NoteUnavailableError: If the valid path is missing, not a file, or escapes containment.
            VaultAccessError: If another filesystem or decoding failure occurs.
        """
        relative_path = self._validate_note_path(path)
        try:
            target = self._root.joinpath(*relative_path.parts).resolve(strict=True)
        except (FileNotFoundError, RuntimeError):
            raise NoteUnavailableError(f"Note is unavailable: {relative_path.as_posix()}") from None
        except OSError:
            raise VaultAccessError("Unable to read note") from None

        if not target.is_relative_to(self._root) or not target.is_file():
            raise NoteUnavailableError(f"Note is unavailable: {relative_path.as_posix()}")

        try:
            with target.open("r", encoding="utf-8", newline="") as note_file:
                return note_file.read()
        except (FileNotFoundError, IsADirectoryError):
            raise NoteUnavailableError(f"Note is unavailable: {relative_path.as_posix()}") from None
        except (OSError, UnicodeError):
            raise VaultAccessError("Unable to read note") from None

    def create_text(self, path: str, content: str) -> None:
        """Create one contained UTF-8 Markdown file without replacing any target.

        The target's parent directory must already exist; this method never creates directory trees.

        Args:
            path: Vault-relative POSIX Markdown path.
            content: Raw Markdown text to store unchanged.

        Raises:
            InvalidNotePath: If the caller path violates the repository contract.
            TypeError: If content is not text.
            NoteAlreadyExistsError: If any filesystem entry already occupies the target.
            VaultAccessError: If the parent is unavailable or another filesystem failure occurs.
        """
        relative_path = self._validate_note_path(path)
        if not isinstance(content, str):
            raise TypeError("Note content must be text")
        try:
            encoded_content = content.encode("utf-8")
        except UnicodeEncodeError:
            raise VaultAccessError("Unable to create note") from None

        try:
            parent = self._root.joinpath(*relative_path.parts[:-1]).resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError):
            raise VaultAccessError("Note parent is unavailable") from None

        if not parent.is_relative_to(self._root) or not parent.is_dir():
            raise VaultAccessError("Note parent is unavailable")

        target = parent / relative_path.name
        try:
            with target.open("xb") as note_file:
                note_file.write(encoded_content)
        except FileExistsError:
            raise NoteAlreadyExistsError(
                f"Note already exists: {relative_path.as_posix()}"
            ) from None
        except OSError:
            raise VaultAccessError("Unable to create note") from None

    def list_markdown_paths(self) -> list[str]:
        """List contained regular Markdown files without reading or following symlinks.

        Returns:
            Vault-relative POSIX ``.md`` paths in deterministic lexical order.

        Raises:
            VaultAccessError: If filesystem traversal cannot complete safely.
        """
        paths: list[str] = []
        directories = [self._root]
        try:
            while directories:
                directory = directories.pop()
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            directories.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False) and entry.name.endswith(".md"):
                            paths.append(Path(entry.path).relative_to(self._root).as_posix())
        except OSError:
            raise VaultAccessError("Unable to list vault") from None

        paths.sort()
        return paths
