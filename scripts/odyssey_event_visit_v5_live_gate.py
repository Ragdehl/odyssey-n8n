#!/usr/bin/env python3
"""Bounded real-provider E5 V5 Events classifier evaluation; no app/vault writes."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

from odyssey_apps.events.provider import EVENTS_PROMPT, OpenAIEventInterpreter

# Frozen before the first paid call, using only invented, non-personal inputs.
CASES = (
    ("visit_es", "Mi prima vendrá a Lyon el 16 de noviembre de 2026", "CREATE"),
    ("arrival_es", "La vecina llegará a casa el 20 de noviembre de 2026", "CREATE"),
    ("visit_fr", "Ma cousine viendra à Lyon le 16 novembre 2026", "CREATE"),
    ("visit_en", "My cousin arrives in Lyon on November 16, 2026", "CREATE"),
    ("uncertain", "Quizá mi prima venga a Lyon el 16 de noviembre de 2026", "ABSTAIN"),
    ("conditional", "Si mi prima viene a Lyon el 16 de noviembre de 2026, saldremos", "ABSTAIN"),
    ("negated", "Mi prima no vendrá a Lyon el 16 de noviembre de 2026", "ABSTAIN"),
    ("past", "Mi prima vino a Lyon el 16 de noviembre de 2025", "ABSTAIN"),
    ("non_event", "Mi prima tiene 30 años el 16 de noviembre de 2026", "ABSTAIN"),
    ("task", "Tengo que llamar a mi prima el 16 de noviembre de 2026", "ABSTAIN"),
    ("ordinary_event", "El 22 de noviembre de 2026 hay foto de clase en el colegio", "CREATE"),
    ("event_query", "¿Qué eventos del colegio hay en noviembre?", "QUERY"),
)
PROMPT_SHA256 = "d43908fb880533dd81ac14dfd7717834dcb6d3f4f022f9c2787e104ae3317ad2"
MAX_CALLS = 12
MAX_ESTIMATED_USD = 0.02  # Project pricing snapshot; NOT a billing figure.


def _priced(usage: object) -> float:
    if usage is None or not isinstance(getattr(usage, "input_tokens", None), int):
        raise ValueError("Model did not return measurable usage; stop campaign")
    inbound = usage.input_tokens
    cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
    output = getattr(usage, "output_tokens", None)
    if not isinstance(output, int) or not (0 <= cached <= inbound):
        raise ValueError("Model usage incomplete")
    return ((inbound - cached) * 0.1 + cached * 0.01 + output * 0.5) / 1_000_000


def main() -> int:
    if os.environ.get("ODYSSEY_EVENT_VISIT_V5_LIVE_APPROVED") != "1" or not os.environ.get(
        "OPENAI_API_KEY"
    ):
        raise SystemExit("An explicit bounded live gate is required")
    if hashlib.sha256(EVENTS_PROMPT.encode()).hexdigest() != PROMPT_SHA256:
        raise SystemExit("Expected signed prompt revision absent")
    if len(CASES) != MAX_CALLS:
        raise SystemExit("Test campaign must remain bounded")
    destination = Path("/home/ragdehl/projects/.odyssey-agent-runs/event-visit-v5-live-20261027")
    destination.mkdir(mode=0o700, exist_ok=True)
    destination.chmod(0o700)
    report = destination / "result.json"
    if report.exists():
        raise SystemExit("This paid campaign has already run; refuse duplicate")
    interpreter = OpenAIEventInterpreter.from_environment()
    rows = []
    estimated = 0.0
    for name, source, expected in CASES:
        if len(rows) >= MAX_CALLS or estimated >= MAX_ESTIMATED_USD:
            break
        started = time.monotonic()
        row = {"case": name, "expected": expected, "model": interpreter.model}
        try:
            candidate = interpreter.interpret(source)
            estimated += _priced(interpreter.last_usage)
            actual = candidate.interpretation.operation.value
            mentions = candidate.interpretation.temporal_mentions
            row.update(
                actual=actual,
                accepted=actual == expected,
                title_quote=candidate.title_quote,
                temporal_roles=[m.role.value for m in mentions],
                temporal_quotes=[m.quote for m in mentions],
                source_bound=candidate.interpretation.source_text == source,
            )
        except Exception as exc:
            row.update(accepted=False, failure_type=type(exc).__name__)
            rows.append(row)
            print("LIVE_CASE=" + json.dumps(row, ensure_ascii=False), flush=True)
            break
        row["duration_s"] = round(time.monotonic() - started, 2)
        rows.append(row)
        print("LIVE_CASE=" + json.dumps(row, ensure_ascii=False), flush=True)
    output = {
        "source_sha": "3001c4e06b084ad007ddc6e0b2a2138486bac4fb",
        "prompt_sha256": PROMPT_SHA256,
        "prompt_schema_name": "e5_event_intent_v5",
        "model": "gpt-6-luna",
        "effort": "low",
        "provider": "real",
        "results": rows,
        "passed": sum(r.get("accepted") is True for r in rows),
        "attempted": len(rows),
        "total_frozen": MAX_CALLS,
        "estimated_usd": round(estimated, 7),
        "max_estimated_usd": MAX_ESTIMATED_USD,
        "product_e2e": False,
        "any_notes_written": False,
    }
    fd = os.open(report, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(
        "LIVE_EVAL_SUMMARY=" + json.dumps({k: v for k, v in output.items() if k != "results"}),
        flush=True,
    )
    return 0 if output["passed"] == MAX_CALLS else 2


if __name__ == "__main__":
    sys.exit(main())
