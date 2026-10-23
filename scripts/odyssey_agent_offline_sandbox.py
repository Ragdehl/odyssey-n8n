#!/usr/bin/env python3
"""Offline Linux filesystem/network proof sandbox for disposable Odyssey tests.

This sandbox deliberately has NO Codex credentials and NO network connectivity.
It is reusable for isolated test scripts, NOT for authenticated Codex model calls.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ISOLATOR = "/usr/bin/bwrap"
SYSTEM_BINDS = ("/usr", "/bin", "/lib")
RUNNER = "/usr/bin/python3"


class OfflineSandboxError(RuntimeError):
    pass


def command_for_sandbox(workspace: Path, program: list[str]) -> list[str]:
    """Expose only a scratch workspace; no home, DEV, PROD, codex or LAN."""
    # Validate the requested workspace and argv before checking host tooling.
    # Invalid requests must be rejected consistently, including in CI hosts
    # where Bubblewrap is not installed. A valid request still fails closed.
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise OfflineSandboxError("Sandbox requires an existing disposable workspace")
    # Never accept a model-controlled workspace pointing at the real user vault.
    # Both realpath and name are fixed to the purpose-built /tmp scratch prefix.
    if workspace.parent != Path("/tmp") or not workspace.name.startswith("odyssey-agent-sandbox-"):
        raise OfflineSandboxError("Only disposable /tmp/odyssey-agent-sandbox-* is permitted")
    if workspace.stat().st_uid != os.getuid():
        raise OfflineSandboxError("Scratch directory must belong to current user")
    if (
        not program
        or not isinstance(program, list)
        or not all(isinstance(x, str) and x and "\x00" not in x for x in program)
    ):
        raise OfflineSandboxError("Command must be a nonempty argv with no NUL")
    if not program[0].startswith("/usr/") and program[0] != "/bin/sh":
        raise OfflineSandboxError("Executable must reside in a read-only system bind")
    if shutil.which("bwrap") != ISOLATOR:
        raise OfflineSandboxError("Unprivileged Bubblewrap is required; fail closed")
    return [
        ISOLATOR,
        "--die-with-parent",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-net",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/lib",
        "/lib",
        "--tmpfs",
        "/etc",
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--dir",
        "/home",
        "--bind",
        str(workspace),
        "/workspace",
        "--chdir",
        "/workspace",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/workspace",
        "--",
        *program,
    ]


def run_synthetic(
    workspace: Path, program: list[str], timeout: int = 20
) -> subprocess.CompletedProcess[str]:
    if not 1 <= timeout <= 60:
        raise OfflineSandboxError("Offline test budget must be 1-60 seconds")
    return subprocess.run(
        command_for_sandbox(workspace, program),
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument(
        "--smoke", action="store_true", help="Use safe fixed denial-of-access probe"
    )
    args = parser.parse_args()
    if not args.smoke:
        parser.error("Only --smoke is supported; do not execute arbitrary unreviewed code")
    host_home = str(Path.home())
    sample = """import json,os,socket
from pathlib import Path
hidden = {name:Path(name).exists() for name in (
 '__HOME__/.codex','__HOME__/.ssh','__HOME__/projects/odyssey-dev',
 '__HOME__/projects/odyssey-prod-release','/data')}
probe=Path('/workspace/synthetic-marker.txt')
probe.write_text('safe sandbox test')
sock=socket.socket()
try:
 sock.settimeout(0.3)
 sock.connect(('127.0.0.1',28780))
 network_disabled=False
except OSError:
 network_disabled=True
finally:
 sock.close()
print(json.dumps({'hidden_host_paths':hidden,'writable_scratch':probe.is_file(),
                  'network_disabled':network_disabled}))
"""
    result = run_synthetic(args.workspace, [RUNNER, "-c", sample.replace("__HOME__", host_home)])
    if result.returncode:
        raise OfflineSandboxError(
            f"Offline sandbox failed safely: RC={result.returncode}: {result.stderr[:250]}"
        )
    report = json.loads(result.stdout.strip())
    print(json.dumps(report, indent=2))
    return (
        0
        if (
            report["writable_scratch"]
            and report["network_disabled"]
            and all(not present for present in report["hidden_host_paths"].values())
        )
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
