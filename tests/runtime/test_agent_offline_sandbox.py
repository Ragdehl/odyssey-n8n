"""Linux-only, disposable proof that offline test processes cannot read Odyssey DEV/PROD."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "scripts/odyssey_agent_offline_sandbox.py"
SPEC = importlib.util.spec_from_file_location("odyssey_agent_offline_sandbox", SRC)
assert SPEC and SPEC.loader
sandbox = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sandbox)

BWRAP_READY = shutil.which("bwrap") == "/usr/bin/bwrap"


def test_offline_sandbox_rejects_real_workspaces_and_symlink_aliases(tmp_path):
    with pytest.raises(sandbox.OfflineSandboxError, match="disposable"):
        sandbox.command_for_sandbox(tmp_path, ["/usr/bin/python3", "-V"])
    safe_alias = Path("/tmp/odyssey-agent-sandbox-symlink-escape-test")
    if not safe_alias.exists() and not safe_alias.is_symlink():
        safe_alias.symlink_to(tmp_path, target_is_directory=True)
        try:
            with pytest.raises(sandbox.OfflineSandboxError, match="disposable"):
                sandbox.command_for_sandbox(safe_alias, ["/usr/bin/python3", "-V"])
        finally:
            safe_alias.unlink()


@pytest.mark.skipif(not BWRAP_READY, reason="Host lacks Linux Bubblewrap")
def test_live_kernel_namespaces_hide_real_home_and_network():
    with tempfile.TemporaryDirectory(prefix="odyssey-agent-sandbox-", dir="/tmp") as folder:
        host_home = str(Path.home())
        snippet = """
import json,os,socket
from pathlib import Path
paths = [
  '__HOME__/.codex',
  '__HOME__/.ssh',
  '__HOME__/projects/odyssey-dev',
  '__HOME__/projects/odyssey-e3-mutation',
  '/data',
]
socket_ok=False
try:
    sock=socket.socket()
    sock.settimeout(0.3)
    sock.connect(('127.0.0.1',28780))
    socket_ok=True
except OSError:
    pass
finally:
    sock.close()
Path('/workspace/only-synthetic.txt').write_text('sandbox marker')
print(json.dumps({'paths':{x:Path(x).exists() for x in paths},
  'network_visible':socket_ok,'workspace_write':Path('/workspace/only-synthetic.txt').is_file()}))
""".replace("__HOME__", host_home)
        command = sandbox.command_for_sandbox(Path(folder), ["/usr/bin/python3", "-c", snippet])
        assert "--unshare-net" in command
        assert "--unshare-pid" in command
        assert "--clearenv" in command
        output = sandbox.run_synthetic(Path(folder), ["/usr/bin/python3", "-c", snippet])
        assert output.returncode == 0, output.stderr
        report = json.loads(output.stdout)
        assert not any(report["paths"].values())
        assert report["network_visible"] is False
        assert report["workspace_write"] is True
        assert (Path(folder) / "only-synthetic.txt").read_text() == "sandbox marker"


@pytest.mark.skipif(not BWRAP_READY, reason="Host lacks Linux Bubblewrap")
def test_symlink_in_sandbox_cannot_escape_into_real_home():
    with tempfile.TemporaryDirectory(prefix="odyssey-agent-sandbox-", dir="/tmp") as folder:
        workspace = Path(folder)
        host_target = str(Path.home() / "projects" / "odyssey-dev")
        (workspace / "escape").symlink_to(host_target)
        snippet = """from pathlib import Path
print(Path('/workspace/escape').exists())
"""
        output = sandbox.run_synthetic(workspace, ["/usr/bin/python3", "-c", snippet])
        assert output.returncode == 0
        assert output.stdout.strip() == "False"


def test_offline_sandbox_rejects_unapproved_executable_and_bad_timeout():
    with tempfile.TemporaryDirectory(prefix="odyssey-agent-sandbox-", dir="/tmp") as folder:
        with pytest.raises(sandbox.OfflineSandboxError, match="read-only"):
            sandbox.command_for_sandbox(Path(folder), ["/workspace/program"])
        with pytest.raises(sandbox.OfflineSandboxError, match="nonempty"):
            sandbox.command_for_sandbox(Path(folder), [])
        with pytest.raises(sandbox.OfflineSandboxError, match="1-60"):
            sandbox.run_synthetic(Path(folder), ["/usr/bin/python3", "-V"], timeout=0)


def test_missing_bubblewrap_still_fails_closed_for_valid_workspace(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _name: None)
    with tempfile.TemporaryDirectory(prefix="odyssey-agent-sandbox-", dir="/tmp") as folder:
        with pytest.raises(sandbox.OfflineSandboxError, match="Bubblewrap"):
            sandbox.command_for_sandbox(Path(folder), ["/usr/bin/python3", "-V"])
