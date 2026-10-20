#!/usr/bin/env python3
"""Synthetic P4 browser->HTTP->REAL Core Writer->Markdown browser integration.

Fixed recorded GPT outputs, no n8n, no provider network, no DEV/PROD vault.
All persistent files belong to one TemporaryDirectory in /tmp.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "odyssey_web"
BROWSER = ROOT / "scripts/odyssey_browser_synthetic_p4.cjs"
sys.path.insert(0, str(ROOT))
SOURCE_CASE = "maya_simple"

# The fake HTTP facade owns presentation-only projection, as n8n normally does.
# Keep only fields allowed by the real conversation/browser schemas. Do not
# invent operational stages, links, note IDs, Core receipts or provider usage.
SAFE_STAGE_KEYS = frozenset(
    {
        "name",
        "outcome",
        "duration_ms",
        "model",
        "reasoning_effort",
        "error_category",
        "usage",
        "provider_calls",
        "start_offset_ms",
        "substeps",
        "coverage",
        "input_sizes",
        "validation_stage",
        "validation_code",
        "provider_status",
        "incomplete_reason",
        "parse_status",
        "result_kind",
        "ordinal",
        "attempt_count",
        "output_text_chars",
        "output_text_bytes",
        "stage_view",
        "route_index",
    }
)


def bounded_stage(stage: dict) -> dict:
    result = {key: value for key, value in stage.items() if key in SAFE_STAGE_KEYS}
    result["provider_calls"] = [bounded_stage(call) for call in stage.get("provider_calls", [])]
    return result


def real_result_browser_detail(value: dict, request_id: str) -> dict:
    from odyssey_core.conversations import _validate_request_detail

    raw = value["operational"]
    detail = {
        "request_id": request_id,
        "operational": {
            "total_duration_ms": raw["total_duration_ms"],
            "stages": [bounded_stage(stage) for stage in raw["stages"]],
        },
        "changes": {
            "affected_stable_note_ids": value.get("affected_stable_note_ids", []),
            "units": [
                {
                    "stable_note_id": unit.get("stable_note_id"),
                    "operation": unit.get("operation"),
                    "status": unit.get("status"),
                }
                for action in value["actions"]
                for unit in action.get("units", [])
            ],
        },
        "flow": value["execution_flow"],
    }
    _validate_request_detail(detail, request_id, "assistant")
    return detail


def run_synthetic_browser(viewport: str = "mobile", case: str = "maya") -> dict:
    if viewport not in {"mobile", "desktop"}:
        raise ValueError("Only fixed synthetic browser viewports are allowed")
    if case not in {"maya", "e4_person_task"}:
        raise ValueError("Only fixed synthetic source cases are allowed")
    from odyssey_core.note_queries import NotesQueryService
    from odyssey_core.notes import parse_note
    from odyssey_runtime.server import _handler_for
    from tests.runtime.test_whole_source_light_product_p4 import (
        SCHEMA,
        RecordedClient,
        _actual_snapshot,
        _fixture,
        _speaker,
    )

    with tempfile.TemporaryDirectory(prefix="odyssey-synthetic-browser-", dir="/tmp") as tmp:
        root = Path(tmp)
        if case == "maya":
            source, route, proposal, review = _actual_snapshot(SOURCE_CASE)
            repo, actor, executor, runtime = _fixture(root)
            executor.client = RecordedClient(
                [
                    route,
                    proposal,
                    review,
                    _speaker(source, proposal, base=1),
                    _speaker(source, proposal),
                ]
            )
        else:
            # Exact E4 vertical fixture: real Core and Tasks write paths,
            # source reviewers and temporal interpretation with recorded models.
            from tests.runtime.test_p4_fresh_person_task import _physical

            repo, actor, executor, runtime, source, _calls = _physical(root, "Marta")
        runtime.notes_service = NotesQueryService(repo, SCHEMA, executor.context_index)
        runtime.vault_repository = repo

        private_server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
        private_thread = Thread(target=private_server.serve_forever, daemon=True)
        private_thread.start()
        delivered_ids: list[str] = []
        proxy_stats = {
            "requests": 0,
            "executions": 0,
            "private_http_calls": 0,
            "assistant_persisted": 0,
            "note_reads": 0,
            "synthetic_presence": 0,
            "denied": 0,
        }

        def real_runtime(endpoint: str, payload: dict) -> tuple[int, dict]:
            proxy_stats["private_http_calls"] += 1
            connection = HTTPConnection("127.0.0.1", private_server.server_port, timeout=15)
            request = {**payload, "authenticated_actor": {"stable_user_id": actor.stable_user_id}}
            connection.request(
                "POST",
                endpoint,
                json.dumps(request, ensure_ascii=False).encode(),
                {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            code = response.status
            value = json.loads(response.read())
            connection.close()
            return code, value

        class BrowserBridge(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, code: int, payload: dict):
                data = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json; charset=utf-8")
                self.send_header("cache-control", "no-store")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                uri = urlsplit(self.path).path
                filename = "index.html" if uri == "/" else uri.lstrip("/")
                if not filename or ".." in filename.split("/") or "\\" in filename:
                    self.send_error(403)
                    return
                file = (WEB / filename).resolve()
                if not file.is_file() or not file.is_relative_to(WEB.resolve()):
                    self.send_error(404)
                    return
                data = file.read_bytes()
                mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                if filename.endswith(".js"):
                    mime = "text/javascript"
                self.send_response(200)
                self.send_header("content-type", mime)
                self.send_header("cache-control", "no-store")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                proxy_stats["requests"] += 1
                try:
                    length = int(self.headers.get("content-length", "0"))
                    if length > 16 * 1024 or length < 1:
                        raise ValueError("oversized")
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError("payload")
                except (ValueError, json.JSONDecodeError):
                    return self.reply(400, {"error": "invalid test request"})
                uri = urlsplit(self.path).path
                if uri == "/api/conversation":
                    operation = data.pop("operation", None)
                    if operation == "presence":
                        proxy_stats["synthetic_presence"] += 1
                        return self.reply(200, {"status": "ignored"})
                    allowed = {
                        "main": "/conversation/main",
                        "progress": "/conversation/progress",
                        "turn": "/conversation/turn",
                    }
                    endpoint = allowed.get(operation)
                    if endpoint is not None:
                        code, result = real_runtime(endpoint, data)
                        return self.reply(code, result)
                if uri == "/api/request" and set(data) == {
                    "request",
                    "request_id",
                    "conversation_id",
                }:
                    proxy_stats["executions"] += 1
                    code, value = real_runtime("/execute", data)
                    if code != 200:
                        return self.reply(code, value)
                    # Synthetic n8n-like finalizer: project actual Writer+Core
                    # evidence to browser contract; NEVER invent physical writes.
                    if value.get("status") != "completed":
                        return self.reply(409, {"error": "recorded source failed"})
                    rid = data["request_id"]
                    delivered_ids.append(rid)
                    detail = real_result_browser_detail(value, rid)
                    normalized = {
                        "request_id": rid,
                        "status": "completed",
                        "kind": "acknowledgement",
                        "message": "Guardado",
                        "note_result_snapshot": value["note_result_snapshot"],
                        "request_detail": detail,
                    }
                    persisted_code, persisted = real_runtime(
                        "/conversation/assistant-response", {"response": normalized}
                    )
                    if persisted_code != 200:
                        return self.reply(502, {"error": "assistant not persisted"})
                    if persisted.get("conversation_diagnostics_preserved") is not True:
                        return self.reply(502, {"error": "synthetic diagnostic save invalid"})
                    proxy_stats["assistant_persisted"] += 1
                    normalized["conversation_persisted"] = True
                    return self.reply(200, normalized)
                if uri == "/api/notes" and data.get("operation") in {
                    "capabilities",
                    "query",
                    "detail",
                    "backlinks",
                }:
                    proxy_stats["note_reads"] += 1
                    code, result = real_runtime("/notes", data)
                    return self.reply(code, result)
                proxy_stats["denied"] += 1
                return self.reply(403, {"error": "test-only facade forbids operation"})

        public_server = ThreadingHTTPServer(("127.0.0.1", 0), BrowserBridge)
        public_thread = Thread(target=public_server.serve_forever, daemon=True)
        public_thread.start()
        try:
            # No host credentials or provider keys are needed by this recorded
            # browser fixture. Explicitly pass only the cached-browser runtime
            # environment, never inherited account secrets.
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(Path.home()),
                "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", ""),
                "ODYSSEY_SYNTHETIC_BROWSER_URL": f"http://127.0.0.1:{public_server.server_port}/",
                "ODYSSEY_SYNTHETIC_SOURCE": source,
                "ODYSSEY_SYNTHETIC_VIEWPORT": viewport,
            }
            result = subprocess.run(
                ["node", str(BROWSER)],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=65,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(
                    f"Synthetic browser failed code={result.returncode} "
                    f"stderr={result.stderr[-300:]} stdout={result.stdout[-1200:]}"
                )
            browser_report = json.loads(result.stdout)
            physical = [parse_note(repo.read_text(name)) for name in repo.list_markdown_paths()]
            days = [
                note
                for note in physical
                if note.metadata["type"] == "calendar_day"
                and "odyssey:fact request=" in note.content
            ]
            person = [
                note
                for note in physical
                if note.metadata["type"] == "person" and note.metadata["name"] == "Maya"
            ]
            tasks = [note for note in physical if note.metadata["type"] == "task"]
            if case == "maya":
                assert len(days) == 1 and len(person) == 1, (
                    "Core facts/person were not physically written"
                )
                assert "(yo:" in days[0].content, (
                    "Implicit speaker SELF missing in physical Markdown"
                )
            else:
                person = [
                    note
                    for note in physical
                    if note.metadata["type"] == "person" and note.metadata["name"] == "Marta"
                ]
                assert len(person) == len(tasks) == 1, "E4 must write one Person and one Task"
                person_path = next(
                    path
                    for path in repo.list_markdown_paths()
                    if parse_note(repo.read_text(path)).metadata.get("id")
                    == person[0].metadata["id"]
                )
                assert f"[[{person_path.removesuffix('.md')}|Marta]]" in tasks[0].content
                assert tasks[0].metadata["target_date"] == "2026-10-17"
                assert tasks[0].metadata["status"] == "pending"
                assert "15:00" not in tasks[0].content, "E4 must not invent a clock time"
            assert browser_report["pass"] is True
            assert proxy_stats["executions"] == 1
            assert proxy_stats["assistant_persisted"] == 1
            assert proxy_stats["note_reads"] >= 1
            assert len(delivered_ids) == 1
            before_replay = {name: repo.read_text(name) for name in repo.list_markdown_paths()}
            replay = runtime.execute_product(source, delivered_ids[0], "main", actor)
            assert replay["delivery_replayed"] is True
            assert {
                name: repo.read_text(name) for name in repo.list_markdown_paths()
            } == before_replay
            assert executor.client.rows == [], "No provider rows remain after the first write"
            return {
                "pass": True,
                "viewport": viewport,
                "case": case,
                "browser": browser_report,
                "provider_mode": "recorded_output",
                "n8n_mode": "synthetic_http_facade",
                "core_writer": "real",
                "markdown_replayed": True,
                "e3_same_request_replay_verified": True,
                "physical_note_count_after_replay": len(before_replay),
                "physical_day_notes": len(days),
                "physical_new_people": len(person),
                "physical_new_tasks": len(tasks),
                "person_task_link_verified": case == "e4_person_task",
                "self_binding_verified": case == "maya",
                "http_stats": proxy_stats,
                "vault_root": "temporary_only",
                "cloudflare_access_checked": False,
                "live_gpt_checked": False,
                "deployed_dev_code_checked": False,
            }
        finally:
            public_server.shutdown()
            public_server.server_close()
            public_thread.join(timeout=4)
            private_server.shutdown()
            private_server.server_close()
            private_thread.join(timeout=4)


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--viewport", choices=("mobile", "desktop"), default="mobile")
    args.add_argument("--case", choices=("maya", "e4_person_task"), default="maya")
    options = args.parse_args()
    try:
        print(
            json.dumps(
                run_synthetic_browser(options.viewport, options.case),
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as error:
        print(
            json.dumps(
                {"pass": False, "error_type": type(error).__name__, "error": str(error)[-850:]},
                ensure_ascii=False,
            )
        )
        sys.exit(1)
