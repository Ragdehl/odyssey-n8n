"""Dynamic P4 n8n integration contract; no Docker or provider needed."""

from __future__ import annotations

import json
import socket
import tempfile
from pathlib import Path

import pytest

from scripts import odyssey_n8n_dynamic_webhook as dynamic


def _code() -> dict:
    return {
        "mode": "runOnceForAllItems",
        "language": "javaScript",
        "jsCode": "return [{json:$input.first().json}];",
    }


def test_webhook_to_actual_writer_http_node_and_original_dev_code_is_one_chain():
    original = _code()
    wf = dynamic.workflow(original, "Ayer hablé con Maya.")
    assert wf["active"] is False
    assert wf["id"] == dynamic.ID
    assert [n["type"] for n in wf["nodes"]] == [
        "n8n-nodes-base.webhook",
        "n8n-nodes-base.code",
        "n8n-nodes-base.if",
        "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.code",
        "n8n-nodes-base.respondToWebhook",
        "n8n-nodes-base.respondToWebhook",
    ]
    assert wf["nodes"][4]["name"] == dynamic.NODE
    assert wf["nodes"][4]["parameters"] == original
    assert wf["nodes"][3]["parameters"]["url"] == "http://127.0.0.1:8799/execute"
    assert wf["nodes"][3]["parameters"]["method"] == "POST"
    assert wf["nodes"][3]["parameters"]["sendBody"] is True
    assert "request_id:" in wf["nodes"][3]["parameters"]["jsonBody"]
    assert "request:" in wf["nodes"][3]["parameters"]["jsonBody"]
    assert not any(node.get("credentials") for node in wf["nodes"])
    assert not any("Synthetic actual Core Writer output" == node["name"] for node in wf["nodes"])


def test_explicit_403_branch_precedes_dynamic_http_write():
    wf = dynamic.workflow(_code(), "Ayer hablé con Maya.")
    nodes = wf["nodes"]
    con = wf["connections"]
    start, guard, branch, writer, original, success, denied = nodes
    assert con[start["name"]]["main"][0][0]["node"] == guard["name"]
    assert con[guard["name"]]["main"][0][0]["node"] == branch["name"]
    assert con[branch["name"]]["main"][0][0]["node"] == writer["name"]
    assert con[branch["name"]]["main"][1][0]["node"] == denied["name"]
    assert con[writer["name"]]["main"][0][0]["node"] == original["name"]
    assert con[original["name"]]["main"][0][0]["node"] == success["name"]
    assert denied["parameters"]["options"]["responseCode"] == 403
    assert success["parameters"]["options"]["responseCode"] == 200
    assert "b.request_id===" in guard["parameters"]["jsCode"]
    assert "b.request===" in guard["parameters"]["jsCode"]


@pytest.mark.parametrize("invalid", ["", "a" * 1001])
def test_bounded_synthetic_source_is_required(invalid):
    with pytest.raises(ValueError):
        dynamic.workflow(_code(), invalid)


def test_source_is_embedded_as_json_not_raw_js_code():
    text = 'Maya dijo: "hola"; \u003cscript>alert(1)</script>'
    workflow = dynamic.workflow(_code(), text)
    validator = workflow["nodes"][1]["parameters"]["jsCode"]
    assert json.dumps(text, ensure_ascii=False) in validator


def test_container_is_networkless_with_only_a_workflow_file_and_local_unix_socket():
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-dynamic-", dir="/tmp") as work,
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-bridge-", dir="/tmp") as bridge,
    ):
        workflow = Path(work) / "workflow.json"
        workflow.write_text("{}")
        share = Path(bridge)
        (share / "broker.cjs").write_text(dynamic.BROKER_JS)
        path = share / "writer.sock"
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(path))
            command = dynamic.docker_command(workflow, share)
        assert "--network" in command
        assert command[command.index("--network") + 1] == "none"
        assert command[command.index("--pull") + 1] == "never"
        assert "--read-only" in command
        assert command[command.index("--cap-drop") + 1] == "ALL"
        assert command[command.index("--security-opt") + 1] == "no-new-privileges"
        assert "-p" not in command and "--publish" not in command
        mounts = [command[i + 1] for i, token in enumerate(command) if token == "--mount"]
        assert len(mounts) == 2
        assert mounts[0].endswith("target=/fixture/workflow.json,readonly")
        assert mounts[1].endswith("target=/bridge,readonly")
        assert all("/data/" not in mount and "/home/" not in mount for mount in mounts)
        assert not any("OPENAI_API_KEY" in x or "CLOUDFLARE" in x for x in command)
        assert dynamic.IMAGE == "docker.n8n.io/n8nio/n8n:2.33.7"


def test_trick_paths_and_vault_access_cannot_be_mounted(tmp_path):
    f = tmp_path / "workflow.json"
    f.write_text("{}")
    with pytest.raises(ValueError):
        dynamic.docker_command(f, tmp_path)
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-dynamic-", dir="/tmp") as work,
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-bridge-", dir="/tmp") as bridge,
    ):
        workflow = Path(work) / "workflow.json"
        workflow.write_text("{}")
        (Path(bridge) / "broker.cjs").write_text(dynamic.BROKER_JS)
        with pytest.raises(ValueError):
            dynamic.docker_command(workflow, Path(bridge))
        (Path(bridge) / "writer.sock").symlink_to(tmp_path)
        with pytest.raises(ValueError):
            dynamic.docker_command(workflow, Path(bridge))


def test_local_broker_has_narrow_execute_route_and_bounded_messages():
    js = dynamic.BROKER_JS
    shell = dynamic.SHELL
    assert "req.url!=='/execute'" in js
    assert "req.method!=='POST'" in js
    assert "raw.length>16000" in js
    assert "createConnection(SOCK)" in js
    assert ".listen(8799,'127.0.0.1'" in js
    assert "127.0.0.1:5678/webhook/" in shell
    assert "n8n start" in shell
    assert "n8n import:workflow" in shell
    assert "n8n publish:workflow" in shell
    assert "wrong_id_http" in shell
    assert "response.status===200" in shell
    assert "real_writer_called_from_webhook:true" in shell


def test_guarded_socket_cannot_be_a_symlink_to_another_unix_server():
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-dynamic-", dir="/tmp") as work,
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-bridge-", dir="/tmp") as bridge,
    ):
        wf = Path(work) / "workflow.json"
        wf.write_text("{}")
        target = Path(work) / "other.sock"
        share = Path(bridge)
        (share / "broker.cjs").write_text(dynamic.BROKER_JS)
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(target))
            (share / "writer.sock").symlink_to(target)
            with pytest.raises(ValueError):
                dynamic.docker_command(wf, share)


def test_broker_source_must_be_pinned_and_not_mutated():
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-dynamic-", dir="/tmp") as work,
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-bridge-", dir="/tmp") as bridge,
    ):
        wf = Path(work) / "workflow.json"
        wf.write_text("{}")
        share = Path(bridge)
        (share / "broker.cjs").write_text("console.log('unexpected network proxy')")
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(share / "writer.sock"))
            with pytest.raises(ValueError):
                dynamic.docker_command(wf, share)
