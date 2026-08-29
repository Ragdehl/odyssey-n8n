"""Contained raw-text filesystem access for the Odyssey Markdown vault."""

from __future__ import annotations

import os
import tempfile
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

        if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
            raise VaultAccessError("Vault root is unusable")
        self._root = root

    @property
    def root(self) -> Path:
        """Return the resolved canonical filesystem root owned by this vault repository."""
        return self._root

    def contains_filesystem_path(self, path: Path) -> bool:
        """Report whether a filesystem path resolves beneath the configured vault.

        This containment check lets derived-storage callers prevent accidental placement inside
        authoritative vault knowledge. It does not require the candidate path to exist.

        Args:
            path: Filesystem path whose resolved location should be checked.

        Returns:
            ``True`` when the path is the vault root or is contained beneath it.

        Raises:
            TypeError: If ``path`` is not a ``pathlib.Path``.
        """
        if not isinstance(path, Path):
            raise TypeError("Filesystem path must be a pathlib.Path")
        try:
            return path.resolve(strict=False).is_relative_to(self._root)
        except (OSError, RuntimeError):
            return False

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

        Example:
            Given ``people/ada.md`` beneath the configured root::

                markdown = repository.read_text("people/ada.md")
        """
        relative_path = self._validate_note_path(path)
        try:
            # Resolve before opening so a symlink cannot redirect a read outside the vault.
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

        Example:
            Create a note only after its parent collection already exists::

                repository.create_text("people/ada.md", "# Ada Lovelace\n")
        """
        relative_path = self._validate_note_path(path)
        if not isinstance(content, str):
            raise TypeError("Note content must be text")
        try:
            encoded_content = content.encode("utf-8")
        except UnicodeEncodeError:
            raise VaultAccessError("Unable to create note") from None

        try:
            # Resolve the parent before opening the target so a symlink cannot redirect
            # creation outside the configured vault.
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

    def replace_text(self, path: str, content: str) -> None:
        """Atomically replace one existing contained Markdown file with UTF-8 text.

        Args:
            path: Vault-relative POSIX Markdown path identifying an existing file.
            content: Replacement text to encode as UTF-8.

        Raises:
            InvalidNotePath: If the caller path violates the repository contract.
            TypeError: If content is not text.
            NoteUnavailableError: If the target is missing, not regular, or unsafe.
            VaultAccessError: If encoding, temporary-file, or replacement I/O fails.

        The temporary file is created beside the target so ``os.replace`` provides an
        atomic authoritative-file transition without creating parent directories.
        """
        relative_path = self._validate_note_path(path)
        if not isinstance(content, str):
            raise TypeError("Note content must be text")
        try:
            encoded_content = content.encode("utf-8")
        except UnicodeEncodeError:
            raise VaultAccessError("Unable to replace note") from None

        candidate = self._root.joinpath(*relative_path.parts)
        try:
            parent = candidate.parent.resolve(strict=True)
            target = parent / candidate.name
            resolved_target = target.resolve(strict=True)
        except (FileNotFoundError, RuntimeError):
            raise NoteUnavailableError(f"Note is unavailable: {relative_path.as_posix()}") from None
        except OSError:
            raise VaultAccessError("Unable to replace note") from None

        if (
            not parent.is_relative_to(self._root)
            or target.is_symlink()
            or not resolved_target.is_relative_to(self._root)
            or not resolved_target.is_file()
        ):
            raise NoteUnavailableError(f"Note is unavailable: {relative_path.as_posix()}")

        temporary_path: str | None = None
        try:
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=parent
            )
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(encoded_content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
        except OSError:
            raise VaultAccessError("Unable to replace note") from None
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass

    def list_markdown_paths(self) -> list[str]:
        """List contained regular Markdown files without reading or following symlinks.

        Returns:
            Vault-relative POSIX ``.md`` paths in deterministic lexical order.

        Raises:
            VaultAccessError: If filesystem traversal cannot complete safely.

        Example:
            A vault containing ``index.md`` and ``people/ada.md`` returns::

                ["index.md", "people/ada.md"]
        """
        paths: list[str] = []
        directories = [self._root]
        try:
            while directories:
                directory = directories.pop()
                with os.scandir(directory) as entries:
                    for entry in entries:
                        # Symlinks are excluded entirely: even an in-vault target could be
                        # replaced between discovery and later access by a caller.
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
