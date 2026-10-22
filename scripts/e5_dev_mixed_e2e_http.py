#!/usr/bin/env python3
"""E5 real n8n + GPT mixed independent Event+Task, Markdown, Calendar, replay.

Disposable synthetic note names. DEV-only, exclusive operator lock.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import uuid
from pathlib import Path
from urllib import request

from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository

BASE = "http://172.18.0.1:28780"
VAULT = VaultRepository(Path("/data/odyssey-dev/vault"))
lock = Path("/tmp/odyssey-e5-dev-e2e.lock").open("w")
fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def api(path: str, payload: dict, *, timeout=200):
    req = request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return response.status, json.load(response)


def scoped(token):
    found = []
    for path in VAULT.list_markdown_paths():
        note = parse_note(VAULT.read_text(path))
        if token in str(note.metadata.get("name", "")):
            found.append((str(path), note.metadata))
    return found


def signatures():
    return {
        str(p): hashlib.sha256(VAULT.read_text(p).encode()).hexdigest()
        for p in VAULT.list_markdown_paths()
    }


def main():
    source_commit = Path("/data/odyssey-dev/runtime/deployed-commit").read_text().strip()
    expected = Path(__file__).resolve().parents[1]
    assert (
        source_commit
        == __import__("subprocess")
        .check_output(["git", "-C", str(expected), "rev-parse", "HEAD"], text=True)
        .strip()
    )
    event_token = uuid.uuid4().hex[:7].upper()
    task_token = uuid.uuid4().hex[:7].upper()
    assert event_token != task_token
    ev = f"Concierto ficticio E5 {event_token}"
    task = f"presentar informe fiscal {task_token}"
    source = f"{ev} el 24 de noviembre de 2026. Tengo que {task} el 25 de noviembre de 2026."
    before_ids = {meta["id"] for _, meta in scoped(event_token) + scoped(task_token)}
    assert not before_ids
    delivery = "e5-mixed-" + uuid.uuid4().hex[:20]
    http, result = api(
        "/api/request", {"request": source, "conversation_id": "main", "request_id": delivery}
    )
    print(
        "E5_MIXED_CREATE="
        + json.dumps({"http": http, "status": result.get("status"), "kind": result.get("kind")}),
        flush=True,
    )
    records = scoped(event_token) + scoped(task_token)
    print(
        "E5_MIXED_PHYSICAL="
        + json.dumps(
            [
                {
                    "type": m.get("type"),
                    "name": m.get("name"),
                    "date": m.get("start_date", m.get("target_date")),
                    "id_present": bool(m.get("id")),
                }
                for _, m in records
            ]
        ),
        flush=True,
    )
    if result.get("status") != "completed":
        return 2
    events = [m for _, m in records if m.get("type") == "event"]
    tasks = [m for _, m in records if m.get("type") == "task"]
    assert len(events) == 1 and len(tasks) == 1, "E5_MIXED_NOTE_COUNT"
    assert events[0].get("start_date") == "2026-11-24"
    cal_status, cal = api("/api/calendar", {"operation": "day", "date": "2026-11-24"})
    assert cal_status == 200 and any(
        e.get("source", {}).get("id") == events[0]["id"] for e in cal.get("events", [])
    )
    cal_status, cal = api("/api/calendar", {"operation": "day", "date": "2026-11-25"})
    assert cal_status == 200 and any(
        item.get("source", {}).get("id") == tasks[0]["id"] for item in cal.get("tasks", [])
    ), "E5_MIXED_TASK_NOT_IN_CALENDAR"
    before = signatures()
    http, replay = api(
        "/api/request", {"request": source, "conversation_id": "main", "request_id": delivery}
    )
    assert http == 200 and replay.get("status") == "completed"
    assert signatures() == before, "E5_MIXED_REPLAY_CHANGED_CANONICAL_BYTES"
    print(
        "E5_MIXED_SUMMARY="
        + json.dumps(
            {
                "pass": True,
                "event_notes": len(events),
                "task_notes": len(tasks),
                "replay_byte_identical": True,
                "calendar_events": 1,
                "calendar_tasks": 1,
                "synthetic": True,
                "production_touched": False,
                "commit": source_commit[:12],
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            "E5_MIXED_STOP=" + json.dumps({"error": type(exc).__name__, "reason": str(exc)[:150]}),
            flush=True,
        )
        raise SystemExit(1) from exc
