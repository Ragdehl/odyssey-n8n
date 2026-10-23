"""Bounded actual-Luna purpose classification gate for C3 help retrieval."""

from __future__ import annotations

import hashlib
import json
import os
import time

from odyssey_runtime.conversation_chat import (
    CHAT_PURPOSE_INSTRUCTIONS,
    chat_purpose_schema,
    classify_standalone_chat_purpose,
)
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway

CASES = (
    ("help-es", "¿Cómo se crean subtareas en Odyssey?", "HELP"),
    ("help-fr", "Comment voir les sessions de travail dans Odyssey ?", "HELP"),
    ("help-notes", "¿Dónde encuentro mis notas dentro de Odyssey?", "HELP"),
    ("help-availability", "¿Odyssey permite editar eventos desde el calendario?", "HELP"),
    ("generic-knowledge", "¿Cómo se organiza un calendario gregoriano?", "GENERAL"),
    ("social-fr", "Merci, c'est gentil !", "GENERAL"),
    ("general-algorithms", "¿Puedes explicar cómo funciona un algoritmo de búsqueda?", "GENERAL"),
    ("compare-product", "¿En qué se diferencian los asistentes de los buscadores?", "GENERAL"),
)


def main() -> int:
    if os.environ.get("ODYSSEY_CHAT_LIVE_APPROVED") != "1" or not os.environ.get("OPENAI_API_KEY"):
        print("CHAT_PURPOSE_GATE_REFUSED authorization/environment unavailable")
        return 2
    if len(CASES) > 8:
        print("CHAT_PURPOSE_GATE_REFUSED call budget")
        return 2
    gate = OpenAIConversationGateway.from_environment()
    prompt_hash = hashlib.sha256(
        (CHAT_PURPOSE_INSTRUCTIONS + json.dumps(chat_purpose_schema(), sort_keys=True)).encode()
    ).hexdigest()[:16]
    print(
        "CHAT_PURPOSE_GATE_START",
        gate.model,
        gate.reasoning_effort,
        "prompt_hash",
        prompt_hash,
        "calls",
        len(CASES),
        "max_output_tokens_per_call",
        120,
        flush=True,
    )
    count = 0
    for name, message, expected in CASES:
        started = time.monotonic()
        try:
            actual = classify_standalone_chat_purpose(gate, message).value
        except Exception as error:
            actual = "ERROR:" + type(error).__name__
        passed = actual == expected
        count += passed
        print(
            json.dumps(
                {
                    "case": name,
                    "expected": expected,
                    "actual": actual,
                    "pass": passed,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            ),
            flush=True,
        )
    print(
        "CHAT_PURPOSE_GATE",
        "PASS" if count == len(CASES) else "FAIL",
        f"{count}/{len(CASES)}",
        "prompt_hash",
        prompt_hash,
        flush=True,
    )
    return 0 if count == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
