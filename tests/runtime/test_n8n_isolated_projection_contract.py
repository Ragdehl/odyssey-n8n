"""Offline guards for the opt-in real n8n Code-node synthetic compatibility test.

No Docker, user n8n database, model provider or actual webhooks are invoked.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import scripts.odyssey_n8n_isolated_projection as isolation


def _pinned_synthetic_artifact(tmp_path, monkeypatch, code: str):
    artifact = tmp_path / "render.json"
    artifact.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "name": isolation.NODE,
                        "type": "n8n-nodes-base.code",
                        "parameters": {"jsCode": code},
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(isolation, "PINNED_RENDER", artifact)
    return artifact


def test_actual_projection_is_pinned_to_only_rendered_code_node(tmp_path, monkeypatch):
    code = (
        "const r=$input.first().json;"
        "const id=$('Odyssey product request').item.json.body.request_id;"
        + " " * 520
        + "return [{json:{id,r}}];"
    )
    fixture = _pinned_synthetic_artifact(tmp_path, monkeypatch, code)
    params = isolation.validated_deployed_projection(fixture)
    assert params["jsCode"] == code
    assert params["mode"] == "runOnceForAllItems"
    with pytest.raises(ValueError, match="exact deployed"):
        isolation.validated_deployed_projection(tmp_path / "not-pinned.json")


@pytest.mark.parametrize(
    "alteration",
    ("second_dependency", "credentials", "duplicate_node", "external_type"),
)
def test_untrusted_n8n_artifacts_are_rejected_before_docker(tmp_path, monkeypatch, alteration):
    code = "const id=$('Odyssey product request').item.json.body.request_id;" + " " * 560
    artifact = _pinned_synthetic_artifact(tmp_path, monkeypatch, code)
    data = json.loads(artifact.read_text())
    node = data["nodes"][0]
    if alteration == "second_dependency":
        node["parameters"]["jsCode"] += "$('DEV private vault').item.json;"
    elif alteration == "credentials":
        node["credentials"] = {"unsafe": "never"}
    elif alteration == "duplicate_node":
        data["nodes"].append(copy.deepcopy(node))
    elif alteration == "external_type":
        node["type"] = "n8n-nodes-base.httpRequest"
    artifact.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        isolation.validated_deployed_projection(artifact)


def test_n8n_synthetic_workflow_has_only_manual_and_code_and_no_credentials():
    result = {
        "request_id": "n8n-contract-1",
        "status": "completed",
        "affected_stable_note_ids": ["date:2026-10-15", "synthetic-maya"],
        "execution_flow": {
            "routes": [{"writes": [{"status": "succeeded"}, {"status": "succeeded"}]}]
        },
    }
    params = {
        "jsCode": "return [{json:$input.first().json}];",
        "mode": "runOnceForAllItems",
        "language": "javaScript",
    }
    workflow = isolation.generate_workflow(result, params)
    assert workflow["id"] == isolation.ID
    assert len(workflow["nodes"]) == 4
    assert [node["type"] for node in workflow["nodes"]] == [
        "n8n-nodes-base.manualTrigger",
        "n8n-nodes-base.code",
        "n8n-nodes-base.code",
        "n8n-nodes-base.code",
    ]
    assert len(workflow["connections"]) == 3
    assert not workflow["active"]
    assert not any(node.get("credentials") for node in workflow["nodes"])
    assert workflow["nodes"][-1]["parameters"] == params
    for changed in [
        {**result, "status": "needs_attention"},
        {**result, "affected_stable_note_ids": []},
        {**result, "request_id": "bad/../../id"},
    ]:
        with pytest.raises(ValueError):
            isolation.generate_workflow(changed, params)


def test_docker_isolation_contract_is_fail_closed_and_no_network_or_vault_mounts():
    # Exact command sent to Docker must be audited before any unattended
    # extension. Here we test fixed engine invariants, not an actual container.
    assert "n8n import:workflow" in isolation.EXECUTE_IN_CONTAINER
    assert "n8n execute --id" in isolation.EXECUTE_IN_CONTAINER
    assert "ODYSSEY_ISOLATED_N8N_RESULT=" in isolation.EXECUTE_IN_CONTAINER
    cmd = isolation.docker_command(Path("/tmp/odyssey-n8n-no-network-fixture/workflow.json"))
    assert cmd[cmd.index("--network") + 1] == "none"
    assert "--read-only" in cmd
    assert cmd[cmd.index("--pull") + 1] == "never"
    assert cmd[cmd.index("--cap-drop") + 1] == "ALL"
    assert cmd[cmd.index("--security-opt") + 1] == "no-new-privileges"
    mounts = [cmd[i + 1] for i, word in enumerate(cmd) if word == "--mount"]
    assert len(mounts) == 1
    assert mounts[0] == (
        "type=bind,source=/tmp/odyssey-n8n-no-network-fixture/workflow.json,"
        "target=/fixture/workflow.json,readonly"
    )
    assert not any("/data/odyssey" in value or "/home/ragdehl" in value for value in cmd)
