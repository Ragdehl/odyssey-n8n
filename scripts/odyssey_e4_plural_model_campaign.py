"""Explicit opt-in E4 fresh GPT campaign on disposable synthetic vaults only.

Run under an authorized private EnvironmentFile and ODYSSEY_E4_LIVE_APPROVED=1.
Never reuse a production/dev vault or expose API secrets in output.
"""

import json
import os
import resource
import tempfile
import time
from pathlib import Path

from odyssey_core.notes import parse_note
from scripts.odyssey_e4_live_browser_n8n import live_product

CASES = (
    (
        "ambos",
        "Hoy he conocido a Clara y a Hugo. Mañana tengo que llamar a ambos.",
        ("Clara", "Hugo"),
        True,
    ),
    (
        "los_tres",
        "Hoy he conocido a Clara, Hugo y Nuria. Mañana tengo que llamar a los tres.",
        ("Clara", "Hugo", "Nuria"),
        True,
    ),
    (
        "uno_de_dos",
        "Hoy he conocido a Clara y a Hugo. Mañana tengo que llamar a uno de los dos.",
        ("Clara", "Hugo"),
        False,
    ),
    (
        "independent_modifier",
        "Hoy terminé el informe. Conocí a Ana y a Luis en el parque. Mañana tengo que llamar a los dos.",
        ("Ana", "Luis"),
        True,
    ),
)


def measure_case(label, source, people, expect_task):
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"odyssey-e4-case-{label}-") as folder:
        with live_product(Path(folder)) as (repo, actor, product):
            result = product.execute_product(source, f"e4-campaign-{label}-20261021", "main", actor)
            notes = {path: parse_note(repo.read_text(path)) for path in repo.list_markdown_paths()}
            persons = [
                (path, n)
                for path, n in notes.items()
                if n.metadata.get("type") == "person" and n.metadata.get("name") in people
            ]
            tasks = [n for n in notes.values() if n.metadata.get("type") == "task"]
            unexpected_people = [
                n.metadata.get("name")
                for n in notes.values()
                if n.metadata.get("type") == "person"
                and n.metadata.get("name") not in (*people, "Persona local")
            ]
            correct_linkage = (
                bool(tasks)
                and len(tasks) == 1
                and all(
                    f"[[{path.removesuffix('.md')}|{n.metadata['name']}]]" in tasks[0].content
                    for path, n in persons
                )
            )
            status = result.get("status")
            passed = (
                (
                    status == "completed"
                    and len(persons) == len(people)
                    and correct_linkage
                    and not unexpected_people
                )
                if expect_task
                else (len(tasks) == 0 and not unexpected_people and status != "completed")
            )
            ops = (
                (result.get("request_detail") or {}).get("operational")
                or result.get("operational")
                or {}
            )
            stages = ops.get("stages", []) if isinstance(ops, dict) else []
            output = {
                "case": label,
                "pass": passed,
                "expected_create": expect_task,
                "status": status,
                "persons": len(persons),
                "tasks": len(tasks),
                "links_complete": correct_linkage,
                "unexpected_people": len(unexpected_people),
                "seconds": round(time.monotonic() - start, 3),
                "stage_count": len(stages),
                "stage_timings": [
                    {
                        "name": s.get("name"),
                        "ms": s.get("duration_ms"),
                        "model": s.get("model"),
                        "tokens": s.get("usage"),
                    }
                    for s in stages
                    if isinstance(s, dict)
                ],
                "note": "ConstantEmbedder fixture, real GPT, no browser/n8n; safe abstention is not a positive pass",
            }
            if status == "completed":
                replay = product.execute_product(
                    source, f"e4-campaign-{label}-20261021", "main", actor
                )
                output["replay"] = replay.get("delivery_replayed")
                output["pass"] &= bool(output["replay"])
            print("E4_CAMPAIGN_RESULT=" + json.dumps(output, ensure_ascii=False), flush=True)
            return output


if os.environ.get("ODYSSEY_E4_LIVE_APPROVED") != "1" or not os.environ.get("OPENAI_API_KEY"):
    raise RuntimeError("Fresh GPT campaign requires explicit approval and trusted credentials")

results = []
for case in CASES:
    try:
        results.append(measure_case(*case))
    except Exception as e:
        print(
            "E4_CAMPAIGN_RESULT="
            + json.dumps(
                {"case": case[0], "pass": False, "error": type(e).__name__, "detail": str(e)[:180]},
                ensure_ascii=False,
            ),
            flush=True,
        )
        results.append({"pass": False})
print(
    "E4_CAMPAIGN_SUMMARY="
    + json.dumps(
        {
            "passed": sum(x["pass"] for x in results),
            "total": len(results),
            "peak_python_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
        ensure_ascii=False,
    ),
    flush=True,
)
raise SystemExit(0 if all(x["pass"] for x in results) else 2)
