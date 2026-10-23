"""Test Codex filesystem isolation with its actual Linux sandbox where available.

No model calls, provider credentials read, product writes, or external network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from scripts import odyssey_codex_permissions as scope

ROOT = Path(__file__).resolve().parents[2]
NATIVE = shutil.which("codex") is not None and os.name == "posix"


def test_explicit_profiles_deny_everything_except_minimal_runtime_git_and_workspace(monkeypatch):
    # This test inspects generated permissions without running the Codex CLI.
    # Hosted CI need not have the authenticated native binary installed.
    monkeypatch.setattr(
        scope,
        "codex_executable",
        lambda: Path("/tmp/synthetic-codex-install/releases/v1/codex"),
    )
    profile, args = scope.permission_overrides(ROOT, read_only=True)
    assert profile == "odyssey-scope-read"
    config = [args[i + 1] for i, value in enumerate(args) if value == "--config"]
    assert 'default_permissions="odyssey-scope-read"' in config
    filesystem = next(
        value for value in config if value.startswith("permissions.") and ".filesystem=" in value
    )
    assert '":root"="deny"' in filesystem
    assert '":minimal"="read"' in filesystem
    assert '":workspace_roots"=' in filesystem
    assert '"."="read"' in filesystem
    assert '"**/*.env"="deny"' in filesystem
    assert '"**/.env.*"="deny"' in filesystem
    assert any(value.endswith(".network.enabled=false") for value in config)
    assert not any(".network.domains" in value for value in config)
    _, editable = scope.permission_overrides(ROOT, read_only=False)
    assert any('"."="write"' in value for value in editable)


def test_permission_profiles_reject_workspaces_outside_own_git_repository(tmp_path):
    with pytest.raises(scope.ScopeError, match="Git"):
        scope.permission_overrides(tmp_path, read_only=True)


@pytest.mark.skipif(not NATIVE, reason="Codex native binary not installed")
def test_actual_codex_native_sandbox_both_profiles_isolate_worktree(tmp_path):
    # Disposable isolated worktree, removed no matter how the sandbox responds.
    with tempfile.TemporaryDirectory(prefix="odyssey-agent-scope-test-", dir="/tmp") as base:
        checkout = Path(base) / "checkout"
        created = subprocess.run(
            ["git", "-C", str(ROOT), "worktree", "add", "--detach", str(checkout), "HEAD"],
            capture_output=True,
            text=True,
            timeout=35,
            check=False,
        )
        assert created.returncode == 0, "Cannot create a clean isolated Git test worktree"
        try:
            read = scope.probe_native_profile(checkout, read_only=True)
            edit = scope.probe_native_profile(checkout, read_only=False)
            assert read["scope_verified"] and edit["scope_verified"]
            assert read["workspace_read_only"] is True
            assert edit["workspace_read_only"] is False
            assert read["private_paths_denied"] == edit["private_paths_denied"] == 3
            assert read["network_denied"] and edit["network_denied"]
            assert not (checkout / ".odyssey-permission-probe-marker").exists()
        finally:
            subprocess.run(
                ["git", "-C", str(ROOT), "worktree", "remove", "--force", str(checkout)],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
