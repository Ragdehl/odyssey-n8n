"""Fresh GPT safety probe: dependent Core/Tasks scopes must not split.

Read-only: only model calls, no vault, runtime, n8n, web browser or Notes.
Does not by itself prove source text cannot be misinterpreted by GPT later.
"""

from __future__ import annotations

import json
import os

from openai import OpenAI

from odyssey_core.independent_source_scopes import (
    IndependentSourceScopesError,
    verify_independent_source_scopes,
)
from odyssey_runtime.whole_source_light import PLANNER_MODEL, ROUTER_MODEL
from odyssey_runtime.whole_source_model_contract import (
    INDEPENDENT_SCOPE_PARTITION_PROMPT,
    INDEPENDENT_SCOPE_PARTITION_SCHEMA,
    INDEPENDENT_SCOPE_REVIEW_PROMPT,
    INDEPENDENT_SCOPE_REVIEW_SCHEMA,
    ROUTE_SCHEMA,
    ROUTER_INSTRUCTIONS,
)

CASES = (
    ("known_person_crossref", "Hoy he conocido a Diana. Mañana tengo que llamarla."),
    (
        "third_person_crossref",
        "Hoy vi a Lidia. Ahora empieza una sesión de trabajo para preparar su presentación.",
    ),
    ("session_crossref", "Hoy vi a Eva. Termina la sesión de trabajo que abrí cuando la conocí."),
)


def ask(client, model, prompt, data, schema, name):
    response = client.responses.create(
        model=model,
        reasoning={"effort": "low"},
        store=False,
        max_output_tokens=1700,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ],
        text={"format": {"type": "json_schema", "strict": True, "schema": schema, "name": name}},
    )
    return json.loads(response.output_text)


def main():
    if os.environ.get("ODYSSEY_APPROVE_LIGHT_POC") != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Real GPT dependency safety opt-in required")
    client = OpenAI(max_retries=0, timeout=80)
    verdicts = []
    for label, source in CASES:
        route = ask(
            client,
            ROUTER_MODEL,
            ROUTER_INSTRUCTIONS,
            {
                "original_source": source,
                "clock": {"date": "2026-10-16", "time": "19:00:00", "timezone": "Europe/Paris"},
            },
            ROUTE_SCHEMA,
            "odyssey_light_capability_route_v1",
        )
        scopes = route.get("app_scopes", [])
        claimed_separable = (
            route.get("interpretation") == "separable"
            and "core" in route.get("capabilities", [])
            and "tasks" in route.get("capabilities", [])
            and len(scopes) >= 2
            and all(not row.get("depends_on_another_scope") for row in scopes)
        )
        validated_split = False
        stage = "router_dependent_or_not_mixed"
        if claimed_separable:
            proposal = ask(
                client,
                PLANNER_MODEL,
                INDEPENDENT_SCOPE_PARTITION_PROMPT,
                {"original_source": source},
                INDEPENDENT_SCOPE_PARTITION_SCHEMA,
                "odyssey_independent_source_scopes_v1",
            )
            review = ask(
                client,
                ROUTER_MODEL,
                INDEPENDENT_SCOPE_REVIEW_PROMPT,
                {"original_source": source, "proposed_scopes": proposal},
                INDEPENDENT_SCOPE_REVIEW_SCHEMA,
                "odyssey_independent_source_scopes_audit_v1",
            )
            stage = "independent_reviewer_rejected"
            try:
                verify_independent_source_scopes(
                    source, proposal, review, permitted_capabilities=frozenset({"core", "tasks"})
                )
            except IndependentSourceScopesError:
                pass
            else:
                validated_split = True
                stage = "FALSE_INDEPENDENCE_ACCEPTED"
        verdict = {
            "case": label,
            "incorrectly_split": validated_split,
            "gate": stage,
            "router_interpretation": route.get("interpretation"),
            "router_capabilities": route.get("capabilities"),
        }
        verdicts.append(verdict)
        print(json.dumps(verdict, ensure_ascii=False), flush=True)
    return 0 if not any(v["incorrectly_split"] for v in verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
