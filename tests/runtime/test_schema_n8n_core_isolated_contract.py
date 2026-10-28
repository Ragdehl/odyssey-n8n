"""Safety boundaries for opt-in isolated, real n8n schema/Core webhook."""

from pathlib import Path

import pytest

from scripts.odyssey_schema_n8n_core_isolated import (
    SCRIPT,
    docker_argv,
    workflow,
)
from scripts.odyssey_schema_n8n_engine_offline import source_code


def test_n8n_core_fixture_uses_exact_notes_code_and_no_secrets():
    raw = Path("scripts/odyssey_schema_n8n_core_isolated.py").read_text()
    flow = workflow()
    assert flow["active"] is False
    assert len(flow["nodes"]) == 6
    assert (
        next(node for node in flow["nodes"] if node["name"] == "Validate Notes request")[
            "parameters"
        ]["jsCode"]
        == source_code()
    )
    for node in flow["nodes"]:
        assert "credentials" not in node
    assert "schema_backfill" in SCRIPT and "schema_scan" in SCRIPT
    for denied in (
        "actor_id:'forged'",
        "approved:true",
        "action:'delete'",
        "expected_revision:true",
        "note_id:'other'",
    ):
        assert denied in SCRIPT
    for important in (
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "no-new-privileges",
        "--pids-limit",
        "target=/fixture/workflow.json,readonly",
        "target=/bridge,readonly",
    ):
        assert important in raw
    assert "/data/odyssey" not in raw
    assert "OPENAI_API_KEY" not in raw
    assert '"--run", action="store_true"' in raw


def test_rejects_non_temporary_mount_roots(tmp_path):
    flow = tmp_path / "workflow.json"
    flow.write_text("{}")
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    with pytest.raises((ValueError, FileNotFoundError)):
        docker_argv(flow, bridge)


def test_exact_workflow_validates_before_core_http_request():
    graph = workflow()["connections"]
    assert graph["Synthetic Notes webhook"]["main"][0][0]["node"] == "Validate Notes request"
    assert graph["Validate Notes request"]["main"][0][0]["node"] == "Authenticated Notes only"
    accepted, rejected = graph["Authenticated Notes only"]["main"]
    assert accepted[0]["node"] == "Invoke real synthetic Core"
    assert rejected[0]["node"] == "Reject untrusted Notes input"
    assert graph["Invoke real synthetic Core"]["main"][0][0]["node"] == "Return actual Core result"
