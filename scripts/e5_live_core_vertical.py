#!/usr/bin/env python3
"""E5 live GPT+Temporal+E3+Markdown+Calendar in a disposable local vault.

This is NOT an n8n/browser test. Emits only synthetic result counts and codes.
Run only in an ephemeral systemd unit with the authorized EnvironmentFile.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from odyssey_apps.calendar import CalendarQueryService
from odyssey_apps.events import EVENT_SCHEMA_EXTENSION
from odyssey_apps.events.execution import execute_event_candidate
from odyssey_apps.events.mutations import EventMutationService
from odyssey_apps.events.provider import OpenAIEventInterpreter
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.apps.calendar.test_queries import Embedder


def main() -> int:
    if os.environ.get("ODYSSEY_E5_LIVE_APPROVED") != "1":
        raise SystemExit("E5 live gate not authorized")
    schema_base = json.loads(
        (Path(__file__).resolve().parents[1] / "config/note-schema.json").read_text()
    )
    schema = compose_application_schema(
        schema_base, (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION)
    )
    clock = {"date": "2026-10-22", "time": "08:00:00", "timezone": "Europe/Paris"}
    now = "2026-10-22T08:00:00+02:00"
    cases = [
        ("create", "Foto del colegio el 22 de noviembre de 2026.", "completed"),
        ("update", "Cambia Foto del colegio al 24 de noviembre de 2026.", "completed"),
        ("cancel", "Cancela Foto del colegio.", "completed"),
    ]
    with tempfile.TemporaryDirectory(prefix="odyssey-e5-real-") as directory:
        root = Path(directory)
        (root / "vault").mkdir(exist_ok=True)
        repository = VaultRepository(root / "vault")
        mutations = EventMutationService(repository, schema)
        provider = OpenAIEventInterpreter.from_environment()
        temporal = OpenAITemporalInterpreter.from_environment(clock)
        observed = []
        for index, (operation, source, expected) in enumerate(cases):
            started = time.monotonic()
            candidate = provider.interpret(source)
            result_temporal = temporal.interpret(source) if operation != "cancel" else None
            result = execute_event_candidate(
                candidate=candidate,
                temporal=result_temporal,
                repository=repository,
                schema=schema,
                mutations=mutations,
                request_id=f"e5-smoke-{index}",
                actor="fixture",
                now=now,
                authenticated=True,
            )
            observed.append(
                {
                    "case": operation,
                    "status": result.status.value,
                    "error": result.planning_error,
                    "duration_s": round(time.monotonic() - started, 2),
                    "event_count": sum(
                        parse_note(repository.read_text(path)).metadata.get("type") == "event"
                        for path in repository.list_markdown_paths()
                    ),
                }
            )
            print("E5_LIVE_CASE=" + json.dumps(observed[-1]), flush=True)
            if result.status.value != expected or observed[-1]["event_count"] != 1:
                break
        index = ContextIndex(root / "context.sqlite3")
        index.rebuild(repository, schema, Embedder())
        calendar = CalendarQueryService(
            repository, schema, NotesQueryService(repository, schema, index)
        )
        old = len(calendar.day("2026-11-22").events)
        moved = len(calendar.day("2026-11-24").events)
        actual_events = sum(
            1
            for path in repository.list_markdown_paths()
            if parse_note(repository.read_text(path)).metadata.get("type") == "event"
        )
        passed = (
            len(observed) == 3
            and all(row["status"] == "completed" and row["event_count"] == 1 for row in observed)
            and old == 0
            and moved == 0
            and actual_events == 1
        )
        print(
            "E5_LIVE_SUMMARY="
            + json.dumps(
                {
                    "passed": passed,
                    "cases": len(observed),
                    "old_calendar": old,
                    "new_calendar_after_cancel": moved,
                    "markdown_files": len(tuple(repository.list_markdown_paths())),
                    "event_notes": actual_events,
                    "provider": "real",
                    "n8n": False,
                    "browser": False,
                }
            ),
            flush=True,
        )
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
