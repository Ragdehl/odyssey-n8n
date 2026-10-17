"""Read-only genuine GPT check for ONE-Tasks-operation scope guard.

Use an explicitly approved ephemeral systemd user unit. No Notes, no vault.
"""

from __future__ import annotations

import json
import os

from openai import OpenAI

from odyssey_runtime.whole_source_light import PLANNER_MODEL
from odyssey_runtime.whole_source_model_contract import (
    TASK_ONLY_SCOPE_PROMPT,
    TASK_ONLY_SCOPE_SCHEMA,
)

CASES = (
    ("start-single", "Ahora inicia una sesión de trabajo en esa tarea.", True),
    ("activity-single", "Anota en la sesión de esa tarea que revisé los plazos.", True),
    ("start-then-edit", "Empieza una sesión en esa tarea y luego modifica la tarea Beta.", False),
    ("start-and-stop", "Inicia una sesión en esa tarea y termínala.", False),
    (
        "new-fact-plus-session",
        "Hoy conocí a Ana. Inicia una sesión de trabajo en esa tarea.",
        False,
    ),
    ("future-narrative", "Mañana revisaré un informe en el colegio.", False),
)


def main() -> int:
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        print("P4_TASK_SCOPE_LIVE_NOT_RUN")
        return 2
    client = OpenAI(max_retries=0, timeout=80)
    outcomes = []
    for key, source, expected in CASES:
        try:
            reply = client.responses.create(
                model=PLANNER_MODEL,
                reasoning={"effort": "low"},
                store=False,
                max_output_tokens=680,
                input=[
                    {"role": "system", "content": TASK_ONLY_SCOPE_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps({"original_source": source}, ensure_ascii=False),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "strict": True,
                        "name": "odyssey_task_only_scope_v1",
                        "schema": TASK_ONLY_SCOPE_SCHEMA,
                    }
                },
            )
            result = json.loads(reply.output_text)
            accepted = (
                result["only_task_semantics"] is True
                and result["exactly_one_operation"] is True
                and result["source_quote"] == source
            )
            passed = accepted is expected
            output = {
                "case": key,
                "accepted": accepted,
                "expected": expected,
                "correct": passed,
                "scope_flags": [result["only_task_semantics"], result["exactly_one_operation"]],
                "literal_source": result["source_quote"] == source,
            }
        except Exception as error:
            output = {"case": key, "error_type": type(error).__name__, "correct": False}
        outcomes.append(output)
        print(json.dumps(output, ensure_ascii=False), flush=True)
    success = sum(item["correct"] for item in outcomes)
    print(
        json.dumps(
            {
                "total": len(outcomes),
                "passed": success,
                "failed": len(outcomes) - success,
                "writes": 0,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return int(success != len(outcomes))


if __name__ == "__main__":
    raise SystemExit(main())
