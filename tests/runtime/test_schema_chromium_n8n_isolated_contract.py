"""Never conflate isolated actual browser+n8n+Core with deployed DEV acceptance."""

from pathlib import Path

import pytest

from scripts.odyssey_schema_chromium_n8n_isolated import (
    INGRESS,
    SHELL,
)
from scripts.odyssey_schema_n8n_core_isolated import docker_argv

ROOT = Path(__file__).resolve().parents[2]


def test_offline_chromium_n8n_two_way_socket_is_bounded():
    js = (ROOT / "scripts/odyssey_schema_backfill_chromium_local.cjs").read_text()
    driver = (ROOT / "scripts/odyssey_schema_chromium_n8n_isolated.py").read_text()
    assert "ODYSSEY_SYNTH_N8N_SOCKET" in js
    assert "socketPath:n8nSocket" in js
    assert "isSocket()" in js
    assert "schema_backfill:advance" in js
    assert "n8nSocket ? body" in js
    assert "schema_scan" in INGRESS and "schema_backfill" in INGRESS
    assert "actor_id" not in INGRESS
    assert "approved" not in INGRESS
    assert "http://127.0.0.1:5678/webhook/" in INGRESS
    assert "n8n publish:workflow" in SHELL
    assert "n8n start" in SHELL
    assert "--followup" in driver
    assert "ODYSSEY_SYNTH_FOLLOWUP" in driver + js
    assert "stage_followup" in INGRESS
    assert "advance_followup" in INGRESS
    assert "gateway.calls == 2" in driver
    assert "AbortSignal.timeout(90000)" in INGRESS
    assert 'core_node["parameters"]["options"]["timeout"] = 90000' in driver
    assert "timeout=190 if followup_mode else 90" in driver
    assert "timeout:followup?95000:20000" in js
    assert "timeout:105000" in js
    assert "docker_argv(flow, share)" in driver
    assert "args[mount].removesuffix(" in driver
    assert "process.wait(timeout=10)" in driver
    assert "TemporaryDirectory(prefix=" in driver
    assert "assert" in driver
    assert "evidence[" in driver
    assert "source-code" not in INGRESS.lower()
    assert "/data/odyssey" not in INGRESS + driver


def test_unsafe_fixture_is_rejected_before_docker_run(tmp_path):
    flow = tmp_path / "workflow.json"
    flow.write_text("{}")
    share = tmp_path / "bridge"
    share.mkdir()
    with pytest.raises((ValueError, FileNotFoundError)):
        docker_argv(flow, share)


def test_not_deployed_ambiguity_protected():
    python_source = (ROOT / "scripts/odyssey_schema_chromium_n8n_isolated.py").read_text()
    assert '"DEV": "NOT_DEPLOYED"' in python_source
    assert '"provider": "FAKE_STRUCTURED_NO_NETWORK" if args.followup else "NONE"' in python_source
    assert '"deployedDev": False' in python_source
    assert "browserReload" in python_source
    assert "after" in python_source
    assert "before" in python_source
    assert "commits == 2" in python_source
    assert 'request_socket(ingress, "/health")' in python_source
