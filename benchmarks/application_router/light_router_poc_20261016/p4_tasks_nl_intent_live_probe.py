"""P4 read-only genuine provider checks of Tasks / Work Session CHAT interpretation.

This tests the legacy Tasks intent recognizer alone; it does NOT prove the
experimental light router, Core Writer, browser, n8n, or a real Work Session
mutation. Intent is checked using actual current TaskOperation schema, never
via individual phrase-specific runtime fixes. No real vault or user data read.

Run explicitly: ODYSSEY_APPROVE_LIGHT_POC=1 python -m \
 benchmarks.application_router.light_router_poc_20261016.p4_tasks_nl_intent_live_probe
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from odyssey_apps.tasks.interpretation import OpenAITaskInterpreter, TaskInterpretationError

CASES = (
    ("start_task", "Empieza a trabajar en la tarea Preparar informe Atlas.", "START_WORK_SESSION"),
    ("stop_task", "Deja de trabajar en la tarea Preparar informe Atlas.", "STOP_WORK_SESSION"),
    (
        "edit_start",
        "Corrige el inicio de la sesión de Preparar informe Atlas a las 17:30.",
        "EDIT_WORK_SESSION",
    ),
    (
        "activity",
        "En la sesión activa he corregido los enlaces del calendario.",
        "ADD_WORK_SESSION_ACTIVITY",
    ),
    (
        "subtask_create",
        "Crea una subtarea de Preparar informe Atlas llamada Revisar contratos.",
        "CREATE",
    ),
    ("task_complete", "Marca Preparar informe Atlas como completada.", "COMPLETE"),
    ("task_reopen", "Reabre la tarea Preparar informe Atlas.", "REOPEN"),
    ("task_query", "¿Qué tareas tengo pendientes?", "QUERY"),
    (
        "subtask_work",
        "He empezado a trabajar en la subtarea Revisar contratos.",
        "START_WORK_SESSION",
    ),
    (
        "activity_dated",
        "Anota que revisé tres facturas en la sesión de Preparar informe Atlas del lunes.",
        "ADD_WORK_SESSION_ACTIVITY",
    ),
)


def main() -> int:
    if os.getenv("ODYSSEY_APPROVE_LIGHT_POC") != "1":
        raise SystemExit("Explicit live evaluation acknowledgement required")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("No model credentials")
    interpreter = OpenAITaskInterpreter.from_environment()
    output = {
        "schema": "odyssey-task-intent-real-model-p4-v1",
        "mode": "real-model-read-only",
        "generated_at": datetime.now(UTC).isoformat(),
        "model": interpreter.model,
        "reasoning": interpreter.reasoning_effort,
        "n8n": False,
        "browser": False,
        "writer_executed": False,
        "source_vault_read": False,
        "cases": [],
    }
    for case_id, source, expected in CASES:
        try:
            interpretation = interpreter.interpret(source)
            actual = interpretation.operation.value
            evidence = {
                "case": case_id,
                "expected": expected,
                "actual": actual,
                "accepted": actual == expected,
                "temporal_mention_count": len(interpretation.temporal_mentions),
                "relationship_roles": [x.role.value for x in interpretation.relationship_mentions],
                "source_task_reference_present": bool(interpretation.task_reference),
                "activity_text_present": bool(interpretation.activity_text),
            }
            if case_id == "subtask_create":
                evidence["accepted"] = (
                    evidence["accepted"] and "PARENT_TASK" in evidence["relationship_roles"]
                )
        except TaskInterpretationError as error:
            evidence = {
                "case": case_id,
                "expected": expected,
                "actual": None,
                "accepted": False,
                "error": type(error).__name__,
            }
        output["cases"].append(evidence)
        print(json.dumps(evidence, ensure_ascii=False), flush=True)
    output["matches"] = sum(x["accepted"] for x in output["cases"])
    output["total"] = len(output["cases"])
    result_path = Path(tempfile.gettempdir()) / "odyssey-p4-task-nl-live-results.json"
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(f"REAL_TASK_INTENT {output['matches']}/{output['total']} read_only", flush=True)
    return 0 if output["matches"] == output["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
