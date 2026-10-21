#!/usr/bin/env python3
"""Real GPT E5 intent smoke, WITHOUT pretending Events has an operational E2E.

Uses existing authorized systemd EnvironmentFile, no logs of secrets and only
synthetic text. Produces a truthful outcome per independent new provider call.
Events is not registered with the current Router/Writer/Calendar product yet.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from openai import OpenAI

from odyssey_apps.events import validate_event_proposal

# Stable small oracle; source text is NEW at provider call time, not canned output.
CASES = (
    ("one_day", "El 22 de noviembre de 2026 hay foto de clase en el colegio.", "CREATE"),
    ("period", "El campamento será del 4 al 8 de julio de 2027.", "CREATE"),
    ("recurrence", "Todos los lunes hasta el 20 de junio de 2027 tenemos piscina.", "CREATE"),
    ("edit", "Cambia la reunión con Marta del martes al jueves.", "UPDATE"),
    ("cancel", "Cancela la excursión del viernes.", "CANCEL"),
    ("query", "¿Qué eventos del colegio hay en noviembre?", "QUERY"),
    ("task_not_event", "Mañana tengo que llamar a Julia para un presupuesto.", "ABSTAIN"),
    ("mixed_action", "El viernes hay excursión y tengo que preparar la mochila.", "ABSTAIN"),
    ("ambiguous_reference", "Hay dos excursiones el viernes. Cambia una al lunes.", "ABSTAIN"),
)

# This is a PRE-INTEGRATION diagnostic of a candidate E5 intent boundary.
# It is not claimed as the production Events model prompt or complete E2E.
INSTRUCTIONS = """You classify an ORIGINAL Spanish user message for an Events-only
capability. An Event is something that happens at a date or time, not a task
to do or a reminder to deliver. Choose exactly one operation: CREATE, UPDATE,
CANCEL, QUERY, ABSTAIN. ABSTAIN for non-Event requests, mixed Event+Task
messages that must be split by Router, or changes to an ambiguous reference.
If ABSTAIN, return temporal_mentions=[] and event_reference=null.
For UPDATE/CANCEL, event_reference must quote verbatim exactly ONE occurrence
of the event's name from the original message, without selecting a canonical
ID. For CREATE/QUERY use event_reference=null.
For temporal_mentions, return only exact, unique, non-overlapping source
substrings, never resolve dates, invent years or include a substring of a
number/word. Roles: DATE for a day/date, START/END for interval/time,
RECURRING_WEEKDAY for the recurring weekday, RECURRENCE_RANGE for the end
or bounded period of recurrence. If a span occurs twice without a unique
provenance, omit that ambiguous mention. Never turn an Event into a Task.
This is a pure read-only classifier. Do not invent facts or write actions.
Output exactly the required strict JSON."""

ROLE_NAMES = ["DATE", "START", "END", "RECURRING_WEEKDAY", "RECURRENCE_RANGE"]
SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["ABSTAIN", "CREATE", "UPDATE", "CANCEL", "QUERY"]},
        "temporal_mentions": {
            "type": "array",
            "maxItems": 16,
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "role": {"type": "string", "enum": ROLE_NAMES},
                },
                "required": ["quote", "role"],
                "additionalProperties": False,
            },
        },
        "event_reference": {"type": ["string", "null"]},
    },
    "required": ["operation", "temporal_mentions", "event_reference"],
    "additionalProperties": False,
}


def main() -> int:
    if os.environ.get("ODYSSEY_E5_LIVE_APPROVED") != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Authorized ephemeral live-model service environment required")
    client = OpenAI(timeout=65, max_retries=0)
    selected = os.environ.get("ODYSSEY_E5_TEST_CASES", "")
    cases = tuple(row for row in CASES if not selected or row[0] in selected.split(","))
    if not cases or len(cases) > 9:
        raise SystemExit("No bounded E5 cases selected")
    result = []
    for case, source, expected in cases:
        started = time.monotonic()
        row: dict[str, object] = {"case": case, "expected": expected, "provider": "real"}
        try:
            response = client.responses.create(
                model="gpt-6-luna",
                reasoning={"effort": "low"},
                max_output_tokens=1200,
                store=False,
                input=[
                    {"role": "system", "content": INSTRUCTIONS},
                    {"role": "user", "content": source},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "e5_events_intent_probe_v1",
                        "strict": True,
                        "schema": SCHEMA,
                    }
                },
            )
            candidate = json.loads(response.output_text)
            verified = validate_event_proposal(source, candidate)
            domain = verified.as_domain_interpretation()
            row.update(
                actual=domain.intent,
                grounded_quotes=[x.source_text for x in domain.evidence],
                valid_handoff=True,
                accepted=domain.intent == expected,
                stop_reason="none" if domain.intent == expected else "unexpected_intent",
            )
        except Exception as exc:
            row.update(
                valid_handoff=False,
                accepted=False,
                stop_reason=type(exc).__name__,
                detail=str(exc)[:180]
                if type(exc).__name__ in {"EventInterpretationError", "JSONDecodeError"}
                else None,
            )
        row["elapsed_s"] = round(time.monotonic() - started, 2)
        result.append(row)
        print("E5_REAL_MODEL_CASE=" + json.dumps(row, ensure_ascii=False), flush=True)
    path = Path("/tmp/odyssey-e5-real-interpretation-20261020.json")
    path.write_text(
        json.dumps(
            {
                "mode": "pre_integration_real_gpt_not_product_e2e",
                "model": "gpt-6-luna",
                "cases": result,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(
        "E5_REAL_MODEL_SUMMARY="
        + json.dumps(
            {
                "accepted": sum(r["accepted"] for r in result),
                "total": len(result),
                "product_e2e": False,
            }
        ),
        flush=True,
    )
    return 0 if all(r["accepted"] for r in result) else 1


if __name__ == "__main__":
    raise SystemExit(main())
