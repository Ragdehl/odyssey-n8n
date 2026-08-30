"""Focused live evidence for Phase 17E's generic explicit tag contract."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openai import OpenAI  # noqa: E402

from odyssey_core.context import ContextFilter  # noqa: E402
from odyssey_core.request_planning import (  # noqa: E402
    OpenAIRequestPlanner,
    RetrieveAction,
    WriteAction,
)

SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
CONTEXT = {"date": "2026-08-30", "time": "10:00", "timezone": "Europe/Paris"}
CASES = (
    ("explicit_add", "Pon el tag muebles a la nota del sofá."),
    ("explicit_remove", "Quita el tag muebles de la nota del sofá."),
    ("tag_retrieval", "Busca mis notas con el tag muebles."),
    ("no_inference", "Estoy pensando en cambiar el sofá."),
    ("semantic_word_not_tag", "Esto es una idea sobre cómo organizar Odyssey."),
    ("explicit_idea", "Ponle el tag idea a la nota de Odyssey."),
)


def run(output_dir: Path) -> None:
    """Execute the six-case production planner matrix and persist validated plans."""
    output_dir.mkdir(parents=True, exist_ok=True)
    planner = OpenAIRequestPlanner(OpenAI(max_retries=0), SCHEMA, CONTEXT)
    rows = []
    for case, text in CASES:
        plan = planner.plan(text)
        writes = [a for a in plan.actions if isinstance(a, WriteAction)]
        retrieves = [a for a in plan.actions if isinstance(a, RetrieveAction)]
        changes = [c for u in (x for a in writes for x in a.units) for c in u.tag_changes]
        filters = [f for a in retrieves for f in a.plan.filters]
        if case == "explicit_add":
            ok = any(c.op == "add" and c.value == "muebles" for c in changes)
        elif case == "explicit_remove":
            ok = any(c.op == "remove" and c.value == "muebles" for c in changes)
        elif case == "tag_retrieval":
            ok = any(f == ContextFilter("tags", "contains", "muebles") for f in filters)
        elif case in {"no_inference", "semantic_word_not_tag"}:
            ok = not changes and not filters
        else:
            ok = any(c.op == "add" and c.value == "idea" for c in changes)
        rows.append(
            {
                "case": case,
                "input": text,
                "request_plan": asdict(plan),
                "pass": ok,
                "reason": "contract satisfied" if ok else "expected explicit tag behavior missing",
                "model": "gpt-5.6-sol",
                "reasoning": "low",
            }
        )
    result = output_dir / "results.json"
    result.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = [{"case": r["case"], "pass": r["pass"], "reason": r["reason"]} for r in rows]
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    run(parser.parse_args().output_dir)
