"""Real NEW GPT router + scope auditor + existing Task interpreter; read-only.

Production ROUTE and TASK_ONLY_SCOPE contracts must lead to the SAME narrow
Tasks interpretation as chat/UI, without trusting the Router as write authority.
The two model checks are real; NO canonical Task/Session is mutated in this
probe. Runtime-domain-UI mutations are independently tested with fake GPT.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI

from benchmarks.application_router.light_router_poc_20261016.p4_tasks_nl_intent_live_probe import (
    CASES,
)
from odyssey_apps.tasks.interpretation import OpenAITaskInterpreter
from odyssey_runtime.whole_source_light import PLANNER_MODEL, ROUTER_MODEL
from odyssey_runtime.whole_source_model_contract import (
    ROUTE_SCHEMA,
    ROUTER_INSTRUCTIONS,
    TASK_ONLY_SCOPE_PROMPT,
    TASK_ONLY_SCOPE_SCHEMA,
)


def ask(client, model, prompt, source, schema, schema_name):
    response = client.responses.create(
        model=model,
        reasoning={"effort": "low"},
        store=False,
        max_output_tokens=800,
        input=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps({"original_source": source}, ensure_ascii=False),
            },
        ],
        text={
            "format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}
        },
    )
    return json.loads(response.output_text)


def main():
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Synthetic live-model opt-in required")
    client = OpenAI(timeout=80, max_retries=0)
    interpreter = OpenAITaskInterpreter.from_environment()
    results = []
    for case_id, source, expected in CASES:
        row = {"case": case_id, "expected": expected}
        try:
            route = ask(
                client,
                ROUTER_MODEL,
                ROUTER_INSTRUCTIONS,
                source,
                ROUTE_SCHEMA,
                "odyssey_light_capability_route_v1",
            )
            row["capabilities"] = route.get("capabilities")
            row["group_proposal"] = route.get("self_relation_span") is not None
            if (
                set(route["capabilities"]) - {"tasks", "temporal"}
                or "tasks" not in route["capabilities"]
            ):
                row["accepted"] = False
                row["boundary"] = "router_not_task_only"
            else:
                scope = ask(
                    client,
                    PLANNER_MODEL,
                    TASK_ONLY_SCOPE_PROMPT,
                    source,
                    TASK_ONLY_SCOPE_SCHEMA,
                    "odyssey_task_only_scope_v1",
                )
                row["scope"] = (
                    scope.get("only_task_semantics") is True
                    and scope.get("exactly_one_operation") is True
                    and scope.get("source_quote") == source
                )
                if not row["scope"]:
                    row["accepted"] = False
                    row["boundary"] = "scope_rejected"
                else:
                    interpretation = interpreter.interpret(source)
                    row["actual"] = interpretation.operation.value
                    row["relationship_roles"] = [
                        role.role.value for role in interpretation.relationship_mentions
                    ]
                    row["accepted"] = row["actual"] == expected
                    if case_id == "subtask_create":
                        row["accepted"] = (
                            row["accepted"] and "PARENT_TASK" in row["relationship_roles"]
                        )
        except Exception as error:
            row["accepted"] = False
            row["boundary"] = type(error).__name__
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    file = Path("/tmp/odyssey-p4-taskonly-route-scope-live.json")
    file.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print("TASK_ONLY_ROUTER_SCOPE", sum(row["accepted"] for row in results), "/", len(results))
    return 0 if all(row["accepted"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
