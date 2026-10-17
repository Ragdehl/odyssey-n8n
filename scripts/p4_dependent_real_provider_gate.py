"""Opt-in fresh GPT smoke: P4 dependent Core -> Task with disposable Markdown.

When provider credentials are legitimately configured in the environment:
ODYSSEY_APPROVE_LIGHT_POC=1 python scripts/p4_dependent_real_provider_gate.py

No credentials are loaded by this script. Zero real-user state, no n8n, no
browser, no calls by default. Core's RequestPlan is frozen, but the Router,
source partition, Task interpreter and three review steps use live GPT calls.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from time import perf_counter

from openai import OpenAI

from odyssey_apps.tasks.interpretation import OpenAITaskInterpreter, TaskOperation
from odyssey_core.notes import parse_note
from tests.runtime.test_p4_dependent_router_integrated import AFTER, SOURCE, _setup


class ObservedClient:
    def __init__(self):
        self.responses = self
        self._client = OpenAI(timeout=80, max_retries=0)
        self.stages: list[str] = []

    def create(self, **kwargs):
        self.stages.append(kwargs["text"]["format"]["name"])
        return self._client.responses.create(**kwargs)


def one_attempt(number: int) -> bool:
    with tempfile.TemporaryDirectory(prefix="odyssey-p4-gpt-dependent-") as root:
        repo, actor, executor, runtime, calls, sessions = _setup(Path(root))
        client = ObservedClient()
        executor.client = client
        interpreted: list[dict[str, object]] = []

        def prepare(text, instant):
            task = OpenAITaskInterpreter.from_environment().interpret(text, ())
            interpreted.append(
                {
                    "operation": task.operation.value,
                    "source_exact": task.source_text == AFTER.strip(),
                    "reference_exact": task.task_reference == "esa tarea",
                }
            )
            return task, None

        executor.dependent_task_prepare = prepare
        started = perf_counter()
        report: dict[str, object] = {"attempt": number, "synthetic_vault_only": True}
        try:
            request_id = f"synthetic-p4-real-depend-{number}"
            first = runtime.execute_product(SOURCE, request_id, "main", actor)
            after = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
            replay = runtime.execute_product(SOURCE, request_id, "main", actor)
            facts = [
                parse_note(repo.read_text(p)).content
                for p in repo.list_markdown_paths()
                if parse_note(repo.read_text(p)).metadata["type"] == "calendar_day"
            ]
            completed = (
                first["status"] == "completed"
                and len(sessions.list_for_task("atlas-p4-dependent-task")) == 1
            )
            report.update(
                {
                    "status": first["status"],
                    "completed": completed,
                    "task_interpretation": interpreted,
                    "canonical_backlink": any(
                        "[[atlas|Preparar informe Atlas]]" in f for f in facts
                    ),
                    "replay": replay.get("delivery_replayed") is True,
                    "unchanged_after_replay": after
                    == {p: repo.read_text(p) for p in repo.list_markdown_paths()},
                    "domain_calls": calls,
                    "model_steps": client.stages,
                }
            )
            report["passed"] = bool(
                completed
                and report["canonical_backlink"]
                and report["replay"]
                and report["unchanged_after_replay"]
                and calls == ["prepare", "core", "task"]
                and len(interpreted) == 1
                and interpreted[0]["operation"] == TaskOperation.START_WORK_SESSION.value
                and interpreted[0]["reference_exact"]
            )
        except Exception as error:
            report.update(
                {
                    "status": "exception",
                    "error_type": type(error).__name__,
                    "passed": False,
                    "model_steps": client.stages,
                }
            )
        report["seconds"] = round(perf_counter() - started, 2)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return bool(report["passed"])


def main() -> int:
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        print("P4_REAL_PROVIDER_NOT_RUN: provider opt-in and credentials unavailable")
        return 2
    count = int(os.environ.get("ODYSSEY_P4_GPT_ATTEMPTS", "3"))
    if count < 1 or count > 10:
        raise SystemExit("Bounded provider test supports 1..10 disposable attempts")
    success = sum(one_attempt(n) for n in range(1, count + 1))
    print(
        json.dumps(
            {
                "total": count,
                "passed": success,
                "failed": count - success,
                "real_gpt": True,
                "full_browser_n8n": False,
            },
            flush=True,
        )
    )
    return 0 if success == count else 1


if __name__ == "__main__":
    raise SystemExit(main())
