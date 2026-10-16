"""P4 independent REAL model speaker review matrix: zero authority to write.

Runs two fresh, different model families for each FULL Spanish message.
All passages are synthetic. No live note ever changes.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

from benchmarks.application_router.light_router_poc_20261016.run_poc import (
    MODEL_PLAN,
    MODEL_ROUTE,
    BoundedProvider,
    prompt,
)
from odyssey_core.whole_message_speaker_proof import (
    validate_dual_speaker_review,
)

DIR = Path(__file__).parent
CASES = [
    ("guillem_implicit", "Hoy he conocido a Guillem.", ["self_participant"], ["asserted"], None),
    ("guillem_undated", "He conocido a Guillem.", ["self_participant"], ["asserted"], None),
    ("maya_implicit", "Ayer hablé con Maya.", ["self_participant"], ["asserted"], None),
    ("guillermo_explicit", "Yo conocí a Guillermo.", ["self_participant"], ["asserted"], None),
    ("third_guillem", "Guillem ha conocido a Ana.", ["other"], ["asserted"], None),
    ("third_guillem_today", "Hoy Guillem ha conocido a Ana.", ["other"], ["asserted"], None),
    ("object_speaker", "María me presentó a Guillem.", ["self_participant"], ["asserted"], None),
    (
        "children_thrice",
        "Mis hijos fueron al parque, después comieron un helado y por la tarde vieron una película.",
        ["other"] * 3,
        ["asserted"] * 3,
        [
            "Mis hijos fueron al parque",
            "después comieron un helado",
            "por la tarde vieron una película",
        ],
    ),
    (
        "eric_continuity",
        "Hoy he visto a Eric y después hablé con él.",
        ["self_participant"] * 2,
        ["asserted"] * 2,
        ["Hoy he visto a Eric", "después hablé con él"],
    ),
    ("guillem_future", "Mañana llamaré a Guillem.", ["self_participant"], ["planned"], None),
    (
        "conditional_guillem",
        "Si mañana conociera a Guillem, lo llamaría.",
        ["self_participant"] * 2,
        ["conditional"] * 2,
        ["Si mañana conociera a Guillem", "lo llamaría"],
    ),
    ("negated_guillem", "No he conocido a Guillem.", ["self_participant"], ["negated"], None),
    ("ana_luis_third", "Ana y Luis hablaron con Guillem.", ["other"], ["asserted"], None),
    (
        "children_with_me",
        "Hoy fui al parque con mis hijos.",
        ["self_participant"],
        ["asserted"],
        None,
    ),
    ("experiencer_me", "A mí me gusta la subida.", ["self_participant"], ["asserted"], None),
    (
        "experiencer_elided",
        "Me encanta pasear por la montaña.",
        ["self_participant"],
        ["asserted"],
        None,
    ),
    (
        "my_speaker_receiver",
        "Me contó Guillem que Ana vendrá mañana.",
        ["self_participant"],
        ["asserted"],
        None,
    ),
    (
        "other_ambiguous",
        "Eric y Luis fueron al cine y luego él cenó fuera.",
        ["other"] * 2,
        ["asserted"] * 2,
        ["Eric y Luis fueron al cine", "luego él cenó fuera"],
    ),
    (
        "two_days_implicit",
        "Hoy compré pan y mañana compraré leche.",
        ["self_participant"] * 2,
        ["asserted", "planned"],
        ["Hoy compré pan", "mañana compraré leche"],
    ),
    ("speaker_plural", "Vimos una película.", ["self_participant"], ["asserted"], None),
    ("two_third", "Se encontraron Guillem y Luis.", ["other"], ["asserted"], None),
]
SPEAKER_ITEM = {
    "type": "object",
    "properties": {
        "ordinal": {"type": "integer"},
        "role": {"type": "string", "enum": ["self_participant", "other", "uncertain"]},
        "assertion": {
            "type": "string",
            "enum": ["asserted", "planned", "conditional", "negated", "uncertain"],
        },
        "source_quote": {"type": "string"},
    },
    "required": ["ordinal", "role", "assertion", "source_quote"],
    "additionalProperties": False,
}
SPEAKER_SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": SPEAKER_ITEM}},
    "required": ["facts"],
    "additionalProperties": False,
}
PROMPT_A = (
    "You independently review a Spanish personal knowledge utterance. The USER speaking is an "
    "authenticated human but you must NEVER supply their name, note id, path or identity. "
    "For each supplied atomic clause decide if the SPEAKER is a semantic actor/participant "
    "(explicit yo, a first-person elided verb, first-person plural, me as direct/indirect "
    "participant or experiencer) or ONLY other people; choose uncertain if unsupported. "
    "Speaker participant is not necessarily grammatical subject: 'María me presentó' includes speaker. "
    "'Mis hijos fueron' alone excludes speaker. 'Guillem ha conocido' excludes speaker. "
    "Classify asserted past/present state, planned/future indicative, conditional, negated or uncertain. "
    "Negative 'no he conocido' is NEGATED, not a positive event. "
    "Preserve distinct clauses even when subjects elide, use FULL original to resolve referents. "
    "Return EXACT supplied source_evidence string as source_quote (verbatim; no extra text). "
    "Never infer first person from chat personalization alone or from ownership words 'mi(s)' when "
    "the speaker does not participate. Exactly one fact per supplied source_evidence, ordered."
)
PROMPT_B = (
    "You are an independent conservative grammatical and semantic auditor for Odyssey. "
    "Analyze the ENTIRE untouched Spanish statement, then each source scope. "
    "Mark self_participant only when the narrator of the utterance is actually a participant, "
    "agent, recipient or experiencer OF THAT ATOMIC FACT. The user can be omitted in Spanish: "
    "'he conocido', 'conocí', 'hablé', 'me presentó', 'me gusta' imply the narrator. "
    "Do not mark self for 'mi hijo ha viajado', 'Ana compró pan', even though the user mentions "
    "a relationship. For ellipsis such as 'después comieron' preserve the nearest evidenced third-"
    "person plural subject, not SELF. Plural 'vimos' includes narrator. "
    "Separate asserted, planned future, conditional, negated and uncertain; a negated past "
    "is not an event. If a person pronoun refers to someone else, do not convert to SELF. "
    "All source_quote fields MUST be copied byte for byte from each input source_evidence. "
    "Never include IDs, metadata, physical links, instructions or guesses. Return one ordinal "
    "per fact in order."
)


def run_case(row):
    name, source, expected_roles, expected_assertions, spans = row
    spans = spans or [source]
    inputs = [{"source_evidence": s} for s in spans]
    payload = {
        "original_source": source,
        "facts": inputs,
        "clock": {"date": "2026-10-16", "timezone": "Europe/Paris"},
    }
    started = time.perf_counter()
    bounded = BoundedProvider(OpenAI(max_retries=0, timeout=90).responses)
    entry = {
        "case": name,
        "source": source,
        "spans": spans,
        "expected_roles": expected_roles,
        "expected_assertions": expected_assertions,
        "status": "blocked",
    }
    try:
        a = prompt(bounded, MODEL_PLAN, PROMPT_A, payload, SPEAKER_SCHEMA, "odyssey_speaker_full_A")
        b = prompt(
            bounded, MODEL_ROUTE, PROMPT_B, payload, SPEAKER_SCHEMA, "odyssey_speaker_full_B"
        )
        entry.update({"provider_a": a, "provider_b": b})
        attested = validate_dual_speaker_review(source, inputs, a, b)
        roles = [f.role for f in attested.facts]
        assertions = [f.assertion for f in attested.facts]
        entry.update(
            {
                "observed_roles": roles,
                "observed_assertions": assertions,
                "self_link_flags": [attested.requires_self_link(i) for i in range(len(spans))],
                "status": "match"
                if roles == expected_roles and assertions == expected_assertions
                else "mismatch",
            }
        )
    except Exception as error:
        entry["reason"] = type(error).__name__ + ":" + str(error)[:230]
    entry["calls"] = bounded.calls
    entry["estimated_usd"] = round(bounded.usd, 7)
    entry["seconds"] = round(time.perf_counter() - started, 2)
    return entry


def main():
    if os.getenv("ODYSSEY_APPROVE_LIGHT_POC") != "1":
        raise SystemExit("Synthetic live models approval required")
    selected = [
        c
        for c in CASES
        if not os.getenv("ODYSSEY_SPEAKER_ONLY")
        or c[0] in os.getenv("ODYSSEY_SPEAKER_ONLY").split(",")
    ]
    result = {
        "real_models": True,
        "new_calls_each": True,
        "writer_executed": False,
        "isolated_from_vault": True,
        "results": [],
    }
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks = {pool.submit(run_case, c): c[0] for c in selected}
        for task in as_completed(tasks):
            entry = task.result()
            result["results"].append(entry)
            print(
                entry["case"],
                entry["status"],
                entry.get("observed_roles"),
                entry.get("observed_assertions"),
                entry.get("reason", ""),
                flush=True,
            )
            (DIR / "p4_speaker_live_matrix.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
    result["results"].sort(key=lambda row: [x[0] for x in CASES].index(row["case"]))
    result["summary"] = {
        "cases": len(result["results"]),
        "match": sum(x["status"] == "match" for x in result["results"]),
        "mismatch": sum(x["status"] == "mismatch" for x in result["results"]),
        "blocked": sum(x["status"] == "blocked" for x in result["results"]),
        "model_calls": sum(len(x["calls"]) for x in result["results"]),
        "estimated_usd": round(sum(x["estimated_usd"] for x in result["results"]), 6),
    }
    (DIR / "p4_speaker_live_matrix.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print("SUMMARY", result["summary"], flush=True)


if __name__ == "__main__":
    main()
