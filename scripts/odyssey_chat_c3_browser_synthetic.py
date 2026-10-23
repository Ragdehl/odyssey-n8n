#!/usr/bin/env python3
"""Actual Odyssey web UI driven in Chromium against isolated C3 HTTP runtime.

A disposable local bridge stands in for n8n. Provider replies are fixed by
default or live Luna with bounded explicit approval. Never a deployed DEV/n8n E2E.
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import tempfile
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
from uuid import uuid4

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from odyssey_runtime.server import _handler_for
from tests.runtime.test_conversation_gateway import FakeClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "odyssey_web"
BROWSER = ROOT / "scripts/odyssey_chat_c3_browser_synthetic.cjs"


def main() -> int:
    real_provider = os.environ.get("ODYSSEY_CHAT_BROWSER_REAL") == "1"
    if real_provider and (
        os.environ.get("ODYSSEY_CHAT_LIVE_APPROVED") != "1" or not os.environ.get("OPENAI_API_KEY")
    ):
        print(json.dumps({"pass": False, "reason": "real provider requires bounded approval"}))
        return 2
    with tempfile.TemporaryDirectory(prefix="odyssey-chat-c3-ui-", dir="/tmp") as folder:
        temp = Path(folder)
        vault = temp / "vault"
        vault.mkdir()
        state = temp / "state"
        actor = AuthenticatedActorContext(str(uuid4()))
        core_calls: list[str] = []
        fake = FakeClient(
            [
                {"mode": "CHAT", "context_scope": "NONE"},
                {"purpose": "GENERAL"},
                {"outcome": "ANSWER", "answer": "¡Hola desde Odyssey!", "supporting_ids": []},
                {"mode": "CHAT", "context_scope": "NONE"},
                {"purpose": "HELP"},
                {
                    "outcome": "ANSWER",
                    "answer": "Puedes añadir subtareas desde una tarea.",
                    "supporting_ids": ["tasks"],
                },
            ]
        )

        def core(_source, rid, *_args, **_kwargs):
            core_calls.append(rid)
            return ApplicationResult(rid, ApplicationStatus.COMPLETED, (), ())

        audit = {"user_submissions": 0, "assistant_persisted": 0, "denied": 0}
        gateway = (
            OpenAIConversationGateway.from_environment()
            if real_provider
            else OpenAIConversationGateway(fake)
        )
        model_counts = {"calls": 0, "max_output_tokens": 0}
        if real_provider:
            invoke = gateway._complete

            def capped_complete(**kwargs):
                budget = kwargs.get("max_tokens")
                if (
                    type(budget) is not int
                    or not 0 < budget <= 750
                    or model_counts["calls"] >= 6
                    or model_counts["max_output_tokens"] + budget > 3000
                ):
                    raise RuntimeError("C3 browser live model budget exhausted")
                model_counts["calls"] += 1
                model_counts["max_output_tokens"] += budget
                return invoke(**kwargs)

            gateway._complete = capped_complete

        runtime = RuntimeComposition(
            core_execute=core,
            refresh_indexes=lambda: None,
            conversation_root_resolver=ConversationRootResolver(state),
            conversation_gateway=gateway,
            conversation_deployed_capabilities=frozenset({"tasks"}),
        )
        private = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
        private_thread = Thread(target=private.serve_forever, daemon=True)
        private_thread.start()

        def runtime_post(route: str, data: dict):
            connection = HTTPConnection(
                "127.0.0.1", private.server_port, timeout=55 if real_provider else 18
            )
            connection.request(
                "POST",
                route,
                json.dumps(
                    {
                        **data,
                        "authenticated_actor": {"stable_user_id": actor.stable_user_id},
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                {"Content-Type": "application/json; charset=utf-8"},
            )
            response = connection.getresponse()
            status, body = response.status, json.loads(response.read())
            connection.close()
            return status, body

        class Bridge(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def reply(self, status, data):
                encoded = json.dumps(data, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self):
                path = urlsplit(self.path).path
                name = "index.html" if path == "/" else path.lstrip("/")
                if ".." in name.split("/") or "\\" in name:
                    return self.send_error(403)
                target = (WEB / name).resolve()
                if not target.is_file() or not target.is_relative_to(WEB.resolve()):
                    return self.send_error(404)
                body = target.read_bytes()
                media = (
                    "text/javascript"
                    if name.endswith(".js")
                    else mimetypes.guess_type(name)[0] or "application/octet-stream"
                )
                self.send_response(200)
                self.send_header("Content-Type", media)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= length <= 16384:
                        raise ValueError("Invalid length")
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict):
                        raise ValueError("Invalid body")
                except (ValueError, TypeError):
                    return self.reply(400, {"error": "invalid synthetic browser request"})
                path = urlsplit(self.path).path
                if path == "/api/conversation":
                    operation = payload.get("operation")
                    if operation == "presence":
                        return self.reply(200, {"ok": True})
                    if operation in {"main", "progress"}:
                        status, response = runtime_post("/conversation/" + operation, payload)
                        return self.reply(status, response)
                if path == "/api/request" and set(payload) == {
                    "request",
                    "request_id",
                    "conversation_id",
                }:
                    audit["user_submissions"] += 1
                    status, result = runtime_post("/execute", payload)
                    if status != 200 or "conversation_reply" not in result:
                        audit["failed_stage"] = "runtime_execute"
                        audit["runtime_status"] = status
                        audit["runtime_result_keys"] = sorted(result)
                        return self.reply(502, {"error": "unexpected runtime route"})
                    reply = {"request_id": payload["request_id"], **result["conversation_reply"]}
                    status, persisted = runtime_post(
                        "/conversation/assistant-response", {"response": reply}
                    )
                    if status != 200 or not persisted.get("conversation_persisted"):
                        audit["failed_stage"] = "assistant_persistence"
                        audit["persistence_status"] = status
                        audit["persistence_result_keys"] = sorted(persisted)
                        return self.reply(502, {"error": "assistant persistence failed"})
                    audit["assistant_persisted"] += 1
                    return self.reply(200, persisted)
                audit["denied"] += 1
                return self.reply(403, {"error": "synthetic browser bridge forbids mutation"})

        bridge = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
        bridge_thread = Thread(target=bridge.serve_forever, daemon=True)
        bridge_thread.start()
        try:
            command = ["node", str(BROWSER), f"http://127.0.0.1:{bridge.server_port}/"]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=150 if real_provider else 80,
                check=False,
            )
            browser_output = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
            turns = runtime.main_conversation(actor)["turns"]
            no_md = not tuple(vault.rglob("*.md"))
            accepted = (
                result.returncode == 0
                and browser_output.get("pass") is True
                and not core_calls
                and no_md
                and audit["user_submissions"] == 2
                and audit["assistant_persisted"] == 2
                and len(turns) == 4
                and (model_counts["calls"] if real_provider else len(fake.responses.calls)) == 6
            )
            print(
                json.dumps(
                    {
                        "kind": "synthetic_browser_user_journey",
                        "pass": accepted,
                        "real_chromium_ui": True,
                        "real_runtime_http": True,
                        "real_n8n": False,
                        "real_provider": real_provider,
                        "provider_call_budget": 6 if real_provider else 0,
                        "provider_calls": (
                            model_counts["calls"] if real_provider else len(fake.responses.calls)
                        ),
                        "max_output_tokens_budgeted": model_counts["max_output_tokens"],
                        "real_DEV_deployed": False,
                        "browser": browser_output,
                        "requests": audit,
                        "saved_transcript_turns": len(turns),
                        "core_calls": len(core_calls),
                        "markdown_files": len(tuple(vault.rglob("*.md"))),
                        "browser_process_exit": result.returncode,
                    },
                    ensure_ascii=False,
                )
            )
            return 0 if accepted else 1
        finally:
            bridge.shutdown()
            bridge.server_close()
            bridge_thread.join(timeout=5)
            private.shutdown()
            private.server_close()
            private_thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
