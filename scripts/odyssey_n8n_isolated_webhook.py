#!/usr/bin/env python3
"""Opt-in real n8n isolated HTTP Webhook -> deployed Code -> response, fixture only.

No real user account, no model calls, no DEV/PROD n8n DB, no network outside
the ephemeral Docker container. P4 Writer result comes from temporary Markdown.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
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

WEBHOOK_ID = "odysseyp4syntheticwebhook20261019"
WEBHOOK_PATH = "odyssey-p4-isolated-fixture-20261019"

SHELL = r"""
set -eu
n8n import:workflow --input /fixture/workflow.json >/tmp/import.log 2>/tmp/import.stderr
n8n publish:workflow --id odysseyp4syntheticwebhook20261019 >/tmp/publish.log 2>/tmp/publish.stderr
n8n start >/tmp/n8n-start.log 2>/tmp/n8n-start.err &
child=$!
trap 'kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true' EXIT
node <<'JS'
const target='http://127.0.0.1:5678/webhook/odyssey-p4-isolated-fixture-20261019';
async function main(){
  // Only in-container local loopback. Container network is physically disabled.
  const fixtureId='n8n-real-webhook-synthetic-20261019';
  let response=null, original=null, last='none', validRequestAttempts=0;
  for(let count=0;count<50;count++){
    validRequestAttempts++;
    try {
      response=await fetch(target,{
        method:'POST',
        headers:{'content-type':'application/json'},
        body:JSON.stringify({request_id:fixtureId,request:'Ayer hablé con Maya.'}),
        signal:AbortSignal.timeout(4000)
      });
      // Publishing a workflow and starting n8n are separate. During warmup,
      // the Webhook can sometimes return HTTP 200 with a non-product body.
      // Never mistake that response for a successful Core write receipt.
      if(response.status===200){
        try {
          const parsed=await response.clone().json();
          if(parsed?.request_id===fixtureId &&
             parsed?.status==='completed' &&
             parsed?.kind==='acknowledgement'){
            original=parsed;
            break;
          }
          last='response_not_ready';
        } catch(_err) {last='non_product_http_body';}
      } else {
        last='not_ready_'+response.status;
        if(response.status!==404 && response.status!==503)break;
      }
    } catch(err) {
      last='not_ready_'+(err?.cause?.code||err?.name||'offline');
    }
    await new Promise(resolve=>setTimeout(resolve,800));
  }
  if(!response || !original){
    console.log('ODYSSEY_N8N_ISOLATED_WEBHOOK='+JSON.stringify({
      passed:false, failure:'webhook_unavailable',category:last,http_status:response?.status||null
    }));
    process.exitCode=3;return;
  }
  const r=original;
  // The fixture only accepts the one request actually recorded in its
  // separate Writer output. Another request MUST NEVER get the same notes.
  const wrongId=await fetch(target,{
    method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({request_id:'wrong-user',request:'Ayer hablé con Maya.'}),
    signal:AbortSignal.timeout(5000)
  });
  const wrongSource=await fetch(target,{
    method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({request_id:fixtureId,request:'An unrelated request.'}),
    signal:AbortSignal.timeout(5000)
  });
  const wrongMethod=await fetch(target,{method:'GET',signal:AbortSignal.timeout(5000)});
  const negativesBlocked=wrongId.status===403 && wrongSource.status===403 &&
    (wrongMethod.status===404 || wrongMethod.status===405);
  const writes=r?.request_detail?.flow?.routes?.[0]?.writes;
  const snapshot=r?.note_result_snapshot;
  const result={
    passed:negativesBlocked && r?.request_id===fixtureId &&
      r?.status==='completed' && r?.kind==='acknowledgement' &&
      writes?.length===2 && writes.every(x=>x.status==='succeeded') &&
      snapshot?.kind==='affected_notes' && snapshot?.total===2 &&
      r?.request_detail?.changes?.affected_stable_note_ids?.length===2,
    http_status:response.status,
    readiness_attempts:validRequestAttempts,
    wrong_id_rejected:!wrongId.ok,
    wrong_source_rejected:!wrongSource.ok,
    wrong_http_method_rejected:!wrongMethod.ok,
    wrong_id_status:wrongId.status,
    wrong_source_status:wrongSource.status,
    wrong_http_method_status:wrongMethod.status,
    write_receipts:writes?.length||0,
    visible_notes:snapshot?.total||0,
    original_code_node:true,
    real_webhook:true,
    runtime_mode:'recorded_gpt_fixture_writer'
  };
  console.log('ODYSSEY_N8N_ISOLATED_WEBHOOK='+JSON.stringify(result));
  if(!result.passed)process.exitCode=7;
}
main().catch(err=>{console.log('ODYSSEY_N8N_ISOLATED_WEBHOOK='+JSON.stringify({
 passed:false,failure:'request_invalid',category:err?.name||'unknown'
}));process.exitCode=4;});
JS
"""


def real_webhook_workflow(raw: dict, code: dict) -> dict:
    """Exactly one read-only synthetic source, one genuine DEV Code and one response."""
    if (
        raw.get("status") != "completed"
        or raw.get("request_id") != "n8n-real-webhook-synthetic-20261019"
    ):
        raise ValueError("Synthetic verified Writer result is mandatory")
    routes = raw.get("execution_flow", {}).get("routes", [])
    if len(routes) != 1 or len(routes[0].get("writes", ())) != 2:
        raise ValueError("The real Writer must have exactly two receipts")
    input_node = {
        "id": "synthetic-webhook",
        "name": NODE_REF,
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 240],
        "webhookId": "odyssey-p4-local-webhook-fixture",
        "parameters": {
            "httpMethod": "POST",
            "path": WEBHOOK_PATH,
            "responseMode": "responseNode",
            "options": {},
        },
    }
    # The result is taken from the actual Writer's result; it is not a
    # dummy fabricated browser acknowledgement or simulated graph.
    # The Webhook input MUST match both the recorded ID and the source text.
    # Otherwise a wrong browser request could receive an unrelated Writer result.
    allowed_source = raw["execution_flow"]["input"]
    source_code = (
        "const b=$('Odyssey product request').first().json.body;"
        "if (!b || b.request_id!=="
        + json.dumps(raw["request_id"])
        + " || b.request!=="
        + json.dumps(allowed_source, ensure_ascii=False)
        + ") throw Error('INVALID_SYNTHETIC_WEBHOOK_INPUT');"
        "return [{json:" + json.dumps(raw, ensure_ascii=False) + "}];"
    )
    fixture = {**_node("Synthetic actual Core Writer result", source_code), "position": [450, 240]}
    projection = {**_node(NODE), "parameters": code, "position": [690, 240]}
    output = {
        "id": "synthetic-return",
        "name": "Return actual bounded n8n response",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.4,
        "position": [910, 240],
        "parameters": {"respondWith": "firstIncomingItem", "options": {"responseCode": 200}},
    }
    # Explicit routing is essential: n8n's default error handling can
    # respond HTTP 200 even if an upstream Code node throws. Give invalid
    # inputs an honest HTTP 403 rather than relying on an uncaught exception.
    validator = {
        **_node(
            "Validate fixed synthetic HTTP request",
            "const b=$('Odyssey product request').first().json.body;"
            "return [{json:{approved:!!b && b.request_id==="
            + json.dumps(raw["request_id"])
            + " && b.request==="
            + json.dumps(allowed_source, ensure_ascii=False)
            + "}}];",
        ),
        "position": [360, 240],
    }
    branch = {
        "id": "validate-fixture-condition",
        "name": "Is exact synthetic request",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [480, 240],
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
                        "id": "synthetic-request-only",
                        "leftValue": "={{ $json.approved }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "true",
                            "singleValue": True,
                        },
                    }
                ],
            }
        },
    }
    denied = {
        "id": "synthetic-forbidden",
        "name": "Return forbidden without Core",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.4,
        "position": [730, 440],
        "parameters": {
            "respondWith": "json",
            "responseBody": '{"error":"INVALID_SYNTHETIC_REQUEST"}',
            "options": {"responseCode": 403},
        },
    }
    nodes = [input_node, validator, branch, fixture, projection, output, denied]

    def next_step(name: str) -> dict:
        return {"node": name, "type": "main", "index": 0}

    links = {
        input_node["name"]: {"main": [[next_step(validator["name"])]]},
        validator["name"]: {"main": [[next_step(branch["name"])]]},
        branch["name"]: {
            "main": [
                [next_step(fixture["name"])],
                [next_step(denied["name"])],
            ]
        },
        fixture["name"]: {"main": [[next_step(projection["name"])]]},
        projection["name"]: {"main": [[next_step(output["name"])]]},
    }
    return {
        "id": WEBHOOK_ID,
        "name": "Isolated P4 real webhook no network",
        "active": False,
        "nodes": nodes,
        "connections": links,
        "settings": {"executionOrder": "v1"},
    }


def safe_docker_command(fixture: Path) -> list[str]:
    # Docker is run with NO network. 'localhost:5678' exists only INSIDE
    # this container, not on the host or either Odyssey n8n installation.
    real = fixture.resolve(strict=True)
    if (
        fixture.is_symlink()
        or real.parent.parent != Path("/tmp")
        or not real.parent.name.startswith("odyssey-n8n-real-webhook-")
        or real.name != "workflow.json"
        or not real.is_file()
        or real.stat().st_uid != os.getuid()
        or not 0 < real.stat().st_size <= 512_000
    ):
        raise ValueError("Only owned disposable /tmp synthetic n8n workflow is permitted")
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
        "N8N_USER_FOLDER=/tmp/synthetic-isolated-n8n",
        "-e",
        "N8N_DIAGNOSTICS_ENABLED=false",
        "-e",
        "N8N_PERSONALIZATION_ENABLED=false",
        "-e",
        "N8N_TEMPLATES_ENABLED=false",
        "-e",
        "N8N_ENCRYPTION_KEY=synthetic-only-local-fixture-no-private-key",
        "--mount",
        f"type=bind,source={real},target=/fixture/workflow.json,readonly",
        "--entrypoint",
        "/bin/sh",
        IMAGE,
        "-c",
        SHELL,
    ]


def run_webhook() -> dict:
    from tests.runtime.test_whole_source_light_product_p4 import (
        RecordedClient,
        _actual_snapshot,
        _fixture,
        _speaker,
    )

    if shutil.which("docker") is None:
        raise RuntimeError("Docker required for real n8n")
    code = validated_deployed_projection(PINNED_RENDER)
    with tempfile.TemporaryDirectory(prefix="odyssey-n8n-real-webhook-", dir="/tmp") as tmp:
        work = Path(tmp)
        vault = work / "physical"
        vault.mkdir()
        source, route, plan, review = _actual_snapshot("maya_simple")
        repo, actor, executor, runtime = _fixture(vault)
        executor.client = RecordedClient(
            [route, plan, review, _speaker(source, plan, base=1), _speaker(source, plan)]
        )
        raw = runtime.execute_product(source, "n8n-real-webhook-synthetic-20261019", "main", actor)
        workflow = real_webhook_workflow(raw, code)
        artifact = work / "workflow.json"
        artifact.write_text(json.dumps(workflow, ensure_ascii=False))
        result = subprocess.run(
            safe_docker_command(artifact),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=155,
            check=False,
        )
        rows = [
            x.removeprefix("ODYSSEY_N8N_ISOLATED_WEBHOOK=")
            for x in result.stdout.splitlines()
            if x.startswith("ODYSSEY_N8N_ISOLATED_WEBHOOK=")
        ]
        if result.returncode or len(rows) != 1:
            # Only report tightly controlled boolean/status summary fields.
            # Do not forward raw n8n logs or a serialized workflow.
            bounded = {}
            if len(rows) == 1:
                try:
                    record = json.loads(rows[0])
                    bounded = {
                        key: record.get(key)
                        for key in (
                            "passed",
                            "failure",
                            "http_status",
                            "content_type",
                            "category",
                            "wrong_id_rejected",
                            "wrong_source_rejected",
                            "wrong_http_method_rejected",
                            "wrong_id_status",
                            "wrong_source_status",
                            "wrong_http_method_status",
                        )
                    }
                except (ValueError, TypeError):
                    bounded = {"failure": "invalid_fixture_verdict"}
            raise RuntimeError(
                f"isolated webhook rc={result.returncode}, "
                f"verdict_count={len(rows)}, summary={bounded}"
            )
        verdict = json.loads(rows[0])
        if verdict.get("passed") is not True:
            raise RuntimeError("Real n8n webhook failed")
        if len(repo.list_markdown_paths()) != 4 or executor.client.rows:
            raise RuntimeError("Unexpected writes after synthetic source projection")
        return {
            **verdict,
            "n8n_engine": "2.33.7",
            "network_disabled": True,
            "actual_dev_code_node": True,
            "real_http_webhook": True,
            "private_user_data_access": False,
            "gpt_live": False,
            "cloudflare_access": False,
            "browser_entry": False,
            "writer_http_live": False,
            "source_vault": "deleted_temporary_only",
        }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--run", action="store_true")
    args = cli.parse_args()
    if not args.run:
        cli.error("Explicit --run required")
    try:
        print(json.dumps(run_webhook(), ensure_ascii=False, indent=2))
    except Exception as error:
        print(
            json.dumps(
                {"passed": False, "failure": type(error).__name__, "summary": str(error)[:320]}
            )
        )
        sys.exit(1)
