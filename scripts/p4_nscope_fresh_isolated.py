"""Opt-in fresh-GPT N independent scopes check on disposable Odyssey Markdown.

No user notes, live n8n or browser. The real TaskInterpreter validates a
prewrite Task scope once; Core's ordinary Writer owns both other facts.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

from odyssey_apps.tasks.interpretation import OpenAITaskInterpreter, TaskOperation
from odyssey_core.notes import parse_note
from scripts.p4_mixed_independent_real_isolated import ObservedClient
from tests.runtime.test_p4_independent_mixed_scopes import CORE, TASK, _runtime

EXTRA = "Me gustan los juegos de mesa."
SOURCE = CORE + " " + TASK + " " + EXTRA


def main() -> int:
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Fresh synthetic GPT test is opt-in only")
    with tempfile.TemporaryDirectory(prefix="odyssey-independent-three-gpt-") as root:
        repo, actor, executor, runtime, task_calls = _runtime(Path(root))
        client = ObservedClient(OpenAI(max_retries=0, timeout=80))
        executor.client = client
        interpretations: list[str] = []

        def prepare(source, _instant):
            meaning = OpenAITaskInterpreter.from_environment().interpret(source, ())
            interpretations.append(meaning.operation.value)
            return meaning, None

        def run_task(source, request_id, identity, interpretation, temporal, _instant):
            if (
                interpretation.operation is not TaskOperation.START_WORK_SESSION
                or temporal is not None
            ):
                raise ValueError("Prewrite Task operation was not START_WORK_SESSION")
            return executor.task_delegate(source, request_id, identity)

        executor.independent_task_prepare = prepare
        executor.independent_task_delegate = run_task
        try:
            result = runtime.execute_product(
                SOURCE, "synthetic-p4-three-independent", "main", actor
            )
            notes_after = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
            replay = runtime.execute_product(
                SOURCE, "synthetic-p4-three-independent", "main", actor
            )
            self_note = parse_note(repo.read_text("self.md"))
            work_sessions = sum(
                parse_note(repo.read_text(path)).metadata["type"] == "work_session"
                for path in repo.list_markdown_paths()
            )
            routes = result.get("execution_flow", {}).get("routes", [])
            passed = (
                result["status"] == "completed"
                and [row["capability"] for row in routes] == ["core", "tasks", "core"]
                and CORE in self_note.content
                and EXTRA in self_note.content
                and len(interpretations) == 1
                and work_sessions == 1
                and len(task_calls) == 1
                and replay.get("delivery_replayed") is True
                and notes_after
                == {path: repo.read_text(path) for path in repo.list_markdown_paths()}
            )
            report = {
                "passed": passed,
                "status": result["status"],
                "reason": result.get("product_reason"),
                "route_capabilities": [row["capability"] for row in routes],
                "task_preparations": len(interpretations),
                "task_operations": interpretations,
                "work_sessions": work_sessions,
                "self_facts": {
                    "first": CORE in self_note.content,
                    "third": EXTRA in self_note.content,
                },
                "replay_immutable": replay.get("delivery_replayed") is True
                and notes_after
                == {path: repo.read_text(path) for path in repo.list_markdown_paths()},
                "provider_calls": client.names,
                "router_decisions": client.route_decisions,
                "only_disposable_vault": True,
            }
            print(json.dumps(report, ensure_ascii=False), flush=True)
            return 0 if passed else 1
        except Exception as error:
            print(
                json.dumps(
                    {
                        "passed": False,
                        "error_type": type(error).__name__,
                        "only_disposable_vault": True,
                    }
                )
            )
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
