#!/usr/bin/env python3
"""Finite real provider semantic review; synthetic evidence, no writes or DEV."""

import hashlib
import json
import os
import time
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from openai import OpenAI

from odyssey_core.candidate_continuation_plan import inspect_selected_candidate_plan
from odyssey_core.candidate_continuation_semantic import (
    CandidateContinuationSemanticError,
    validate_independent_continuation_verdict,
)
from odyssey_runtime.candidate_continuation_review import (
    CONTINUATION_SEMANTIC_REVIEW_PROMPT,
    prepare_continuation_semantic_review_call,
)
from odyssey_runtime.whole_source_light import WholeSourceLightExecutor
from tests.runtime.test_candidate_continuation_plan import _ready_inspector
from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan

MODEL = "gpt-5.6-luna"
REPORT = Path("/tmp/odyssey-e5-continuation-live-v3-20261030.jsonl")
CASES = (
    ("es", "Mañana iré al cine con él.", "él", "Iré al cine con {{ref:0}}.", "2026-10-05", True),
    (
        "teatro",
        "Mañana iré al teatro con él.",
        "él",
        "Iré al teatro con {{ref:0}}.",
        "2026-10-05",
        True,
    ),
    (
        "en",
        "Tomorrow I will go to the cinema with him.",
        "him",
        "I will go to the cinema with {{ref:0}}.",
        "2026-10-05",
        True,
    ),
    (
        "fr",
        "Demain j'irai au cinéma avec lui.",
        "lui",
        "J'irai au cinéma avec {{ref:0}}.",
        "2026-10-05",
        True,
    ),
    ("ayer", "Ayer fui al cine con él.", "él", "Fui al cine con {{ref:0}}.", "2026-10-03", True),
    (
        "negacion",
        "Mañana no iré al cine con él.",
        "él",
        "Iré al cine con {{ref:0}}.",
        "2026-10-05",
        False,
    ),
    (
        "condicion",
        "Si llueve mañana, iré al cine con él.",
        "él",
        "Iré al cine con {{ref:0}}.",
        "2026-10-05",
        False,
    ),
    (
        "fecha",
        "Pasado mañana iré al cine con él.",
        "él",
        "Iré al cine con {{ref:0}}.",
        "2026-10-05",
        False,
    ),
    (
        "verbo",
        "Mañana iré al teatro con él.",
        "él",
        "Iré al cine con {{ref:0}}.",
        "2026-10-05",
        False,
    ),
    (
        "omision",
        "Mañana iré al cine con él y después visitaré un museo.",
        "él",
        "Iré al cine con {{ref:0}}.",
        "2026-10-05",
        False,
    ),
    (
        "tercera-persona",
        "Mañana iré al cine con él y con Ana.",
        "él",
        "Iré al cine con {{ref:0}}.",
        "2026-10-05",
        False,
    ),
    (
        "pregunta",
        "¿Mañana iré al cine con él?",
        "él",
        "Iré al cine con {{ref:0}}.",
        "2026-10-05",
        False,
    ),
    (
        "duda",
        "Quizá mañana iré al cine con él.",
        "él",
        "Iré al cine con {{ref:0}}.",
        "2026-10-05",
        False,
    ),
    (
        "correccion",
        "Mañana iré al cine con él, no, al teatro.",
        "él",
        "Iré al cine con {{ref:0}}.",
        "2026-10-05",
        False,
    ),
    ("pasado", "Ayer fui al cine con él.", "él", "Iré al cine con {{ref:0}}.", "2026-10-05", False),
    (
        "negacion-fr",
        "Demain je n'irai pas au cinéma avec lui.",
        "lui",
        "J'irai au cinéma avec {{ref:0}}.",
        "2026-10-05",
        False,
    ),
)


def main():
    if (
        os.environ.get("ODYSSEY_E5_CONTINUATION_LIVE_APPROVED") != "1"
        or os.environ.get("ODYSSEY_E5_CONTINUATION_MAX_CALLS") != "16"
        or not os.environ.get("OPENAI_API_KEY")
    ):
        print("REFUSED: finite authorized protected provider environment required", flush=True)
        return 2
    h = hashlib.sha256(CONTINUATION_SEMANTIC_REVIEW_PROMPT.encode()).hexdigest()
    if REPORT.is_symlink():
        raise RuntimeError("untrusted report")
    rows = [json.loads(x) for x in REPORT.read_text().splitlines()] if REPORT.exists() else []
    if len(rows) > 16 or any(
        r["name"] != CASES[i][0] or r["prompt_sha256"] != h or r["model"] != MODEL
        for i, r in enumerate(rows)
    ):
        print("REFUSED: campaign mismatch", flush=True)
        return 2
    print(
        json.dumps(
            {
                "model": MODEL,
                "effort": "low",
                "limit": 16,
                "prior_calls": len(rows),
                "prompt_sha256": h,
            }
        ),
        flush=True,
    )
    client = OpenAI(timeout=75, max_retries=0)
    obj = object.__new__(WholeSourceLightExecutor)
    obj.client = client
    for name, pending, mention, proposed, date, expected in CASES[len(rows) :]:
        with TemporaryDirectory(prefix="odyssey-e5-live-") as td:
            context, _, _ = _ready_inspector(Path(td))
            prefix = "Hablé con Eric. Hablé con Luis. "
            src = prefix + pending
            at = pending.rfind(mention)
            context = replace(
                context,
                original_source=src,
                source_start=len(prefix),
                source_end=len(src),
                reference_start=len(prefix) + at,
                reference_end=len(prefix) + at + len(mention),
            )
            plan = _linked_day_plan(
                date, proposed, mention, date, target_name=context.selected_name
            )
            inspect = inspect_selected_candidate_plan(context, plan)
            prompt, data, schema = prepare_continuation_semantic_review_call(context, inspect)
            start = time.monotonic()
            try:
                response = obj._ask(
                    MODEL, prompt, data, schema, "odyssey_e5_candidate_continuation_v1"
                )
                approved = False
                try:
                    validate_independent_continuation_verdict(context, inspect, response)
                    approved = True
                except CandidateContinuationSemanticError:
                    pass
                provider_approved = (
                    response.get("approved") is True and response.get("complete") is True
                )
                passed = approved if expected else not provider_approved
                reason = response.get("reason")
                outcome = (
                    "approved"
                    if approved
                    else ("unvalidated_approval" if provider_approved else "rejected")
                )
                error = None
            except Exception as exc:
                outcome, error, reason, passed = "error", type(exc).__name__, None, False
            row = dict(
                name=name,
                model=MODEL,
                prompt_sha256=h,
                expected=expected,
                outcome=outcome,
                pass_result=passed,
                reason=reason,
                error=error,
                elapsed_ms=round((time.monotonic() - start) * 1000),
            )
            with REPORT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    count = sum(row["pass_result"] for row in rows)
    print(f"REAL_GATE {count}/16 prompt={h}", flush=True)
    return 0 if count == 16 else 1


if __name__ == "__main__":
    raise SystemExit(main())
