#!/usr/bin/env python3
"""E5 active-P4-router live provider-only source classification; no vault writes."""

from __future__ import annotations

import json
import os

from openai import OpenAI

from odyssey_runtime.whole_source_model_contract import capability_route_contract

CASES = [
    ("create", "Concierto ficticio E5 X9 del 29 de octubre de 2026.", "events"),
    ("edit", "Cambia Concierto ficticio E5 X9 al 30 de octubre de 2026.", "events"),
    ("cancel", "Cancela Concierto ficticio E5 X9.", "events"),
    ("query", "¿Qué eventos del colegio hay en octubre de 2026?", "events"),
    ("historical", "Ayer vi a Irene por la calle.", "not-events"),
    ("task", "Mañana tengo que llamar a Julia.", "not-events"),
    (
        "mixed_independent",
        "Concierto ficticio E5 el 24 de noviembre de 2026. Tengo que presentar el informe Atlas el 25 de noviembre de 2026.",
        "mixed-independent",
    ),
    (
        "mixed_dependent",
        "Excursión escolar el 24 de noviembre de 2026 y tengo que preparar la mochila para esa excursión.",
        "mixed-dependent",
    ),
]


def main():
    if os.environ.get("ODYSSEY_E5_LIVE_APPROVED") != "1":
        raise SystemExit("E5 live provider probe disabled")
    schema, instructions = capability_route_contract(enable_events=True)
    client = OpenAI(max_retries=0, timeout=60)
    rows = []
    only = os.environ.get("ODYSSEY_E5_CASE", "")
    for name, source, want in CASES:
        if only and name != only:
            continue
        response = client.responses.create(
            model="gpt-6-luna",
            reasoning={"effort": "low"},
            store=False,
            max_output_tokens=1700,
            input=[
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "original_source": source,
                            "clock": {
                                "date": "2026-10-22",
                                "time": "09:00:00",
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
                    "name": "odyssey_light_capability_route_events_v1",
                    "strict": True,
                    "schema": schema,
                }
            },
        )
        data = json.loads(response.output_text)
        caps = data.get("capabilities", [])
        independent = (
            {"events", "tasks"} <= set(caps)
            and data.get("interpretation") == "separable"
            and data.get("reason") == "independent"
            and len(data.get("app_scopes", [])) >= 2
            and {scope.get("capability") for scope in data["app_scopes"]} == {"events", "tasks"}
            and all(scope.get("depends_on_another_scope") is False for scope in data["app_scopes"])
        )
        okay = (
            independent
            if want == "mixed-independent"
            else not independent
            if want == "mixed-dependent"
            else set(caps) in ({"events"}, {"events", "temporal"}) and len(caps) == len(set(caps))
            if want == "events"
            else "events" not in caps
        )
        row = {
            "case": name,
            "capabilities": caps,
            "scopes": len(data.get("app_scopes", [])),
            "interpretation": data.get("interpretation"),
            "reason": data.get("reason"),
            "pass": okay,
        }
        rows.append(row)
        print("E5_P4_REAL=" + json.dumps(row), flush=True)
    print(
        "E5_P4_REAL_SUMMARY="
        + json.dumps({"passed": sum(r["pass"] for r in rows), "total": len(rows)}),
        flush=True,
    )
    return 0 if all(row["pass"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
