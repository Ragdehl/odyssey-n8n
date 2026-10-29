"""Offline, secret-free guards for the disposable authenticated #157 browser path."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.odyssey_n8n_dynamic_webhook import BROKER_JS, docker_command

ROOT = Path(__file__).resolve().parents[2]


def test_family_case_refuses_live_provider_before_spawning_any_services(tmp_path):
    """A family test cannot accidentally consume a paid GPT session."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(ROOT),
        "ODYSSEY_E4_RECORDED": "0",
        "ODYSSEY_E4_RECORDED_CASE": "issue157_day",
    }
    response = subprocess.run(
        [sys.executable, str(ROOT / "scripts/odyssey_e4_live_browser_n8n.py")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert response.returncode != 0
    assert "Family fixture requires recorded model responses" in response.stderr
    assert not list(tmp_path.iterdir())


def test_recorded_n8n_container_is_networkless_and_only_mounts_ephemeral_test_files():
    """The tested n8n command cannot see the host's DEV/PROD canonical vaults."""
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-dynamic-", dir="/tmp") as wf_root,
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-bridge-", dir="/tmp") as bridge_root,
    ):
        fixture = Path(wf_root) / "workflow.json"
        fixture.write_text("{}", encoding="utf-8")
        bridge = Path(bridge_root)
        (bridge / "broker.cjs").write_text(BROKER_JS, encoding="utf-8")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(str(bridge / "writer.sock"))
            argv = docker_command(fixture, bridge)
        assert argv[argv.index("--network") + 1] == "none"
        assert "--read-only" in argv
        assert argv[argv.index("--cap-drop") + 1] == "ALL"
        assert argv[argv.index("--security-opt") + 1] == "no-new-privileges"
        mounts = [
            argv[index + 1] for index, argument in enumerate(argv[:-1]) if argument == "--mount"
        ]
        assert len(mounts) == 2
        assert {mount.split(",target=")[1].split(",")[0] for mount in mounts} == {
            "/fixture/workflow.json",
            "/bridge",
        }
        assert set(mounts) == {
            f"type=bind,source={fixture},target=/fixture/workflow.json,readonly",
            f"type=bind,source={bridge},target=/bridge,readonly",
        }
        assert not any("/data/odyssey" in arg for arg in argv)
