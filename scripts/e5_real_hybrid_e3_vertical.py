#!/usr/bin/env python3
"""Real E5 Router → Event GPT → Temporal GPT → E3 in disposable Markdown.

Deliberately does not claim n8n or browser E2E.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

from odyssey_apps.calendar import CalendarQueryService
from odyssey_apps.events.execution import execute_event_candidate
from odyssey_apps.events.mutations import EventMutationService
from odyssey_apps.events.provider import OpenAIEventInterpreter
from odyssey_apps.events.schema import EVENT_SCHEMA_EXTENSION
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_core.context import ContextIndex
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.calendar.test_queries import Embedder


def main() -> int:
    if os.environ.get("ODYSSEY_E5_LIVE_APPROVED") != "1":
        raise SystemExit("Live E5 E2E not authorized")
    root_path = Path(__file__).resolve().parents[1]
    base = json.loads((root_path / "config/note-schema.json").read_text())
    schema = compose_application_schema(base, (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION))
    clock = {"date": "2026-10-22", "time": "08:00:00", "timezone": "Europe/Paris"}
    with tempfile.TemporaryDirectory(prefix="e5-physical-route-") as t:
        root = Path(t)
        (root / "vault").mkdir()
        repo = VaultRepository(root / "vault")
        context = ContextIndex(root / "context.sqlite3")
        embedder = Embedder()
        context.rebuild(repo, schema, embedder)
        client = OpenAI(max_retries=0, timeout=55)
        router = OpenAIFactCandidateRouter(client, prompt_revision="v6", event_routing=True)
        event_model = OpenAIEventInterpreter(client)
        temporal_model = OpenAITemporalInterpreter(client, clock, scoped_date_time_context=True)
        mutations = EventMutationService(repo, schema)
        actor = AuthenticatedActorContext("ae6adef2-df0b-45d7-b76a-32cc9a1e31e9")
        persisted_actor = {"human": actor.stable_user_id, "app": "fixture"}
        rows = []
        for ordinal, source in enumerate(
            (
                "Foto del colegio el 22 de noviembre de 2026.",
                "Cambia Foto del colegio al 24 de noviembre de 2026.",
                "Cancela Foto del colegio.",
            )
        ):

            def event_handler(text, rid, current_actor=None, _prior=()):
                if current_actor != actor:
                    raise ValueError("Events actor mismatch")
                candidate = event_model.interpret(text)
                temp = (
                    temporal_model.interpret(text)
                    if candidate.interpretation.operation.value in {"CREATE", "UPDATE"}
                    else None
                )
                return execute_event_candidate(
                    candidate=candidate,
                    temporal=temp,
                    repository=repo,
                    schema=schema,
                    mutations=mutations,
                    request_id=rid,
                    actor=persisted_actor,
                    now="2026-10-22T08:00:00+02:00",
                    authenticated=True,
                )

            response = execute_candidate_routed_message(
                source,
                router=router,
                temporal=temporal_model,
                core_planner_factory=lambda *_: None,
                candidate_coverage_factory=lambda *_: (_ for _ in ()).throw(
                    AssertionError("Events route must not execute Core candidate planning")
                ),
                repository=repo,
                schema=schema,
                context_index=context,
                semantic_index=None,
                embedder=embedder,
                contextual_reasoner=None,
                actor=persisted_actor,
                now="2026-10-22T08:00:00+02:00",
                context_limit=5,
                request_id_factory=lambda ordinal=ordinal: f"e5-routing-{ordinal}",
                bundle_compiler=lambda proposal: compile_hybrid_candidate_bundle(
                    proposal, enable_tasks=True, enable_events=True
                ),
                authenticated_actor=actor,
                event_route_executor=event_handler,
            )
            count = sum(
                parse_note(repo.read_text(path)).metadata.get("type") == "event"
                for path in repo.list_markdown_paths()
            )
            row = {
                "step": ordinal,
                "status": response.status.value,
                "events": count,
                "affected": len(response.affected_stable_note_ids),
                "error": response.planning_error,
                "clarification": response.clarification_code,
            }
            rows.append(row)
            print("E5_ROUTER_TO_E3_REAL=" + json.dumps(row), flush=True)
            if response.status.value != "completed" or count != 1:
                break
        context.rebuild(repo, schema, embedder)
        calendar = CalendarQueryService(repo, schema, NotesQueryService(repo, schema, context))
        visible_24 = len(calendar.day("2026-11-24").events)
        passed = (
            len(rows) == 3 and all(r["status"] == "completed" for r in rows) and visible_24 == 0
        )
        print(
            "E5_ROUTER_TO_CALENDAR_SUMMARY="
            + json.dumps(
                {
                    "pass": passed,
                    "steps": len(rows),
                    "event_count": rows[-1]["events"],
                    "calendar_cancelled_count": visible_24,
                    "n8n": False,
                    "browser": False,
                }
            ),
            flush=True,
        )
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
