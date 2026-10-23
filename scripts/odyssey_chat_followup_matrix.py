"""Bounded, real GPT-6 Luna behavior checks for Odyssey's two-axis follow-up.

Only synthetic prompts. Run with the existing protected transient systemd unit,
ODYSSEY_CHAT_LIVE_APPROVED=1. Never sends requests to Router or writes notes.
"""

from __future__ import annotations

import argparse
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

# Each tuple: stable case, current source, actor-local prior turns,
# Expected intent and historical referent ambiguity, but the LLM may emit
# ONLY intent. Provenance and identity are evaluated downstream by Core.
CASES = (
    (
        "bruno-then-we",
        "Luego también hemos ido a tomar algo.",
        ("Hoy he visto a Bruno, al que le encanta la guitarra.", "La información se ha guardado."),
        ("ROUTER", "CANDIDATE_PRESENT"),
    ),
    (
        "solo-then-everyone",
        "Luego hemos ido todos a tomar algo.",
        ("Ayer fui solo al cine.", "Anotado."),
        ("ROUTER", "MISSING_OR_CONFLICTING"),
    ),
    (
        "help-after-note",
        "¿Qué puedes hacer, Odyssey?",
        ("Hoy he terminado el informe.", "Anotado."),
        ("CHAT", "NOT_REQUIRED"),
    ),
    (
        "save-ellipsis",
        "Apunta también que su concierto fue increíble.",
        ("He hablado con Marta sobre su recital.", "Registrado."),
        ("ROUTER", "CANDIDATE_PRESENT"),
    ),
    (
        "ambiguous-both",
        "Los dos estaban contentos.",
        ("Hablé con Ana, Juan y Luis.", "Entendido."),
        ("ROUTER", "MISSING_OR_CONFLICTING"),
    ),
    (
        "grounded-pair",
        "Los dos estaban contentos.",
        ("Hoy vinieron Ana y Luis.", "Anotado."),
        ("ROUTER", "CANDIDATE_PRESENT"),
    ),
    (
        "new-independent-task",
        "Mañana tengo que comprar pan.",
        ("Hablé con Ana y Luis.", "Anotado."),
        ("ROUTER", "NOT_REQUIRED"),
    ),
    (
        "not-a-save",
        "Gracias, hablamos mañana.",
        ("Hoy hice un pastel.", "Guardado."),
        ("CHAT", "NOT_REQUIRED"),
    ),
    (
        "correction",
        "No, me refería a Marta.",
        ("¿A cuál te refieres, Ana o Marta?", "Elige un nombre para continuar."),
        ("ROUTER", "CANDIDATE_PRESENT"),
    ),
    (
        "vague-reference",
        "Y eso también.",
        ("Ayer hicimos muchas cosas.", "Entendido."),
        ("CLARIFY", "MISSING_OR_CONFLICTING"),
    ),
    (
        "negated-operation",
        "No guardes lo anterior.",
        ("El domingo fui al parque.", "Anotado."),
        ("ROUTER", "CANDIDATE_PRESENT"),
    ),
    (
        "conversation-history",
        "¿Qué me dijiste sobre organizar mis ideas?",
        ("Te explicaba cómo agrupar proyectos.", "Espero que te sirva."),
        ("CHAT", "CANDIDATE_PRESENT"),
    ),
    (
        "explicit-entity",
        "Bruno toca la guitarra.",
        ("He hablado con Ana.", "Anotado."),
        ("ROUTER", "NOT_REQUIRED"),
    ),
    (
        "mixed-question-fact",
        "Fui al cine ayer, ¿cómo puedo ver mis tareas?",
        ("La semana pasada escribí un informe.", "Anotado."),
        ("ROUTER", "NOT_REQUIRED"),
    ),
    (
        "contradictory-person",
        "Él estaba contento.",
        ("Hablé con Juan y luego con Pedro.", "Anotado."),
        ("ROUTER", "MISSING_OR_CONFLICTING"),
    ),
)

# Repetitions capture instability on sensitive group references without
# launching an unbounded optimization loop.
REPEAT_CASES = ("bruno-then-we", "solo-then-everyone", "grounded-pair", "ambiguous-both")


HOLDOUT = (
    (
        "french-activity",
        "Je suis allé au cinéma avec lui.",
        ("Hier j'ai rencontré Marc.", "C'est noté."),
        "ROUTER",
    ),
    (
        "french-help",
        "Comment fonctionne la chronologie des notes?",
        ("J'ai terminé le rapport.", "C'est enregistré."),
        "CHAT",
    ),
    (
        "explicit-note-query",
        "¿Qué dice mi nota sobre Daniel?",
        ("Hablé ayer de mi jardín.", "Guardado."),
        "ROUTER",
    ),
    (
        "negated-saving-help",
        "No guardes esto, solo explícame cómo se usa el calendario.",
        ("He usado Odyssey para mis tareas.", "Bien."),
        "CHAT",
    ),
    (
        "correction-of-time",
        "Perdón, me equivoqué: era a las seis.",
        ("Habíamos quedado a las cinco.", "Anotado."),
        "ROUTER",
    ),
    (
        "ambiguous-clarify",
        "Sí, el otro.",
        ("¿Te refieres a Ana o a Marta?", "Necesito el nombre."),
        "CLARIFY",
    ),
    (
        "mixed-person-event",
        "Después llegó mi hija y nos fuimos al parque.",
        ("Ayer vi a mi hermana.", "Guardado."),
        "ROUTER",
    ),
    (
        "historical-chat",
        "Volvamos a lo que hablamos el mes pasado.",
        ("Te estaba explicando la diferencia entre planes.", "Entendido."),
        "CHAT",
    ),
    (
        "explain-error",
        "No ha funcionado. ¿Qué ha pasado?",
        ("No pude completar la operación.", "Hay información por aclarar."),
        "CHAT",
    ),
    (
        "french-fact",
        "J'ai fait une randonnée avec Luc aujourd'hui.",
        ("Hier j'ai cuisiné.", "Noté."),
        "ROUTER",
    ),
)


def main() -> int:
    """Require explicit provider gate and report every bounded real decision."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", action="store_true", help="Fresh unseen multilingual cases")
    args = parser.parse_args()
    if os.environ.get("ODYSSEY_CHAT_LIVE_APPROVED") != "1":
        print("FOLLOWUP_MATRIX_REFUSED: authorization absent")
        return 2
    if not os.environ.get("OPENAI_API_KEY"):
        print("FOLLOWUP_MATRIX_REFUSED: provider environment absent")
        return 2
    gateway = OpenAIConversationGateway.from_environment()
    digest = hashlib.sha256(
        (
            CONTEXT_RESOLVE_INSTRUCTIONS + json.dumps(followup_assessment_schema(), sort_keys=True)
        ).encode()
    ).hexdigest()[:16]
    selected = (
        tuple((a, b, c, (d,)) for a, b, c, d in HOLDOUT)
        if args.holdout
        else (*CASES, *(c for c in CASES if c[0] in REPEAT_CASES))
    )
    total = len(selected)
    if total > 20:
        return 2
    print(
        "FOLLOWUP_MATRIX",
        gateway.model,
        gateway.reasoning_effort,
        "prompt_hash",
        digest,
        "calls",
        total,
        flush=True,
    )
    passed = 0
    for case_id, message, history, expected in selected:
        previous = tuple(
            {"role": ("user" if index == 0 else "assistant"), "text": entry}
            for index, entry in enumerate(history)
        )
        started = time.monotonic()
        try:
            result = gateway.classify_after_context(message, ConversationState(), previous)
            actual = result.intent.value
            assert result.referent_evidence.value == "UNVERIFIED"
            assert result.write_authorized is False
        except Exception as error:
            actual = "ERROR:" + type(error).__name__
        expected_intent = expected[0]
        passed += actual == expected_intent
        print(
            json.dumps(
                {
                    "case": case_id,
                    "expected_intent": expected_intent,
                    "actual_intent": actual,
                    "referent_proof": "UNVERIFIED",
                    "pass": actual == expected_intent,
                    "ms": round((time.monotonic() - started) * 1000),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    print(
        "FOLLOWUP_MATRIX_RESULT",
        "PASS" if passed == total else "FAIL",
        f"{passed}/{total}",
        "prompt_hash",
        digest,
        flush=True,
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
