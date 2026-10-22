#!/usr/bin/env python3
"""Isolated DEV-only real HTTP n8n → GPT → E3 → Markdown → Calendar → Chromium.

Only synthetic, unique Events are written into the DEV vault. Never PROD.
Every success is proved by canonical readback rather than HTTP alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import request
from uuid import uuid4

from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository

SRC = Path(__file__).resolve().parents[1]
ROOT = Path("/data/odyssey-dev")
N8N = "http://172.18.0.1:28780"
DATE1 = "2026-10-29"
DATE2 = "2026-10-30"
REPORT = Path(
    "/home/ragdehl/projects/.odyssey-agent-runs/e5-dev-rollout-20261022/dev-http-browser-report.json"
)


def post(path: str, value: dict, *, timeout=210):
    req = request.Request(
        N8N + path,
        json.dumps(value, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read(450_000))
        assert response.status == 200, (path, response.status)
        return data


def fingerprints(repo):
    return {
        str(path): hashlib.sha256(repo.read_text(path).encode("utf-8")).hexdigest()
        for path in repo.list_markdown_paths()
    }


def events(repo):
    found = []
    for path in repo.list_markdown_paths():
        note = parse_note(repo.read_text(path))
        if note.metadata.get("type") == "event":
            found.append((str(path), note.metadata))
    return found


def browser(label, date, visible):
    env = os.environ.copy()
    env.update(
        {
            "ODYSSEY_E5_EVENT_LABEL": label,
            "ODYSSEY_E5_DAY": date,
            "ODYSSEY_E5_VISIBLE": "1" if visible else "0",
            "LD_LIBRARY_PATH": "/tmp/odyssey-p4-browser-deps/root/usr/lib/aarch64-linux-gnu",
        }
    )
    check = subprocess.run(
        ["node", str(SRC / "scripts/e5_dev_browser_event.cjs")],
        cwd=str(SRC),
        env=env,
        capture_output=True,
        text=True,
        timeout=155,
    )
    lines = [line for line in check.stdout.splitlines() if line.startswith("E5_DEV_CHROMIUM=")]
    if not lines:
        raise RuntimeError("E5_DEV_BROWSER_NO_RECEIPT")
    receipt = json.loads(lines[-1].removeprefix("E5_DEV_CHROMIUM="))
    if not receipt.get("pass") or check.returncode:
        print("E5_BROWSER_FAILURE=" + json.dumps(receipt, ensure_ascii=False)[:800], flush=True)
        raise RuntimeError("E5_DEV_BROWSER_VERIFICATION_FAILED")
    return receipt


def day_events(date):
    response = post("/api/calendar", {"operation": "day", "date": date}, timeout=30)
    assert response.get("kind") == "calendar_day", response.get("kind")
    return response.get("events", [])


def main():
    deployed = (ROOT / "runtime/deployed-commit").read_text().strip()
    expected = (SRC / "deploy/odyssey-dev-runtime.service").read_text()
    assert deployed.startswith("924067e"), ("not deployed candidate", deployed[:12])
    assert "ODYSSEY_ENABLED_APPLICATIONS=tasks,events" in expected
    repo = VaultRepository(ROOT / "vault")
    before_events = {meta["id"] for _, meta in events(repo)}
    label = "Concierto ficticio E5 " + uuid4().hex[:7].upper()
    requests = [
        f"{label} el 29 de octubre de 2026.",
        None,
        None,
    ]
    report = {"commit": deployed, "synthetic": True, "prod_touched": False, "steps": []}

    def send(step, source, delivery):
        started = time.monotonic()
        answer = post(
            "/api/request", {"request": source, "request_id": delivery, "conversation_id": "main"}
        )
        row = {
            "step": step,
            "http": 200,
            "status": answer.get("status"),
            "seconds": round(time.monotonic() - started, 2),
        }
        report["steps"].append(row)
        print("E5_DEV_REQUEST=" + json.dumps(row), flush=True)
        if answer.get("status") != "completed":
            raise RuntimeError("E5_" + step.upper() + "_NOT_COMPLETED")
        return answer

    def event_readback():
        fresh = [(path, meta) for path, meta in events(repo) if meta["id"] not in before_events]
        if len(fresh) != 1:
            raise RuntimeError("E5_CANONICAL_CARDINALITY_INVALID")
        return fresh[0]

    delivery = "e5-dev-" + uuid4().hex[:24]
    send("create", requests[0], delivery)
    path, meta = event_readback()
    assert meta["start_date"] == DATE1 and meta["event_status"] == "scheduled", meta
    assert len([e for e in day_events(DATE1) if e["source"]["id"] == meta["id"]]) == 1
    assert len([e for e in day_events(DATE2) if e["source"]["id"] == meta["id"]]) == 0
    actual_name = meta["name"]
    report["create"] = {"event_count": 1, "calendar_visible": True}
    before_replay = fingerprints(repo)
    send("create_replay", requests[0], delivery)
    assert fingerprints(repo) == before_replay, "E5 replay altered Markdown"
    report["replay"] = {"byte_identical": True}
    report["browser_create"] = browser(actual_name, DATE1, True)
    edit = f"Cambia {actual_name} al 30 de octubre de 2026."
    send("reschedule", edit, "e5-dev-" + uuid4().hex[:24])
    _, after = event_readback()
    assert after["id"] == meta["id"] and after["start_date"] == DATE2
    assert len([e for e in day_events(DATE1) if e["source"]["id"] == meta["id"]]) == 0
    assert len([e for e in day_events(DATE2) if e["source"]["id"] == meta["id"]]) == 1
    report["browser_update"] = browser(actual_name, DATE2, True)
    query = "¿Qué eventos del colegio hay en octubre de 2026?"
    answer = post(
        "/api/request",
        {"request": query, "request_id": "e5-dev-" + uuid4().hex[:24], "conversation_id": "main"},
    )
    report["query"] = {
        "status": answer.get("status"),
        "snapshot_count": len((answer.get("note_result_snapshot") or {}).get("note_ids", [])),
    }
    print("E5_DEV_QUERY=" + json.dumps(report["query"]), flush=True)
    cancel = f"Cancela {actual_name}."
    send("cancel", cancel, "e5-dev-" + uuid4().hex[:24])
    _, done = event_readback()
    assert done["id"] == meta["id"] and done["event_status"] == "cancelled"
    assert len([e for e in day_events(DATE2) if e["source"]["id"] == meta["id"]]) == 0
    report["browser_cancel"] = browser(actual_name, DATE2, False)
    report["pass"] = report["query"]["status"] == "completed"
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    REPORT.chmod(0o600)
    print(
        "E5_DEV_E2E_SUMMARY="
        + json.dumps(
            {
                "pass": report["pass"],
                "operations": [r["step"] for r in report["steps"]],
                "byte_identical_replay": True,
                "browser_profiles": 2,
                "query_status": report["query"]["status"],
                "prod_touched": False,
            }
        ),
        flush=True,
    )
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(
            "E5_DEV_E2E_STOP=" + json.dumps({"type": type(exc).__name__, "detail": str(exc)[:180]}),
            flush=True,
        )
        sys.exit(1)
