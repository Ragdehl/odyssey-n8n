"""Pure guards for real n8n Webhook opt-in with a disposable Writer fixture.

No Docker containers, credentials, network, user-owned vault or GPT required.
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import pytest

from scripts import odyssey_n8n_isolated_webhook as webhook


def _real_writer_shape():
    return {
        "status": "completed",
        "request_id": "n8n-real-webhook-synthetic-20261019",
        "execution_flow": {
            "input": "Ayer hablé con Maya.",
            "routes": [
                {
                    "writes": [
                        {"status": "succeeded", "target": "date:2026-10-15"},
                        {"status": "succeeded", "target": "synthetic-maya"},
                    ]
                }
            ],
        },
        "affected_stable_note_ids": ["date:2026-10-15", "synthetic-maya"],
    }


def _real_code():
    return {
        "mode": "runOnceForAllItems",
        "language": "javaScript",
        "jsCode": "const x=$('Odyssey product request').item.json.body.request_id;"
        "return [{json:{request_id:x}}];",
    }


def test_isolated_n8n_webhook_has_separate_authorized_and_forbidden_paths():
    wf = webhook.real_webhook_workflow(_real_writer_shape(), _real_code())
    assert wf["id"] == webhook.WEBHOOK_ID
    assert wf["active"] is False
    assert len(wf["nodes"]) == 7
    assert [node["type"] for node in wf["nodes"]] == [
        "n8n-nodes-base.webhook",
        "n8n-nodes-base.code",
        "n8n-nodes-base.if",
        "n8n-nodes-base.code",
        "n8n-nodes-base.code",
        "n8n-nodes-base.respondToWebhook",
        "n8n-nodes-base.respondToWebhook",
    ]
    assert wf["nodes"][0]["name"] == webhook.NODE_REF
    assert wf["nodes"][0]["parameters"]["responseMode"] == "responseNode"
    assert wf["nodes"][5]["parameters"]["respondWith"] == "firstIncomingItem"
    assert wf["nodes"][6]["parameters"]["options"]["responseCode"] == 403
    assert wf["nodes"][4]["name"] == webhook.NODE
    assert wf["nodes"][4]["parameters"] == _real_code()
    assert len(wf["connections"]) == 5
    branch = wf["connections"][wf["nodes"][2]["name"]]["main"]
    assert branch[0][0]["node"] == wf["nodes"][3]["name"]
    assert branch[1][0]["node"] == wf["nodes"][6]["name"]
    assert (
        wf["nodes"][2]["parameters"]["conditions"]["conditions"][0]["leftValue"]
        == "={{ $json.approved }}"
    )
    assert not any("credentials" in node for node in wf["nodes"])
    assert not any(node["type"] == "n8n-nodes-base.httpRequest" for node in wf["nodes"])


def test_fixture_code_rejects_wrong_request_id_and_original_source():
    wf = webhook.real_webhook_workflow(_real_writer_shape(), _real_code())
    code = wf["nodes"][3]["parameters"]["jsCode"]
    guard = wf["nodes"][1]["parameters"]["jsCode"]
    assert "b.request_id===" in guard and "b.request===" in guard
    assert "INVALID_SYNTHETIC_WEBHOOK_INPUT" in code
    assert "$('Odyssey product request').first().json.body" in code
    assert "b.request_id!==" in code
    assert "b.request!==" in code
    assert "Ayer hablé con Maya." in code
    assert "n8n-real-webhook-synthetic-20261019" in code
    assert "return [{json:" in code


@pytest.mark.parametrize("tamper", ("incorrect_id", "bad_status", "missing_writes", "extra_route"))
def test_unverified_writer_never_becomes_an_http_response(tamper):
    raw = copy.deepcopy(_real_writer_shape())
    if tamper == "incorrect_id":
        raw["request_id"] = "different-actor"
    if tamper == "bad_status":
        raw["status"] = "needs_attention"
    if tamper == "missing_writes":
        raw["execution_flow"]["routes"][0]["writes"] = []
    if tamper == "extra_route":
        raw["execution_flow"]["routes"].append(raw["execution_flow"]["routes"][0])
    with pytest.raises(ValueError):
        webhook.real_webhook_workflow(raw, _real_code())


def test_real_n8n_webhook_container_lacks_external_network_privileges_and_ports(tmp_path):
    with tempfile.TemporaryDirectory(prefix="odyssey-n8n-real-webhook-", dir="/tmp") as name:
        input_file = Path(name) / "workflow.json"
        input_file.write_text("{}")
        command = webhook.safe_docker_command(input_file)
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--pull") + 1] == "never"
    assert "--read-only" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--security-opt") + 1] == "no-new-privileges"
    assert "--publish" not in command and "-p" not in command
    mounts = [command[n + 1] for n, v in enumerate(command) if v == "--mount"]
    assert len(mounts) == 1
    assert "target=/fixture/workflow.json,readonly" in mounts[0]
    assert not any("/data/" in v or "/home/" in v or "docker.sock" in v for v in mounts)
    assert not any("OPENAI_API_KEY" in v or "CLOUDFLARE" in v for v in command)
    assert webhook.IMAGE == "docker.n8n.io/n8nio/n8n:2.33.7"


def test_http_checks_include_positive_and_three_negative_real_requests():
    shell = webhook.SHELL
    assert "n8n import:workflow --input" in shell
    assert "n8n publish:workflow --id" in shell
    assert "n8n start" in shell
    assert "http://127.0.0.1:5678/webhook/" in shell
    assert "request_id:'wrong-user'" in shell
    assert "request:'An unrelated request.'" in shell
    assert "method:'GET'" in shell
    assert "negativesBlocked" in shell
    assert "wrongId.status===403" in shell
    assert "wrongSource.status===403" in shell
    assert "writes?.length===2" in shell


def test_unsafe_synthetic_mount_is_rejected(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        webhook.safe_docker_command(tmp_path / "not-a-file")
    symlink = tmp_path / "redirect-workflow.json"
    target = tmp_path / "real-workflow.json"
    target.write_text("{}")
    symlink.symlink_to(target)
    with pytest.raises(ValueError):
        webhook.safe_docker_command(symlink)
    with pytest.raises(ValueError):
        webhook.safe_docker_command(Path(__file__).resolve())
