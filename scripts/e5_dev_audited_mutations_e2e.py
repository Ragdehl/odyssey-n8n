#!/usr/bin/env python3
"""Audit findings E5: real DEV HTTP GPT → E3 → Markdown → Calendar.

Isolated synthetic Event identities. One exclusive DEV writer, never PROD.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from urllib import request

from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[1]
REPO = VaultRepository(Path("/data/odyssey-dev/vault"))
WEB = "http://172.18.0.1:28780"
LOCK = Path("/tmp/odyssey-e5-dev-e2e.lock").open("w")


def send(path: str, body: dict, timeout: int = 180):
    req = request.Request(
        WEB + path,
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as reply:
        assert reply.status == 200
        return json.load(reply)


def event(name: str):
    matches = []
    for path in REPO.list_markdown_paths():
        note = parse_note(REPO.read_text(path))
        if note.metadata.get("type") == "event" and note.metadata.get("name") == name:
            matches.append((path, note.metadata))
    assert len(matches) == 1, ("wrong-event-cardinality", name, len(matches))
    return matches[0]


def fingerprint():
    return {
        str(path): hashlib.sha256(REPO.read_text(path).encode()).hexdigest()
        for path in REPO.list_markdown_paths()
    }


def message(text: str, delivery: str):
    answer = send(
        "/api/request", {"request": text, "conversation_id": "main", "request_id": delivery}
    )
    print(
        "E5_AUDIT_HTTP="
        + json.dumps(
            {
                "delivery_suffix": delivery[-7:],
                "status": answer.get("status"),
                "kind": answer.get("kind"),
            }
        ),
        flush=True,
    )
    return answer


def hits(day: str, note_id: str):
    data = send("/api/calendar", {"operation": "day", "date": day}, timeout=30)
    assert data.get("kind") == "calendar_day"
    return sum(e.get("source", {}).get("id") == note_id for e in data.get("events", []))


def main() -> int:
    fcntl.flock(LOCK.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    active = Path("/data/odyssey-dev/runtime/deployed-commit").read_text().strip()
    expected = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    assert active == expected, "DEV and tested source differ"
    resume = os.environ.get("ODYSSEY_E5_RESUME_EVENT", "")
    excursion = resume or f"Excursión ficticia Auditoría {uuid.uuid4().hex[:8].upper()}"
    theater = f"Teatro ficticio Auditoría {uuid.uuid4().hex[:8].upper()}"
    if resume:
        assert resume.startswith("Excursión ficticia Auditoría ")
        _, note = event(excursion)
        assert note["event_status"] == "scheduled"
        assert note["start_date"] == "2026-10-26" and note["revision"] == 1
        print("E5_AUDIT_RESUMED_VERIFIED_SAFE_WRONG_DAY=" + resume, flush=True)
    else:
        seed_exc = f"{excursion} el lunes 26 de octubre de 2026."
        answer = message(seed_exc, "e5-audit-create-" + uuid.uuid4().hex[:20])
        assert answer.get("status") == "completed", "excursion-create-failed"
        _, note = event(excursion)
        assert note["event_status"] == "scheduled" and note["start_date"] == "2026-10-26"
        before = fingerprint()
        wrong = f"Cancela {excursion} del viernes 30 de octubre de 2026."
        answer = message(wrong, "e5-audit-wrong-" + uuid.uuid4().hex[:20])
        # n8n presents runtime needs_attention as failed/cannot_answer.
        assert answer.get("status") == "needs_attention" or (
            answer.get("status") == "failed" and answer.get("kind") == "cannot_answer"
        ), "wrong-day-refusal-must-be-safe"
        assert fingerprint() == before, "wrong-day-changed-canonical"
        assert event(excursion)[1]["event_status"] == "scheduled"
    right = f"Cancela {excursion} del lunes 26 de octubre de 2026."
    answer = message(right, "e5-audit-right-" + uuid.uuid4().hex[:20])
    assert answer.get("status") == "completed", "correct-day-must-cancel"
    assert event(excursion)[1]["event_status"] == "cancelled"
    assert hits("2026-10-26", note["id"]) == 0

    seed_theater = f"{theater} el martes 27 de octubre de 2026."
    answer = message(seed_theater, "e5-audit-theater-" + uuid.uuid4().hex[:20])
    assert answer.get("status") == "completed", "theater-create-failed"
    _, old = event(theater)
    assert old["start_date"] == "2026-10-27"
    move = f"Mueve {theater} del martes 27 de octubre de 2026 al jueves 29 de octubre de 2026."
    delivery = "e5-audit-move-" + uuid.uuid4().hex[:20]
    answer = message(move, delivery)
    assert answer.get("status") == "completed", "old-new-move-failed"
    _, moved = event(theater)
    assert moved["start_date"] == "2026-10-29" and "end_date" not in moved
    assert hits("2026-10-27", moved["id"]) == 0
    assert hits("2026-10-28", moved["id"]) == 0
    assert hits("2026-10-29", moved["id"]) == 1
    before_replay = fingerprint()
    answer = message(move, delivery)
    assert answer.get("status") == "completed"
    assert fingerprint() == before_replay, "same-id-replay-modified-markdown"
    print(
        "E5_AUDIT_DEV_E2E="
        + json.dumps(
            {
                "pass": True,
                "wrong_date_cancel_rejected": True,
                "right_date_cancelled": True,
                "old_new_reschedule_correct": True,
                "no_fabricated_multi_day_event": True,
                "replay_byte_identical": True,
                "synthetic_only": True,
                "production_touched": False,
                "deployed_sha": active[:12],
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
            "E5_AUDIT_DEV_STOP="
            + json.dumps({"error_class": type(exc).__name__, "detail": str(exc)[:165]}),
            flush=True,
        )
        raise SystemExit(1) from exc
