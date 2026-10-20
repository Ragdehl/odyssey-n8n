#!/usr/bin/env python3
"""Real n8n Webhook -> HTTP Request -> Unix broker -> real P4 Writer; synthetic only.

One n8n container with network NONE, only synthetic JSON + Unix socket mounted.
Python runtime on host can access only an ephemeral test VaultRepository and a
RecordedClient.  Zero actual DEV/PROD writes, provider traffic or credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.odyssey_n8n_isolated_projection import (  # noqa: E402
    IMAGE,
    NODE,
    NODE_REF,
    PINNED_RENDER,
    _node,
    validated_deployed_projection,
)

ID = "odysseyp4dynamicwebhook20261019"
PATH = "odyssey-p4-dynamic-synthetic-20261019"
REQUEST_ID = "n8n-dynamic-synthetic-20261019"
E4_SOURCE = "Hoy conocí a Marta. Mañana debo llamar a esa persona."

BROKER_JS = r"""
'use strict';
const http=require('node:http');
const net=require('node:net');
const SOCK='/bridge/writer.sock';
http.createServer((req,res)=>{
  if(req.method!=='POST'||req.url!=='/execute'){
    res.writeHead(403,{'content-type':'application/json'});return res.end('{}');
  }
  let raw='',done=false;
  function fail(code=502){if(done)return;done=true;res.writeHead(code);res.end('{}');}
  req.on('data',part=>{raw+=part.toString('utf8');
    if(raw.length>16000){req.destroy();fail(413);}
  });
  req.on('end',()=>{
    if(done)return;
    let data;
    try{data=JSON.parse(raw);}catch{return fail(400);}
    if(!data || typeof data!=='object')return fail(400);
    const connection=net.createConnection(SOCK);
    let reply='';
    connection.setTimeout(20000);
    connection.on('connect',()=>connection.write(JSON.stringify(data)+'\n'));
    connection.on('data',part=>{
      reply+=part.toString('utf8');
      if(reply.length>900000){connection.destroy();return fail(502);}
      const n=reply.indexOf('\n');
      if(n<0 || done)return;
      try {
        const parsed=JSON.parse(reply.slice(0,n));
        if(!Number.isInteger(parsed.status)||typeof parsed.body!=='object')throw Error('invalid');
        done=true;
        res.writeHead(parsed.status,{'content-type':'application/json','cache-control':'no-store'});
        res.end(JSON.stringify(parsed.body));
        connection.end();
      } catch {connection.destroy();fail(502);}
    });
    connection.on('error',()=>fail(502));
    connection.on('timeout',()=>{connection.destroy();fail(504);});
  });
}).listen(8799,'127.0.0.1',()=>console.log('BROKER_READY'));
"""

SHELL = r"""
set -eu
node /bridge/broker.cjs >/tmp/broker.log 2>/tmp/broker.err &
broker=$!
trap 'kill "$broker" "$child" 2>/dev/null || true; wait "$broker" "$child" 2>/dev/null || true' EXIT
n8n import:workflow --input /fixture/workflow.json >/tmp/import.log 2>/tmp/import.err
n8n publish:workflow --id odysseyp4dynamicwebhook20261019 >/tmp/publish.log 2>/tmp/publish.err
n8n start >/tmp/start.log 2>/tmp/start.err &
child=$!
node <<'JS'
const target='http://127.0.0.1:5678/webhook/odyssey-p4-dynamic-synthetic-20261019';
const original={request_id:'n8n-dynamic-synthetic-20261019',request:'Ayer hablé con Maya.'};
async function request(method,body){
  return await fetch(target,{method,headers:{'content-type':'application/json'},
    ...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(24000)});
}
async function main(){
  let response,valid,last='not_ready',attempts=0;
  for(let n=0;n<65;n++){
    attempts++;
    try{
      const r=await request('POST',original);
      if(r.status===200){
        try {
          const j=await r.json();
          if(j?.request_id===original.request_id && j?.status==='completed'
              && j?.request_detail?.flow?.routes?.reduce((n,r)=>n+(r.writes?.length||0),0)===2){
            response=r;valid=j;break;
          }
          last='unexpected_product_response';
        }catch{last='invalid_json_during_startup';}
      }else {last='not_ready_'+r.status;}
    }catch(err){last=err?.name||'socket_wait';}
    await new Promise(resolve=>setTimeout(resolve,700));
  }
  if(!valid){
    console.log('ODYSSEY_DYNAMIC_N8N='+JSON.stringify({pass:false,reason:last,attempts}));
    process.exitCode=3;return;
  }
  const replay=await request('POST',original);
  const again=await replay.json();
  const badId=await request('POST',{...original,request_id:'unknown-request'});
  const badSource=await request('POST',{...original,request:'Otro hecho inventado'});
  const badMethod=await request('GET',null);
  const writes=valid?.request_detail?.flow?.routes?.flatMap(r=>r.writes||[])||[];
  const result={
    pass:response.status===200 && replay.status===200 &&
      badId.status===403 && badSource.status===403 && badMethod.status===404 &&
      valid.kind==='acknowledgement' && valid.note_result_snapshot?.total===2 &&
      writes?.length===2 && writes.every(x=>x.status==='succeeded') &&
      again?.request_id===original.request_id && again?.status==='completed' &&
      again?.request_detail?.flow?.routes?.reduce((n,r)=>n+(r.writes?.length||0),0)===2,
    first_http:response.status,replay_http:replay.status,
    wrong_id_http:badId.status,wrong_source_http:badSource.status,
    wrong_method_http:badMethod.status,
    receipt_count:writes?.length||0,
    note_count:valid?.note_result_snapshot?.total||0,
    ready_attempts:attempts,real_writer_called_from_webhook:true
  };
  console.log('ODYSSEY_DYNAMIC_N8N='+JSON.stringify(result));
  if(!result.pass)process.exitCode=7;
}
main().catch(err=>{console.log('ODYSSEY_DYNAMIC_N8N='+JSON.stringify({
 pass:false,reason:'driver_exception',category:err?.name||'unknown'}));process.exitCode=4;});
JS
"""


# Both drivers are literally pinned fixtures: no inherited network credentials,
# remote payload or untrusted shell string may modify the n8n launch command.
E4_SHELL = SHELL.replace(
    "request:'Ayer hablé con Maya.'",
    "request:" + json.dumps(E4_SOURCE, ensure_ascii=False),
)
assert E4_SHELL != SHELL


def workflow(code: dict, text: str) -> dict:
    if not text or len(text) > 1000:
        raise ValueError("Only fixed bounded synthetic source is allowed")
    webhook = {
        "id": "synthetic-dynamic-webhook",
        "name": NODE_REF,
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 220],
        "webhookId": "odyssey-p4-dynamic-only",
        "parameters": {
            "httpMethod": "POST",
            "path": PATH,
            "responseMode": "responseNode",
            "options": {},
        },
    }
    guard = {
        **_node(
            "Validate isolated request",
            "const b=$('Odyssey product request').first().json.body;"
            "return [{json:{approved:!!b && b.request_id==="
            + json.dumps(REQUEST_ID)
            + " && b.request==="
            + json.dumps(text, ensure_ascii=False)
            + "}}];",
        ),
        "position": [365, 220],
    }
    branch = {
        "id": "synthetic-guard",
        "name": "Only known fixture",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [500, 220],
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
                        "id": "exact_fixture_guard",
                        "leftValue": "={{ $json.approved }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
            }
        },
    }
    writer = {
        "id": "dynamic-real-core-writer",
        "name": "Execute real P4 writer through restricted local bridge",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.5,
        "position": [665, 160],
        "parameters": {
            "method": "POST",
            "url": "http://127.0.0.1:8799/execute",
            "sendBody": True,
            "contentType": "json",
            "specifyBody": "json",
            "jsonBody": "={{ { request_id: $('Odyssey product request').first().json.body.request_id, request: $('Odyssey product request').first().json.body.request, conversation_id: 'main' } }}",
            "options": {"timeout": 26000},
            "response": {"response": {"neverError": False, "responseFormat": "json"}},
        },
    }
    original = {**_node(NODE), "position": [900, 160], "parameters": code}
    ok = {
        "id": "return-dynamic",
        "name": "Return genuine Writer result",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.4,
        "position": [1130, 160],
        "parameters": {"respondWith": "firstIncomingItem", "options": {"responseCode": 200}},
    }
    deny = {
        "id": "reject-dynamic",
        "name": "Reject other synthetic requests",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.4,
        "position": [680, 420],
        "parameters": {
            "respondWith": "json",
            "responseBody": '{"error":"INVALID_SYNTHETIC_REQUEST"}',
            "options": {"responseCode": 403},
        },
    }

    def edge(name: str) -> dict:
        return {"node": name, "type": "main", "index": 0}

    con = {
        webhook["name"]: {"main": [[edge(guard["name"])]]},
        guard["name"]: {"main": [[edge(branch["name"])]]},
        branch["name"]: {"main": [[edge(writer["name"])], [edge(deny["name"])]]},
        writer["name"]: {"main": [[edge(original["name"])]]},
        original["name"]: {"main": [[edge(ok["name"])]]},
    }
    return {
        "id": ID,
        "name": "Real n8n dynamic synthetic P4 Writer",
        "active": False,
        "nodes": [webhook, guard, branch, writer, original, ok, deny],
        "connections": con,
        "settings": {"executionOrder": "v1"},
    }


def docker_command(workflow_file: Path, bridge_dir: Path, *, driver: str = SHELL) -> list[str]:
    if driver not in (SHELL, E4_SHELL):
        raise ValueError("Only pinned offline product drivers are allowed")
    wf = workflow_file.resolve(strict=True)
    share = bridge_dir.resolve(strict=True)
    broker = share / "broker.cjs"
    socket_path = share / "writer.sock"
    if (
        workflow_file.is_symlink()
        or bridge_dir.is_symlink()
        or broker.is_symlink()
        or socket_path.is_symlink()
        or wf.is_symlink()
        or wf.name != "workflow.json"
        or wf.parent.parent != Path("/tmp")
        or not wf.parent.name.startswith("odyssey-n8n-dynamic-")
        or share.parent != Path("/tmp")
        or not share.name.startswith("odyssey-n8n-bridge-")
        or share.stat().st_uid != os.getuid()
        or wf.stat().st_uid != os.getuid()
        or not (0 < wf.stat().st_size < 300000)
        or not broker.is_file()
        or broker.stat().st_uid != os.getuid()
        or broker.read_text() != BROKER_JS
        or not socket_path.is_socket()
        or socket_path.stat().st_uid != os.getuid()
    ):
        raise ValueError("Only owned ephemeral fixture, bounded bridge and active local socket")
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
        "N8N_USER_FOLDER=/tmp/isolated-n8n-dynamic",
        "-e",
        "N8N_DIAGNOSTICS_ENABLED=false",
        "-e",
        "N8N_PERSONALIZATION_ENABLED=false",
        "-e",
        "N8N_TEMPLATES_ENABLED=false",
        "-e",
        "N8N_ENCRYPTION_KEY=synthetic-dynamic-no-real-credentials",
        "--mount",
        f"type=bind,source={wf},target=/fixture/workflow.json,readonly",
        "--mount",
        f"type=bind,source={share},target=/bridge,readonly",
        "--entrypoint",
        "/bin/sh",
        IMAGE,
        "-c",
        driver,
    ]


def run(case: str = "maya") -> dict:
    if case not in {"maya", "e4_person_task"}:
        raise ValueError("Only pinned synthetic cases are permitted")
    from odyssey_core.notes import parse_note
    from tests.runtime.test_whole_source_light_product_p4 import (
        RecordedClient,
        _actual_snapshot,
        _fixture,
        _speaker,
    )

    if shutil.which("docker") is None:
        raise RuntimeError("Isolated Docker n8n not available")
    code = validated_deployed_projection(PINNED_RENDER)
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-dynamic-", dir="/tmp") as root,
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-bridge-", dir="/tmp") as bridge,
    ):
        location = Path(root)
        share = Path(bridge)
        os.chmod(share, 0o700)
        (location / "vault").mkdir()
        if case == "maya":
            source, route, plan, review = _actual_snapshot("maya_simple")
            repo, actor, executor, runtime = _fixture(location / "vault")
            executor.client = RecordedClient(
                [route, plan, review, _speaker(source, plan, base=1), _speaker(source, plan)]
            )
        else:
            from tests.runtime.test_p4_fresh_person_task import _physical

            repo, actor, executor, runtime, source, _calls = _physical(location / "vault", "Marta")
            if source != E4_SOURCE:
                raise RuntimeError("E4 recorded fixture drifted from pinned n8n driver")
        stats = {
            "calls": 0,
            "completed": 0,
            "replayed": 0,
            "rejected": 0,
            "first_writes": 0,
            "replay_markdown_unchanged": False,
        }
        physical_snapshot: dict[str, str] = {}
        sock_path = share / "writer.sock"

        def current_markdown_hashes() -> dict[str, str]:
            return {
                filename: hashlib.sha256(repo.read_text(filename).encode()).hexdigest()
                for filename in repo.list_markdown_paths()
            }

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                raw = self.rfile.readline(16001)
                reply = {"status": 403, "body": {"status": "forbidden"}}
                stats["calls"] += 1
                try:
                    payload = json.loads(raw)
                    if (
                        len(raw) <= 16000
                        and type(payload) is dict
                        and set(payload) == {"request_id", "request", "conversation_id"}
                        and payload["request_id"] == REQUEST_ID
                        and payload["request"] == source
                        and payload["conversation_id"] == "main"
                    ):
                        result = runtime.execute_product(source, REQUEST_ID, "main", actor)
                        stats["completed"] += 1
                        hashes = current_markdown_hashes()
                        if result.get("delivery_replayed"):
                            stats["replayed"] += 1
                            stats["replay_markdown_unchanged"] = hashes == physical_snapshot
                            if not stats["replay_markdown_unchanged"]:
                                raise RuntimeError("E3 replay changed physical synthetic Markdown")
                        else:
                            stats["first_writes"] += 1
                            physical_snapshot.update(hashes)
                        reply = {"status": 200, "body": result}
                    else:
                        stats["rejected"] += 1
                except (ValueError, TypeError):
                    stats["rejected"] += 1
                self.wfile.write((json.dumps(reply, ensure_ascii=False) + "\n").encode())

        with socketserver.ThreadingUnixStreamServer(str(sock_path), Handler) as unix:
            os.chmod(sock_path, 0o600)
            thread = threading.Thread(target=unix.serve_forever, daemon=True)
            thread.start()
            try:
                (share / "broker.cjs").write_text(BROKER_JS)
                os.chmod(share / "broker.cjs", 0o444)
                entry = location / "workflow.json"
                entry.write_text(json.dumps(workflow(code, source), ensure_ascii=False))
                completed = subprocess.run(
                    docker_command(
                        entry, share, driver=E4_SHELL if case == "e4_person_task" else SHELL
                    ),
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=155,
                    check=False,
                )
            finally:
                unix.shutdown()
                unix.server_close()
                thread.join(timeout=3)
        markers = [
            x.split("ODYSSEY_DYNAMIC_N8N=", 1)[1]
            for x in completed.stdout.splitlines()
            if x.startswith("ODYSSEY_DYNAMIC_N8N=")
        ]
        if len(markers) != 1:
            raise RuntimeError(f"No n8n result (rc={completed.returncode})")
        verdict = json.loads(markers[0])
        if completed.returncode or verdict.get("pass") is not True:
            return {
                "pass": False,
                "reason": verdict.get("reason", "unknown"),
                "runtime_calls": stats["calls"],
                "verdict": verdict,
            }
        notes = [parse_note(repo.read_text(p)) for p in repo.list_markdown_paths()]
        days = [
            n
            for n in notes
            if n.metadata.get("type") == "calendar_day" and "odyssey:fact request=" in n.content
        ]
        person = [
            n
            for n in notes
            if n.metadata.get("type") == "person" and n.metadata.get("name") == "Maya"
        ]
        if case == "maya":
            assert len(days) == 1 and len(person) == 1, "physical_counts"
            assert "(yo:" in days[0].content, "missing_SELF"
            person_task_link_verified = False
            tasks = []
        else:
            person = [
                note
                for note in notes
                if note.metadata.get("type") == "person" and note.metadata.get("name") == "Marta"
            ]
            tasks = [note for note in notes if note.metadata.get("type") == "task"]
            assert len(person) == len(tasks) == 1, "E4 physical Person/Task counts"
            person_path = next(
                path
                for path in repo.list_markdown_paths()
                if parse_note(repo.read_text(path)).metadata.get("id") == person[0].metadata["id"]
            )
            person_task_link_verified = (
                f"[[{person_path.removesuffix('.md')}|Marta]]" in tasks[0].content
                and tasks[0].metadata.get("status") == "pending"
                and tasks[0].metadata.get("target_date") == "2026-10-17"
            )
            assert person_task_link_verified, "E4 canonical Person link/Task properties invalid"
        assert stats["completed"] == 2, f"completed_writer_calls_{stats['completed']}"
        assert stats["replayed"] == 1, f"replay_count_{stats['replayed']}"
        assert stats["first_writes"] == 1, "not_exactly_one_physical_first_write"
        assert stats["replay_markdown_unchanged"], "E3_replay_changed_Markdown"
        assert executor.client.rows == [], "provider_called_on_replay"
        return {
            **verdict,
            "python_writer_http_calls": stats["completed"],
            "replay_without_provider": stats["replayed"] == 1,
            "physical_markdown_byte_equivalent_on_replay": stats["replay_markdown_unchanged"],
            "real_n8n_http_request_node": True,
            "real_p4_core_writer_called_at_request_time": True,
            "physical_day_notes": len(days),
            "case": case,
            "physical_maya_notes": len(person) if case == "maya" else 0,
            "physical_e4_person_notes": len(person) if case == "e4_person_task" else 0,
            "physical_e4_task_notes": len(tasks),
            "e4_person_task_link_verified": person_task_link_verified,
            "self_link_in_day": case == "maya",
            "no_external_network": True,
            "gpt_mode": "recorded",
            "dev_prod_untouched": True,
            "host_mounts": "fixture_json_and_synthetic_unix_broker_only",
            "browser_or_cloudflare_covered": False,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--case", choices=("maya", "e4_person_task"), default="maya")
    arg = parser.parse_args()
    if not arg.run:
        parser.error("Use explicit --run")
    try:
        result = run(arg.case)
        print(json.dumps(result, indent=2))
        if result.get("pass") is not True:
            raise SystemExit(1)
    except Exception as exc:
        print(
            json.dumps({"pass": False, "error_type": type(exc).__name__, "reason": str(exc)[:200]})
        )
        raise SystemExit(1) from exc
