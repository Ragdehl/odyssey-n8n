"""Fresh-provider mixed Core + Work Session P4 experiment, disposable vault only.

Router, source partition/reviewer, Core planner/speaker and Task-only reviewer
are fresh GPT calls. The task delegate is a concrete Core/Tasks Work Session
service with a known fixture task, not the full product Task interpreter. No
real browser, installed n8n, user notes or PROD state are touched.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

from odyssey_apps.tasks.interpretation import OpenAITaskInterpreter, TaskOperation
from odyssey_core.notes import parse_note
from tests.runtime.test_p4_independent_mixed_scopes import SOURCE, TASK, _runtime


class ObservedClient:
    """Log only call name and bounded semantic shape, not credentials."""

    def __init__(self, client):
        self.responses = self
        self.client = client
        self.names = []
        self.route_decisions = []

    def create(self, **kwargs):
        name = kwargs["text"]["format"]["name"]
        self.names.append(name)
        response = self.client.responses.create(**kwargs)
        if name == "odyssey_light_capability_route_v1":
            try:
                parsed = json.loads(response.output_text)
                self.route_decisions.append(
                    {
                        "capabilities": parsed.get("capabilities"),
                        "interpretation": parsed.get("interpretation"),
                        "app_scope_count": len(parsed.get("app_scopes", [])),
                        "scopes_independent": all(
                            item.get("depends_on_another_scope") is False
                            for item in parsed.get("app_scopes", [])
                        ),
                    }
                )
            except (TypeError, ValueError):
                self.route_decisions.append({"invalid": True})
        return response


def main() -> int:
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Synthetic GPT provider execution requires explicit local opt-in")
    with tempfile.TemporaryDirectory(prefix="p4-mixed-independent-real-") as tmp:
        repo, actor, executor, runtime, calls = _runtime(Path(tmp))
        # Separate real provider check that the product Tasks interpreter
        # would choose the proper domain operation on this exact scope.
        task_interpretation = OpenAITaskInterpreter.from_environment().interpret(TASK)
        task_interpreter_correct = (
            task_interpretation.operation is TaskOperation.START_WORK_SESSION
            and task_interpretation.task_reference is not None
        )
        client = ObservedClient(OpenAI(max_retries=0, timeout=80))
        executor.client = client
        try:
            first = runtime.execute_product(SOURCE, "p4-mixed-independent-real", "main", actor)
            pre_replay = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
            replay = runtime.execute_product(SOURCE, "p4-mixed-independent-real", "main", actor)
            identical = pre_replay == {
                path: repo.read_text(path) for path in repo.list_markdown_paths()
            }
            self_note = parse_note(repo.read_text("self.md"))
            preference = "correr por la tarde" in self_note.content.casefold()
            physical_note_summary = [
                {
                    "type": parse_note(repo.read_text(path)).metadata["type"],
                    "content_preview": parse_note(repo.read_text(path)).content[:280],
                }
                for path in repo.list_markdown_paths()
                if parse_note(repo.read_text(path)).content.strip()
            ]
            sessions = [
                parse_note(repo.read_text(p))
                for p in repo.list_markdown_paths()
                if parse_note(repo.read_text(p)).metadata["type"] == "work_session"
            ]
            evidence = {
                "status": first["status"],
                "complete": first["status"] == "completed",
                "preference_canonical": preference,
                "sessions_created": len(sessions),
                "task_service_calls": len(calls),
                "task_interpreter_real_gpt": task_interpretation.operation.value,
                "task_interpreter_correct": task_interpreter_correct,
                "same_id_replay": replay.get("delivery_replayed") is True,
                "replay_preserves_all_bytes": identical,
                "provider_steps": client.names,
                "router_decisions": client.route_decisions,
                "physical_note_summary": physical_note_summary,
                "temporary_vault_only": True,
            }
            print(json.dumps(evidence, ensure_ascii=False), flush=True)
            return (
                0
                if (
                    evidence["complete"]
                    and preference
                    and len(sessions) == 1
                    and len(calls) == 1
                    and task_interpreter_correct
                    and evidence["same_id_replay"]
                    and identical
                )
                else 1
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "provider_steps": client.names,
                        "router_decisions": client.route_decisions,
                        "temporary_vault_only": True,
                    }
                ),
                flush=True,
            )
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
