"""Read-only Odyssey start-of-work context, without loading or displaying secrets.

This command diagnoses state; it never grants permission to deploy, merge,
change local files, or call billable model providers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV_ROOT = Path("/home/ragdehl/projects/odyssey-dev")
DEV_MARKER = Path("/data/odyssey-dev/runtime/deployed-commit")
PROTECTED_ENV = Path("/home/ragdehl/.config/odyssey/secrets.env")


def _command(
    *args: str,
    cwd: Path | None = None,
    timeout: float = 4.0,
    env: dict[str, str] | None = None,
) -> str | None:
    """Return bounded diagnostic command stdout or None on failure/timeout."""
    try:
        result = subprocess.run(
            args, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _git(repo: Path, *args: str) -> str | None:
    """Read Git metadata without modifying the worktree."""
    if not (repo / ".git").exists():
        return None
    return _command("git", *args, cwd=repo)


def _marker(path: Path) -> str | None:
    """Read a deployment marker if it is a plausible full hex commit ID."""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value if re.fullmatch(r"[a-f0-9]{40}", value) else None


def _health(url: str) -> str:
    """Obtain one bounded HTTP health status; never dump response bodies."""
    return (
        _command(
            "curl",
            "--silent",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            "--max-time",
            "2",
            url,
            timeout=3.0,
        )
        or "unknown"
    )


def _active_processes() -> dict[str, int | str]:
    """Count concurrent release/agent commands, never return process arguments."""
    raw = _command("ps", "-eo", "args", timeout=3.0)
    if raw is None:
        return {"status": "unknown"}
    # Detection is a hint, not a locking primitive or confirmation of ownership.
    tokens = {
        "deployment": ("odyssey-dev deploy", "odyssey-prod deploy"),
        "agent_supervisor": ("odyssey_agent_cycle.py run",),
        "codex": ("codex exec",),
    }
    return {
        key: sum(any(token in line for token in needles) for line in raw.splitlines()[1:])
        for key, needles in tokens.items()
    }


def inspect(
    *,
    repo: Path = ROOT,
    dev_root: Path = DEV_ROOT,
    marker_path: Path = DEV_MARKER,
    env_path: Path = PROTECTED_ENV,
    check_health: bool = True,
) -> dict[str, object]:
    """Return non-secret diagnostic state with explicit unknowns and mismatches."""
    src = _git(repo, "rev-parse", "HEAD")
    dev = _git(dev_root, "rev-parse", "HEAD")
    marker = _marker(marker_path)
    local_changes = _git(repo, "status", "--porcelain")
    remote = _git(repo, "rev-parse", "--verify", "refs/remotes/origin/dev")
    branch = _git(repo, "branch", "--show-current")
    dirty = None if local_changes is None else bool(local_changes)
    env_present = env_path.is_file()
    env_readable = env_present and os.access(env_path, os.R_OK)
    user_env = os.environ.copy()
    user_env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
    user_env.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    # Read a benign property only; never query/show the user's environment.
    manager = _command(
        "systemctl",
        "--user",
        "show",
        "--property=Version",
        timeout=2.5,
        env=user_env,
    )
    systemd_available = bool(manager and manager.startswith("Version="))
    result: dict[str, object] = {
        "source_branch": branch or "unknown",
        "source_sha": src or "unknown",
        "source_clean": None if dirty is None else not dirty,
        "remote_dev_sha_from_local_refs": remote or "unknown",
        "dev_checkout_sha": dev or "unknown",
        "dev_deployed_marker": marker or "unknown",
        "dev_checkout_matches_marker": bool(dev and marker and dev == marker),
        "provider_environment": {
            "protected_file_present": env_present,
            "protected_file_readable": env_readable,
            "systemd_user_manager_available": systemd_available,
            "key_value_examined": False,
        },
        "concurrent_process_hints": _active_processes(),
    }
    if check_health:
        result["dev_health"] = {
            "runtime_http": _health("http://127.0.0.1:28765/healthz"),
            "n8n_http": _health("http://172.18.0.1:28780/healthz"),
        }
    result["warnings"] = [
        message
        for triggered, message in (
            (src is None, "Source Git state unavailable"),
            (dirty is True, "Source worktree contains uncommitted changes; do not overwrite"),
            (not marker or not dev, "DEV marker/checkout unknown; do not deploy"),
            (bool(dev and marker and dev != marker), "DEV checkout differs from deployment marker"),
            (
                not env_readable or not systemd_available,
                "Protected provider access unavailable; do not invent a credential path",
            ),
        )
        if triggered
    ]
    return result


def main() -> int:
    """Print read-only JSON or compact human-readable diagnostic results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Machine-readable safe status")
    parser.add_argument("--no-health", action="store_true", help="Skip local HTTP probes")
    args = parser.parse_args()
    result = inspect(check_health=not args.no_health)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key in (
            "source_branch",
            "source_sha",
            "source_clean",
            "dev_checkout_sha",
            "dev_deployed_marker",
            "dev_checkout_matches_marker",
        ):
            print(f"{key}: {result[key]}")
        print("provider_environment: " + json.dumps(result["provider_environment"], sort_keys=True))
        print("concurrent_process_hints: " + json.dumps(result["concurrent_process_hints"]))
        if "dev_health" in result:
            print("dev_health: " + json.dumps(result["dev_health"]))
        for warning in result["warnings"]:
            print("WARNING: " + warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
