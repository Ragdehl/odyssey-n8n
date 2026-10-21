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


def inspect_physical_cohort(notes, people, *, expect_task):
    """Exact source-cohort oracle; a duplicate cannot replace a missing name."""
    names = [
        note.metadata.get("name")
        for note in notes.values()
        if note.metadata.get("type") == "person"
    ]
    expected = ["Persona local", *(people if expect_task else ())]
    valid_inventory = sorted(names) == sorted(expected)
    person_notes = [
        (path, note)
        for path, note in notes.items()
        if note.metadata.get("type") == "person" and note.metadata.get("name") in people
    ]
    ids = [note.metadata.get("id") for _, note in person_notes]
    valid_ids = len(ids) == len(set(ids)) and all(isinstance(value, str) and value for value in ids)
    tasks = [note for note in notes.values() if note.metadata.get("type") == "task"]
    valid_links = bool(expect_task) and len(tasks) == 1 and valid_inventory and valid_ids
    if valid_links:
        actual_person_links = {
            f"[[{path.removesuffix('.md')}|{note.metadata['name']}]]" for path, note in person_notes
        }
        all_person_links = {
            f"[[{path.removesuffix('.md')}|{note.metadata['name']}]]"
            for path, note in notes.items()
            if note.metadata.get("type") == "person"
        }
        task_text = tasks[0].content
        valid_links = (
            len(actual_person_links) == len(people)
            and all(task_text.count(link) == 1 for link in actual_person_links)
            and all(link not in task_text for link in (all_person_links - actual_person_links))
        )
    return {
        "inventory_complete": valid_inventory,
        "persons": len(person_notes),
        "tasks": len(tasks),
        "links_complete": bool(valid_links),
        "valid_ids": valid_ids,
        "unexpected_people": len(names) - len(expected) if len(names) > len(expected) else 0,
        "accepted": (valid_inventory and valid_ids and len(tasks) == 1 and valid_links)
        if expect_task
        else (valid_inventory and len(tasks) == 0),
    }


def markdown_bytes(repo):
    return {path: repo.read_text(path) for path in repo.list_markdown_paths()}


def replay_is_exact(before, after, replay):
    return replay.get("delivery_replayed") is True and before == after


def measure_case(label, source, people, expect_task):
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"odyssey-e4-case-{label}-") as folder:
        with live_product(Path(folder)) as (repo, actor, product):
            result = product.execute_product(source, f"e4-campaign-{label}-20261021", "main", actor)
            notes = {path: parse_note(repo.read_text(path)) for path in repo.list_markdown_paths()}
            checked = inspect_physical_cohort(notes, people, expect_task=expect_task)
            status = result.get("status")
            passed = checked["accepted"] and (
                status == "completed" if expect_task else status != "completed"
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
                "persons": checked["persons"],
                "tasks": checked["tasks"],
                "links_complete": checked["links_complete"],
                "inventory_complete": checked["inventory_complete"],
                "unique_ids": checked["valid_ids"],
                "unexpected_people": checked["unexpected_people"],
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
                before_replay = markdown_bytes(repo)
                replay = product.execute_product(
                    source, f"e4-campaign-{label}-20261021", "main", actor
                )
                output["replay"] = replay.get("delivery_replayed")
                output["replay_bytes_unchanged"] = replay_is_exact(
                    before_replay, markdown_bytes(repo), replay
                )
                output["pass"] &= output["replay_bytes_unchanged"]
            print("E4_CAMPAIGN_RESULT=" + json.dumps(output, ensure_ascii=False), flush=True)
            return output


def main():
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
                    {
                        "case": case[0],
                        "pass": False,
                        "error": type(e).__name__,
                        "detail": str(e)[:180],
                    },
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


if __name__ == "__main__":
    main()
