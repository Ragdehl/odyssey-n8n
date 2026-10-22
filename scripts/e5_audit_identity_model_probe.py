"""Read-only real GPT gate: does a quoted Event reference retain identity?"""

import json
import os

from odyssey_apps.events.interpretation import EventOperation
from odyssey_apps.events.provider import OpenAIEventInterpreter

if os.environ.get("ODYSSEY_E5_LIVE_APPROVED") != "1":
    raise SystemExit("Explicit real-model gate flag required")
model = OpenAIEventInterpreter.from_environment()
cases = (
    (
        "cancel",
        "Cancela Excursión escolar E5 C1A7B830 del lunes 26 de octubre de 2026.",
        "Excursión escolar E5 C1A7B830",
        EventOperation.CANCEL,
    ),
    (
        "update",
        "Mueve Teatro escolar E5 B4C5D6E7 del martes 27 de octubre de 2026 al jueves 29 de octubre de 2026.",
        "Teatro escolar E5 B4C5D6E7",
        EventOperation.UPDATE,
    ),
)
receipts = []
for label, source, reference, expected in cases:
    candidate = model.interpret(source)
    value = candidate.interpretation
    result = {
        "case": label,
        "operation": value.operation.value,
        "reference": value.event_reference,
        "quote_preserved": value.event_reference == reference,
        "role_names": [m.role.value for m in value.temporal_mentions],
    }
    result["pass"] = result["quote_preserved"] and value.operation is expected
    receipts.append(result)
    print("E5_SOURCE_REFERENCE_GPT=" + json.dumps(result, ensure_ascii=False), flush=True)
all_pass = all(x["pass"] for x in receipts)
print(
    "E5_SOURCE_REFERENCE_SUMMARY=" + json.dumps({"pass": all_pass, "cases": len(receipts)}),
    flush=True,
)
raise SystemExit(0 if all_pass else 2)
