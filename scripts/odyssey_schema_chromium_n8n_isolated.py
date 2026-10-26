#!/usr/bin/env python3
"""Real Chromium -> real offline n8n webhook -> real Core/E3/Git (synthetic).

Container has NO network, shared home, user notes, Cloudflare, credentials
or provider. Its sole writable mount is an ephemeral bridge containing Unix
sockets; the only canonical Markdown vault lives in a separate temp directory
visible to the host Core, not to the container.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from odyssey_core.notes import parse_note  # noqa: E402
from odyssey_core.schema_retrospection_jobs import LocalSchemaScanJobs  # noqa: E402
from scripts.odyssey_n8n_dynamic_webhook import BROKER_JS  # noqa: E402
from scripts.odyssey_schema_n8n_core_isolated import (  # noqa: E402
    docker_argv,
    workflow,
)
from tests.runtime.test_schema_backfill_notes_vertical import (  # noqa: E402
    ALICE,
    fixture,
)

BROWSER = ROOT / "scripts/odyssey_schema_backfill_chromium_local.cjs"
INGRESS = r"""
'use strict';
const http=require('node:http');
const fs=require('node:fs');
const SO='\/bridge\/ingress.sock'.replaceAll('\\/','/');
const target='http://127.0.0.1:5678/webhook/odyssey-schema-core-offline-20261026';
const preflight={operation:'schema_scan',scan_kind:'backfill_property',
  target_type_id:'person',property_id:'profesion',expected_revision:1,action:'status'};
async function forward(body) {
  const response=await fetch(target,{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify(body),signal:AbortSignal.timeout(13000)});
  return {status:response.status,body:await response.text()};
}
http.createServer(async(req,res)=>{
 try{
  if(req.url==='/health'&&req.method==='GET'){
   const reply=await forward(preflight);
   const parsed=JSON.parse(reply.body);
   res.writeHead(reply.status===200&&parsed.kind==='schema_scan'?200:503);
   res.end('ready');return;
  }
  if(req.url!=='/execute'||req.method!=='POST'){
   res.writeHead(403);res.end('{}');return;
  }
  let data='';
  for await (const p of req) {
   data+=p.toString('utf8');
   if(data.length>3000){res.writeHead(413);res.end('{}');return;}
  }
  let body;try{body=JSON.parse(data)}catch{res.writeHead(400);res.end('{}');return}
  if(!body||typeof body!=='object'||Array.isArray(body)||
    !['schema_scan','schema_backfill'].includes(body.operation)||
    body.target_type_id!=='person'||body.property_id!=='profesion'||
    body.expected_revision!==1||
    !['status','stage','advance'].includes(body.action)||
    Object.keys(body).some(k=>!['operation','target_type_id','property_id',
      'expected_revision','scan_kind','action'].includes(k))||
    (body.operation==='schema_scan'&&
      (body.scan_kind!=='backfill_property'||body.action==='stage'))||
    (body.operation==='schema_backfill'&&body.scan_kind!==undefined)) {
    res.writeHead(403);res.end('{}');return;
  }
  const reply=await forward(body);
  res.writeHead(reply.status,{'content-type':'application/json'});
  res.end(reply.body);
 } catch(e) {res.writeHead(503);res.end(JSON.stringify({error:'fixture_unavailable'}));}
}).listen(SO,()=>{fs.chmodSync(SO,0o600);console.log('SCHEMA_BROWSER_N8N_INGRESS_READY')});
"""
SHELL = r"""
set -eu
node /bridge/broker.cjs >/tmp/broker.log 2>/tmp/broker.err &
broker=$!
node /bridge/ingress.cjs >/tmp/ingress.log 2>/tmp/ingress.err &
ingress=$!
n8n import:workflow --input /fixture/workflow.json >/tmp/import.log 2>/tmp/import.err
n8n publish:workflow --id odyssey-schema-core-isolated-20261026 >/tmp/publish.log 2>/tmp/publish.err
n8n start >/tmp/start.log 2>/tmp/start.err &
child=$!
trap 'kill "$broker" "$ingress" "$child" 2>/dev/null || true; wait "$broker" "$ingress" "$child" 2>/dev/null || true' EXIT
wait "$child"
"""


def request_socket(sock: Path, path: str) -> tuple[int, str]:
    connection = http.client.HTTPConnection("127.0.0.1", timeout=7)
    channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    channel.settimeout(7)
    channel.connect(str(sock))
    connection.sock = channel
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read(1024).decode(errors="replace")
    finally:
        connection.close()


def run_viewport(root: Path, view: str) -> dict:
    folder = root / view
    folder.mkdir()
    # Both mounts must be directly beneath /tmp, never a nested project/
    # account directory; Core's actual temporary vault is not mounted.
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-schema-socket-", dir="/tmp") as bridge,
        tempfile.TemporaryDirectory(prefix="odyssey-schema-core-", dir="/tmp") as flow_dir,
    ):
        share = Path(bridge)
        os.chmod(share, 0o700)
        app, repo, state = fixture(folder)
        app.schema_scan_factory = lambda actor: LocalSchemaScanJobs(
            state_root=state, repository=repo, actor_id=actor
        )
        before = {
            p: hashlib.sha256(repo.read_text(p).encode()).hexdigest()
            for p in repo.list_markdown_paths()
        }
        stats = {"core": 0}

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                raw = self.rfile.readline(16001)
                reply = {"status": 403, "body": {"error": "DENIED"}}
                try:
                    payload = json.loads(raw)
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
                        and payload.get("authenticated_actor")
                        == {"stable_user_id": ALICE.stable_user_id}
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
                        request = {
                            k: v
                            for k, v in payload.items()
                            if k not in {"operation", "authenticated_actor"}
                        }
                        reply = {"status": 200, "body": app.notes(operation, request, ALICE)}
                        stats["core"] += 1
                except (ValueError, TypeError, KeyError):
                    pass
                self.wfile.write((json.dumps(reply, ensure_ascii=False) + "\n").encode())

        writer_socket = share / "writer.sock"
        with socketserver.ThreadingUnixStreamServer(str(writer_socket), Handler) as server:
            os.chmod(writer_socket, 0o600)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            image_log = share / "container.log"
            cidfile = share / "cid"
            try:
                (share / "broker.cjs").write_text(BROKER_JS)
                (share / "ingress.cjs").write_text(INGRESS)
                os.chmod(share / "broker.cjs", 0o444)
                os.chmod(share / "ingress.cjs", 0o444)
                flow = Path(flow_dir) / "workflow.json"
                flow.write_text(json.dumps(workflow(), ensure_ascii=False))
                args = docker_argv(flow, share)
                # Container may create ONLY its own ingress.sock in disposable
                # /tmp bridge; no host vault or credential path is mounted.
                args.insert(3, "--cidfile")
                args.insert(4, str(cidfile))
                mount = next(
                    i
                    for i, arg in enumerate(args)
                    if isinstance(arg, str) and "target=/bridge" in arg
                )
                assert args[mount].endswith(",readonly")
                args[mount] = args[mount].removesuffix(",readonly")
                args[-1] = SHELL
                with image_log.open("w") as output:
                    process = subprocess.Popen(
                        args, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT
                    )
                    try:
                        ingress = share / "ingress.sock"
                        ready = False
                        for _ in range(125):
                            if process.poll() is not None:
                                break
                            if ingress.is_socket():
                                try:
                                    status, _ = request_socket(ingress, "/health")
                                    if status == 200:
                                        ready = True
                                        break
                                except (OSError, TimeoutError, ConnectionError):
                                    pass
                            time.sleep(0.55)
                        if not ready:
                            raise RuntimeError(
                                "Isolated n8n ingress not ready: " + image_log.read_text()[-700:]
                            )
                        environment = os.environ.copy()
                        environment["ODYSSEY_SYNTH_LOCAL_HTTP"] = "http://127.0.0.1:1/"
                        environment["ODYSSEY_SYNTH_N8N_SOCKET"] = str(ingress)
                        libs = Path(
                            "/home/ragdehl/projects/.odyssey-agent-runs/"
                            "e6-chromium-runtime-deps/root/usr/lib/aarch64-linux-gnu"
                        )
                        if libs.is_dir():
                            environment["LD_LIBRARY_PATH"] = (
                                str(libs) + ":" + environment.get("LD_LIBRARY_PATH", "")
                            )
                        browser = subprocess.run(
                            ["node", str(BROWSER), view],
                            cwd=ROOT,
                            capture_output=True,
                            text=True,
                            timeout=90,
                            env=environment,
                        )
                        output_lines = [
                            json.loads(line.split("ODYSSEY_BACKFILL_BROWSER=", 1)[1])
                            for line in browser.stdout.splitlines()
                            if line.startswith("ODYSSEY_BACKFILL_BROWSER=")
                        ]
                        if (
                            browser.returncode
                            or len(output_lines) != 1
                            or not output_lines[0].get("pass")
                        ):
                            raise RuntimeError(
                                "Chromium/n8n/Core did not pass: "
                                + str(output_lines)
                                + browser.stderr[-450:]
                            )
                        evidence = output_lines[0]
                    finally:
                        if cidfile.is_file():
                            cid = cidfile.read_text().strip()
                            if len(cid) == 64 and all(c in "0123456789abcdef" for c in cid):
                                subprocess.run(
                                    ["docker", "stop", "-t", "3", cid],
                                    timeout=15,
                                    capture_output=True,
                                    check=False,
                                )
                        if process.poll() is None:
                            process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
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
        if not (
            commits == 2
            and notes["0.md"]["profesion"] == "médica"
            and notes["0.md"]["revision"] == 2
            and "profesion" not in notes["1.md"]
            and after["0.md"] != before["0.md"]
            and after["1.md"] == before["1.md"]
            and evidence["n8n"] == "REAL_OFFLINE"
            and evidence["reloadPersisted"]
        ):
            raise RuntimeError("Synthetic Markdown/Git evidence differs from browser")
        return {
            "viewport": view,
            "pass": True,
            "actualChromium": True,
            "actualN8n": True,
            "actualCoreGit": True,
            "deployedDev": False,
            "provider": "NONE",
            "updated": 1,
            "deferred": 1,
            "gitCommits": commits,
            "coreRequests": stats["core"],
            "browserReload": True,
            "noDuplicateWrites": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("Opt-in only: --run starts offline disposable n8n/Chromium/Core")
        return 0
    with tempfile.TemporaryDirectory(prefix="odyssey-schema-full-ui-", dir="/tmp") as temp:
        results = [run_viewport(Path(temp), view) for view in ("desktop", "mobile")]
    result = {
        "pass": all(x["pass"] for x in results),
        "route": "Chromium -> real offline n8n -> host Core/E3 -> Markdown/Git",
        "DEV": "NOT_DEPLOYED",
        "provider": "NONE",
        "results": results,
    }
    print("ODYSSEY_SCHEMA_FULL_OFFLINE_UI=" + json.dumps(result))
    return 0 if result["pass"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
