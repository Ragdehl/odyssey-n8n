"""Bounded real-provider prompt behavior campaign for the Odyssey chat classifier.

Invoke only inside an approved transient systemd user EnvironmentFile unit,
with ODYSSEY_CHAT_LIVE_APPROVED=1. Uses synthetic prompts, no real vault/n8n.
No provider outputs are executable. Fail closed on unexpected mode decisions.
"""

from __future__ import annotations

import hashlib
import json
import os
import time

from odyssey_runtime.conversation_gateway import (
    CLASSIFY_INSTRUCTIONS,
    ConversationState,
    OpenAIConversationGateway,
    decision_schema,
)

CASES: tuple[tuple[str, str, ConversationState, set[tuple[str, str]]], ...] = (
    (
        "save-person",
        "Hoy he visto a Bruno y le encanta la guitarra.",
        ConversationState(),
        {("ROUTER", "NONE")},
    ),
    ("create-task", "Recuérdame llamar a Marta mañana.", ConversationState(), {("ROUTER", "NONE")}),
    (
        "read-notes",
        "¿Dónde trabaja Ana según mis notas?",
        ConversationState(),
        {("ROUTER", "NONE")},
    ),
    (
        "work-session",
        "He empezado a trabajar en el presupuesto.",
        ConversationState(),
        {("ROUTER", "NONE")},
    ),
    ("help", "¿Qué puedes hacer, Odyssey?", ConversationState(), {("CHAT", "NONE")}),
    ("thanks", "Gracias, muy amable.", ConversationState(), {("CHAT", "NONE")}),
    (
        "followup",
        "Luego también hemos ido a tomar algo.",
        ConversationState(active_topic="He visto a Bruno."),
        {("CONTEXT", "RECENT")},
    ),
    (
        "clarification",
        "No, me refería a Bruno.",
        ConversationState(pending_clarification=True, last_status="needs_attention"),
        {("CONTEXT", "RECENT")},
    ),
    (
        "old-conversation",
        "¿Qué fue lo que hablamos sobre ese viaje en julio?",
        ConversationState(),
        {("CONTEXT", "HISTORY")},
    ),
    ("missing-object", "Apunta eso también.", ConversationState(), {("CONTEXT", "RECENT")}),
    (
        "mixed",
        "Hoy he comprado una bicicleta. ¿Y cómo puedo organizar mis tareas?",
        ConversationState(),
        {("ROUTER", "NONE")},
    ),
    (
        "plain-chat",
        "¿En qué se diferencia un asistente de un buscador?",
        ConversationState(),
        {("CHAT", "NONE")},
    ),
)


def main() -> int:
    """Run only the bounded explicitly authorized synthetic evaluation."""
    if os.environ.get("ODYSSEY_CHAT_LIVE_APPROVED") != "1":
        print("CHAT_PROMPT_GATE_REFUSED authorization missing")
        return 2
    if len(CASES) > 12 or not os.environ.get("OPENAI_API_KEY"):
        print("CHAT_PROMPT_GATE_REFUSED configuration missing")
        return 2

    gateway = OpenAIConversationGateway.from_environment()
    prompt_hash = hashlib.sha256(
        (CLASSIFY_INSTRUCTIONS + json.dumps(decision_schema(), sort_keys=True)).encode()
    ).hexdigest()[:16]
    print(
        "CHAT_PROMPT_GATE model",
        gateway.model,
        "effort",
        gateway.reasoning_effort,
        "prompt_hash",
        prompt_hash,
        "cases",
        len(CASES),
        flush=True,
    )
    passed = 0
    for identifier, phrase, state, expected in CASES:
        started = time.monotonic()
        try:
            decision = gateway.classify(phrase, state)
            actual = (decision.mode.value, decision.context_scope.value)
            match = actual in expected
        except Exception as error:
            actual = ("ERROR", type(error).__name__)
            match = False
        elapsed = int((time.monotonic() - started) * 1000)
        print(
            json.dumps(
                {
                    "id": identifier,
                    "expected": sorted(expected),
                    "actual": actual,
                    "pass": match,
                    "duration_ms": elapsed,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        passed += match
        # Upper bound one request per case; no retry storm.
    print(
        "CHAT_PROMPT_GATE",
        "PASS" if passed == len(CASES) else "FAIL",
        f"{passed}/{len(CASES)}",
        "prompt_hash",
        prompt_hash,
        flush=True,
    )
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
