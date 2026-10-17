"""Genuine GPT Router generality regression, no writes and no user vault.

Use the established transient systemd user unit EnvironmentFile path and
ODYSSEY_APPROVE_LIGHT_POC=1. Do not run in deterministic CI, not a product E2E.
"""

from __future__ import annotations

import json
import os
from time import perf_counter

from openai import OpenAI

from odyssey_runtime.whole_source_light import ROUTER_MODEL
from odyssey_runtime.whole_source_model_contract import ROUTE_SCHEMA, ROUTER_INSTRUCTIONS

CASES = (
    (
        "dependent-es-alias",
        "Hoy revisé Preparar informe Atlas. Ahora empieza una sesión de trabajo en esa tarea.",
        ("core", "tasks"),
    ),
    (
        "dependent-es-task",
        "Esta mañana avancé con la tarea Diseñar pantalla Azul. Inicia una sesión de trabajo para esa tarea.",
        ("core", "tasks"),
    ),
    (
        "dependent-fr",
        "J’ai relu le dossier de la tâche Atlas. Démarre une session de travail sur cette tâche.",
        ("core", "tasks"),
    ),
    (
        "dependent-en",
        "I reviewed the Atlas reporting task. Start a work session on that task.",
        ("core", "tasks"),
    ),
    ("single-tasks", "Empieza a trabajar en Preparar informe Atlas.", ("tasks",)),
    (
        "session-activity-only",
        "En la sesión de trabajo de Atlas he revisado los plazos.",
        ("tasks",),
    ),
    ("person-then-todo", "Hoy he conocido a Lara y mañana tengo que llamarla.", ("core", "tasks")),
    ("future-fact-not-task", "Mañana asistiré a una reunión del colegio.", ("core",)),
    (
        "multiple-dependency-groups",
        "Hoy revisé la tarea Atlas, empieza una sesión en esa tarea y después corrige la tarea Beta.",
        ("core", "tasks"),
    ),
    ("implicit-self-person", "Hoy he conocido a Guillem.", ("core",)),
    ("implicit-self-elliptic", "Hoy conocí a Guillem y mañana debo llamarlo.", ("core", "tasks")),
    ("multiple-people-one-fact", "Hoy vi a Ana y Luis en el parque.", ("core",)),
    (
        "children-shared-actor",
        "Hoy mis hijos fueron al museo, jugaron y cenaron juntos.",
        ("core",),
    ),
    ("sprint-day-context", "Mañana es el final del sprint de trabajo.", ("core",)),
    ("new-project-fact", "Hoy he creado el proyecto XBOm.", ("core",)),
    ("group-pronoun", "Hoy hablé con Bea y con mis hijos.", ("core",)),
    ("explicit-create-task", "Crea una tarea de preparar la presentación Atlas.", ("tasks",)),
    (
        "explicit-create-subtask",
        "Crea una subtarea de revisar los gráficos dentro de la tarea Atlas.",
        ("tasks",),
    ),
    ("stop-session", "Termina ahora la sesión de trabajo de Atlas.", ("tasks",)),
    ("edit-session-time", "Corrige el inicio de la sesión de Atlas a las 15:10.", ("tasks",)),
    ("core-personal-preference", "Me gusta la subida.", ("core",)),
    (
        "two-tasks-no-core",
        "Inicia sesión en la tarea Atlas y después completa la tarea Beta.",
        ("tasks",),
    ),
)


def main() -> int:
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        print("P4_ROUTER_DIVERSITY_NOT_RUN: authorized provider environment missing")
        return 2
    client = OpenAI(max_retries=0, timeout=80)
    results = []
    for name, original, required in CASES:
        started = perf_counter()
        try:
            response = client.responses.create(
                model=ROUTER_MODEL,
                reasoning={"effort": "low"},
                store=False,
                max_output_tokens=1700,
                input=[
                    {"role": "system", "content": ROUTER_INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "original_source": original,
                                "clock": {
                                    "date": "2026-10-17",
                                    "time": "14:00:00",
                                    "timezone": "Europe/Paris",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_light_capability_route_v1",
                        "strict": True,
                        "schema": ROUTE_SCHEMA,
                    }
                },
            )
            value = json.loads(response.output_text)
            capabilities = set(value["capabilities"])
            exact = capabilities & {"core", "tasks"} == set(required)
            scopes = value.get("app_scopes", [])
            depended = any(part.get("depends_on_another_scope") is True for part in scopes)
            expected_dependent = name.startswith("dependent-")
            separate_multi = name not in {"multiple-dependency-groups", "two-tasks-no-core"} or (
                len(scopes) >= (3 if name == "multiple-dependency-groups" else 2)
                and sum(part.get("capability") == "tasks" for part in scopes) >= 2
            )
            complete = (
                exact
                and separate_multi
                and (
                    not expected_dependent
                    or (
                        value["interpretation"] == "joint"
                        and depended
                        and any(x.get("capability") == "core" for x in scopes)
                        and any(x.get("capability") == "tasks" for x in scopes)
                    )
                )
            )
            result = {
                "case": name,
                "expected": required,
                "capabilities": value["capabilities"],
                "interpretation": value.get("interpretation"),
                "scopes": scopes,
                "passed": complete,
                "seconds": round(perf_counter() - started, 2),
            }
        except Exception as exc:
            result = {
                "case": name,
                "error_type": type(exc).__name__,
                "passed": False,
                "seconds": round(perf_counter() - started, 2),
            }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    passed = sum(item["passed"] for item in results)
    print(
        json.dumps(
            {
                "total": len(CASES),
                "passed": passed,
                "failed": len(CASES) - passed,
                "provider": True,
                "no_write": True,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
