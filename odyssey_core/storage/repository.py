"""Contained raw-text filesystem access for the Odyssey Markdown vault."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

_REQUEST_READ_MAX_BYTES = 8 * 1024 * 1024
_REQUEST_READ_MAX_NOTES = 4096
_REQUEST_PATH_LIST_MAX_NOTES = 20_000


class InvalidNotePath(ValueError):
    """Indicate that a caller supplied an invalid vault-relative note path."""


class NoteUnavailableError(OSError):
    """Indicate that a valid note path cannot identify an accessible note file."""


class NoteAlreadyExistsError(OSError):
    """Indicate that create-only storage refused an existing target."""


class NoteContentConflictError(ValueError):
    """Physical Markdown differs from the expected content at replace time."""


class VaultAccessError(OSError):
    """Indicate an unexpected or unsafe filesystem access outcome."""


@dataclass(slots=True)
class _RequestReads:
    """Bound only within one delivery; never trust a saved result without live stat."""

    texts: dict[str, tuple[tuple[object, ...], str]] = field(default_factory=dict)
    bytes_used: int = 0
    paths: tuple[str, ...] | None = None
    directory_versions: tuple[tuple[Path, tuple[int, ...]], ...] = ()


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
        self._request_reads: ContextVar[_RequestReads | None] = ContextVar(
            f"odyssey_vault_request_reads_{id(self)}", default=None
        )

    @contextmanager
    def scoped_unchanged_reads(self) -> Iterator[None]:
        """Avoid repeat filesystem I/O *inside one delivery* without caching authority.

        Every reused text is first checked against its live resolved path,
        inode, device, size, mtime and ctime; directory listings are similarly
        checked against every previously discovered directory. Writes made by
        this repository invalidate its context-local hints. Any mismatch is
        resolved again from the canonical vault. No caching across requests.
        """
        token = self._request_reads.set(_RequestReads())
        try:
            yield
        finally:
            self._request_reads.reset(token)

    @staticmethod
    def _fingerprint(target: Path) -> tuple[object, ...]:
        """Get a live filesystem version; an unsafe/missing path must not be reused."""
        status = target.stat()
        return (
            str(target),
            status.st_dev,
            status.st_ino,
            status.st_size,
            status.st_mtime_ns,
            status.st_ctime_ns,
        )

    @staticmethod
    def _stat_version(entry: os.stat_result) -> tuple[int, int, int, int, int]:
        """Identify a source without access time, which reads may change."""
        return (entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns, entry.st_ctime_ns)

    @staticmethod
    @contextmanager
    def _serialize_replacements(parent: Path) -> Iterator[None]:
        """Serialize cooperating Core writers using the physical directory.

        No extra Markdown, lock file or database is introduced. POSIX file
        locks cannot arbitrate editors that intentionally ignore the lock;
        a fresh source-hash compare also runs within this critical section.
        """
        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise VaultAccessError("Invalid write directory")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _invalidate_request_hints(self, path: str) -> None:
        """Never allow an internal mutation to reuse older request-local evidence."""
        scope = self._request_reads.get()
        if scope is not None:
            previous = scope.texts.pop(path, None)
            if previous is not None:
                scope.bytes_used -= int(previous[0][3])
            scope.paths = None
            scope.directory_versions = ()

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
        if (
            not normalized.parts
            or ".." in normalized.parts
            or ".git" in normalized.parts
            or normalized.suffix != ".md"
        ):
            raise InvalidNotePath("Invalid note path")
        return normalized

    def file_version(self, path: str) -> tuple[object, ...]:
        """Return a current contained-file version for derived lookup freshness.

        This is a *change detector*, not proof of the note's ID, type, or body.
        No symlink or out-of-vault path can authorize a cached lookup.
        """
        relative = self._validate_note_path(path)
        try:
            physical = self._root.joinpath(*relative.parts).resolve(strict=True)
            if not physical.is_relative_to(self._root) or not physical.is_file():
                raise NoteUnavailableError("Canonical note is unavailable")
            return self._fingerprint(physical)
        except (FileNotFoundError, RuntimeError):
            raise NoteUnavailableError("Canonical note is unavailable") from None
        except OSError:
            raise VaultAccessError("Cannot check canonical source freshness") from None

    def note_version_snapshot(self) -> dict[str, tuple[object, ...]]:
        """Version every canonical regular Markdown file in one no-symlink walk.

        This is a physical-version CHANGE DETECTOR, not a canonical content
        proof. Re-ground selected notes with read_text and Writer/CAS. Directory
        and file changes while enumerating make the batch unusable, never a
        negative source-of-truth claim.
        """
        paths: dict[str, tuple[object, ...]] = {}
        directories = [self._root]
        before_directories: list[tuple[Path, tuple[object, ...]]] = []
        try:
            while directories:
                folder = directories.pop()
                before_status = folder.lstat()
                if not stat.S_ISDIR(before_status.st_mode):
                    raise VaultAccessError("Vault folder changed during version scan")
                before_directories.append((folder, self._fingerprint(folder)))
                with os.scandir(folder) as entries:
                    for entry in entries:
                        # Local Git history is operational metadata, never
                        # a canonical Note. Git can update it while a scan
                        # runs; do not treat those internal changes as a
                        # changing Markdown inventory.
                        if entry.is_symlink() or entry.name == ".git":
                            continue
                        entry_status = entry.stat(follow_symlinks=False)
                        if stat.S_ISDIR(entry_status.st_mode):
                            directories.append(Path(entry.path))
                        elif stat.S_ISREG(entry_status.st_mode) and entry.name.endswith(".md"):
                            path = Path(entry.path).relative_to(self._root).as_posix()
                            paths[path] = (
                                entry.path,
                                entry_status.st_dev,
                                entry_status.st_ino,
                                entry_status.st_size,
                                entry_status.st_mtime_ns,
                                entry_status.st_ctime_ns,
                            )
                        if len(paths) > 30_000:
                            raise VaultAccessError("Vault version proof exceeds bounded capacity")
            if any(
                not stat.S_ISDIR(folder.lstat().st_mode) or self._fingerprint(folder) != previous
                for folder, previous in before_directories
            ):
                raise VaultAccessError("Vault folder changed during version scan")
        except VaultAccessError:
            raise
        except (OSError, RuntimeError, ValueError) as error:
            raise VaultAccessError("Cannot enumerate canonical source versions") from error
        return paths

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

        scope = self._request_reads.get()
        path_key = relative_path.as_posix()
        version = None
        if scope is not None:
            try:
                version = self._fingerprint(target)
            except OSError:
                raise NoteUnavailableError(f"Note is unavailable: {path_key}") from None
            cached = scope.texts.get(path_key)
            if cached is not None and cached[0] == version:
                return cached[1]
        try:
            with target.open("r", encoding="utf-8", newline="") as note_file:
                content = note_file.read()
            if scope is not None:
                try:
                    previous = scope.texts.pop(path_key, None)
                    if previous is not None:
                        scope.bytes_used -= int(previous[0][3])
                    if self._fingerprint(target) == version:
                        size = int(version[3])
                        if (
                            size <= _REQUEST_READ_MAX_BYTES - scope.bytes_used
                            and len(scope.texts) < _REQUEST_READ_MAX_NOTES
                        ):
                            scope.texts[path_key] = (version, content)
                            scope.bytes_used += size
                except OSError:
                    previous = scope.texts.pop(path_key, None)
                    if previous is not None:
                        scope.bytes_used -= int(previous[0][3])
            return content
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
            self._invalidate_request_hints(relative_path.as_posix())
        except FileExistsError:
            raise NoteAlreadyExistsError(
                f"Note already exists: {relative_path.as_posix()}"
            ) from None
        except OSError:
            raise VaultAccessError("Unable to create note") from None

    def replace_text(
        self, path: str, content: str, *, expected_source_hash: str | None = None
    ) -> None:
        """Atomically replace one existing contained Markdown file with UTF-8 text.

        When a hash is provided, compare actual file bytes again next to the
        physical os.replace call, not only earlier during Core planning.

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
        if expected_source_hash is not None and (
            not isinstance(expected_source_hash, str)
            or len(expected_source_hash) != 64
            or any(c not in "0123456789abcdef" for c in expected_source_hash)
        ):
            raise ValueError("Expected source hash must be lowercase SHA-256")
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

        with self._serialize_replacements(parent):
            temporary_path: str | None = None
            try:
                descriptor, temporary_path = tempfile.mkstemp(
                    prefix=f".{target.name}.", suffix=".tmp", dir=parent
                )
                with os.fdopen(descriptor, "wb") as temporary_file:
                    temporary_file.write(encoded_content)
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())
                if expected_source_hash is not None:
                    # Source/CAS is revalidated at the actual persistence
                    # boundary, catching same-revision edits during serialization.
                    # We also verify the inode after reading to reject a path swap.
                    digest = hashlib.sha256()
                    descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
                    with os.fdopen(descriptor, "rb") as previous:
                        opened = os.fstat(previous.fileno())
                        if not stat.S_ISREG(opened.st_mode):
                            raise NoteContentConflictError("Canonical source became unsafe")
                        for block in iter(lambda: previous.read(65536), b""):
                            digest.update(block)
                        if self._stat_version(os.fstat(previous.fileno())) != self._stat_version(
                            opened
                        ):
                            raise NoteContentConflictError(
                                "Canonical source changed during compare"
                            )
                    if self._stat_version(
                        os.stat(target, follow_symlinks=False)
                    ) != self._stat_version(opened) or not hmac.compare_digest(
                        digest.hexdigest(), expected_source_hash
                    ):
                        raise NoteContentConflictError("Canonical source changed before replace")
                os.replace(temporary_path, target)
                temporary_path = None
                self._invalidate_request_hints(relative_path.as_posix())
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

    def remove_text(self, path: str) -> None:
        """Remove one existing contained Markdown file without following symlinks.

        This primitive exists for request-local rollback of a just-created canonical note. Domain
        deletion still uses Odyssey soft-delete semantics; callers must not use this as a user delete.
        """
        relative_path = self._validate_note_path(path)
        candidate = self._root.joinpath(*relative_path.parts)
        try:
            parent = candidate.parent.resolve(strict=True)
            target = parent / candidate.name
            resolved_target = target.resolve(strict=True)
        except (FileNotFoundError, RuntimeError):
            raise NoteUnavailableError(f"Note is unavailable: {relative_path.as_posix()}") from None
        except OSError:
            raise VaultAccessError("Unable to remove note") from None
        if (
            not parent.is_relative_to(self._root)
            or target.is_symlink()
            or not resolved_target.is_relative_to(self._root)
            or not resolved_target.is_file()
        ):
            raise NoteUnavailableError(f"Note is unavailable: {relative_path.as_posix()}")
        try:
            target.unlink()
            self._invalidate_request_hints(relative_path.as_posix())
        except FileNotFoundError:
            raise NoteUnavailableError(f"Note is unavailable: {relative_path.as_posix()}") from None
        except OSError:
            raise VaultAccessError("Unable to remove note") from None

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
        scope = self._request_reads.get()
        if scope is not None and scope.paths is not None:
            try:
                if all(
                    directory.is_dir()
                    and not directory.is_symlink()
                    and self._fingerprint(directory) == expected
                    for directory, expected in scope.directory_versions
                ):
                    return list(scope.paths)
            except OSError:
                pass
        paths: list[str] = []
        directories = [self._root]
        observed_directories: list[tuple[Path, tuple[object, ...]]] = []
        try:
            while directories:
                directory = directories.pop()
                if scope is not None:
                    observed_directories.append((directory, self._fingerprint(directory)))
                with os.scandir(directory) as entries:
                    for entry in entries:
                        # Symlinks are excluded entirely: even an in-vault target could be
                        # replaced between discovery and later access by a caller.
                        if entry.is_symlink() or entry.name == ".git":
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            directories.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False) and entry.name.endswith(".md"):
                            paths.append(Path(entry.path).relative_to(self._root).as_posix())
        except OSError:
            raise VaultAccessError("Unable to list vault") from None

        paths.sort()
        if scope is not None:
            if len(paths) <= _REQUEST_PATH_LIST_MAX_NOTES:
                try:
                    versions = tuple(
                        (directory, self._fingerprint(directory))
                        for directory, _before in observed_directories
                    )
                except OSError:
                    scope.paths = None
                    scope.directory_versions = ()
                else:
                    # A new directory/file appearing DURING enumeration must
                    # not become a cached negative lookup for later scans.
                    if all(
                        original == current
                        for (_directory, original), (_path, current) in zip(
                            observed_directories, versions, strict=True
                        )
                    ):
                        scope.paths = tuple(paths)
                        scope.directory_versions = versions
                    else:
                        scope.paths = None
                        scope.directory_versions = ()
            else:
                scope.paths = None
                scope.directory_versions = ()
        return paths
