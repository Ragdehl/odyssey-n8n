#!/usr/bin/env python3
"""Least-privilege Codex native execution profiles, tested before any model runs.

These permissions govern Codex-executed shell/tool commands, not the Codex
client's own provider authentication. Never grant full host read or network.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

PROFILE_READ = "odyssey-scope-read"
PROFILE_EDIT = "odyssey-scope-edit"


class ScopeError(RuntimeError):
    pass


def codex_executable() -> Path:
    launcher = shutil.which("codex")
    if not launcher:
        raise ScopeError("Codex CLI not installed")
    binary = Path(launcher).resolve(strict=True)
    home = Path.home().resolve()
    # The authenticated Codex binary is in its own versioned install tree.
    expected = home / ".codex/packages/standalone/releases"
    if not binary.is_relative_to(expected):
        raise ScopeError("Unexpected Codex binary location; manual review required")
    return binary


def common_git_dir(repo: Path) -> Path:
    r = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise ScopeError("Cannot establish Git source for the agent worktree")
    common = Path(r.stdout.strip()).resolve(strict=True)
    # A worktree must be of the approved Odyssey checkout; forbid other repos.
    checkout = Path(__file__).resolve().parents[1]
    established = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    if established.returncode:
        raise ScopeError("Cannot verify Odyssey Git common directory")
    expected = Path(established.stdout.strip()).resolve(strict=True)
    if common != expected:
        raise ScopeError("Agent worktree is not linked to Odyssey repository")
    return common


def permission_overrides(worktree: Path, *, read_only: bool) -> tuple[str, list[str]]:
    """Return named profile and complete, self-contained CLI --config arguments."""
    dest = worktree.resolve(strict=True)
    if not dest.is_dir():
        raise ScopeError("Worktree must exist")
    git_dir = common_git_dir(dest)
    binary_dir = codex_executable().parent
    profile = PROFILE_READ if read_only else PROFILE_EDIT
    fs = {
        ":root": "deny",
        ":minimal": "read",
        str(binary_dir): "read",
        str(git_dir): "read",
        ":workspace_roots": {
            ".": "read" if read_only else "write",
            ".git": "read",
            "**/*.env": "deny",
            "**/.env.*": "deny",
        },
    }

    # The .git file in a worktree is read via the workspace permission.
    # Codex --config parses TOML, not JSON: a JSON dictionary would be a
    # string and silently cause the launcher to reject the profile.
    def toml_inline(mapping: dict) -> str:
        parts = []
        for key, value in mapping.items():
            rendered = toml_inline(value) if isinstance(value, dict) else json.dumps(value)
            parts.append(f"{json.dumps(key)}={rendered}")
        return "{" + ",".join(parts) + "}"

    args = [
        "--config",
        f'default_permissions="{profile}"',
        "--config",
        f"permissions.{profile}.filesystem=" + toml_inline(fs),
        "--config",
        f"permissions.{profile}.network.enabled=false",
        "--config",
        "features.network_proxy=false",
    ]
    return profile, args


PROBE = r"""import json,os,pathlib,socket,subprocess
home=pathlib.Path.home()
private=[
 home/".codex/auth.json",
 home/"projects/odyssey-dev",
 pathlib.Path("/data"),
]
read=[]
for p in private:
 try:
  fd=os.open(p,os.O_RDONLY)
  os.close(fd)
  read.append(True)
 except OSError:
  read.append(False)
try:
 s=socket.socket()
 s.close()
 network_available=True
except OSError:
 network_available=False
repo=pathlib.Path.cwd()
source_open=(repo/"AGENTS.md").read_text(encoding="utf-8").startswith("#")
git=subprocess.run(["git","status","--porcelain"],capture_output=True,text=True,timeout=8)
write=False
marker=repo/".odyssey-permission-probe-marker"
try:
 marker.write_text("synthetic test")
 write=True
 marker.unlink()
except OSError:
 pass
print(json.dumps({
 "private_readable":read,
 "network_socket_available":network_available,
 "workspace_source_readable":source_open,
 "git_status_ok":git.returncode==0,
 "workspace_writable":write,
}))
"""


def probe_native_profile(worktree: Path, *, read_only: bool) -> dict:
    """Zero-model OS access check using Codex's SAME policy as exec."""
    dest = worktree.resolve(strict=True)
    name, overrides = permission_overrides(dest, read_only=read_only)
    cmd = [
        "codex",
        "sandbox",
        "-P",
        name,
        "-C",
        str(dest),
        *overrides,
        "--",
        "/usr/bin/python3",
        "-c",
        PROBE,
    ]
    result = subprocess.run(cmd, cwd=dest, capture_output=True, text=True, timeout=25, check=False)
    # Never print the sandbox's stderr: keep provider/config details off logs.
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if result.returncode or len(lines) != 1:
        raise ScopeError("Native Codex permission profile refused or failed to start")
    try:
        proof = json.loads(lines[0])
    except (ValueError, TypeError) as exc:
        raise ScopeError("Invalid native profile proof") from exc
    expected_write = not read_only
    if (
        proof.get("private_readable") != [False, False, False]
        or proof.get("network_socket_available") is not False
        or proof.get("workspace_source_readable") is not True
        or proof.get("git_status_ok") is not True
        or proof.get("workspace_writable") is not expected_write
    ):
        raise ScopeError("Native Codex profile failed least-privilege OS proof")
    return {
        "profile": name,
        "scope_verified": True,
        "network_denied": True,
        "private_paths_denied": 3,
        "git_available": True,
        "workspace_read_only": read_only,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--role", choices=["review", "builder"], required=True)
    options = parser.parse_args()
    print(
        json.dumps(
            probe_native_profile(options.worktree, read_only=options.role == "review"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
