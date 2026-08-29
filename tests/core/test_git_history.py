"""Deterministic Phase 17C local Git history coverage."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from odyssey_core import GitHistoryRecorder, HistoryStatus, create_entity
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def git(root: Path, *args: str) -> str:
    """Run a test-only Git command and return stdout."""
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout


def vault(tmp_path: Path) -> VaultRepository:
    """Create a disposable initialized vault with an explicit baseline commit."""
    git(tmp_path, "init", "-q")
    git(
        tmp_path,
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.com",
        "commit",
        "--allow-empty",
        "-m",
        "baseline",
    )
    return VaultRepository(tmp_path)


def note(repository: VaultRepository, path: str = "marta.md", entity_id: str = "marta") -> None:
    """Create one schema-valid canonical person fixture."""
    create_entity(
        repository,
        SCHEMA,
        path=path,
        entity_id=entity_id,
        metadata={"name": entity_id.title(), "type": "person", "relationship_to_user": "amiga"},
        content=f"# {entity_id.title()}\n",
        actor="fixture",
        now="2026-08-29T10:00:00+02:00",
    )
    git(repository.root, "add", path)
    git(
        repository.root,
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.com",
        "commit",
        "-m",
        "note",
    )


def record(repository: VaultRepository, request_id: str, ids: tuple[str, ...]):
    """Begin and record one adapter request."""
    recorder = GitHistoryRecorder(repository.root)
    snapshot = recorder.begin(request_id)
    return recorder.record(
        request_id=request_id,
        snapshot=snapshot,
        affected_stable_note_ids=ids,
        repository=repository,
        schema=SCHEMA,
    )


def test_clean_update_commits_with_bounded_trailer(tmp_path: Path) -> None:
    """Create one request commit and expose its SHA without note content in metadata."""
    repository = vault(tmp_path)
    note(repository)
    recorder = GitHistoryRecorder(repository.root)
    snapshot = recorder.begin("request-17c")
    repository.replace_text("marta.md", repository.read_text("marta.md") + "Updated.\n")
    result = recorder.record(
        request_id="request-17c",
        snapshot=snapshot,
        affected_stable_note_ids=("marta",),
        repository=repository,
        schema=SCHEMA,
    )
    assert result.status is HistoryStatus.COMMITTED
    message = git(tmp_path, "show", "-s", "--format=%B", result.commit_sha or "HEAD")
    assert "Odyssey-Request: request-17c" in message
    assert "Updated." not in message


def test_unrelated_staged_file_is_not_in_request_commit(tmp_path: Path) -> None:
    """Path-restricted commit preserves an unrelated staged manual edit."""
    repository = vault(tmp_path)
    note(repository)
    create_entity(
        repository,
        SCHEMA,
        path="manual.md",
        entity_id="manual",
        metadata={"name": "Manual", "type": "person", "relationship_to_user": "amiga"},
        content="# Manual\n",
        actor="fixture",
        now="2026-08-29T10:00:00+02:00",
    )
    git(tmp_path, "add", "manual.md")
    recorder = GitHistoryRecorder(repository.root)
    snapshot = recorder.begin("request-staged")
    repository.replace_text("marta.md", repository.read_text("marta.md") + "Changed.\n")
    result = recorder.record(
        request_id="request-staged",
        snapshot=snapshot,
        affected_stable_note_ids=("marta",),
        repository=repository,
        schema=SCHEMA,
    )
    assert result.status is HistoryStatus.COMMITTED
    assert git(tmp_path, "show", "--format=", "--name-only", "HEAD").strip() == "marta.md"
    assert "manual.md" in git(tmp_path, "diff", "--cached", "--name-only")


def test_unrelated_unstaged_file_is_not_in_request_commit(tmp_path: Path) -> None:
    """An unrelated manual working-tree edit remains dirty and outside the request commit."""
    repository = vault(tmp_path)
    note(repository)
    note(repository, "manual.md", "manual")
    repository.replace_text("manual.md", repository.read_text("manual.md") + "Manual edit.\n")
    recorder = GitHistoryRecorder(repository.root)
    snapshot = recorder.begin("request-unstaged")
    repository.replace_text("marta.md", repository.read_text("marta.md") + "Changed.\n")
    result = recorder.record(
        request_id="request-unstaged",
        snapshot=snapshot,
        affected_stable_note_ids=("marta",),
        repository=repository,
        schema=SCHEMA,
    )
    assert result.status is HistoryStatus.COMMITTED
    assert git(tmp_path, "show", "--format=", "--name-only", "HEAD").strip() == "marta.md"
    assert "manual.md" in git(tmp_path, "diff", "--name-only")


def test_pre_dirty_affected_path_is_skipped(tmp_path: Path) -> None:
    """Known user edits on an affected path prevent automatic attribution."""
    repository = vault(tmp_path)
    note(repository)
    repository.replace_text("marta.md", repository.read_text("marta.md") + "Manual.\n")
    recorder = GitHistoryRecorder(tmp_path)
    snapshot = recorder.begin("request-unsafe")
    result = recorder.record(
        request_id="request-unsafe",
        snapshot=snapshot,
        affected_stable_note_ids=("marta",),
        repository=repository,
        schema=SCHEMA,
    )
    assert result.status is HistoryStatus.SKIPPED_UNSAFE


def test_no_changes_and_wrong_root_fail_closed(tmp_path: Path) -> None:
    """Empty requests produce no commit and parent Git repositories are rejected."""
    repository = vault(tmp_path)
    note(repository)
    assert record(repository, "request-none", ()).status is HistoryStatus.NO_CHANGES
    child = tmp_path / "child"
    child.mkdir()
    with pytest.raises(RuntimeError, match="root"):
        GitHistoryRecorder(child).begin("request-root")


def test_begin_requires_explicit_baseline_commit(tmp_path: Path) -> None:
    """A freshly initialized repository is not silently bootstrapped by Odyssey."""
    git(tmp_path, "init", "-q")
    with pytest.raises(RuntimeError, match="baseline"):
        GitHistoryRecorder(tmp_path).begin("request-no-baseline")


def test_status_snapshot_preserves_both_rename_paths(tmp_path: Path) -> None:
    """Porcelain -z rename records retain both destination and source path boundaries."""
    repository = vault(tmp_path)
    note(repository)
    git(tmp_path, "mv", "marta.md", "renamed.md")
    snapshot = GitHistoryRecorder(tmp_path).begin("request-rename")
    assert {"marta.md", "renamed.md"} <= snapshot.dirty_paths


def test_missing_id_is_explicit_failure(tmp_path: Path) -> None:
    """Unresolvable successful IDs never broaden the candidate path set."""
    repository = vault(tmp_path)
    note(repository)
    result = record(repository, "request-missing", ("unknown",))
    assert result.status is HistoryStatus.FAILED


def test_repeated_affected_id_is_deduplicated_for_attribution(tmp_path: Path) -> None:
    """Repeated successful touches of one stable identity still produce one safe path commit."""
    repository = vault(tmp_path)
    note(repository)
    recorder = GitHistoryRecorder(repository.root)
    snapshot = recorder.begin("request-repeat")
    repository.replace_text("marta.md", repository.read_text("marta.md") + "Changed twice.\n")
    result = recorder.record(
        request_id="request-repeat",
        snapshot=snapshot,
        affected_stable_note_ids=("marta", "marta"),
        repository=repository,
        schema=SCHEMA,
    )
    assert result.status is HistoryStatus.COMMITTED
    assert git(tmp_path, "show", "--format=", "--name-only", "HEAD").strip() == "marta.md"


def test_create_and_multi_note_attribution_make_one_commit(tmp_path: Path) -> None:
    """Attribute newly created and multiple successful notes to one request commit."""
    repository = vault(tmp_path)
    recorder = GitHistoryRecorder(repository.root)
    snapshot = recorder.begin("request-create")
    for path, entity_id in (("marta.md", "marta"), ("laura.md", "laura")):
        create_entity(
            repository,
            SCHEMA,
            path=path,
            entity_id=entity_id,
            metadata={
                "name": entity_id.title(),
                "type": "person",
                "relationship_to_user": "amiga",
            },
            content=f"# {entity_id.title()}\n",
            actor="fixture",
            now="2026-08-29T10:00:00+02:00",
        )
    result = recorder.record(
        request_id="request-create",
        snapshot=snapshot,
        affected_stable_note_ids=("marta", "laura"),
        repository=repository,
        schema=SCHEMA,
    )
    assert result.status is HistoryStatus.COMMITTED
    assert set(git(tmp_path, "show", "--format=", "--name-only", "HEAD").split()) == {
        "marta.md",
        "laura.md",
    }


def test_git_commit_failure_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Expose commit failure to the application boundary without filesystem rollback."""
    repository = vault(tmp_path)
    note(repository)
    recorder = GitHistoryRecorder(repository.root)
    snapshot = recorder.begin("request-failure")
    repository.replace_text("marta.md", repository.read_text("marta.md") + "Changed.\n")

    original_run = recorder._run

    def fail_commit(root: Path, *args: str, **kwargs: object):
        """Fail only the commit operation while retaining normal Git inspection behavior."""
        if "commit" in args:
            raise RuntimeError("Git operation failed: commit")
        return original_run(root, *args, **kwargs)

    monkeypatch.setattr(recorder, "_run", fail_commit)
    with pytest.raises(RuntimeError, match="commit"):
        recorder.record(
            request_id="request-failure",
            snapshot=snapshot,
            affected_stable_note_ids=("marta",),
            repository=repository,
            schema=SCHEMA,
        )
    assert "Changed." in repository.read_text("marta.md")
