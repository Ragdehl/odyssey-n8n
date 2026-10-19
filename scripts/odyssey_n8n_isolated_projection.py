#!/usr/bin/env python3
"""Run real n8n Code execution against real P4 Writer output in a NO-NET container.

Only synthetic Markdown is created under an auto-deleted /tmp vault. No user
credentials, n8n DB, DEV/PROD mounts, model network, webhooks, or deployment.
This verifies an ACTUAL deployed n8n Code-node revision, not the full workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED_RENDER = Path("/data/odyssey-dev/runtime/n8n-render/odyssey-online.json")
sys.path.insert(0, str(ROOT))
IMAGE = "docker.n8n.io/n8nio/n8n:2.33.7"
ID = "odysseyp4synth20261019"
NODE = "Route bounded product result"
NODE_REF = "Odyssey product request"

# This command executes inside a disposable Docker container with zero network.
# It imports the synthetic workflow into a temporary SQLite DB, executes the
# real n8n node engine, and reports only structural properties.
EXECUTE_IN_CONTAINER = r"""
set -eu
n8n import:workflow --input /fixture/workflow.json > /tmp/import.log 2>&1
n8n execute --id odysseyp4synth20261019 --rawOutput > /tmp/execution.json 2>/tmp/n8n-errors.log
node -e '
const fs=require("node:fs");
const raw=fs.readFileSync("/tmp/execution.json","utf8");
const start=raw.indexOf("{");
if(start<0)throw Error("n8n CLI produced no JSON");
const d=JSON.parse(raw.slice(start));
const runs=d?.data?.resultData?.runData?.["Route bounded product result"];
const r=runs?.at(-1)?.data?.main?.[0]?.[0]?.json;
const writes=r?.request_detail?.flow?.routes?.[0]?.writes;
const snapshot=r?.note_result_snapshot;
const final = {
 passed: d.status==="success" && d.finished===true &&
   r?.route==="direct" && r?.status==="completed" &&
   r?.kind==="acknowledgement" && writes?.length===2 &&
   writes.every(w=>w.status==="succeeded") &&
   snapshot?.kind==="affected_notes" && snapshot?.total===2 &&
   r?.request_detail?.changes?.affected_stable_note_ids?.length===2,
 execution_status:d?.status||"missing",
 has_execution_flow:Array.isArray(r?.request_detail?.flow?.routes),
 write_receipts:writes?.length||0,
 notes:snapshot?.total||0,
 node_name:"Route bounded product result",
 node_execution_count:runs?.length||0
};
console.log("ODYSSEY_ISOLATED_N8N_RESULT="+JSON.stringify(final));
if(!final.passed)process.exitCode=7;
'
"""


def _node(name: str, code: str = "", kind: str = "n8n-nodes-base.code") -> dict:
    return {
        "id": re.sub("[^a-z0-9]+", "-", name.lower()).strip("-"),
        "name": name,
        "type": kind,
        "typeVersion": 1 if kind.endswith("manualTrigger") else 2,
        "position": [220, 260],
        "parameters": {}
        if kind.endswith("manualTrigger")
        else {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": code},
    }


def validated_deployed_projection(path: Path) -> dict:
    """Read only the pinned deployed DEV artifact; never import remote secrets."""
    if path != PINNED_RENDER or path.resolve(strict=True) != PINNED_RENDER.resolve(strict=True):
        raise ValueError("Only the exact deployed DEV render path is supported")
    workflow = json.loads(path.read_text())
    matches = [node for node in workflow.get("nodes", ()) if node.get("name") == NODE]
    if len(matches) != 1:
        raise ValueError("Expected exactly one canonical n8n routing node")
    match = matches[0]
    if match.get("type") != "n8n-nodes-base.code" or "credentials" in match:
        raise ValueError("Only credential-free real Code node is accepted")
    code = match.get("parameters", {}).get("jsCode")
    if not isinstance(code, str) or not 500 <= len(code) <= 64000:
        raise ValueError("Invalid canonical Code source size")
    if set(re.findall(r"\$\('([^']+)'\)", code)) != {NODE_REF}:
        raise ValueError("Unexpected additional n8n workflow dependency")
    return {"jsCode": code, "mode": "runOnceForAllItems", "language": "javaScript"}


def generate_workflow(real_result: dict, code_params: dict) -> dict:
    if real_result.get("status") != "completed" or (
        len(real_result.get("affected_stable_note_ids", ())) != 2
    ):
        raise ValueError("Expected an authentic two-write Core success")
    identifier = real_result["request_id"]
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", identifier):
        raise ValueError("Synthetic request id is invalid")
    from_source = _node("Start synthetic fixture", kind="n8n-nodes-base.manualTrigger")
    request = _node(
        NODE_REF,
        "return [{json:{body:{request_id:" + json.dumps(identifier) + "}}}];",
    )
    response = _node(
        "Synthetic Core Writer output",
        "return [{json:" + json.dumps(real_result, ensure_ascii=False) + "}];",
    )
    actual = {**_node(NODE), "parameters": code_params}
    members = [from_source, request, response, actual]
    links = {
        before["name"]: {"main": [[{"node": after["name"], "type": "main", "index": 0}]]}
        for before, after in zip(members[:-1], members[1:], strict=True)
    }
    return {
        "id": ID,
        "name": "Odyssey offline real n8n projection",
        "nodes": members,
        "connections": links,
        "settings": {"executionOrder": "v1"},
        "active": False,
    }


def docker_command(input_path: Path) -> list[str]:
    """Never mount private data or allow n8n to reach host services."""
    return [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,mode=1777,size=96m",
        "-e",
        "N8N_USER_FOLDER=/tmp/test-n8n",
        "-e",
        "N8N_DIAGNOSTICS_ENABLED=false",
        "-e",
        "N8N_PERSONALIZATION_ENABLED=false",
        "-e",
        "N8N_ENCRYPTION_KEY=synthetic-only-no-live-secret-20261019",
        "--mount",
        f"type=bind,source={input_path},target=/fixture/workflow.json,readonly",
        "--entrypoint",
        "/bin/sh",
        IMAGE,
        "-c",
        EXECUTE_IN_CONTAINER,
    ]


def run() -> dict:
    from tests.runtime.test_whole_source_light_product_p4 import (
        RecordedClient,
        _actual_snapshot,
        _fixture,
        _speaker,
    )

    if shutil.which("docker") is None:
        raise RuntimeError("Docker unavailable: real n8n isolation cannot be verified")
    code_params = validated_deployed_projection(PINNED_RENDER)
    with tempfile.TemporaryDirectory(prefix="odyssey-n8n-no-network-", dir="/tmp") as folder:
        root = Path(folder)
        source, route, plan, review = _actual_snapshot("maya_simple")
        (root / "physical").mkdir()
        repo, actor, executor, runtime = _fixture(root / "physical")
        executor.client = RecordedClient(
            [
                route,
                plan,
                review,
                _speaker(source, plan, base=1),
                _speaker(source, plan),
            ]
        )
        raw = runtime.execute_product(source, "n8n-realcode-fixture-20261019", "main", actor)
        assert raw["status"] == "completed"
        assert len(raw["execution_flow"]["routes"][0]["writes"]) == 2
        assert len(repo.list_markdown_paths()) == 4

        input_path = root / "n8n-fixture.json"
        input_path.write_text(json.dumps(generate_workflow(raw, code_params), ensure_ascii=False))
        command = docker_command(input_path)
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=110,
            check=False,
        )
        markers = [
            row.removeprefix("ODYSSEY_ISOLATED_N8N_RESULT=")
            for row in result.stdout.splitlines()
            if row.startswith("ODYSSEY_ISOLATED_N8N_RESULT=")
        ]
        if result.returncode or len(markers) != 1:
            raise RuntimeError(
                f"Offline n8n execution not accepted (rc={result.returncode}, "
                f"result_count={len(markers)}). Log category: "
                f"{'exec_failed' if result.returncode else 'no_verdict'}"
            )
        data = json.loads(markers[0])
        if data.get("passed") is not True:
            raise RuntimeError("Real n8n projection rejected synthetic Writer output")
        # The in-container node did not mutate the already-materialized vault.
        assert len(repo.list_markdown_paths()) == 4
        assert executor.client.rows == []
        return {
            **data,
            "n8n_version": "2.33.7",
            "actual_n8n_code": True,
            "actual_n8n_workflow_engine": True,
            "isolated_n8n_db": True,
            "no_network": True,
            "host_mount_count": 1,
            "mounted_source_is_synthetic_workflow_only": True,
            "gpt_live": False,
            "actual_n8n_webhook": False,
            "access_authentication": False,
            "notes_written_to_dev_or_prod": False,
            "source_code_artifact": "deployed_DEV_read_only",
        }


if __name__ == "__main__":
    # A single explicit opt-in is required because this starts a Docker container.
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--run", action="store_true")
    args = cli.parse_args()
    if not args.run:
        cli.error("Explicit --run required; never launch Docker via implicit imports")
    try:
        print(json.dumps(run(), indent=2))
    except Exception as error:
        print(json.dumps({"passed": False, "failure": type(error).__name__}))
        sys.exit(1)
