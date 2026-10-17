"""Opt-in real GPT+product-runtime+Core Writer+HTTP exercise; ephemeral vault only.

Never deploys, never connects to n8n, never copies real user notes. The product
route code, not the benchmark implementation, owns GPT and Core execution.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from openai import OpenAI

from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from odyssey_runtime.server import _handler_for
from tests.runtime.test_whole_source_light_product_p4 import _fixture

# A safe HTTP replay is not proof that a required positive action succeeded.
EXPECTED = {
    "new_meeting": ("completed", 1, False),
    "cross_app": ("completed", 2, True),
    "two_dates": ("completed", 2, False),
    "third_person": ("completed", 1, False),
    "negative": ("needs_attention", 0, False),
    "implicit_undated_self": ("completed", 1, False),
    "pronoun_two_dates": ("completed", 2, False),
    "conditional": ("needs_attention", 0, False),
    "self_preference": ("completed", 1, False),
    "undated_third": ("needs_attention", 0, False),
}

INPUTS = (
    ("new_meeting", "Ayer hablé con Clara Solis."),
    ("cross_app", "Hoy he conocido a Maite Solis, mañana tengo que llamarla."),
    ("two_dates", "Hoy compré pan y mañana compraré leche."),
    ("third_person", "Hoy Bruno Prototipo ha conocido a Carla Prototipo."),
    ("negative", "No he conocido a Pedro Prototipo."),
    ("implicit_undated_self", "He conocido a Nerea Ensayo."),
    ("pronoun_two_dates", "Ayer hablé con Rebeca Ensayo y hoy he vuelto a hablar con ella."),
    ("conditional", "Si mañana conociera a Nuria Ensayo, la llamaría."),
    ("self_preference", "A mí me gusta pasear por el monte."),
    ("undated_third", "Raúl Ensayo vive en Zaragoza."),
)


def main():
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1":
        raise SystemExit("Explicit synthetic live-model approval is required")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Provider credentials unavailable")
    evidence = {
        "mode": "real-new-model-product-route-isolated-http",
        "browser": False,
        "n8n": False,
        "production_data": False,
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="p4-prod-actual-isolated-") as tmp:
        repo, actor, service, runtime = _fixture(Path(tmp))
        service.client = OpenAI(max_retries=0, timeout=80)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def post(source, request_id):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=150)
            body = {
                "request": source,
                "request_id": request_id,
                "conversation_id": "main",
                "authenticated_actor": {"stable_user_id": actor.stable_user_id},
            }
            connection.request(
                "POST", "/execute", json.dumps(body), {"Content-Type": "application/json"}
            )
            result = connection.getresponse()
            payload = json.loads(result.read())
            status = result.status
            connection.close()
            return status, payload

        try:
            selected = os.environ.get("ODYSSEY_P4_PRODUCT_ONLY")
            inputs = [item for item in INPUTS if not selected or item[0] in selected.split(",")]
            if not inputs:
                raise ValueError("No requested product scenarios")
            for index, (case, source) in enumerate(inputs):
                request_id = f"product-light-live-{index}"
                before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
                start = time.monotonic()
                try:
                    status, result = post(source, request_id)
                    after = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
                    changed = {
                        path: value for path, value in after.items() if before.get(path) != value
                    }
                    real_facts = 0
                    for _path, value in after.items():
                        note = parse_note(value)
                        real_facts += note.content.count("odyssey:fact request=" + request_id)
                    replay_http, replay = post(source, request_id)
                    replay_same = {
                        path: repo.read_text(path) for path in repo.list_markdown_paths()
                    } == after
                    expected_status, expected_facts, expected_new_task = EXPECTED[case]
                    fresh_tasks = sum(
                        parse_note(value).metadata.get("type") == "task"
                        for value in changed.values()
                    )
                    # Speaker/SELF and graph evidence for an undated Spanish
                    # first-person sentence cannot be inferred from a positive
                    # fact count. Check the actual Notes projection/backlink.
                    implicit_self_backlink = None
                    if case == "implicit_undated_self" and status == 200:
                        found = [
                            parse_note(body)
                            for body in after.values()
                            if parse_note(body).metadata.get("name") == "Nerea Ensayo"
                            and parse_note(body).metadata.get("type") == "person"
                        ]
                        implicit_self_backlink = len(found) == 1 and any(
                            back.source.id == "self-note"
                            for back in NotesQueryService(
                                repo, service.schema, service.context_index
                            )
                            .backlinks(found[0].metadata["id"])
                            .items
                        )
                    accepted = (
                        status == 200
                        and result.get("status") == expected_status
                        and real_facts == expected_facts
                        and (fresh_tasks > 0) == expected_new_task
                        and replay_http == 200
                        and replay.get("delivery_replayed") is True
                        and replay_same
                        and (expected_status != "needs_attention" or not changed)
                        and (implicit_self_backlink is None or implicit_self_backlink)
                    )
                    row = {
                        "accepted": accepted,
                        "expected_status": expected_status,
                        "expected_source_facts": expected_facts,
                        "fresh_task_count": fresh_tasks,
                        "case": case,
                        "http": status,
                        "status": result.get("status"),
                        "duration_s": round(time.monotonic() - start, 2),
                        "affected_count": len(result.get("affected_stable_note_ids") or []),
                        "physical_source_fact_count": real_facts,
                        "physical_changed_note_count": len(changed),
                        "implicit_self_backlink_verified": implicit_self_backlink,
                        "replay_http": replay_http,
                        "replay": replay.get("delivery_replayed"),
                        "replay_preserves_all_bytes": replay_same,
                        "clarification": result.get("clarification_code"),
                        "error": result.get("error"),
                        "task_count": sum(
                            parse_note(v).metadata.get("type") == "task" for v in after.values()
                        ),
                    }
                except Exception as error:
                    row = {
                        "case": case,
                        "error": type(error).__name__,
                        "duration_s": round(time.monotonic() - start, 2),
                    }
                evidence["cases"].append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    path = Path(tempfile.gettempdir()) / "odyssey-p4-product-live-actual.json"
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    return 0 if all(c.get("accepted") is True for c in evidence["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
