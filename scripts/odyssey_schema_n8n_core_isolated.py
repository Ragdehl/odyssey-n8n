#!/usr/bin/env python3
"""Real isolated n8n Webhook + actual Notes validator -> Core/E3/Git.

One offline n8n Docker container, one owned AF_UNIX bridge and one synthetic
vault in /tmp. No user notes, DEV deployment, provider calls or network ports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from odyssey_core.notes import parse_note  # noqa: E402
from odyssey_core.schema_retrospection_jobs import LocalSchemaScanJobs  # noqa: E402
from scripts.odyssey_n8n_dynamic_webhook import BROKER_JS  # noqa: E402
from scripts.odyssey_n8n_isolated_projection import IMAGE, _node  # noqa: E402
from scripts.odyssey_schema_n8n_engine_offline import source_code  # noqa: E402
from tests.runtime.test_schema_backfill_notes_vertical import ALICE, fixture  # noqa: E402

ID = "odyssey-schema-core-isolated-20261026"
URL_PATH = "odyssey-schema-core-offline-20261026"
MARKER = "ODYSSEY_SCHEMA_CORE_N8N="

SCRIPT = r"""
set -eu
node /bridge/broker.cjs >/tmp/broker.log 2>/tmp/broker.err &
broker=$!
n8n import:workflow --input /fixture/workflow.json >/tmp/import.log 2>/tmp/import.err
n8n publish:workflow --id odyssey-schema-core-isolated-20261026 >/tmp/publish.log 2>/tmp/publish.err
n8n start >/tmp/start.log 2>/tmp/start.err &
child=$!
trap 'kill "$broker" "$child" 2>/dev/null || true; wait "$broker" "$child" 2>/dev/null || true' EXIT
node <<'JS'
const target='http://127.0.0.1:5678/webhook/odyssey-schema-core-offline-20261026';
const base={target_type_id:'person',property_id:'profesion',expected_revision:1};
const valid=[
 {operation:'schema_scan',scan_kind:'backfill_property',...base,action:'advance'},
 {operation:'schema_backfill',...base,action:'stage'},
 {operation:'schema_backfill',...base,action:'advance'},
 {operation:'schema_backfill',...base,action:'advance'},
 {operation:'schema_backfill',...base,action:'status'},
 {operation:'schema_backfill',...base,action:'advance'}
];
const bad=[
 {operation:'schema_backfill',...base,action:'advance',actor_id:'forged'},
 {operation:'schema_backfill',...base,action:'advance',approved:true},
 {operation:'schema_backfill',...base,action:'delete'},
 {operation:'schema_backfill',...base,action:'advance',expected_revision:true},
 {operation:'schema_backfill',...base,action:'advance',note_id:'other'}
];
async function post(value){
 const r=await fetch(target,{method:'POST',
   headers:{'content-type':'application/json'},body:JSON.stringify(value),
   signal:AbortSignal.timeout(25000)});
 let response=null;try{response=await r.json()}catch{}
 return {code:r.status,json:response};
}
async function run(){
 let start=null,last='not_ready',attempts=0;
 for(let i=0;i<80;i++){
  attempts++;
  try{
   const x=await post(valid[0]);
   if(x.code===200&&x.json?.kind==='schema_scan'&&x.json?.status==='complete'){
    start=x;break;
   }
   last='not_ready_'+x.code;
  }catch(e){last=e?.name||'not_ready';}
  await new Promise(done=>setTimeout(done,650));
 }
 if(!start){
  console.log('ODYSSEY_SCHEMA_CORE_N8N='+JSON.stringify({pass:false,reason:last,attempts}));
  process.exitCode=3;return;
 }
 const results=[start];
 for(const x of valid.slice(1))results.push(await post(x));
 const negatives=[];
 for(const x of bad)negatives.push(await post(x));
 const pass=results.every(x=>x.code===200)&&results.length===6&&
  results[1].json?.pending===2&&
  results[2].json?.updated===1&&
  results[3].json?.deferred===1&&
  results[4].json?.status==='awaiting_ai'&&
  results[5].json?.updated===1&&
  results[5].json?.deferred===1&&
  negatives.every(x=>x.code===403);
 console.log('ODYSSEY_SCHEMA_CORE_N8N='+JSON.stringify({
  pass,attempts,read:true,stage:results[1].json?.pending,
  updated:results[2].json?.updated,deferred:results[4].json?.deferred,
  replayWithoutAdditionalUpdates:results[5].json?.updated===1,
  rejected:negatives.filter(x=>x.code===403).length,
  realN8n:true,realCore:true,provider:'NONE',deployedDev:false
 }));
 if(!pass)process.exitCode=7;
}
run().catch(error=>{
 console.log('ODYSSEY_SCHEMA_CORE_N8N='+JSON.stringify({
 pass:false,reason:'isolated_runner_error',type:error?.name||'unknown'}));
 process.exitCode=4;
});
JS
"""


def workflow() -> dict:
    hook = {
        "id": "schema-fixture-webhook",
        "name": "Synthetic Notes webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [100, 160],
        "webhookId": "schema-only-offline",
        "parameters": {
            "httpMethod": "POST",
            "path": URL_PATH,
            "responseMode": "responseNode",
            "options": {},
        },
    }
    validation = {**_node("Validate Notes request", source_code()), "position": [350, 160]}
    test = {
        "id": "filter-invalid",
        "name": "Authenticated Notes only",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [540, 160],
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2,
                },
                "combinator": "and",
                "conditions": [
                    {
                        "id": "notes-validity",
                        "leftValue": "={{ $json.invalid !== true }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
            }
        },
    }
    core = {
        "id": "real-schema-core",
        "name": "Invoke real synthetic Core",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.5,
        "position": [740, 80],
        "parameters": {
            "method": "POST",
            "url": "http://127.0.0.1:8799/execute",
            "sendBody": True,
            "contentType": "json",
            "specifyBody": "json",
            "jsonBody": "={{ $json }}",
            "options": {"timeout": 26000},
            "response": {"response": {"neverError": False, "responseFormat": "json"}},
        },
    }
    accepted = {
        "id": "return-canonical-schema",
        "name": "Return actual Core result",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.4,
        "position": [950, 80],
        "parameters": {"respondWith": "firstIncomingItem", "options": {"responseCode": 200}},
    }
    rejected = {
        "id": "reject-untrusted-shape",
        "name": "Reject untrusted Notes input",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.4,
        "position": [730, 340],
        "parameters": {
            "respondWith": "json",
            "responseBody": '{"error":"INVALID_SYNTHETIC_NOTES"}',
            "options": {"responseCode": 403},
        },
    }

    def to(name: str) -> dict:
        return {"node": name, "type": "main", "index": 0}

    return {
        "id": ID,
        "name": "Odyssey real offline schema webhook/Core",
        "active": False,
        "nodes": [hook, validation, test, core, accepted, rejected],
        "settings": {"executionOrder": "v1"},
        "connections": {
            hook["name"]: {"main": [[to(validation["name"])]]},
            validation["name"]: {"main": [[to(test["name"])]]},
            test["name"]: {"main": [[to(core["name"])], [to(rejected["name"])]]},
            core["name"]: {"main": [[to(accepted["name"])]]},
        },
    }


def docker_argv(flow: Path, share: Path) -> list[str]:
    """Never mount DEV, PROD, home, Docker socket or credentials."""
    if (
        flow.is_symlink()
        or share.is_symlink()
        or flow.parent.parent != Path("/tmp")
        or share.parent != Path("/tmp")
        or not flow.parent.name.startswith("odyssey-schema-core-")
        or not share.name.startswith("odyssey-schema-socket-")
        or flow.name != "workflow.json"
        or flow.stat().st_size > 130000
        or share.stat().st_uid != os.getuid()
        or (share / "broker.cjs").read_text() != BROKER_JS
        or not (share / "writer.sock").is_socket()
    ):
        raise ValueError("Real n8n may only use synthetic temporary fixtures")
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
        "--pids-limit",
        "180",
        "--tmpfs",
        "/tmp:rw,mode=1777,size=192m",
        "-e",
        "N8N_USER_FOLDER=/tmp/odyssey-synthetic-schema",
        "-e",
        "N8N_DIAGNOSTICS_ENABLED=false",
        "-e",
        "N8N_PERSONALIZATION_ENABLED=false",
        "-e",
        "N8N_TEMPLATES_ENABLED=false",
        "-e",
        "N8N_ENCRYPTION_KEY=synthetic-not-actual-credentials",
        "--mount",
        f"type=bind,source={flow},target=/fixture/workflow.json,readonly",
        "--mount",
        f"type=bind,source={share},target=/bridge,readonly",
        "--entrypoint",
        "/bin/sh",
        IMAGE,
        "-c",
        SCRIPT,
    ]


def run() -> dict:
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-schema-core-", dir="/tmp") as tmp,
        tempfile.TemporaryDirectory(prefix="odyssey-schema-socket-", dir="/tmp") as bridge,
    ):
        root, share = Path(tmp), Path(bridge)
        os.chmod(share, 0o700)
        fixture_root = root / "data"
        fixture_root.mkdir()
        app, repo, state = fixture(fixture_root)
        app.schema_scan_factory = lambda actor: LocalSchemaScanJobs(
            state_root=state, repository=repo, actor_id=actor
        )
        before = {
            p: hashlib.sha256(repo.read_text(p).encode()).hexdigest()
            for p in repo.list_markdown_paths()
        }
        counters: dict = {"accepted": 0, "denied": 0}

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                raw = self.rfile.readline(16001)
                reply: dict = {"status": 403, "body": {"error": "DENIED"}}
                try:
                    payload = json.loads(raw)
                    valid_actor = payload.get("authenticated_actor") == {
                        "stable_user_id": ALICE.stable_user_id
                    }
                    operation = payload.get("operation")
                    keys = {
                        "operation",
                        "target_type_id",
                        "property_id",
                        "expected_revision",
                        "action",
                        "authenticated_actor",
                    } | ({"scan_kind"} if operation == "schema_scan" else set())
                    if (
                        len(raw) <= 16000
                        and type(payload) is dict
                        and set(payload) == keys
                        and valid_actor
                        and operation in {"schema_scan", "schema_backfill"}
                        and payload["target_type_id"] == "person"
                        and payload["property_id"] == "profesion"
                        and type(payload["expected_revision"]) is int
                        and payload["expected_revision"] == 1
                        and payload["action"] in {"stage", "advance", "status"}
                        and (
                            operation != "schema_scan"
                            or (
                                payload.get("scan_kind") == "backfill_property"
                                and payload["action"] != "stage"
                            )
                        )
                    ):
                        body = {
                            key: value
                            for key, value in payload.items()
                            if key not in {"operation", "authenticated_actor"}
                        }
                        reply = {"status": 200, "body": app.notes(operation, body, ALICE)}
                        counters["accepted"] += 1
                    else:
                        counters["denied"] += 1
                except (ValueError, TypeError, KeyError):
                    counters["denied"] += 1
                self.wfile.write((json.dumps(reply, ensure_ascii=False) + "\n").encode())

        sock = share / "writer.sock"
        with socketserver.ThreadingUnixStreamServer(str(sock), Handler) as unix:
            os.chmod(sock, 0o600)
            thread = threading.Thread(target=unix.serve_forever, daemon=True)
            thread.start()
            try:
                (share / "broker.cjs").write_text(BROKER_JS)
                os.chmod(share / "broker.cjs", 0o444)
                flow = root / "workflow.json"
                flow.write_text(json.dumps(workflow(), ensure_ascii=False))
                result = subprocess.run(
                    docker_argv(flow, share),
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=165,
                )
            finally:
                unix.shutdown()
                unix.server_close()
                thread.join(timeout=5)
        signals = [
            json.loads(line.split(MARKER, 1)[1])
            for line in result.stdout.splitlines()
            if line.startswith(MARKER)
        ]
        if len(signals) != 1:
            raise RuntimeError(
                "Isolated n8n/Core did not return verdict; exit="
                + str(result.returncode)
                + ", stderr-tail="
                + result.stderr[-350:]
            )
        evidence = signals[0]
        after = {
            p: hashlib.sha256(repo.read_text(p).encode()).hexdigest()
            for p in repo.list_markdown_paths()
        }
        notes = {p: parse_note(repo.read_text(p)).metadata for p in after}
        commits = int(
            subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
            ).strip()
        )
        accepted = (
            result.returncode == 0
            and evidence.get("pass") is True
            and counters["accepted"] == 6
            and counters["denied"] == 0
            and notes["0.md"]["profesion"] == "médica"
            and notes["0.md"]["revision"] == 2
            and "profesion" not in notes["1.md"]
            and commits == 2
            and after["0.md"] != before["0.md"]
            and after["1.md"] == before["1.md"]
        )
        return {
            "pass": accepted,
            "n8n": "real isolated Webhook, Code, IF and HTTP Request",
            "validator": "exact current Notes JS",
            "provider": "NONE",
            "browser": "NOT_TESTED",
            "deployedDEV": False,
            "n8nResult": evidence,
            "coreCalls": counters["accepted"],
            "gitCommits": commits,
            "markdownUpdated": 1,
            "deferredUnchanged": after["1.md"] == before["1.md"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("Use --run to launch one offline n8n/Core synthetic fixture")
        return 0
    result = run()
    print("ODYSSEY_SCHEMA_CORE_ISOLATED=" + json.dumps(result, ensure_ascii=False))
    return 0 if result["pass"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
