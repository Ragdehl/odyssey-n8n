#!/usr/bin/env python3
"""Single-shot synthetic n8n-to-canonical weekly E5 smoke; no prod."""

from __future__ import annotations

import fcntl
import json
import uuid
from pathlib import Path
from urllib import request

from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository

lock = Path("/tmp/odyssey-e5-dev-e2e.lock").open("w")
fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
repo = VaultRepository(Path("/data/odyssey-dev/vault"))
label = "Natacion prueba E5 " + uuid.uuid4().hex[:7].upper()
source = f"{label} todos los lunes del 5 de abril al 28 de junio de 2027."
body = json.dumps(
    {
        "request": source,
        "request_id": "e5-weekly-" + uuid.uuid4().hex[:20],
        "conversation_id": "main",
    },
    ensure_ascii=False,
).encode()
req = request.Request(
    "http://172.18.0.1:28780/api/request",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with request.urlopen(req, timeout=185) as result:
    reply = json.loads(result.read(500000))
print(
    "E5_WEEKLY_REQUEST",
    json.dumps(
        {"http": 200, "status": reply.get("status"), "kind": reply.get("kind")}, ensure_ascii=False
    ),
    flush=True,
)
matching = []
for path in repo.list_markdown_paths():
    note = parse_note(repo.read_text(path))
    if note.metadata.get("name") == label:
        matching.append((str(path), note.metadata))
print(
    "E5_WEEKLY_PHYSICAL",
    json.dumps(
        [
            {
                "path": p,
                "type": n.get("type"),
                "start_date": n.get("start_date"),
                "end_date": n.get("end_date"),
                "recurrence_weekday": n.get("recurrence_weekday"),
                "event_status": n.get("event_status"),
            }
            for p, n in matching
        ],
        ensure_ascii=False,
    ),
    flush=True,
)


def day(value):
    body = json.dumps({"operation": "day", "date": value}).encode()
    req = request.Request(
        "http://172.18.0.1:28780/api/calendar",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        data = json.load(response)
    return len([x for x in data.get("events", []) if x.get("source", {}).get("name") == label])


days = {
    value: day(value)
    for value in ["2027-04-05", "2027-04-06", "2027-04-12", "2027-06-28", "2027-07-05"]
}
pass_ = (
    reply.get("status") == "completed"
    and len(matching) == 1
    and matching[0][1].get("type") == "event"
    and matching[0][1].get("recurrence_weekday") == 0
    and matching[0][1].get("end_date") == "2027-06-28"
    and days
    == {"2027-04-05": 1, "2027-04-06": 0, "2027-04-12": 1, "2027-06-28": 1, "2027-07-05": 0}
)
print(
    "E5_WEEKLY_SUMMARY",
    json.dumps(
        {
            "pass": pass_,
            "days": days,
            "label": label,
            "request_status": reply.get("status"),
            "event_count": len(matching),
        },
        ensure_ascii=False,
    ),
    flush=True,
)
raise SystemExit(0 if pass_ else 2)
