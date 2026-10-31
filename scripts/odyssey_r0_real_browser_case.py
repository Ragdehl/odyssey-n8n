#!/usr/bin/env python3
"""Run exactly one paid R0 source through the existing isolated E4 harness.

This is deliberately an acceptance *adapter*, not an Odyssey execution path.
It is only runnable from the approved transient systemd EnvironmentFile command.
It never selects an Odyssey route from a case id: the id is used solely to load
one immutable corpus source and to bind the durable campaign receipt.
"""

from __future__ import annotations

import argparse
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
from contextlib import ExitStack, contextmanager
from datetime import datetime
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "odyssey_web"
CLOCK = "2026-10-04T17:35:00+02:00"
SELF = "fixture-person-alex"
# A normal multi-stage message requires multiple real provider calls.
# Bound their *aggregate* pessimistic cost to the reserved amount before each
# attempt; a one-call cap incorrectly blocked every R0 message after Planner.
MAX_CALLS = 16
RESERVE_USD = 0.25


class Refused(RuntimeError):
    """The adapter cannot safely make a live attempt."""


def _case(case_id: str, source_sha256: str) -> str:
    from scripts.odyssey_r0_browser_campaign import campaign_cases

    matches = [item for item in campaign_cases() if item.id == case_id]
    if len(matches) != 1 or matches[0].source_sha256 != source_sha256:
        raise Refused("case/source SHA does not match the frozen R0 corpus")
    return matches[0].source


def _receipt(path: Path, case: str, digest: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Refused("campaign receipt is unreadable") from error
    if value.get("case") != case or value.get("source_sha256") != digest:
        raise Refused("campaign receipt does not belong to this case")
    if value.get("outcome") != "armed" or value.get("reserved_usd") != RESERVE_USD:
        raise Refused("case is not freshly armed with the fixed $0.25 reservation")
    return value


def _snapshot(repo: Any) -> dict[str, str]:
    return {path: repo.read_text(path) for path in repo.list_markdown_paths()}


@contextmanager
def _r0_product(root: Path):
    """Compose the real runtime around exactly the committed 13-note fixture."""
    from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
    from odyssey_core.note_queries import NotesQueryService
    from odyssey_runtime import composition
    from tests.core.test_reference_preflight import UnresolvedReasoner
    from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
    from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder

    repo, _context, _semantic, _embedder = fresh_corpus_vault(root)
    state, derived = root / "state", root / "derived"
    (state / "pending").mkdir(parents=True)
    actor = AuthenticatedActorContext(str(uuid4()))
    # The fixture is canonical evidence; its original Alex binding is part of
    # the acceptance contract and is not synthesized by the adapter.
    from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA

    SelfBindingRepository(state, repo, SCHEMA).bind(actor.stable_user_id, SELF)
    env = {
        "ODYSSEY_LIGHT_SOURCE_V1": "1",
        "ODYSSEY_ENABLED_APPLICATIONS": "tasks,events",
        "ODYSSEY_VAULT_ROOT": str(repo.root),
        "ODYSSEY_RUNTIME_ROOT": str(derived),
        "ODYSSEY_STATE_ROOT": str(state),
        "ODYSSEY_PENDING_ROOT": str(state / "pending"),
        "ODYSSEY_EMBEDDING_CACHE": str(root / "embedding-cache"),
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, env))
        stack.enter_context(
            patch.object(composition, "GitHistoryRecorder", side_effect=lambda *a, **k: None)
        )
        stack.enter_context(
            patch.object(
                composition, "FastEmbedTextEmbedder", side_effect=lambda **kw: ConstantEmbedder()
            )
        )
        stack.enter_context(
            patch.object(
                composition, "_build_contextual_reasoner", side_effect=lambda: UnresolvedReasoner()
            )
        )
        stack.enter_context(
            patch.object(
                composition,
                "_current_time",
                side_effect=lambda: {
                    "date": "2026-10-04",
                    "time": "17:35",
                    "timezone": "Europe/Paris",
                    "timestamp": CLOCK,
                },
            )
        )
        product = composition.build_runtime_from_environment()
        if product.hybrid_candidate_execute is not None:
            product.hybrid_candidate_execute.now = lambda: datetime.fromisoformat(CLOCK)
        product.notes_service = NotesQueryService(
            repo, product.canonical_schema, product.hybrid_candidate_execute.context_index
        )
        product.vault_repository = repo
        yield repo, actor, product


def _prepare_additional_test_fixture(case_id: str, repo: Any, product: Any) -> int:
    """Seed typed preconditions in a disposable vault, never the product or corpus.

    The historic 27 always retain their exact 13-note starting fixture. The
    appended acceptance cases may require *test-only* task/SELF knowledge.
    No `if case_id == ...` or name-based branch enters Odyssey's runtime.
    """
    from dataclasses import replace

    from odyssey_core import create_entity
    from odyssey_core.atomic_facts import render_atomic_facts
    from odyssey_core.notes import parse_note, serialize_note
    from scripts.odyssey_r0_browser_campaign import ADDITIONAL

    catalog = json.loads(ADDITIONAL.read_text(encoding="utf-8"))["cases"]
    row = next((entry for entry in catalog if entry["id"] == case_id), None)
    steps = [] if row is None else row.get("fixture_setup", [])
    if not isinstance(steps, list):
        raise Refused("Additional case setup is invalid")
    for step in steps:
        if step.get("kind") == "replace_self_facts":
            facts = step.get("facts")
            if (
                not isinstance(facts, list)
                or not 1 <= len(facts) <= 8
                or any(
                    not isinstance(fact, str) or not fact.endswith(".") or len(fact) > 180
                    for fact in facts
                )
            ):
                raise Refused("Unsafe typed synthetic SELF facts")
            path = "Alex.md"
            note = parse_note(repo.read_text(path))
            if note.metadata.get("id") != SELF:
                raise Refused("Synthetic SELF fixture identity changed")
            # One canonical fact ID per relation, not a joined legacy line:
            # otherwise target projection can incorrectly treat wife+children
            # as one unseparable proven group. These are TEST data only.
            body = render_atomic_facts(
                tuple(facts), "r0-synthetic-relations", tuple(range(len(facts))), "2026-10-04"
            )
            repo.replace_text(path, serialize_note(replace(note, content=body)))
        elif step.get("kind") == "create_task":
            task_name, task_id, task_path = (step.get("name"), step.get("id"), step.get("path"))
            if not all(isinstance(v, str) and v for v in (task_name, task_id, task_path)):
                raise Refused("Invalid synthetic Task fixture")
            create_entity(
                repo,
                product.canonical_schema,
                path=task_path,
                entity_id=task_id,
                metadata={"name": task_name, "type": "task", "status": "pending"},
                content=f"- {task_name}.\n",
                actor="r0-synthetic-fixture",
                now=CLOCK,
            )
        else:
            raise Refused("Unknown synthetic fixture setup operation")
    if steps:
        executor = product.hybrid_candidate_execute
        executor.context_index.rebuild(repo, product.canonical_schema, executor.embedder)
        executor.semantic_index.rebuild(repo, product.canonical_schema, executor.embedder)
    return len(steps)


def _attach_prewrite_diagnostics(product: Any, evidence: dict[str, Any]) -> None:
    """Observe the existing P4 trust boundary without authorizing any action.

    The bridge stores only named gates, bounded numeric/bool counters and a
    request ID digest. No prompts, identities, private notes or model output.
    Production already has this callback; this test composes with it rather
    than replacing or bypassing the underlying decision.
    """
    executor = product.hybrid_candidate_execute
    if executor is None or not callable(getattr(executor, "_observe_prewrite", None)):
        raise Refused("Active P4 prewrite diagnostic boundary unavailable")
    previous = executor.prewrite_diagnostic
    items: list[dict[str, Any]] = []
    evidence["core_prewrite_gates"] = items

    def observed(delivery: str, gate: str, values: dict[str, int | bool]) -> None:
        if len(items) < 64:
            items.append(
                {
                    "delivery_sha256": hashlib.sha256(delivery.encode("utf-8")).hexdigest(),
                    "gate": gate,
                    "values": {
                        key: value
                        for key, value in values.items()
                        if isinstance(key, str) and (type(value) is bool or type(value) is int)
                    },
                }
            )
        if previous is not None:
            previous(delivery, gate, values)

    executor.prewrite_diagnostic = observed


def _record_usage(receipt: Path, usage: list[dict[str, Any]]) -> None:
    """Persist redacted per-call telemetry without weakening the reservation."""
    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["provider_usage"] = usage
    temporary = receipt.with_suffix(receipt.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.chmod(0o600)
    temporary.replace(receipt)


def _usage_wrapper(usage: list[dict[str, Any]], receipt: Path):
    """Bound provider calls and charge pessimistic preflight cost, even on errors."""
    from openai.resources.responses.responses import Responses

    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"]
    original = Responses.create
    lock = threading.Lock()
    counters = {"attempts": 0, "charged": 0.0, "inflight": 0.0}

    def bounded(self, *args, **kwargs):
        model = kwargs.get("model")
        rate = rates.get(model)
        maximum = kwargs.get("max_output_tokens")
        if not isinstance(rate, dict) or type(maximum) is not int or not 1 <= maximum <= 6000:
            raise Refused("Unknown model or unbounded R0 provider output")
        # UTF-8 bytes is conservative compared with prompt token count.
        payload_bytes = len(json.dumps(kwargs, ensure_ascii=False, default=str).encode("utf-8"))
        ceiling = (
            payload_bytes * rate["input_per_million"] + maximum * rate["output_per_million"]
        ) / 1_000_000
        with lock:
            if (
                counters["attempts"] >= MAX_CALLS
                or counters["charged"] + counters["inflight"] + ceiling > RESERVE_USD
            ):
                raise Refused(
                    f"R0 provider preflight veto model={model} input_bytes={payload_bytes} output_cap={maximum} estimated_usd={ceiling:.5f} charged_usd={counters['charged']:.5f} pending_usd={counters['inflight']:.5f} attempts={counters['attempts']}"
                )
            counters["attempts"] += 1
            counters["inflight"] += ceiling
        try:
            reply = original(self, *args, **kwargs)
        except BaseException:
            with lock:
                counters["charged"] += ceiling
                counters["inflight"] -= ceiling
                usage.append(
                    {"model": model, "charged_usd": round(ceiling, 8), "usage_complete": False}
                )
                _record_usage(receipt, usage)
            raise
        observed = getattr(reply, "usage", None)
        input_tokens = getattr(observed, "input_tokens", None)
        output_tokens = getattr(observed, "output_tokens", None)
        complete = type(input_tokens) is int and type(output_tokens) is int
        charge = (
            (input_tokens * rate["input_per_million"] + output_tokens * rate["output_per_million"])
            / 1_000_000
            if complete
            else ceiling
        )
        # Never book less than a valid price, but refuse an anomalously
        # expensive response rather than continuing to call the provider.
        with lock:
            counters["charged"] += charge
            counters["inflight"] -= ceiling
            usage.append(
                {
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "usage_complete": complete,
                    "charged_usd": round(charge, 8),
                    "provider_schema": kwargs.get("text", {}).get("format", {}).get("name"),
                }
            )
            _record_usage(receipt, usage)
        return reply

    return patch.object(Responses, "create", bounded)


def _trace(
    case: str, digest: str, outcome: str, usage: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return {
        "case": case,
        "source_sha256": digest,
        "outcome": outcome,
        "visible_ui_submitted": extra.get("visible", False),
        "real_n8n_single_throwaway_container": extra.get("n8n", False),
        "isolated_actor_vault": extra.get("isolated", False),
        "fresh_vault_per_case": extra.get("isolated", False),
        "original_fixture_13_notes": extra.get("fixture", False),
        "fixed_original_clock": extra.get("clock", False),
        "source_preserved": extra.get("source", False),
        "markdown_source_readback": extra.get("markdown", False),
        "ui_reload_readback": extra.get("ui", False),
        "replay_checked": extra.get("replay", False),
        "cloudflare_public_access_used": False,
        "provider_usage": usage,
        "forensics": extra.get("forensics", {}),
    }


def run(case: str, digest: str, receipt: Path) -> dict[str, Any]:
    if os.environ.get("ODYSSEY_R0_LIVE_APPROVED") != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise Refused("requires transient-systemd approval and protected provider environment")
    _receipt(receipt, case, digest)
    source = _case(case, digest)
    import scripts.odyssey_e4_live_browser_n8n as e4

    # This is selection at the harness boundary only. The n8n workflow is the
    # existing E4 workflow and its source guard accepts precisely this source.
    e4.E4_SOURCE = source
    usage: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {"case": case, "source_sha256": digest, "clock": CLOCK, "self": SELF}
    with (
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-dynamic-r0-", dir="/tmp") as tmp,
        tempfile.TemporaryDirectory(prefix="odyssey-n8n-bridge-r0-", dir="/tmp") as bridge,
    ):
        root, share = Path(tmp), Path(bridge)
        share.chmod(0o700)
        (share / "broker.cjs").write_text(e4.BROKER_JS, encoding="utf-8")
        (share / "broker.cjs").chmod(0o444)
        with _r0_product(root / "data") as (repo, actor, product):
            _attach_prewrite_diagnostics(product, evidence)
            original_before_setup = _snapshot(repo)
            evidence["fixture_count"] = len(original_before_setup)
            if len(original_before_setup) != 13:
                raise Refused("R0 original fixture is not exactly 13 Markdown notes")
            evidence["fixture_setup_actions"] = _prepare_additional_test_fixture(
                case, repo, product
            )
            before = _snapshot(repo)
            evidence["fixture_count_after_setup"] = len(before)
            sock = share / "writer.sock"
            token = secrets.token_urlsafe(32)
            results: list[dict[str, Any]] = []
            n8n_calls = [0]
            writer_failures = []

            class Writer(socketserver.StreamRequestHandler):
                def handle(self):
                    body = {"status": 403, "body": {"error": "denied"}}
                    try:
                        payload = json.loads(self.rfile.readline(16001))
                        if (
                            set(payload) == {"request_id", "request", "conversation_id"}
                            and payload["request"] == source
                            and payload["conversation_id"] == "main"
                            and re.fullmatch(r"[A-Za-z0-9-]{8,110}", payload["request_id"])
                        ):
                            result = product.execute_product(
                                source, payload["request_id"], "main", actor
                            )
                            results.append(result)
                            body = {"status": 200, "body": result}
                    except Exception as error:
                        writer_failures.append(
                            {"class": type(error).__name__, "detail": str(error)[:170]}
                        )
                        body = {"status": 500, "body": {"error": type(error).__name__}}
                    self.wfile.write((json.dumps(body, ensure_ascii=False) + "\n").encode())

            def private(endpoint: str, payload: dict) -> tuple[int, dict]:
                con = HTTPConnection("127.0.0.1", server.server_port, timeout=30)
                con.request(
                    "POST",
                    endpoint,
                    json.dumps(
                        {
                            **payload,
                            "authenticated_actor": {"stable_user_id": actor.stable_user_id},
                        },
                        ensure_ascii=False,
                    ).encode(),
                    {"Content-Type": "application/json"},
                )
                response = con.getresponse()
                value = json.loads(response.read())
                con.close()
                return response.status, value

            class Bridge(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass

                def auth(self):
                    cookie = SimpleCookie()
                    cookie.load(self.headers.get("Cookie", ""))
                    value = cookie.get("odyssey_test_auth")
                    return value is not None and secrets.compare_digest(value.value, token)

                def send_json(self, code: int, value: dict):
                    raw = json.dumps(value, ensure_ascii=False).encode()
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def do_GET(self):
                    if not self.auth():
                        self.send_error(403)
                        return
                    name = (
                        "index.html"
                        if urlsplit(self.path).path == "/"
                        else urlsplit(self.path).path.lstrip("/")
                    )
                    file = (WEB / name).resolve()
                    if not file.is_file() or not file.is_relative_to(WEB.resolve()):
                        self.send_error(404)
                        return
                    raw = file.read_bytes()
                    self.send_response(200)
                    self.send_header(
                        "Content-Type",
                        "text/javascript"
                        if name.endswith(".js")
                        else mimetypes.guess_type(name)[0] or "application/octet-stream",
                    )
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def do_POST(self):
                    if not self.auth():
                        self.send_json(403, {"error": "auth"})
                        return
                    try:
                        data = json.loads(
                            self.rfile.read(int(self.headers.get("Content-Length", "0")))
                        )
                    except Exception:
                        self.send_json(400, {"error": "input"})
                        return
                    uri = urlsplit(self.path).path
                    if uri == "/api/conversation":
                        op = data.pop("operation", None)
                        if op == "presence":
                            self.send_json(200, {"status": "ignored"})
                            return
                        target = {
                            "main": "/conversation/main",
                            "progress": "/conversation/progress",
                            "turn": "/conversation/turn",
                        }.get(op)
                        if target:
                            code, value = private(target, data)
                            self.send_json(code, value)
                            return
                    if uri == "/api/notes" and data.get("operation") in {
                        "capabilities",
                        "query",
                        "detail",
                        "backlinks",
                    }:
                        code, value = private("/notes", data)
                        self.send_json(code, value)
                        return
                    if uri == "/api/calendar" and data.get("operation") in {"month", "day", "week"}:
                        code, value = private("/calendar", data)
                        self.send_json(code, value)
                        return
                    if uri == "/api/request" and set(data) == {
                        "request",
                        "request_id",
                        "conversation_id",
                    }:
                        n8n_calls[0] += 1
                        code, value = e4.docker_post(container, data)
                        durable = {k: v for k, v in value.items() if k != "route"}
                        if code == 200:
                            private("/conversation/assistant-response", {"response": durable})
                        self.send_json(code, value)
                        return
                    self.send_json(403, {"error": "operation"})

            with socketserver.ThreadingUnixStreamServer(str(sock), Writer) as unix:
                unix_thread = threading.Thread(target=unix.serve_forever, daemon=True)
                unix_thread.start()
                server = ThreadingHTTPServer(
                    ("127.0.0.1", 0),
                    __import__("odyssey_runtime.server", fromlist=["_handler_for"])._handler_for(
                        product
                    ),
                )
                server_thread = threading.Thread(target=server.serve_forever, daemon=True)
                server_thread.start()
                try:
                    with (
                        _usage_wrapper(usage, receipt),
                        e4.isolated_n8n(root, sock, share) as container,
                    ):
                        public = ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
                        public_thread = threading.Thread(target=public.serve_forever, daemon=True)
                        public_thread.start()
                        try:
                            env = {
                                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                "HOME": str(Path.home()),
                                "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH")
                                or "/home/ragdehl/projects/.odyssey-agent-runs/e6-chromium-runtime-deps/root/usr/lib/aarch64-linux-gnu",
                                "ODYSSEY_R0_BROWSER_URL": f"http://127.0.0.1:{public.server_port}/",
                                "ODYSSEY_R0_SOURCE": source,
                                "ODYSSEY_R0_AUTH": token,
                            }
                            browser = subprocess.run(
                                ["node", str(ROOT / "scripts/odyssey_r0_real_browser_case.cjs")],
                                cwd=ROOT,
                                text=True,
                                capture_output=True,
                                env=env,
                                timeout=230,
                                check=False,
                            )
                            observed = json.loads(
                                [line for line in browser.stdout.splitlines() if line.strip()][-1]
                            )
                            evidence["browser"] = observed
                            after = _snapshot(repo)
                            from odyssey_core.notes import parse_note, validate_note

                            for text in after.values():
                                validate_note(parse_note(text), product.canonical_schema)
                            evidence["markdown_before_sha256"] = hashlib.sha256(
                                json.dumps(before, sort_keys=True).encode()
                            ).hexdigest()
                            evidence["markdown_after_sha256"] = hashlib.sha256(
                                json.dumps(after, sort_keys=True).encode()
                            ).hexdigest()
                            evidence["changed_notes"] = sum(
                                before.get(path) != text for path, text in after.items()
                            )
                            replay_ok = False
                            if results:
                                replay = product.execute_product(
                                    source, results[0]["request_id"], "main", actor
                                )
                                replay_ok = (
                                    replay.get("delivery_replayed") is True
                                    and _snapshot(repo) == after
                                )
                            evidence["replay_ok"] = replay_ok
                            evidence["n8n_request_count"] = n8n_calls[0]
                            evidence["writer_failures"] = writer_failures
                            evidence["runtime_status"] = (
                                results[0].get("status") if results else "none"
                            )
                            if results:
                                original_result = results[0]
                                detail = original_result.get("request_detail") or {}
                                evidence["product_diagnostic"] = {
                                    "status": original_result.get("status"),
                                    "kind": original_result.get("kind"),
                                    "clarification_code": original_result.get("clarification_code"),
                                    "message": str(original_result.get("message") or "")[:240],
                                    "detail_issue": detail.get("diagnostic_issue"),
                                    "routes": [
                                        {
                                            "capability": row.get("capability"),
                                            "status": row.get("status"),
                                            "reason": str(row.get("reason") or "")[:180],
                                            "writes": len(row.get("writes") or []),
                                        }
                                        for row in (
                                            (original_result.get("execution_flow") or {}).get(
                                                "routes"
                                            )
                                            or []
                                        )
                                    ],
                                }
                            browser_ok = browser.returncode == 0 and observed.get("pass") is True
                            visible = browser_ok and observed.get("sourceShown") is True
                            ui = (
                                browser_ok
                                and observed.get("notesChecked") is True
                                and observed.get("calendarChecked") is True
                            )
                            source_proof = bool(results) and any(
                                (result.get("execution_flow") or {}).get("input") == source
                                for result in results
                            )
                            # Running the application is not itself a semantic
                            # oracle. Even a completed write remains deferred
                            # until independent source/fact audit proves it.
                            outcome = (
                                "deferred"
                                if (
                                    visible
                                    and ui
                                    and source_proof
                                    and replay_ok
                                    and n8n_calls[0] > 0
                                )
                                else "failed"
                            )
                            return _trace(
                                case,
                                digest,
                                outcome,
                                usage,
                                visible=visible,
                                n8n=n8n_calls[0] > 0,
                                isolated=True,
                                fixture=True,
                                clock=True,
                                source=source_proof,
                                markdown=True,
                                ui=ui,
                                replay=replay_ok,
                                forensics=evidence,
                            )
                        finally:
                            public.shutdown()
                            public.server_close()
                            public_thread.join(timeout=2)
                finally:
                    server.shutdown()
                    server.server_close()
                    server_thread.join(timeout=2)
                    unix.shutdown()
                    unix_thread.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        required=True,
    )
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        trace = run(args.case, args.source_sha256, args.receipt)
    except Exception as error:
        trace = _trace(
            args.case,
            args.source_sha256,
            "failed",
            [],
            forensics={"error": type(error).__name__, "detail": str(error)[:200]},
        )
    if trace.get("provider_usage"):
        try:
            record = _receipt(args.receipt, args.case, args.source_sha256)
            rows = trace["provider_usage"]
            cost = round(sum(float(x.get("charged_usd", RESERVE_USD)) for x in rows), 8)
            if all(x.get("usage_complete") is True for x in rows) and 0 <= cost <= RESERVE_USD:
                from scripts.odyssey_r0_browser_campaign import _atomic_json

                record.update({"usage_complete": True, "charged_usd": cost})
                _atomic_json(args.receipt, record)
        except (ValueError, KeyError, TypeError, OSError):
            pass
    print(json.dumps(trace, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
