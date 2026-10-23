"""Live, finite test of the *second* conversation classification prompt.

Requires protected transient systemd EnvironmentFile and
ODYSSEY_CHAT_LIVE_APPROVED=1. Strictly synthetic, read-only; no n8n/DEV.
"""

from __future__ import annotations

import hashlib
import json
import os
import time

from odyssey_runtime.conversation_gateway import (
    CONTEXT_RESOLVE_INSTRUCTIONS,
    ConversationState,
    OpenAIConversationGateway,
    followup_assessment_schema,
)

CASES = (
    (
        "bruno-continuation",
        "Luego también hemos ido a tomar algo.",
        (
            {"role": "user", "text": "Hoy he visto a Bruno, al que le encanta la guitarra."},
            {"role": "assistant", "text": "La información se ha guardado."},
        ),
        ("ROUTER",),
    ),
    (
        "missing-group-members",
        "Luego hemos ido todos a tomar algo.",
        (
            {"role": "user", "text": "Ayer fui solo al cine."},
            {"role": "assistant", "text": "Anotado."},
        ),
        ("ROUTER",),
    ),
    (
        "unrelated-help",
        "¿Qué puedes hacer, Odyssey?",
        (
            {"role": "user", "text": "Hoy he terminado la declaración de la renta."},
            {"role": "assistant", "text": "La información se ha guardado."},
        ),
        ("CHAT",),
    ),
)


def main() -> int:
    """Compatibility gate: three real intent-only calls, never identity proof."""
    if os.environ.get("ODYSSEY_CHAT_LIVE_APPROVED") != "1" or not os.environ.get("OPENAI_API_KEY"):
        print("CHAT_CONTEXT_GATE_REFUSED: no authorization/environment")
        return 2
    gateway = OpenAIConversationGateway.from_environment()
    digest = hashlib.sha256(
        (
            CONTEXT_RESOLVE_INSTRUCTIONS + json.dumps(followup_assessment_schema(), sort_keys=True)
        ).encode()
    ).hexdigest()[:16]
    print(
        "CHAT_CONTEXT_INTENT_GATE_START",
        gateway.model,
        gateway.reasoning_effort,
        digest,
        flush=True,
    )
    passed = 0
    for name, message, previous, expected in CASES:
        started = time.monotonic()
        try:
            choice = gateway.classify_after_context(message, ConversationState(), previous)
            actual = (choice.intent.value,)
        except Exception as error:
            actual = ("ERROR", type(error).__name__)
        okay = actual == expected
        passed += okay
        print(
            json.dumps(
                {
                    "case": name,
                    "actual": actual,
                    "expected": expected,
                    "pass": okay,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            ),
            flush=True,
        )
    print(
        "CHAT_CONTEXT_GATE",
        "PASS" if passed == len(CASES) else "FAIL",
        f"{passed}/{len(CASES)}",
        "prompt_hash",
        digest,
        flush=True,
    )
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
