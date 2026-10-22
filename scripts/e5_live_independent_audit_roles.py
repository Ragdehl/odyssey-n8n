#!/usr/bin/env python3
"""One-shot E5 auditor findings real-model source/Temporal proof, NO writes."""

from __future__ import annotations

import json
import os

from odyssey_apps.events.provider import OpenAIEventInterpreter
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter

CASES = (
    ("cancel_qualified", "Cancela Excursión del viernes 30 de octubre de 2026.", "CANCEL"),
    (
        "reschedule_old_new",
        "Mueve Teatro del martes 27 de octubre de 2026 al jueves 29 de octubre de 2026.",
        "UPDATE",
    ),
)


def main() -> int:
    if os.environ.get("ODYSSEY_E5_LIVE_APPROVED") != "1":
        raise SystemExit("Real-model audit regression not authorized")
    clock = {"date": "2026-10-22", "time": "13:30:00", "timezone": "Europe/Paris"}
    interpreter = OpenAIEventInterpreter.from_environment()
    temporal = OpenAITemporalInterpreter.from_environment(clock)
    rows = []
    for name, source, expected in CASES:
        c = interpreter.interpret(source)
        t = temporal.interpret(source)
        roles = [
            {"role": m.role.value, "quote": m.quote} for m in c.interpretation.temporal_mentions
        ]
        resolved = [
            {
                "quote": m.temporal_text,
                "kind": m.resolution.kind.value,
                "date": m.resolution.exact_date,
                "datetime": m.resolution.exact_datetime,
            }
            for m in t.mentions
        ]
        valid = c.interpretation.operation.value == expected and bool(roles)
        if name == "cancel_qualified":
            valid = valid and len(roles) == 1 and roles[0]["role"] == "DATE"
        else:
            valid = valid and {r["role"] for r in roles} == {"ORIGINAL_DATE", "NEW_DATE"}
        rows.append(
            {
                "case": name,
                "operation": c.interpretation.operation.value,
                "roles": roles,
                "resolved": resolved,
                "pass": valid,
            }
        )
        print("E5_REAL_AUDIT_ROLE=" + json.dumps(rows[-1], ensure_ascii=False), flush=True)
    ok = all(row["pass"] for row in rows)
    print(
        "E5_REAL_AUDIT_SUMMARY="
        + json.dumps({"pass": ok, "cases": len(rows), "provider": "real", "mutation": False}),
        flush=True,
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
