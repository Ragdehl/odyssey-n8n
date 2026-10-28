#!/usr/bin/env python3
"""Real n8n Notes validator on synthetic cases, network-disabled disposable engine."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.odyssey_n8n_isolated_projection import IMAGE, _node  # noqa: E402

RUN_ID = "odyssey-schema-backfill-engine-20261026"


def source_code() -> str:
    text = (ROOT / "workflows/odyssey-online.ts").read_text()
    frag = text[text.index("const notesValidate = node(") :]
    frag = frag[: frag.index("\nconst notesValid = node(")]
    backtick = chr(96)
    code = frag.split("jsCode: " + backtick, 1)[1].split(backtick + " }, position:", 1)[0]
    var = chr(36)
    code = code.replace(
        var + "{conversationIdentity}",
        "const authenticated_actor = {stable_user_id: '00000000-0000-4000-8000-000000000001'};",
    )
    code = code.replace(
        var
        + "{deploymentEnvironment === 'DEV' ? ', authenticated_actor' : ', external_principal'}",
        ", authenticated_actor",
    )
    if var + "{" in code or not 5000 < len(code) < 65000:
        raise RuntimeError("Invalid source Notes validator extraction")
    return code


def workflow() -> dict:
    correct = {
        "operation": "schema_backfill",
        "target_type_id": "person",
        "property_id": "profesion",
        "expected_revision": 1,
        "action": "advance",
    }
    cases = [
        ("valid", correct),
        ("followup_stage", {**correct, "action": "stage_followup"}),
        ("followup_status", {**correct, "action": "status_followup"}),
        ("followup_advance", {**correct, "action": "advance_followup"}),
        ("forged", {**correct, "authenticated_actor": {"stable_user_id": "forged"}}),
        ("bad_action", {**correct, "action": "reset"}),
        ("scan", {**correct, "operation": "schema_scan", "scan_kind": "backfill_property"}),
        ("bool_version", {**correct, "expected_revision": True}),
        ("extra_approval", {**correct, "approved": True}),
        ("forged_followup", {**correct, "action": "advance_followup", "job_id": "forged"}),
    ]
    nodes = [
        {
            "id": "manual",
            "name": "Begin synthetic validator",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [120, 220],
            "parameters": {},
        }
    ]
    edges = {}
    previous = nodes[0]["name"]
    for i, (label, body) in enumerate(cases):
        incoming = _node(
            "Synthetic request " + label, "return [{json:{body:" + json.dumps(body) + "}}];"
        )
        validator = _node("Validate " + label, source_code())
        incoming["position"] = [280 + 330 * i, 220]
        validator["position"] = [450 + 330 * i, 220]
        nodes.extend((incoming, validator))
        edges[previous] = {"main": [[{"node": incoming["name"], "type": "main", "index": 0}]]}
        edges[incoming["name"]] = {
            "main": [[{"node": validator["name"], "type": "main", "index": 0}]]
        }
        previous = validator["name"]
    return {
        "id": RUN_ID,
        "name": "Real n8n isolated Notes Code test",
        "active": False,
        "nodes": nodes,
        "connections": edges,
        "settings": {"executionOrder": "v1"},
    }


SHELL = r"""
set -eu
n8n import:workflow --input /fixture/workflow.json >/tmp/import.log 2>/tmp/import.err
n8n execute --id odyssey-schema-backfill-engine-20261026 --rawOutput >/tmp/trace.json 2>/tmp/n8n.err
node <<'JS'
const fs=require('node:fs');
const raw=fs.readFileSync('/tmp/trace.json','utf8');
const start=raw.indexOf('{');if(start<0)throw Error('missing n8n result');
const trace=JSON.parse(raw.slice(start));
const names=['valid','followup_stage','followup_status','followup_advance','forged','bad_action','scan','bool_version','extra_approval','forged_followup'];
const results={};
for(const name of names){
 results[name]=trace?.data?.resultData?.runData?.['Validate '+name]
  ?.at(-1)?.data?.main?.[0]?.[0]?.json||null;
}
const actor='00000000-0000-4000-8000-000000000001';
const pass=trace.status==='success' && trace.finished===true &&
 names.every(x=>results[x]!==null) &&
 results.valid?.operation==='schema_backfill' &&
 results.valid?.authenticated_actor?.stable_user_id===actor &&
 results.valid?.invalid!==true &&
 ['stage_followup','status_followup','advance_followup']
  .every((a,i)=>results[['followup_stage','followup_status','followup_advance'][i]]?.action===a &&
   results[['followup_stage','followup_status','followup_advance'][i]]?.invalid!==true &&
   results[['followup_stage','followup_status','followup_advance'][i]]?.authenticated_actor?.stable_user_id===actor) &&
 results.scan?.operation==='schema_scan' &&
 results.scan?.authenticated_actor?.stable_user_id===actor &&
 results.scan?.invalid!==true &&
 ['forged','bad_action','bool_version','extra_approval','forged_followup']
  .every(x=>results[x]?.invalid===true);
console.log('ODYSSEY_SCHEMA_N8N_ENGINE='+JSON.stringify({
 pass, engine:'real n8n 2', code:'exact current Notes validator',
 allowed:5,rejected:['forged','bad_action','bool_version','extra_approval','forged_followup']
  .filter(x=>results[x]?.invalid===true).length, provider:'NONE',deployedDev:false}));
if(!pass)process.exitCode=7;
JS
"""


def run() -> dict:
    with tempfile.TemporaryDirectory(prefix="odyssey-schema-n8n-engine-", dir="/tmp") as tmp:
        workflow_file = Path(tmp) / "workflow.json"
        workflow_file.write_text(json.dumps(workflow(), ensure_ascii=False))
        assert not workflow_file.is_symlink() and workflow_file.stat().st_size < 140000
        argv = [
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
            "--pids-limit",
            "180",
            "--tmpfs",
            "/tmp:rw,mode=1777,size=192m",
            "-e",
            "N8N_USER_FOLDER=/tmp/test-n8n-schema",
            "-e",
            "N8N_DIAGNOSTICS_ENABLED=false",
            "-e",
            "N8N_PERSONALIZATION_ENABLED=false",
            "-e",
            "N8N_ENCRYPTION_KEY=synthetic-only-no-real-secrets",
            "--mount",
            "type=bind,source=" + str(workflow_file) + ",target=/fixture/workflow.json,readonly",
            "--entrypoint",
            "/bin/sh",
            IMAGE,
            "-c",
            SHELL,
        ]
        finished = subprocess.run(argv, capture_output=True, text=True, timeout=135)
    parsed = [
        json.loads(line.split("ODYSSEY_SCHEMA_N8N_ENGINE=", 1)[1])
        for line in finished.stdout.splitlines()
        if line.startswith("ODYSSEY_SCHEMA_N8N_ENGINE=")
    ]
    if len(parsed) != 1:
        raise RuntimeError(
            "Real n8n did not produce a result (exit "
            + str(finished.returncode)
            + ", error: "
            + finished.stderr[-350:]
            + ")"
        )
    return {**parsed[0], "pass": finished.returncode == 0 and parsed[0]["pass"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("Run with --run to execute the isolated real n8n Docker engine.")
        return 0
    result = run()
    print("ODYSSEY_SCHEMA_N8N_RESULT=" + json.dumps(result))
    return 0 if result["pass"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
