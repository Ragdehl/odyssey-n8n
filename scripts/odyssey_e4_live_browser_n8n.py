#!/usr/bin/env python3
"""Live E4: authenticated local browser → real offline n8n → GPT → Markdown."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import secrets
import socketserver
import subprocess
import tempfile
import threading
import time
from contextlib import ExitStack, contextmanager
from datetime import datetime
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_runtime import composition
from odyssey_runtime.server import _handler_for
from scripts.odyssey_n8n_dynamic_webhook import (
    BROKER_JS,
    docker_command,
    workflow,
)
from scripts.odyssey_n8n_dynamic_webhook import (
    E4_SOURCE as DEFAULT_E4_SOURCE,
)
from scripts.odyssey_n8n_isolated_projection import PINNED_RENDER, validated_deployed_projection
from tests.core.test_reference_preflight import UnresolvedReasoner
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "odyssey_web"
BROWSER = ROOT / (
    "scripts/odyssey_e5_clarification_live_browser.cjs"
    if os.environ.get("ODYSSEY_E4_RECORDED_CASE") == "e5_selected"
    else "scripts/odyssey_e4_live_browser.cjs"
)
CLOCK = "2026-10-20T10:30:00+02:00"
# Entirely disposable test-run selection; cannot modify the deployed product.
RECORDED_CASE = os.environ.get("ODYSSEY_E4_RECORDED_CASE", "person_task")
if RECORDED_CASE not in {
    "person_task",
    "issue157_day",
    "generic_day",
    "recovery_day",
    "e5_selected",
}:
    raise RuntimeError("Unsupported isolated browser fixture")
if (
    RECORDED_CASE in {"issue157_day", "recovery_day"}
    and os.environ.get("ODYSSEY_E4_RECORDED") != "1"
):
    raise RuntimeError("Family fixture requires recorded model responses")
if RECORDED_CASE in {"issue157_day", "recovery_day"}:
    from tests.runtime.test_issue157_family_day_recollection import SOURCE as FAMILY_SOURCE
else:
    FAMILY_SOURCE = None
# Source and expected physical targets are test inputs, never production routing.
E4_SOURCE = (
    "He elegido a Luis."
    if RECORDED_CASE == "e5_selected"
    else os.environ.get("ODYSSEY_E4_SYNTHETIC_SOURCE", "He visto a Manu.")
    if RECORDED_CASE == "generic_day"
    else FAMILY_SOURCE or os.environ.get("ODYSSEY_E4_SYNTHETIC_SOURCE", DEFAULT_E4_SOURCE)
)
EXPECTED_PERSON_NAMES = (
    ("Eric", "Luis")
    if RECORDED_CASE == "e5_selected"
    else ()
    if RECORDED_CASE == "generic_day"
    else tuple(json.loads(os.environ.get("ODYSSEY_E4_SYNTHETIC_PERSONS", '["Marta"]')))
)
if (
    not isinstance(E4_SOURCE, str)
    or not 1 <= len(E4_SOURCE) <= 500
    or not 0 <= len(EXPECTED_PERSON_NAMES) <= 8
    or (RECORDED_CASE != "generic_day" and not EXPECTED_PERSON_NAMES)
    or len(set(EXPECTED_PERSON_NAMES)) != len(EXPECTED_PERSON_NAMES)
    or any(
        not isinstance(name, str)
        or not name.strip()
        or (
            RECORDED_CASE not in {"issue157_day", "recovery_day", "e5_selected"}
            and name not in E4_SOURCE
        )
        for name in EXPECTED_PERSON_NAMES
    )
):
    raise RuntimeError("Invalid synthetic browser E4 test fixture")
EXEC_JS = """const fs=require('node:fs');const raw=fs.readFileSync(0,'utf8');
fetch('http://127.0.0.1:5678/webhook/odyssey-p4-dynamic-synthetic-20261019',{
method:'POST',headers:{'content-type':'application/json'},body:raw,
signal:AbortSignal.timeout(160000)}).then(async r=>{
const body=await r.text();let parsed;
try{parsed=JSON.parse(body)}catch{parsed={status:'n8n_non_json_response',http_status:r.status,preview:body.slice(0,100)}}
console.log(JSON.stringify({status:r.status,body:parsed}));
}).catch(e=>{console.error(e.name);process.exitCode=4;});"""


@contextmanager
def live_product(root: Path):
    vault, state, derived = (root / n for n in ("vault", "state", "derived"))
    for p in (vault, state / "pending", derived):
        p.mkdir(parents=True)
    repo = VaultRepository(vault)
    base = json.loads((ROOT / "config/note-schema.json").read_text())
    schema = compose_application_schema(base, (TASK_SCHEMA_EXTENSION,))
    create_entity(
        repo,
        schema,
        path="self.md",
        entity_id="self-e4-live",
        metadata={"name": "Persona local", "type": "person"},
        content="",
        actor="fixture",
        now=CLOCK,
    )
    actor = AuthenticatedActorContext(str(uuid4()))
    SelfBindingRepository(state, repo, schema).bind(actor.stable_user_id, "self-e4-live")
    embedder = ConstantEmbedder()
    for index in (
        ContextIndex(derived / "context.sqlite3"),
        SemanticEntityIndex(derived / "semantic.sqlite3"),
        SemanticEntityIndex(derived / "semantic-tasks.sqlite3"),
    ):
        index.rebuild(repo, schema, embedder)
    env = {
        "ODYSSEY_LIGHT_SOURCE_V1": "1",
        "ODYSSEY_ENABLED_APPLICATIONS": "tasks",
        "ODYSSEY_VAULT_ROOT": str(vault),
        "ODYSSEY_RUNTIME_ROOT": str(derived),
        "ODYSSEY_STATE_ROOT": str(state),
        "ODYSSEY_PENDING_ROOT": str(state / "pending"),
        "ODYSSEY_EMBEDDING_CACHE": str(root / "fake-cache"),
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, env))
        stack.enter_context(
            patch.object(composition, "FastEmbedTextEmbedder", side_effect=lambda **kw: embedder)
        )
        stack.enter_context(
            patch.object(
                composition,
                "_build_contextual_reasoner",
                side_effect=lambda *a, **k: UnresolvedReasoner(),
            )
        )
        stack.enter_context(
            patch.object(composition, "GitHistoryRecorder", side_effect=lambda *a, **k: None)
        )
        # Optional adversarial midnight crossing: Core's wall-clock has moved
        # on, while the user delivery and all prewrite interpretation remain
        # anchored to the same original instant. Only the fixture changes.
        wall_clock = (
            "2026-10-21T00:00:02+02:00"
            if os.environ.get("ODYSSEY_E4_ADVANCE_CORE_WALL_CLOCK") == "1"
            else CLOCK
        )
        stack.enter_context(
            patch.object(
                composition,
                "_current_time",
                side_effect=lambda: {
                    "date": wall_clock[:10],
                    "time": wall_clock[11:19],
                    "timezone": "Europe/Paris",
                    "timestamp": wall_clock,
                },
            )
        )
        product = composition.build_runtime_from_environment()
        # Freeze the source executor's injectable clock too. Mocking only the
        # composition clock leaves relative words like "mañana" resolved from
        # the host's real date, invalidating the E2E temporal assertion.
        assert product.hybrid_candidate_execute is not None
        product.hybrid_candidate_execute.now = lambda: datetime.fromisoformat(CLOCK)
        product.notes_service = NotesQueryService(
            repo, schema, product.hybrid_candidate_execute.context_index
        )
        product.vault_repository = repo
        yield repo, actor, product


def assert_person_inventory(
    notes: dict, expected: tuple[str, ...], *, self_name: str = "Persona local"
) -> None:
    """Live acceptance must count EVERY physical Person, including fabricated ones.

    The fixture seeds exactly one SELF; a wrong extra Person is never filtered
    out before comparing the inventory. Duplicates also fail by count.
    """
    actual = [
        note.metadata.get("name")
        for note in notes.values()
        if note.metadata.get("type") == "person"
    ]
    assert len(actual) == len(expected) + 1, "Unexpected physical Person inventory"
    assert sorted(actual) == sorted((self_name, *expected)), (
        "Missing, duplicated or fabricated Person in live E4 vault"
    )


def build_workflow():
    if RECORDED_CASE == "e5_selected":
        # For isolated E5 acceptance, render the precise current source
        # Code node rather than the older DEV deployed revision.
        import re

        source = (ROOT / "workflows/odyssey-online.ts").read_text()
        marker = chr(96)
        dollar = chr(36)
        helper = source.split("const costHelpers = String.raw" + marker, 1)[1].split(
            marker + ";", 1
        )[0]
        route = source.split("const routeCode = " + marker, 1)[1].split(marker + ";", 1)[0]
        pricing = dollar + "{pricingSnapshotLiteral}"
        cost = dollar + "{costHelpers}"
        assert set(re.findall(r"\$\{[^}]+\}", route)) == {pricing, cost}
        code = route.replace(pricing, json.dumps({"as_of": "synthetic", "models": {}}))
        code = code.replace(cost, helper)
        assert 25000 < len(code) < 65000
        params = {"jsCode": code, "mode": "runOnceForAllItems", "language": "javaScript"}
    else:
        params = validated_deployed_projection(PINNED_RENDER)
    graph = workflow(params, E4_SOURCE)
    guard = next(node for node in graph["nodes"] if node["name"] == "Validate isolated request")
    if RECORDED_CASE == "e5_selected":
        writer = next(node for node in graph["nodes"] if node["name"].startswith("Execute real P4"))
        writer["parameters"]["jsonBody"] = (
            "={{ { request_id: $('Odyssey product request').first().json.body.request_id, "
            "request: $('Odyssey product request').first().json.body.request, "
            "conversation_id: 'main', "
            "reply_to_request_id: $('Odyssey product request').first().json.body.reply_to_request_id } }}"
        )
    guard["parameters"]["jsCode"] = (
        "const b=$('Odyssey product request').first().json.body;"
        "return [{json:{approved:!!b && typeof b.request_id==='string' && "
        "/^[a-zA-Z0-9-]{8,110}$/.test(b.request_id) && "
        "b.request===" + json.dumps(E4_SOURCE, ensure_ascii=False) + "}}];"
    )
    writer = next(node for node in graph["nodes"] if node["name"].startswith("Execute real P4"))
    writer["parameters"]["options"]["timeout"] = 155000
    return graph


def docker_post(name: str, body: dict, timeout=180) -> tuple[int, dict]:
    proc = subprocess.run(
        ["docker", "exec", "-i", name, "node", "-e", EXEC_JS],
        input=json.dumps(body, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError("n8n request failure: " + proc.stderr[-240:])
    reply = json.loads(proc.stdout.strip().splitlines()[-1])
    return reply["status"], reply["body"]


@contextmanager
def isolated_n8n(root: Path, sock: Path, share: Path):
    entry = root / "workflow.json"
    entry.write_text(json.dumps(build_workflow(), ensure_ascii=False))
    assert (share / "broker.cjs").read_text() == BROKER_JS
    docker = docker_command(entry, share)
    name = "odyssey-e4-live-" + uuid4().hex[:12]
    at = docker.index("--entrypoint")
    docker[at:at] = ["--name", name]
    docker[-1] = """set -eu
node /bridge/broker.cjs >/tmp/broker.log 2>/tmp/broker.err &
trap 'kill $! 2>/dev/null || true' EXIT
n8n import:workflow --input /fixture/workflow.json >/tmp/import.log 2>/tmp/import.err
n8n publish:workflow --id odysseyp4dynamicwebhook20261019 >/tmp/publish.log 2>/tmp/publish.err
exec n8n start"""
    with open(root / "docker.log", "w") as stream:
        proc = subprocess.Popen(docker, stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT)
        try:
            ready = False
            for _ in range(110):
                try:
                    check = subprocess.run(
                        [
                            "docker",
                            "exec",
                            name,
                            "node",
                            "-e",
                            "fetch('http://127.0.0.1:5678/healthz',{signal:AbortSignal.timeout(1500)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(2))",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=8,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    continue
                if check.returncode == 0:
                    ready = True
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.7)
            if not ready:
                raise RuntimeError("Ephemeral n8n startup failed; see isolated log")
            webhook_ready = False
            last_webhook_status = None
            for _ in range(55):
                try:
                    last_webhook_status, rejected = docker_post(
                        name,
                        {
                            "request_id": "deliberately-unknown-123",
                            "request": "invalid synthetic probe",
                            "conversation_id": "main",
                        },
                        timeout=12,
                    )
                    if last_webhook_status == 403:
                        webhook_ready = True
                        break
                except (subprocess.TimeoutExpired, ValueError, KeyError):
                    last_webhook_status = "probe_timeout"
                time.sleep(0.6)
            if not webhook_ready:
                raise RuntimeError(f"Ephemeral n8n webhook not available: {last_webhook_status}")
            print("E4_N8N_ISOLATED_READY", flush=True)
            yield name
        finally:
            subprocess.run(
                ["docker", "stop", "--time", "2", name],
                capture_output=True,
                timeout=18,
                check=False,
            )
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)


@contextmanager
def selected_product(root: Path):
    if RECORDED_CASE == "e5_selected":
        from openai import OpenAI
        from pytest import MonkeyPatch

        from odyssey_runtime.whole_source_light import WholeSourceLightExecutor
        from tests.runtime.test_candidate_continuation_factory_callback import ACTOR, _factory
        from tests.runtime.test_candidate_pending_state import NOW

        original_temporal = composition.OpenAITemporalInterpreter.from_environment
        original_planner = composition.OpenAIRequestPlanner.from_environment
        original_ask = WholeSourceLightExecutor._ask
        real_key = os.environ.get("OPENAI_API_KEY")
        mp = MonkeyPatch()
        try:
            root.mkdir(parents=True, exist_ok=True)
            product, repo, pending, _context, _trace = _factory(
                root,
                mp,
                undated=True,
                temporal_mode="empty",
                select=False,
                conversation="main",
            )
            original_id = pending.open_requests("main")[0]
            record = pending.read(original_id)
            store = product._conversation_store(ACTOR.stable_user_id)
            store.append_turn(
                request_id=original_id,
                role="user",
                text=record["original_request"],
                created_at=NOW,
            )
            store.append_turn(
                request_id=original_id,
                role="assistant",
                text="No puedo identificar con seguridad a «él». ¿Eric o Luis?",
                status="needs_attention",
                created_at=NOW,
            )
            if os.environ.get("ODYSSEY_E4_RECORDED") != "1":
                if not real_key:
                    raise RuntimeError("Isolated E5 real provider key unavailable")
                mp.setenv("OPENAI_API_KEY", real_key)
                mp.setattr(
                    composition.OpenAITemporalInterpreter,
                    "from_environment",
                    classmethod(original_temporal.__func__),
                )
                mp.setattr(
                    composition.OpenAIRequestPlanner,
                    "from_environment",
                    classmethod(original_planner.__func__),
                )
                mp.setattr(WholeSourceLightExecutor, "_ask", original_ask)
                closure = dict(
                    zip(
                        product.candidate_continuation_execute.__code__.co_freevars,
                        (
                            cell.cell_contents
                            for cell in product.candidate_continuation_execute.__closure__
                        ),
                        strict=True,
                    )
                )
                closure["light_source_execute"].client = OpenAI(max_retries=0, timeout=70)
            yield repo, ACTOR, product
        finally:
            mp.undo()
    elif RECORDED_CASE == "generic_day":
        from tests.runtime.test_p4_general_day_journal_fallback import _reviewed_day
        from tests.runtime.test_whole_source_light_product_p4 import (
            SCHEMA,
            RecordedClient,
            _fixture,
        )

        root.mkdir(parents=True)
        repo, actor, executor, runtime = _fixture(root)
        executor.event_delegate = lambda *_: (_ for _ in ()).throw(
            RuntimeError("Past-day source misrouted as Event")
        )
        if os.environ.get("ODYSSEY_E4_RECORDED") == "1":
            executor.client = RecordedClient(_reviewed_day(E4_SOURCE, "2026-10-16"))
        else:
            from types import SimpleNamespace

            from openai import OpenAI

            create = OpenAI(max_retries=0, timeout=70).responses.create
            calls = 0

            def bounded_create(**kwargs):
                nonlocal calls
                if calls >= 8:
                    raise RuntimeError("Live E2E provider cap reached (8 calls)")
                calls += 1
                print(
                    "E4_REAL_PROVIDER_CALL="
                    + str(calls)
                    + " model="
                    + str(kwargs.get("model"))
                    + " schema="
                    + str(kwargs.get("text", {}).get("format", {}).get("name")),
                    flush=True,
                )
                response = create(**kwargs)
                try:
                    parsed = json.loads(response.output_text)
                    facts = parsed.get("facts", [])
                    meta = {
                        "schema": kwargs.get("text", {}).get("format", {}).get("name"),
                        "capabilities": parsed.get("capabilities"),
                        "self_relation_count": len(parsed.get("self_relation_spans") or []),
                        "fact_count": len(facts) if isinstance(facts, list) else -1,
                        "unresolved_count": len(parsed.get("unresolved") or []),
                        "entities_count": len(parsed.get("entities") or []),
                        "needs_clarification": [
                            f.get("needs_clarification") for f in facts if isinstance(f, dict)
                        ]
                        if isinstance(facts, list)
                        else [],
                        "participants_count": [
                            len(f.get("participants") or []) for f in facts if isinstance(f, dict)
                        ]
                        if isinstance(facts, list)
                        else [],
                        "review_approved": parsed.get("approved"),
                        "review_complete": parsed.get("complete"),
                        "review_supported": [
                            f.get("supported") for f in facts if isinstance(f, dict)
                        ]
                        if isinstance(facts, list)
                        else [],
                        "review_reference_count": [
                            len(f.get("reference_names") or [])
                            for f in facts
                            if isinstance(f, dict)
                        ]
                        if isinstance(facts, list)
                        else [],
                        "reason": str(parsed.get("reason") or "")[:180],
                    }
                    print(
                        "E4_REAL_MODEL_DECISION=" + json.dumps(meta, ensure_ascii=False), flush=True
                    )
                except (ValueError, AttributeError, TypeError):
                    print("E4_REAL_MODEL_DECISION=UNPARSEABLE", flush=True)
                return response

            executor.prewrite_diagnostic = lambda _delivery, gate, values: print(
                "E4_PREWRITE_GATE=" + gate + " " + json.dumps(values, ensure_ascii=False),
                flush=True,
            )
            executor.client = SimpleNamespace(responses=SimpleNamespace(create=bounded_create))
        runtime.notes_service = NotesQueryService(repo, SCHEMA, executor.context_index)
        runtime.vault_repository = repo
        yield repo, actor, runtime
    elif RECORDED_CASE in {"issue157_day", "recovery_day"}:
        from tests.runtime.test_issue157_family_day_recollection import (
            _family,
            _model_responses,
        )
        from tests.runtime.test_whole_source_light_product_p4 import SCHEMA, RecordedClient

        root.mkdir(parents=True)
        repo, actor, executor, runtime = _family(root)
        if RECORDED_CASE == "recovery_day":
            from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
            from odyssey_runtime.execution_checkpoints import LocalExecutionCheckpointStore
            from tests.runtime.test_c4_safe_prewrite_recovery import RETRY_ADVICE, _bad_route
            from tests.runtime.test_conversation_gateway import FakeClient

            executor.client = RecordedClient([_bad_route(), *_model_responses()])
            runtime.conversation_graph_gateway = OpenAIConversationGateway(
                FakeClient([RETRY_ADVICE])
            )
            runtime.conversation_prewrite_recovery_enabled = True
            runtime.execution_checkpoint_store_factory = LocalExecutionCheckpointStore
        else:
            executor.client = RecordedClient(_model_responses())
        runtime.notes_service = NotesQueryService(repo, SCHEMA, executor.context_index)
        runtime.vault_repository = repo
        yield repo, actor, runtime
    elif os.environ.get("ODYSSEY_E4_RECORDED") == "1":
        from tests.runtime.test_p4_fresh_person_task import _physical
        from tests.runtime.test_whole_source_light_product_p4 import SCHEMA

        root.mkdir(parents=True)
        repo, actor, executor, runtime, source, _ = _physical(root, "Marta")
        assert source == E4_SOURCE
        runtime.notes_service = NotesQueryService(repo, SCHEMA, executor.context_index)
        runtime.vault_repository = repo
        yield repo, actor, runtime
    else:
        with live_product(root) as product:
            yield product


def run() -> dict:
    if os.environ.get("ODYSSEY_E4_RECORDED") != "1" and (
        os.environ.get("ODYSSEY_E4_LIVE_APPROVED") != "1" or not os.environ.get("OPENAI_API_KEY")
    ):
        raise RuntimeError("Explicit live approval and trusted API credentials required")
    started = time.monotonic()
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-dynamic-e4-live-", dir="/tmp") as tmp,
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-bridge-", dir="/tmp") as bridge,
    ):
        root = Path(tmp)
        share = Path(bridge)
        share.chmod(0o700)
        (share / "broker.cjs").write_text(BROKER_JS)
        (share / "broker.cjs").chmod(0o444)
        with selected_product(root / "data") as (repo, actor, product):
            stats = {
                "writer_calls": 0,
                "first_writes": 0,
                "replay": 0,
                "browser_requests": 0,
                "denied": 0,
                "n8n_calls": 0,
                "assistant_persisted": 0,
                "notes_read": 0,
            }
            captured_ids = []
            unix_path = share / "writer.sock"

            def snapshot():
                return {
                    p: hashlib.sha256(repo.read_text(p).encode()).hexdigest()
                    for p in repo.list_markdown_paths()
                }

            class Writer(socketserver.StreamRequestHandler):
                def handle(self):
                    raw = self.rfile.readline(16001)
                    answer = {"status": 403, "body": {"error": "synthetic request denied"}}
                    try:
                        payload = json.loads(raw)
                        if (
                            len(raw) <= 16000
                            and isinstance(payload, dict)
                            and set(payload)
                            == (
                                {"request_id", "request", "conversation_id", "reply_to_request_id"}
                                if RECORDED_CASE == "e5_selected"
                                else {"request_id", "request", "conversation_id"}
                            )
                            and isinstance(payload["request_id"], str)
                            and re.fullmatch("[a-zA-Z0-9-]{8,110}", payload["request_id"])
                            and payload["request"] == E4_SOURCE
                            and payload["conversation_id"] == "main"
                        ):
                            stats["writer_calls"] += 1
                            result = product.execute_product(
                                E4_SOURCE,
                                payload["request_id"],
                                "main",
                                actor,
                                **(
                                    {"reply_to_request_id": payload["reply_to_request_id"]}
                                    if RECORDED_CASE == "e5_selected"
                                    else {}
                                ),
                            )
                            print(
                                "E4_WRITER_STATUS="
                                + str(result.get("status"))
                                + " replay="
                                + str(bool(result.get("delivery_replayed"))),
                                flush=True,
                            )
                            detail = result.get("request_detail") or {}
                            diagnostic_flow = (
                                detail.get("flow") or detail.get("execution_flow") or {}
                            )
                            print(
                                "E4_WRITER_DIAGNOSTIC="
                                + json.dumps(
                                    {
                                        "clarification": result.get("clarification_code")
                                        or result.get("clarification"),
                                        "flow_routes": [
                                            {
                                                "stage_count": route.get("stage_count"),
                                                "writes": len(route.get("writes") or []),
                                            }
                                            for route in diagnostic_flow.get("routes", [])
                                        ],
                                    },
                                    ensure_ascii=False,
                                ),
                                flush=True,
                            )
                            if result.get("delivery_replayed"):
                                stats["replay"] += 1
                            else:
                                stats["first_writes"] += 1
                            answer = {"status": 200, "body": result}
                    except (ValueError, TypeError, KeyError):
                        pass
                    self.wfile.write((json.dumps(answer, ensure_ascii=False) + "\n").encode())

            def private_call(endpoint: str, payload: dict) -> tuple[int, dict]:
                con = HTTPConnection("127.0.0.1", private_server.server_port, timeout=25)
                data = {**payload, "authenticated_actor": {"stable_user_id": actor.stable_user_id}}
                con.request(
                    "POST",
                    endpoint,
                    json.dumps(data, ensure_ascii=False).encode(),
                    {"Content-Type": "application/json"},
                )
                reply = con.getresponse()
                code = reply.status
                value = json.loads(reply.read())
                con.close()
                return code, value

            token = secrets.token_urlsafe(32)

            class BrowserBridge(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass

                def authenticated(self):
                    try:
                        cookie = SimpleCookie()
                        cookie.load(self.headers.get("Cookie", ""))
                        value = cookie.get("odyssey_test_auth")
                        return value is not None and secrets.compare_digest(value.value, token)
                    except Exception:
                        return False

                def reply(self, code: int, payload: dict):
                    raw = json.dumps(payload, ensure_ascii=False).encode()
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def do_GET(self):
                    if not self.authenticated():
                        stats["denied"] += 1
                        return self.send_error(403)
                    uri = urlsplit(self.path).path
                    filename = "index.html" if uri == "/" else uri.lstrip("/")
                    if not filename or ".." in filename.split("/") or "\\" in filename:
                        return self.send_error(403)
                    file = (WEB / filename).resolve()
                    if not file.is_file() or not file.is_relative_to(WEB.resolve()):
                        return self.send_error(404)
                    raw = file.read_bytes()
                    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    if filename.endswith(".js"):
                        mime = "text/javascript"
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def do_POST(self):
                    if not self.authenticated():
                        stats["denied"] += 1
                        return self.reply(403, {"error": "auth required"})
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                        if not 0 < size <= 16000:
                            raise ValueError("size")
                        data = json.loads(self.rfile.read(size))
                        if not isinstance(data, dict):
                            raise ValueError("object")
                    except (ValueError, TypeError):
                        return self.reply(400, {"error": "invalid input"})
                    uri = urlsplit(self.path).path
                    print(
                        "E4_BROWSER_API=" + str(uri) + " keys=" + ",".join(sorted(data)), flush=True
                    )
                    stats["browser_requests"] += 1
                    if uri == "/api/conversation":
                        op = data.pop("operation", None)
                        if op == "presence":
                            return self.reply(200, {"status": "ignored"})
                        target = {
                            "main": "/conversation/main",
                            "progress": "/conversation/progress",
                            "turn": "/conversation/turn",
                        }.get(op)
                        if target:
                            code, answer = private_call(target, data)
                            return self.reply(code, answer)
                    if uri == "/api/notes" and data.get("operation") in {
                        "capabilities",
                        "query",
                        "detail",
                        "backlinks",
                    }:
                        stats["notes_read"] += 1
                        code, answer = private_call("/notes", data)
                        return self.reply(code, answer)
                    if uri == "/api/request" and set(data) == (
                        {"request", "request_id", "conversation_id", "reply_to_request_id"}
                        if RECORDED_CASE == "e5_selected"
                        else {"request", "request_id", "conversation_id"}
                    ):
                        stats["n8n_calls"] += 1
                        captured_ids.append(data["request_id"])
                        code, answer = docker_post(container, data)
                        print(
                            "E4_N8N_REPLY="
                            + json.dumps(
                                {
                                    "http": code,
                                    "status": answer.get("status"),
                                    "kind": answer.get("kind"),
                                    "keys": sorted(answer),
                                }
                            )[:650],
                            flush=True,
                        )
                        if code != 200:
                            return self.reply(code, answer)
                        if (
                            answer.get("status") != "completed"
                            or answer.get("request_id") != data["request_id"]
                        ):
                            return self.reply(409, {"error": "E4 live model refused operation"})
                        # n8n's transport route is not part of the durable assistant schema.
                        # Persist the original n8n result without this transport-only field.
                        durable_answer = {k: v for k, v in answer.items() if k != "route"}
                        persisted_code, persisted = private_call(
                            "/conversation/assistant-response", {"response": durable_answer}
                        )
                        print(
                            "E4_ASSISTANT_PERSIST="
                            + json.dumps(
                                {
                                    "http": persisted_code,
                                    "diagnostics_preserved": persisted.get(
                                        "conversation_diagnostics_preserved"
                                    ),
                                    "error": str(persisted.get("error", ""))[:130],
                                    "keys": sorted(persisted),
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                        if persisted_code != 200 or not persisted.get(
                            "conversation_diagnostics_preserved"
                        ):
                            return self.reply(502, {"error": "assistant persistence failed"})
                        stats["assistant_persisted"] += 1
                        answer["conversation_persisted"] = True
                        return self.reply(200, answer)
                    return self.reply(403, {"error": "unrecognized test operation"})

            with socketserver.ThreadingUnixStreamServer(str(unix_path), Writer) as unix:
                unix_path.chmod(0o600)
                unix_thread = threading.Thread(target=unix.serve_forever, daemon=True)
                unix_thread.start()
                private_server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(product))
                private_thread = threading.Thread(target=private_server.serve_forever, daemon=True)
                private_thread.start()
                try:
                    with isolated_n8n(root, unix_path, share) as container:
                        public = ThreadingHTTPServer(("127.0.0.1", 0), BrowserBridge)
                        public_thread = threading.Thread(target=public.serve_forever, daemon=True)
                        public_thread.start()
                        try:
                            browser_env = {
                                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                "HOME": str(Path.home()),
                                "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH")
                                or (
                                    "/home/ragdehl/projects/.odyssey-agent-runs/"
                                    "e6-chromium-runtime-deps/root/usr/lib/aarch64-linux-gnu"
                                ),
                                "ODYSSEY_SYNTHETIC_BROWSER_URL": f"http://127.0.0.1:{public.server_port}/",
                                "ODYSSEY_SYNTHETIC_SOURCE": E4_SOURCE,
                                "ODYSSEY_E4_EXPECTED_PERSONS": json.dumps(EXPECTED_PERSON_NAMES),
                                "ODYSSEY_E4_RECORDED_CASE": RECORDED_CASE,
                                "ODYSSEY_E4_RECORDED": "1"
                                if os.environ.get("ODYSSEY_E4_RECORDED") == "1"
                                else "0",
                                "ODYSSEY_E4_EXPECTED_WRITES": str(
                                    1
                                    if RECORDED_CASE
                                    in {"issue157_day", "generic_day", "recovery_day"}
                                    else len(EXPECTED_PERSON_NAMES)
                                    + (1 if os.environ.get("ODYSSEY_E4_RECORDED") == "1" else 2)
                                ),
                                "ODYSSEY_SYNTHETIC_AUTH": token,
                                "ODYSSEY_SYNTHETIC_VIEWPORT": os.environ.get(
                                    "ODYSSEY_E4_VIEWPORT", "mobile"
                                ),
                            }
                            print("E4_BROWSER_AUTHENTICATED_STARTED", flush=True)
                            proc = subprocess.run(
                                ["node", str(BROWSER)],
                                env=browser_env,
                                cwd=ROOT,
                                text=True,
                                capture_output=True,
                                timeout=255,
                                check=False,
                            )
                            print("E4_BROWSER_RUN=" + proc.stdout[-2200:], flush=True)
                            if proc.returncode:
                                raise RuntimeError(
                                    "Chromium E4 failed: "
                                    + proc.stderr[-200:]
                                    + " "
                                    + proc.stdout[-900:]
                                )
                            browser = json.loads(proc.stdout.strip().splitlines()[-1])
                            assert browser["pass"] is True, browser
                            assert len(captured_ids) == 1, captured_ids
                            before = snapshot()
                            replay_body = {
                                "request_id": captured_ids[0],
                                "request": E4_SOURCE,
                                "conversation_id": "main",
                            }
                            if RECORDED_CASE == "e5_selected":
                                turns = product._conversation_store(
                                    actor.stable_user_id
                                ).load_main_page()["turns"]
                                replay_body["reply_to_request_id"] = turns[0]["request_id"]
                            http, replayed = docker_post(container, replay_body)
                            assert http == 200 and replayed.get("status") == "completed"
                            assert snapshot() == before, "E3 changed Markdown bytes"
                            notes = {
                                p: parse_note(repo.read_text(p)) for p in repo.list_markdown_paths()
                            }
                            if RECORDED_CASE == "e5_selected":
                                days = [
                                    note
                                    for note in notes.values()
                                    if note.metadata.get("id") == "date:2026-10-04"
                                ]
                                assert len(days) == 1, days
                                body = days[0].content
                                assert (
                                    body.count("He estado con [[Luis|Luis]] en el parque.") == 1
                                ), body
                                assert not any(
                                    n.metadata.get("type") in {"task", "event"}
                                    for n in notes.values()
                                )
                                assert stats["replay"] == stats["first_writes"] == 1, stats
                                assert stats["assistant_persisted"] == 1, stats
                                assert stats["denied"] >= 1
                                return {
                                    "passed": True,
                                    "source_case": "e5_selected",
                                    "seconds": round(time.monotonic() - started, 2),
                                    "gpt": "recorded"
                                    if os.environ.get("ODYSSEY_E4_RECORDED") == "1"
                                    else "real",
                                    "n8n": "real_offline_docker",
                                    "browser": "Chromium real",
                                    "authentication": "synthetic_local_cookie_gate",
                                    "cloudflare_access_tested": False,
                                    "canonical_date": "2026-10-04",
                                    "journal_wikilink": True,
                                    "replay_no_duplicate": True,
                                    "browser_gate": browser["pass"],
                                    "dev_prod_untouched": True,
                                }
                            if RECORDED_CASE == "generic_day":
                                day_notes = [
                                    n
                                    for n in notes.values()
                                    if n.metadata.get("type") == "calendar_day"
                                    and n.metadata.get("id") == "date:2026-10-16"
                                ]
                                assert len(day_notes) == 1
                                body = day_notes[0].content
                                assert E4_SOURCE in body
                                assert body.count("odyssey:fact request=") == 1
                                assert (
                                    len(
                                        [
                                            n
                                            for n in notes.values()
                                            if n.metadata.get("type") == "person"
                                        ]
                                    )
                                    == 1
                                )
                                assert not any(
                                    n.metadata.get("type") in {"task", "event"}
                                    for n in notes.values()
                                )
                                assert stats["replay"] == stats["first_writes"] == 1
                                assert stats["assistant_persisted"] == 1
                                assert stats["notes_read"] >= 1 and stats["denied"] >= 1
                                return {
                                    "passed": True,
                                    "source_case": RECORDED_CASE,
                                    "seconds": round(time.monotonic() - started, 2),
                                    "gpt": "recorded"
                                    if os.environ.get("ODYSSEY_E4_RECORDED") == "1"
                                    else "real",
                                    "n8n": "real_offline_docker",
                                    "browser": "Chromium real",
                                    "authentication": "synthetic_local_cookie_gate",
                                    "unauth_denied": True,
                                    "physical_persons": 1,
                                    "physical_days": 1,
                                    "physical_day_facts": 1,
                                    "physical_tasks": 0,
                                    "physical_events": 0,
                                    "markdown_e3_replay_unchanged": True,
                                    "notes_after": len(notes),
                                    "statistics": stats,
                                    "browser_gate": browser["pass"],
                                    "cloudflare_access_tested": False,
                                    "dev_prod_untouched": True,
                                }
                            if RECORDED_CASE in {"issue157_day", "recovery_day"}:
                                from tests.runtime.test_issue157_family_day_recollection import (
                                    DAY,
                                    PEOPLE,
                                )

                                family_people = [
                                    note.metadata.get("name")
                                    for note in notes.values()
                                    if note.metadata.get("type") == "person"
                                ]
                                assert len(family_people) == 4
                                assert set(family_people) == {"Persona autenticada", *PEOPLE}, (
                                    "Unexpected or duplicated synthetic identity"
                                )
                                day_notes = [
                                    n
                                    for n in notes.values()
                                    if n.metadata.get("type") == "calendar_day"
                                    and n.metadata.get("id") == f"date:{DAY}"
                                ]
                                assert len(day_notes) == 1
                                body = day_notes[0].content
                                assert body.count("odyssey:fact request=") == 2
                                assert "jardín" in body and "museo" in body
                                assert all("[[" + person in body for person in PEOPLE)
                                assert not any(
                                    n.metadata.get("type") in {"task", "event"}
                                    for n in notes.values()
                                )
                                assert stats["replay"] == stats["first_writes"] == 1
                                assert (
                                    stats["assistant_persisted"] == 1 and stats["notes_read"] >= 1
                                )
                                assert stats["denied"] >= 1
                                if RECORDED_CASE == "recovery_day":
                                    checkpoint = product._checkpoint_store(actor.stable_user_id)
                                    assert checkpoint is not None
                                    events = checkpoint.load(captured_ids[0])["events"]
                                    assert (
                                        sum(
                                            event["stage"] == "diagnostic.prewrite_reinterpretation"
                                            for event in events
                                        )
                                        == 1
                                    )
                                    assert (
                                        product.hybrid_candidate_execute.client.calls.count(
                                            "odyssey_light_capability_route_events_v1"
                                        )
                                        == 2
                                    )
                                return {
                                    "passed": True,
                                    "source_case": RECORDED_CASE,
                                    "seconds": round(time.monotonic() - started, 2),
                                    "gpt": "recorded",
                                    "n8n": "real_offline_docker",
                                    "browser": "Chromium real",
                                    "authentication": "synthetic_local_cookie_gate",
                                    "unauth_denied": True,
                                    "physical_persons": len(family_people),
                                    "physical_days": len(day_notes),
                                    "physical_day_facts": 2,
                                    "physical_tasks": 0,
                                    "physical_events": 0,
                                    "family_links": len(PEOPLE),
                                    "markdown_e3_replay_unchanged": True,
                                    "notes_after": len(notes),
                                    "statistics": stats,
                                    "browser_gate": browser["pass"],
                                    "cloudflare_access_tested": False,
                                    "dev_prod_untouched": True,
                                }
                            assert_person_inventory(
                                notes,
                                EXPECTED_PERSON_NAMES,
                                self_name=(
                                    "Persona autenticada"
                                    if os.environ.get("ODYSSEY_E4_RECORDED") == "1"
                                    else "Persona local"
                                ),
                            )
                            people = [
                                (p, n)
                                for p, n in notes.items()
                                if n.metadata.get("type") == "person"
                                and n.metadata.get("name") in EXPECTED_PERSON_NAMES
                            ]
                            tasks = [n for n in notes.values() if n.metadata.get("type") == "task"]
                            days = [
                                n
                                for n in notes.values()
                                if n.metadata.get("type") == "calendar_day"
                            ]
                            assert len(people) == len(EXPECTED_PERSON_NAMES)
                            assert len(tasks) == 1
                            assert {note.metadata.get("name") for _, note in people} == set(
                                EXPECTED_PERSON_NAMES
                            )
                            assert all(
                                f"[[{person_path.removesuffix('.md')}|{person.metadata['name']}]]"
                                in tasks[0].content
                                for person_path, person in people
                            )
                            print(
                                "E4_TASK_DATE_READBACK="
                                + json.dumps(
                                    {
                                        "actual": tasks[0].metadata.get("target_date"),
                                        "expected": (
                                            "2026-10-17"
                                            if os.environ.get("ODYSSEY_E4_RECORDED") == "1"
                                            else "2026-10-21"
                                        ),
                                        "clock": CLOCK,
                                    },
                                    ensure_ascii=False,
                                ),
                                flush=True,
                            )
                            assert tasks[0].metadata.get("target_date") == (
                                "2026-10-17"
                                if os.environ.get("ODYSSEY_E4_RECORDED") == "1"
                                else "2026-10-21"
                            )
                            assert tasks[0].metadata.get("status") == "pending"
                            assert stats["replay"] == 1 and stats["first_writes"] == 1
                            assert stats["assistant_persisted"] == 1 and stats["notes_read"] >= 1
                            assert stats["denied"] >= 1, (
                                "authentication negative case never exercised"
                            )
                            return {
                                "passed": True,
                                "seconds": round(time.monotonic() - started, 2),
                                "gpt": "recorded"
                                if os.environ.get("ODYSSEY_E4_RECORDED") == "1"
                                else "real",
                                "n8n": "real_offline_docker",
                                "browser": "Chromium real",
                                "authentication": "synthetic_local_cookie_gate",
                                "unauth_denied": True,
                                "physical_persons": len(people),
                                "physical_tasks": len(tasks),
                                "physical_days": len(days),
                                "person_task_link": True,
                                "markdown_e3_replay_unchanged": True,
                                "notes_after": len(notes),
                                "statistics": stats,
                                "browser_gate": browser["pass"],
                                "cloudflare_access_tested": False,
                                "dev_prod_untouched": True,
                            }
                        finally:
                            public.shutdown()
                            public.server_close()
                            public_thread.join(timeout=3)
                finally:
                    private_server.shutdown()
                    private_server.server_close()
                    private_thread.join(timeout=3)
                    unix.shutdown()
                    unix_thread.join(timeout=3)


if __name__ == "__main__":
    result = run()
    print("E4_LIVE_AUTHENTICATED_RESULT=" + json.dumps(result, ensure_ascii=False), flush=True)
