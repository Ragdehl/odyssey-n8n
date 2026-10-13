"""One genuine GPT-5.6 replan for F22 second Task using Core-owned Note context.

Router/Tasks/Temporal prior actual outputs are reused only as semantic evidence.
No production notes and no fabricated GPT reply; one bounded new model call.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from openai import OpenAI

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    OpenAITaskInterpreter,
    TaskCorePlanner,
    TaskLifecycleGuard,
    compose_scoped_task_domain_interpretation,
)
from odyssey_apps.tasks.scoped_evidence import TaskScopedEvidence
from odyssey_core.application import execute_request
from odyssey_core.domain_interpretation import InheritedTemporalReference
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.schema_types import planning_schema_for_capability
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

OUT = Path(__file__).parent
BASE_USD = 0.65539565
CAP_USD = 0.02


class PaidCoreOnly:
    def __init__(self, client):
        self.client = client
        self.rows = []

    def create(self, **kwargs):
        if len(self.rows) >= 1 or kwargs.get("model") != "gpt-5.6-luna":
            raise RuntimeError("Only one new GPT-5.6 Core call approved")
        response = self.client.create(**kwargs)
        usage = response.usage
        row = {
            "model": kwargs["model"],
            "status": response.status,
            "output_text": response.output_text,
            "input_tokens": int(usage.input_tokens),
            "output_tokens": int(usage.output_tokens),
        }
        self.rows.append(row)
        cost = 1.1 * (row["input_tokens"] * 0.20 + row["output_tokens"] * 1.20) / 1_000_000
        if cost > CAP_USD or BASE_USD + cost >= 1:
            raise RuntimeError("Approved cumulative provider budget exceeded")
        return response


def main():
    if os.getenv("ODYSSEY_APPROVE_HYBRID_EXPERIMENT") != "1" or not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Experiment not authorized")
    target = OUT / "F22-second.json"
    if target.exists():
        raise RuntimeError("Immutable genuine result already exists")
    src = next(row["source"] for row in CASES if row["id"] == "F22")
    fragment = " y escribir a Luis"
    previous = json.loads((OUT.parent / "hybrid_tasks_v1/F22-full-v2.json").read_text())
    task_row = previous["provider_outputs"][3]
    inherited = InheritedTemporalReference(
        "Hoy", "2026-10-04", 0, 3, hashlib.sha256(src.encode()).hexdigest(), 0
    )
    evidence = TaskScopedEvidence(
        fragment, hashlib.sha256(src.encode()).hexdigest(), 1, (inherited,)
    )
    task = OpenAITaskInterpreter(FrozenProvider([task_row])).interpret_scoped(
        fragment, scoped_evidence=evidence
    )
    domain = compose_scoped_task_domain_interpretation(task, None, evidence, now=NOW)
    paid = PaidCoreOnly(OpenAI(max_retries=0, timeout=85).responses)
    with tempfile.TemporaryDirectory(prefix="odyssey-f22-source-referent-") as tmp:
        repo, ctx, semantic, emb = fresh_corpus_vault(Path(tmp))
        task_schema = compose_application_schema(SCHEMA, (TASK_SCHEMA_EXTENSION,))
        plan_schema = planning_schema_for_capability(task_schema, "tasks")
        ctx.rebuild(repo, task_schema, emb)
        semantic.rebuild(repo, plan_schema, emb)
        planner = TaskCorePlanner(
            OpenAILunaExperimentalPlanner(
                SimpleNamespace(responses=paid), plan_schema, CLOCK, domain_interpretation=domain
            ),
            task.task,
        )
        before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
        result = execute_request(
            fragment,
            planner=planner,
            repository=repo,
            schema=plan_schema,
            context_index=ctx,
            semantic_index=semantic,
            embedder=emb,
            contextual_reasoner=object(),
            actor="f22-genuine-linked-task",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "f22-generic-canonical-source",
            preflight_id_allocator=lambda: "f22-general-verified-link",
            write_preflight_guard=TaskLifecycleGuard(task.task.operation),
        )
        changed = {
            p: repo.read_text(p)
            for p in repo.list_markdown_paths()
            if before.get(p) != repo.read_text(p)
        }
    cost = 1.1 * sum(
        (r["input_tokens"] * 0.20 + r["output_tokens"] * 1.20) / 1_000_000 for r in paid.rows
    )
    receipt = {
        "source_sha256": hashlib.sha256(src.encode()).hexdigest(),
        "fragment": fragment,
        "frozen_task_interpreter": task_row,
        "trusted_inherited_day": inherited.to_payload(),
        "real_new_model_outputs": paid.rows,
        "status": result.status.value,
        "planning_error": result.planning_error,
        "changed_notes": changed,
        "estimated_new_usd": round(cost, 8),
        "estimated_cumulative_usd": round(BASE_USD + cost, 8),
    }
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, default=str) + "\n")
    print("STATUS", receipt["status"], receipt["planning_error"], flush=True)
    print("LLM", [(row["model"], row["output_text"][:1300]) for row in paid.rows], flush=True)
    print(
        "NOTES",
        [
            (p, [line for line in b.splitlines() if line.startswith("- ")])
            for p, b in changed.items()
        ],
        flush=True,
    )
    print("USD", receipt["estimated_cumulative_usd"], flush=True)


if __name__ == "__main__":
    main()
