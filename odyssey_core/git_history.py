"""Request-scoped local Git history for the canonical Markdown vault."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .notes import NoteFormatError, NoteValidationError, parse_note, validate_note

if TYPE_CHECKING:
    from .storage import VaultRepository


class HistoryStatus(StrEnum):
    """Describe the bounded outcome of request-level Git history recording."""

    DISABLED = "DISABLED"
    NO_CHANGES = "NO_CHANGES"
    COMMITTED = "COMMITTED"
    SKIPPED_UNSAFE = "SKIPPED_UNSAFE"
    FAILED = "FAILED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


@dataclass(frozen=True, slots=True)
class GitHistoryResult:
    """Expose bounded Git evidence without retaining requests or note contents."""

    status: HistoryStatus
    commit_sha: str | None = None
    reason: str | None = None

    @classmethod
    def disabled(cls) -> GitHistoryResult:
        """Return evidence for an unconfigured history recorder."""
        return cls(HistoryStatus.DISABLED)


@dataclass(frozen=True, slots=True)
class GitHistorySnapshot:
    """Capture paths already dirty before a valid request begins."""

    dirty_paths: frozenset[str]


class HistoryRecorder(Protocol):
    """Define the application boundary for optional request-level history."""

    def begin(self, request_id: str) -> GitHistorySnapshot:
        """Inspect the exact vault and return its pre-request dirty-path snapshot."""

    def record(
        self,
        *,
        request_id: str,
        snapshot: GitHistorySnapshot,
        affected_stable_note_ids: tuple[str, ...],
        repository: VaultRepository,
        schema: dict[str, Any],
    ) -> GitHistoryResult:
        """Attribute successful note IDs and create at most one safe local commit."""


class GitHistoryRecorder:
    """Record safe Markdown mutations in the exact configured vault repository."""

    def __init__(self, vault_root: str | Path) -> None:
        """Configure a recorder for an existing local vault Git repository."""
        self.vault_root = Path(vault_root)

    def begin(self, request_id: str) -> GitHistorySnapshot:
        """Verify the vault Git root and snapshot tracked, staged, and untracked paths."""
        del request_id
        root = self._git_root()
        return GitHistorySnapshot(frozenset(self._status_paths(root)))

    def record(
        self,
        *,
        request_id: str,
        snapshot: GitHistorySnapshot,
        affected_stable_note_ids: tuple[str, ...],
        repository: VaultRepository,
        schema: dict[str, Any],
    ) -> GitHistoryResult:
        """Resolve successful IDs, reject unsafe attribution, and commit exact paths only."""
        root = self._git_root()
        if repository.root.resolve() != root:
            return GitHistoryResult(HistoryStatus.FAILED, reason="repository root mismatch")
        requested_ids = tuple(dict.fromkeys(affected_stable_note_ids))
        if not requested_ids:
            return GitHistoryResult(HistoryStatus.NO_CHANGES)

        matches_by_id = {stable_id: [] for stable_id in requested_ids}
        for path in repository.list_markdown_paths():
            try:
                note = parse_note(repository.read_text(path))
                validate_note(note, schema)
            except (NoteFormatError, NoteValidationError, OSError):
                return GitHistoryResult(HistoryStatus.FAILED, reason="canonical attribution failed")
            stable_id = note.metadata.get("id")
            if stable_id in matches_by_id:
                matches_by_id[stable_id].append(path)

        paths: list[str] = []
        for stable_id in requested_ids:
            matches = matches_by_id[stable_id]
            if len(matches) != 1:
                return GitHistoryResult(HistoryStatus.FAILED, reason="affected ID cannot be mapped")
            paths.append(matches[0])
        paths.sort()
        if set(paths) & snapshot.dirty_paths:
            return GitHistoryResult(
                HistoryStatus.SKIPPED_UNSAFE, reason="affected path was pre-dirty"
            )
        self._run(root, "add", "--", *paths)
        diff = self._run(root, "diff", "--cached", "--quiet", "--", *paths, check=False)
        if diff.returncode == 0:
            return GitHistoryResult(HistoryStatus.NO_CHANGES)
        if diff.returncode != 1:
            raise RuntimeError("Git staged diff inspection failed")
        message = f"odyssey: apply request\n\nOdyssey-Request: {request_id}"
        self._run(
            root,
            "-c",
            "user.name=Odyssey Local",
            "-c",
            "user.email=odyssey@localhost",
            "commit",
            "--only",
            "-m",
            message,
            "--",
            *paths,
        )
        sha = self._run(root, "rev-parse", "HEAD").stdout.strip()
        return GitHistoryResult(HistoryStatus.COMMITTED, commit_sha=sha)

    def _git_root(self) -> Path:
        """Return the exact initialized vault Git root with an existing baseline commit."""
        root = self.vault_root.resolve(strict=True)
        actual = Path(self._run(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
        if actual != root:
            raise RuntimeError("Git repository root does not match vault root")
        head = self._run(root, "rev-parse", "--verify", "HEAD", check=False)
        if head.returncode != 0:
            raise RuntimeError("Git repository has no baseline commit")
        return root

    @staticmethod
    def _run(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run one fixed-argument Git operation beneath the configured root."""
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False, shell=False
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"Git operation failed: {args[0]}")
        return result

    def _status_paths(self, root: Path) -> set[str]:
        """Parse NUL-delimited porcelain status while preserving rename/copy path pairs."""
        result = self._run(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        tokens = result.stdout.split("\0")
        paths: set[str] = set()
        index = 0
        while index < len(tokens) - 1:
            entry = tokens[index]
            if len(entry) < 4:
                raise RuntimeError("Git status output is malformed")
            paths.add(entry[3:])
            if entry[0] in "RC" or entry[1] in "RC":
                index += 1
                if index >= len(tokens) - 1:
                    raise RuntimeError("Git status rename output is malformed")
                paths.add(tokens[index])
            index += 1
        return paths
